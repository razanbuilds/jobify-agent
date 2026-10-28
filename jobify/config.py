"""Central configuration.

Two presets are compared in the evals:
  A_baseline = naive agent (minimal prompt, no memory, no injection defence, no approval gate)
  B_full     = the engineered harness (AGENTS.md, memory, defence, approval, compaction, budgets)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()

DATA_DIR = Path(os.getenv("JOBIFY_DATA_DIR", ROOT / "data"))

# Shadow prices (USD per token). The models are free, but we budget as if they were not.
PRICE_IN = 0.15 / 1_000_000
PRICE_OUT = 0.60 / 1_000_000


def jobs_path() -> Path:
    return Path(os.getenv("JOBIFY_JOBS", DATA_DIR / "jobs.json"))


def applications_path() -> Path:
    return Path(os.getenv("JOBIFY_APPLICATIONS", DATA_DIR / "applications.json"))


@dataclass(frozen=True)
class Config:
    name: str = "B_full"
    model: str = os.getenv("MODEL", "openai/gpt-oss-20b:free")
    use_agents_md: bool = True      # context file with rules
    use_memory: bool = True         # saved user preferences injected into the prompt
    defend_injection: bool = True   # sanitize + wrap tool output that contains third-party text
    require_approval: bool = True   # human gate on write tools
    compact: bool = True            # cap tool output + compact old observations
    max_steps: int = 8              # model calls
    max_tool_calls: int = 10
    max_cost_usd: float = 0.02
    context_char_budget: int = 12000
    max_tool_chars: int = 3000
    memory_cap: int = 1500


CONFIG_A = Config(
    name="A_baseline",
    use_agents_md=False,
    use_memory=False,
    defend_injection=False,
    require_approval=False,
    compact=False,
)
CONFIG_B = Config()
