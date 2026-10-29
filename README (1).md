# Jobify Agent: job-search and application copilot

Capstone project for [Advanced Agentic AI Systems Engineering - SDAIA Academy](https://github.com/sdaiaacademy/agentic-ai/) (track: **Your harness**).

**Status (29 Oct 2026):** the harness, the four tools (the job database over MCP), the approval gate, budgets, retrieval,
memory, security defences and the 19 unit tests are working and verified. The 18-task eval suite was run on both configs
with Groq `openai/gpt-oss-20b`; the generated results are at the end of this file and in `evals/results/`.

Jobify finds jobs, reads them, checks them against the user's **real profile**, ranks and explains the matches,
and drafts an application. It never saves anything without the user's explicit approval.

```
user -> agent loop (budgets) -> tools: search_jobs / get_job / save_application (job DB, MCP) + search_profile (BM25)
                 |                         ^ third-party job text is sanitized and marked untrusted
                 +-> AGENTS.md + memory + compaction
                 +-> write action -> APPROVAL GATE -> tracker
```

## Quick start (for reviewers)
Tested on Windows with Python 3.14. Python 3.11+ is recommended. On Mac/Linux use `python3`,
`source .venv/bin/activate` and `cp`.

```
git clone https://github.com/razanbuilds/jobify-agent
cd jobify-agent
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**1. No API key needed** (offline checks):
```
python -m unittest discover -s tests          # 19 tests
python -m jobify.cli --mock                   # fake model, only tests the harness (try: "Prepare an application for AI product roles and save it")
```

**2. With a free model key.** Any OpenAI-compatible provider works. Create `.env` (copy `.env.example`):
```
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_API_KEY=your_key_here
MODEL=openai/gpt-oss-20b
```
(OpenRouter also works: leave `LLM_BASE_URL` out, set `OPENROUTER_API_KEY` and a `:free` model.)
```
python -m jobify.cli                          # chat; approval is asked in the terminal
python -m jobify.cli --mcp                    # job database served over MCP (stdio)
uvicorn jobify.api:app --reload               # HTTP service: POST /chat, POST /approve, GET /trace/{id}
```
Try: `Find AI product roles in Saudi Arabia`, then `Prepare an application for j01 and save it` and answer `y` or `n`.

**3. Evals** (needs a key; our results are already in `evals/results/`):
```
python -m evals.run_evals --config both --sleep 5
```

## Requirements checklist
| Requirement | Where |
|---|---|
| 3+ tools, one over MCP | `search_jobs`, `get_job`, `save_application` (MCP server: `jobify/mcp_server.py`, client: `jobify/mcp_client.py`), `search_profile` (`jobify/retrieval.py`) |
| Context file | `AGENTS.md` |
| Memory or retrieval | BM25 retrieval over `data/profile/*.md`; capped memory in `data/memory.json` |
| Compaction or budget rule | `agent._compact` (old observations shrink above a context budget), tool output cap |
| Approval on a write action | `agent.py`: pause and resume (`/approve` in the API) before `save_application` |
| Step and cost budgets | `config.py`: 8 steps, 10 tool calls, $0.02 shadow cost; the run stops with an explicit message |
| 15+ eval tasks, two configs, error analysis | `evals/tasks.json` (18 tasks), config A vs B, `docs/ERROR_ANALYSIS.md` |
| Security note | `docs/SECURITY_NOTE.md` (trifecta, attack, defence, PDPL) |
| Service and traces | `jobify/api.py` (FastAPI); JSONL traces in `traces/` and `evals/results/traces/` |

**MCP status:** `--mcp` tested live on 29 Oct 2026. Job search runs through the MCP server over stdio (mcp 2.x, `MCPServer`),
and the approval gate still applies to `save_application`.

## Evaluation
- **Config A (baseline):** minimal prompt, no memory, no injection defence, no approval gate, no compaction.
- **Config B (full harness):** `AGENTS.md`, memory, sanitizing and untrusted-data marking, approval gate, compaction, budgets.
- Same model, same tools, same data. Graders are deterministic (tool calls, regexes on the answer, the tracker file).
- Model: Groq `openai/gpt-oss-20b` (free tier, OpenAI-compatible API). Date of the run: 29 Oct 2026.
- Results of the latest run are at the end of this file (`evals/results/summary.md`); raw results and traces are in `evals/results/`.

Error analysis: see `docs/ERROR_ANALYSIS.md`.

## Security
Trifecta: private data (profile) + untrusted content (job text) are present; the third leg, exfiltration, is removed by design
(no tool can send data out; the only write is a local tracker, gated by approval; the MCP server does not receive API keys).
Attack: indirect prompt injection in job `j12`. Defence: sanitizing, untrusted-data marking, approval gate, budgets.
Details, residual risks and PDPL: `docs/SECURITY_NOTE.md`. Tests: evals t13, t14, t15 and `tests/test_core.py`.

## Honest limits
- The sanitizer is regex-based and can be bypassed by paraphrased or non-English injections; the approval gate and the missing exfiltration tool are what actually protect the user.
- Evals use a small synthetic job set (`data/jobs.json`) so they are reproducible; `data/profile/` holds sample data.
- Free models vary in tool-calling quality, so repeated runs can differ.

## Repo layout
```
AGENTS.md  data/ (jobs, profile, memory)  jobify/ (agent, tools, retrieval, security, mcp_*, api, cli)
evals/ (tasks.json, graders, run_evals, results/)  tests/  docs/ (SECURITY_NOTE, ERROR_ANALYSIS)
```
