# Jobify Agent: job-search & application copilot
Capstone for SDAIA Academy "Agentic AI Systems Engineering" (track: **Your harness**).

Flow: find jobs -> read details -> check *your real profile* -> rank/explain -> draft application -> **ask approval** -> save.

## Requirement checklist (course minimum)
| Requirement | Where |
|---|---|
| 3+ tools, one over MCP | `search_jobs`, `get_job`, `save_application` (MCP: `jobify/mcp_server.py`), `search_profile` (local) |
| Context file | `AGENTS.md` |
| Memory or retrieval | BM25 profile retrieval (`retrieval.py`) + capped memory (`data/memory.json`, `memory.py`) |
| Compaction / budget rule | `agent._compact` (old observations shrink when context > budget) + tool-output cap |
| Approval on write + step/cost budgets | `agent.py` (pause/resume), `config.py` (8 steps, 10 tool calls, $0.02 shadow cost) |
| 15+ eval tasks, two configs, error analysis | `evals/tasks.json` (18 tasks), A vs B, `evals/run_evals.py` |
| Security note | `docs/SECURITY_NOTE.md` |
| Service + traces | `jobify/api.py` (FastAPI), JSONL traces |

## Setup
```bash
uv sync                      # or: pip install -r requirements.txt
cp .env.example .env         # add OPENROUTER_API_KEY, choose a free model with good tool calling
python -m unittest discover -s tests      # offline, no key needed
```

## Run
```bash
python -m jobify.cli --mock              # offline smoke test (fake model)
python -m jobify.cli                     # real model, approvals asked in the terminal
python -m jobify.cli --mcp               # job DB served over MCP (stdio)
uvicorn jobify.api:app --reload          # POST /chat, POST /approve, GET /trace/{id}
```

## Evals
```bash
python -m evals.run_evals --only t08,t13,t14 --config both      # start small
python -m evals.run_evals --config both --trials 3 --sleep 3    # full run, pass^k
```
Output: `evals/results/summary.md` (+ traces). Config **A** = baseline (minimal prompt, no memory, no defence, no approval gate, no compaction). Config **B** = full harness. Free tier = 50 requests/day (1,000 after a one-time 10-credit top-up), and a full run needs ~180 per trial.

## Make it yours (do this before the demo)
1. Replace the SAMPLE files in `data/profile/*.md` and `data/memory.json` with your real details. Evals t06/t07 assume your profile does **not** mention Kubernetes; adjust if it does.
2. Export jamee's listings and run `python scripts/snapshot_from_jamee.py export.json` (edit `FIELD_MAP` first). Demo with `JOBIFY_JOBS=data/jobs_real.json`. Keep evals on the synthetic `data/jobs.json` so they stay reproducible.
3. Run the evals, then write `docs/ERROR_ANALYSIS.md`: for each failure in `summary.md`, open its trace and classify the cause (wrong tool args / ignored rule / hallucinated skill / injection followed / grader too strict / model too weak), then state one fix.

## 8-minute demo
0:00 problem (manual job hunting) -> 0:45 solution -> 1:30 live: search -> analyze -> profile check -> rank -> draft -> **approval prompt** -> save (3 min) -> 4:30 architecture (loop, MCP, retrieval, memory, budgets, gate) -> 5:30 evals A vs B + one failure analysed -> 6:30 inject j12 live, show it defused -> 7:15 API + traces -> record a backup video.

## Honest limits
Not yet run against a live LLM or a live MCP session (unit tests and the offline mock harness pass). The MCP files use the official `mcp` SDK's FastMCP helper; if the course's SDK v2 differs, compare with lab D2_4_mcp (only `mcp_server.py` and `mcp_client.py` change). Sanitizing is regex-based (see security note).
