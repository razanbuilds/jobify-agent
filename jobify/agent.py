"""The harness: agent loop + budgets + approval gate + injection defence + compaction + tracing."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import config, security
from .config import Config
from .memory import load_memory_text
from .tools import EXTERNAL_TOOLS, WRITE_TOOLS, ToolBox

BASELINE_PROMPT = "You are a helpful job search assistant. Use the tools to help the user."

STOP_TEXT = {
    "step_budget": "Step budget exceeded. I could not safely complete the request.",
    "tool_budget": "Tool-call budget exceeded. I could not safely complete the request.",
    "cost_budget": "Cost budget exceeded. I could not safely complete the request.",
}


@dataclass
class Trace:
    events: list = field(default_factory=list)
    steps: int = 0
    tool_calls: int = 0
    cost: float = 0.0

    def add(self, type: str, **data) -> None:
        self.events.append({"type": type, **data})

    def of(self, type: str) -> list:
        return [e for e in self.events if e["type"] == type]

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in self.events), encoding="utf-8")


@dataclass
class RunResult:
    answer: str
    stopped: str  # done | awaiting_approval | step_budget | tool_budget | cost_budget
    trace: Trace
    pending: dict | None = None
    state: dict | None = None


def _tool_msg(call_id: str, content: str) -> dict:
    return {"role": "tool", "tool_call_id": call_id, "content": content}


class Agent:
    def __init__(self, llm, toolbox: ToolBox, cfg: Config = config.CONFIG_B):
        self.llm, self.toolbox, self.cfg = llm, toolbox, cfg

    # ---- context ---------------------------------------------------------------------------
    def system_prompt(self) -> str:
        c = self.cfg
        base = (config.ROOT / "AGENTS.md").read_text(encoding="utf-8") if c.use_agents_md else BASELINE_PROMPT
        if c.use_memory:
            base += "\n\n## Saved user preferences\n" + load_memory_text(c.memory_cap)
        return base

    def _compact(self, messages: list[dict], trace: Trace) -> None:
        """Compaction rule: when the context is over budget, shrink old tool observations in place."""
        total = sum(len(str(m.get("content") or "")) for m in messages)
        if total <= self.cfg.context_char_budget:
            return
        changed = 0
        for i, m in enumerate(messages[:-4]):
            if m["role"] == "tool" and len(m["content"]) > 300:
                m["content"] = m["content"][:200] + " ...[compacted]"
                changed += 1
        if changed:
            trace.add("compacted", messages=changed, chars_before=total)

    # ---- public API ------------------------------------------------------------------------
    def run(self, user_message: str, approve=None) -> RunResult:
        """approve(name, args) -> bool. If None, the run PAUSES at a write and returns awaiting_approval."""
        messages = [{"role": "system", "content": self.system_prompt()},
                    {"role": "user", "content": user_message}]
        return self._loop(messages, Trace(), approve)

    def resume(self, state: dict, approved: bool) -> RunResult:
        messages, trace, call = state["messages"], state["trace"], state["pending"]
        trace.add("approval_response", approved=bool(approved))
        obs = self._run_write(call, bool(approved), trace)
        messages.append(_tool_msg(call["id"], obs))
        return self._loop(messages, trace, None)

    # ---- the loop --------------------------------------------------------------------------
    def _loop(self, messages: list[dict], trace: Trace, approve) -> RunResult:
        cfg = self.cfg
        while True:
            if trace.steps >= cfg.max_steps:
                return self._stop("step_budget", trace)
            if trace.cost >= cfg.max_cost_usd:
                return self._stop("cost_budget", trace)
            if cfg.compact:
                self._compact(messages, trace)

            resp = self.llm.chat(messages, self.toolbox.specs())
            usage = resp.get("usage") or {}
            tin = usage.get("in") or sum(len(str(m.get("content") or "")) for m in messages) // 4
            tout = usage.get("out") or len(resp.get("content") or "") // 4
            trace.steps += 1
            trace.cost += tin * config.PRICE_IN + tout * config.PRICE_OUT
            trace.add("model", step=trace.steps, tokens_in=tin, tokens_out=tout, cost=round(trace.cost, 6))

            calls = resp.get("tool_calls") or []
            if not calls:
                trace.add("stop", reason="done")
                return RunResult(resp.get("content") or "", "done", trace)

            messages.append({
                "role": "assistant", "content": resp.get("content") or "",
                "tool_calls": [{"id": c["id"], "type": "function",
                                "function": {"name": c["name"], "arguments": json.dumps(c["arguments"])}}
                               for c in calls]})

            for i, call in enumerate(calls):
                if trace.tool_calls >= cfg.max_tool_calls:
                    return self._stop("tool_budget", trace)
                name, args = call["name"], call["arguments"]
                trace.tool_calls += 1
                trace.add("tool_call", step=trace.steps, name=name, args=args)

                if name in WRITE_TOOLS and cfg.require_approval:
                    if approve is None:  # pause: hand control back to the human
                        for later in calls[i + 1:]:
                            messages.append(_tool_msg(later["id"], "Not executed: waiting for the user to "
                                                                   "approve a previous action."))
                        trace.add("approval_request", name=name, args=args)
                        proposal = f"PROPOSED ACTION (needs your approval): {name}\n" + \
                                   json.dumps(args, ensure_ascii=False, indent=2)
                        return RunResult(proposal, "awaiting_approval", trace, pending=call,
                                         state={"messages": messages, "trace": trace, "pending": call})
                    obs = self._run_write(call, bool(approve(name, args)), trace)
                else:
                    obs = self._execute(call, trace, approved=None)
                messages.append(_tool_msg(call["id"], obs))

    # ---- helpers ---------------------------------------------------------------------------
    def _run_write(self, call: dict, approved: bool, trace: Trace) -> str:
        if approved:
            return self._execute(call, trace, approved=True)
        trace.add("write_denied", name=call["name"], args=call["arguments"])
        return "The user DENIED this action. It was not performed. Do not retry; tell the user it was not saved."

    def _execute(self, call: dict, trace: Trace, approved) -> str:
        name, args = call["name"], call["arguments"]
        try:
            raw = self.toolbox.call(name, args)
        except Exception as e:  # noqa: BLE001  errors are observations, not crashes
            raw = f"ERROR: {type(e).__name__}: {e}"
        if name in WRITE_TOOLS:
            trace.add("write", name=name, args=args, approved=approved, result=raw[:200])
        trace.add("tool_result", name=name, chars=len(raw))
        return self._treat(name, raw, trace)

    def _treat(self, name: str, raw: str, trace: Trace) -> str:
        cfg, text = self.cfg, raw
        if cfg.defend_injection and name in EXTERNAL_TOOLS:
            text, n = security.sanitize(text)
            if n:
                trace.add("injection_flagged", tool=name, removed=n)
        if cfg.compact and len(text) > cfg.max_tool_chars:
            text = text[: cfg.max_tool_chars] + " ...[truncated]"
            trace.add("truncated", tool=name)
        if cfg.defend_injection and name in EXTERNAL_TOOLS:
            text = security.wrap_untrusted(text, name)
        return text

    def _stop(self, reason: str, trace: Trace) -> RunResult:
        used = ", ".join(e["name"] for e in trace.of("tool_call")) or "none"
        trace.add("stop", reason=reason)
        return RunResult(f"{STOP_TEXT[reason]} (tools used so far: {used})", reason, trace)
