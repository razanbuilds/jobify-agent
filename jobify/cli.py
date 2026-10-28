"""Interactive CLI.  python -m jobify.cli [--config A|B] [--mcp] [--mock]"""
from __future__ import annotations

import argparse
import json
import os

from . import config
from .agent import Agent
from .llm import make_llm
from .tools import ToolBox


def ask(name: str, args: dict) -> bool:
    print(f"\n[APPROVAL NEEDED] {name}")
    print(json.dumps(args, ensure_ascii=False, indent=2))
    return input("Approve? [y/N] ").strip().lower() == "y"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="B")
    ap.add_argument("--mcp", action="store_true")
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--model", default=None)
    a = ap.parse_args()
    if a.mock:
        os.environ["MOCK"] = "1"
    cfg = config.CONFIG_A if a.config.upper().startswith("A") else config.CONFIG_B
    agent = Agent(make_llm(a.model or cfg.model), ToolBox(use_mcp=a.mcp), cfg)
    print(f"Jobify agent  config={cfg.name}  mcp={a.mcp}  (Ctrl+C to quit)")
    while True:
        try:
            msg = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not msg:
            continue
        res = agent.run(msg, approve=ask)
        print(f"\nagent> {res.answer}")
        print(f"[{res.stopped} | steps={res.trace.steps} tools={res.trace.tool_calls} "
              f"est_cost=${res.trace.cost:.4f}]")


if __name__ == "__main__":
    main()
