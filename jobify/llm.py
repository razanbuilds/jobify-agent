"""LLM adapters. OpenRouterLLM = real free models (Chat Completions API). MockLLM = offline plumbing test."""
from __future__ import annotations

import json
import os
import re
import time


class OpenRouterLLM:
    def __init__(self, model: str | None = None, api_key: str | None = None,
                 base_url: str = "https://openrouter.ai/api/v1"):
        from openai import OpenAI

        self.model = model or os.getenv("MODEL", "openai/gpt-oss-20b:free")
        self.client = OpenAI(base_url=base_url, api_key=api_key or os.environ["OPENROUTER_API_KEY"])

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        last: Exception | None = None
        for attempt in range(4):  # free models rate-limit: back off and retry
            try:
                resp = self.client.chat.completions.create(
                    model=self.model, messages=messages, tools=tools, temperature=0)
                break
            except Exception as e:  # noqa: BLE001
                last = e
                time.sleep(2 ** attempt)
        else:
            raise RuntimeError(f"LLM call failed after retries: {last}")
        msg = resp.choices[0].message
        calls = []
        for tc in msg.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except ValueError:
                args = {}
            calls.append({"id": tc.id, "name": tc.function.name, "arguments": args})
        usage = getattr(resp, "usage", None)
        return {
            "content": msg.content or "",
            "tool_calls": calls,
            "usage": {"in": getattr(usage, "prompt_tokens", 0) or 0,
                      "out": getattr(usage, "completion_tokens", 0) or 0},
        }


class MockLLM:
    """Deterministic stand-in so the harness (loop, budgets, approval, evals) can be tested offline.
    It is NOT a model: scores from it mean nothing. Policy: search -> get_job -> search_profile ->
    (save if the user asked) -> answer."""

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        user = next(m["content"] for m in messages if m["role"] == "user")
        tool_msgs = [m["content"] for m in messages if m["role"] == "tool"]
        n = len(tool_msgs)
        usage = {"in": len(json.dumps(messages)) // 4, "out": 40}
        ids = re.findall(r"\bj\d{2,3}\b", tool_msgs[0]) if tool_msgs else []

        def call(name: str, args: dict) -> dict:
            return {"content": "", "tool_calls": [{"id": f"call_{n}", "name": name, "arguments": args}],
                    "usage": usage}

        if n == 0:
            return call("search_jobs", {"query": user[:80]})
        if n == 1:
            return call("get_job", {"job_id": ids[0]}) if ids else self._final("No matching jobs found.", usage)
        if n == 2:
            return call("search_profile", {"query": "skills experience"})
        if n == 3 and re.search(r"(?i)save|apply|application", user):
            return call("save_application", {"job_id": ids[0], "cover_letter": "Dear hiring team, ...",
                                             "notes": "drafted by mock"})
        return self._final(f"Top match: {ids[0] if ids else 'none'}. Last step: {tool_msgs[-1][:80]}", usage)

    @staticmethod
    def _final(text: str, usage: dict) -> dict:
        return {"content": text, "tool_calls": [], "usage": usage}


def make_llm(model: str | None = None):
    if os.getenv("MOCK") == "1":
        return MockLLM()
    return OpenRouterLLM(model)
