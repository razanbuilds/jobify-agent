"""Run the eval suite on config A (baseline) and B (full harness).

  python -m evals.run_evals --config both --trials 1            # real model (needs OPENROUTER_API_KEY)
  python -m evals.run_evals --mock --config both                # plumbing test only (scores meaningless)
  python -m evals.run_evals --only t08,t13 --config B

Free-tier note: ~18 tasks x 2 configs x ~5 model calls = ~180 requests per trial. The free quota is
50/day (1,000/day after a one-time 10-credit top-up), so run with --only first.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from dataclasses import replace
from pathlib import Path

from jobify import config
from jobify.agent import Agent
from jobify.llm import make_llm
from jobify.tools import ToolBox

from . import graders

HERE = Path(__file__).parent


def run_task(task: dict, cfg, trial: int, tmp: Path, model: str | None) -> dict:
    cfg = replace(cfg, **task.get("overrides", {}))
    apps = tmp / f"apps_{cfg.name}_{task['id']}_{trial}.json"
    os.environ["JOBIFY_APPLICATIONS"] = str(apps)
    os.environ["JOBIFY_JOBS"] = str(config.DATA_DIR / "jobs.json")  # evals always use the frozen synthetic set
    policy = task.get("approve", "pause")
    out = {"task": task["id"], "config": cfg.name, "trial": trial}
    try:
        agent = Agent(make_llm(model or cfg.model), ToolBox(use_mcp=False), cfg)
        approve = None if policy == "pause" else (lambda n, a, p=policy: p == "approve")
        res = agent.run(task["prompt"], approve=approve)
    except Exception as e:  # noqa: BLE001
        out.update(error=f"{type(e).__name__}: {e}", checks={c: False for c in task["checks"]}, passed=False)
        return out
    checks = {c: graders.check(c, res, apps) for c in task["checks"]}
    trace_path = HERE / "results" / "traces" / f"{cfg.name}_{task['id']}_{trial}.jsonl"
    res.trace.save(trace_path)
    out.update(checks=checks, passed=all(checks.values()), stopped=res.stopped, steps=res.trace.steps,
               tool_calls=res.trace.tool_calls, cost=round(res.trace.cost, 5),
               answer=res.answer[:300], trace=str(trace_path.relative_to(HERE.parent)))
    return out


def summarize(results: list[dict], tasks: list[dict], cfg_names: list[str], trials: int) -> str:
    by = {(r["task"], r["config"]): [] for r in results}
    for r in results:
        by[(r["task"], r["config"])].append(r)
    lines = ["# Eval results", "", "| task | tags | " + " | ".join(cfg_names) + " |",
             "|---|---|" + "---|" * len(cfg_names)]
    totals = {c: [0, 0, 0] for c in cfg_names}  # passed trials, total trials, pass^k tasks
    for t in tasks:
        row = [t["id"], ",".join(t.get("tags", []))]
        for c in cfg_names:
            rs = by.get((t["id"], c), [])
            ok = sum(r["passed"] for r in rs)
            totals[c][0] += ok
            totals[c][1] += len(rs)
            totals[c][2] += int(bool(rs) and ok == len(rs))
            row.append(("✓" if ok == len(rs) else "✗") if trials == 1 else f"{ok}/{len(rs)}")
        lines.append("| " + " | ".join(row) + " |")
    lines += ["", "## Totals", ""]
    for c in cfg_names:
        ok, n, allk = totals[c]
        lines.append(f"- **{c}**: {ok}/{n} trials passed = {100 * ok / max(n, 1):.1f}%"
                     + (f"; pass^{trials} (all trials pass): {allk}/{len(tasks)}" if trials > 1 else ""))
    if len(cfg_names) == 2:
        a, b = (100 * totals[c][0] / max(totals[c][1], 1) for c in cfg_names)
        lines.append(f"- Improvement {cfg_names[0]} -> {cfg_names[1]}: {b - a:+.1f} percentage points")
    lines += ["", "## Failures (for your error analysis)", ""]
    for r in results:
        if not r["passed"]:
            bad = [c for c, ok in r["checks"].items() if not ok]
            lines.append(f"- `{r['config']}` {r['task']} (trial {r['trial']}): failed {bad}"
                         + (f" - ERROR {r['error']}" if r.get("error") else f" - trace: {r.get('trace')}"))
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="both", choices=["A", "B", "both"])
    ap.add_argument("--trials", type=int, default=1)
    ap.add_argument("--only", default="")
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--model", default=None)
    ap.add_argument("--sleep", type=float, default=0.0, help="seconds between tasks (free-tier rate limits)")
    a = ap.parse_args()
    if a.mock:
        os.environ["MOCK"] = "1"
    tasks = json.loads((HERE / "tasks.json").read_text(encoding="utf-8"))
    if a.only:
        wanted = set(a.only.split(","))
        tasks = [t for t in tasks if t["id"] in wanted]
    cfgs = {"A": [config.CONFIG_A], "B": [config.CONFIG_B], "both": [config.CONFIG_A, config.CONFIG_B]}[a.config]
    results = []
    with tempfile.TemporaryDirectory() as td:
        for t in tasks:
            for cfg in cfgs:
                for k in range(1, a.trials + 1):
                    r = run_task(t, cfg, k, Path(td), a.model)
                    results.append(r)
                    print(f"{cfg.name:11s} {t['id']} trial{k}: {'PASS' if r['passed'] else 'FAIL'}")
                    time.sleep(a.sleep)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)
    (out_dir / f"results_{stamp}.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    md = summarize(results, tasks, [c.name for c in cfgs], a.trials)
    (out_dir / "summary.md").write_text(md, encoding="utf-8")
    print("\n" + md)


if __name__ == "__main__":
    main()
