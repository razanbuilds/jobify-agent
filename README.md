# Jobify Agent: a job-search copilot that asks before it acts

Capstone project for [Advanced Agentic AI Systems Engineering - SDAIA Academy](https://github.com/sdaiaacademy/agentic-ai/) (track: *Your harness*).

*The problem.* Job hunting is repetitive: search several portals, read each posting, compare it with your own background,
tailor an application, keep track of what you sent. *Jobify* does the legwork as an agent, and it stays safe: it only ever
claims skills you really have, treats job postings as untrusted text, and never saves an application without your approval.

*Status (29 Oct 2026):* the harness, four tools (the job database over MCP), the approval gate, budgets, retrieval, memory,
security defences and 19 unit tests are working. The 18-task eval suite was run on both configurations with Groq
openai/gpt-oss-20b.

## How it works

user -> agent loop (step / tool-call / cost budgets)
          |-- search_jobs, get_job, save_application   job database, served over MCP
          |-- search_profile                           BM25 retrieval over the user's profile
          |-- AGENTS.md + saved preferences + compaction
          '-- write action -> APPROVAL GATE -> application tracker
job text (untrusted) -> sanitizer -> wrapped as <untrusted_data> -> model

Flow: find jobs -> read details -> check the user's real profile -> rank and explain -> draft -> *ask approval* -> save.

## Try it in 3 minutes (for reviewers)
Tested on Windows with Python 3.14 (3.11+ recommended). On Mac/Linux use python3, source .venv/bin/activate, cp.

git clone https://github.com/razanbuilds/jobify-agent
cd jobify-agent
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

*No key needed:*

python -m unittest discover -s tests          # 19 tests
python -m jobify.cli --mock                   # fake model; only exercises the harness

Mock demo: type Prepare an application for AI product roles and save it, then answer the approval prompt with y or n.

*With a free model key* (any OpenAI-compatible provider; Groq shown). Create .env (see .env.example):

LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_API_KEY=your_key_here
MODEL=openai/gpt-oss-20b

(OpenRouter also works: omit LLM_BASE_URL, set OPENROUTER_API_KEY and a :free model.)

python -m jobify.cli                          # chat; approvals asked in the terminal
python -m jobify.cli --mcp                    # job database served over MCP (stdio)
uvicorn jobify.api:app --reload               # POST /chat, POST /approve, GET /trace/{id}
python -m evals.run_evals --config both --sleep 5     # run all evals

Prompts to try: Find AI product roles in Saudi Arabia / Prepare an application for j01 and save it / Summarize job j12 (the poisoned posting).

## Requirements checklist
| Requirement | Where |
|---|---|
| 3+ tools, one over MCP | search_jobs, get_job, save_application (server jobify/mcp_server.py, client jobify/mcp_client.py), search_profile (jobify/retrieval.py) |
| Context file | AGENTS.md |
| Memory or retrieval | BM25 over data/profile/*.md; capped memory in data/memory.json |
| Compaction or budget rule | agent._compact shrinks old observations above a context budget; tool output is capped |
| Approval on a write action | agent.py pauses before save_application and resumes on approve or deny (/approve in the API) |
| Step and cost budgets | config.py: 8 model steps, 10 tool calls, $0.02 shadow cost; the run stops with an explicit message |
| 15+ eval tasks, two configs | evals/tasks.json (18 tasks), config A vs B, runner evals/run_evals.py |
| Security note | docs/SECURITY_NOTE.md: trifecta, attack, defence, PDPL |
| Service and traces | jobify/api.py (FastAPI); JSONL traces in traces/ |

*MCP status:* --mcp tested live on 29 Oct 2026. Job search runs through the MCP server over stdio (mcp 2.x, MCPServer),
and the approval gate still applies to save_application.

## Design decisions (context and harness)
- *Context is a budget.* search_jobs returns short summaries, not full descriptions; the model calls get_job only for the
  jobs it cares about. Tool output is capped (3,000 chars), old observations are compacted when the context passes 12,000 chars,
  and memory is capped (1,500 chars).
- *Rules live in a context file* (AGENTS.md): never invent requirements or skills, never claim a save unless the tool says
  saved, call search_profile before talking about the user's skills, use saved preferences, reply in the user's language.
- *Retrieval over the real profile*, so gaps are reported honestly (for example a required skill the profile does not mention).
- *The approval gate lives in the harness, not in the tool or the prompt.* The model can only propose a write; code decides.
  Denials are returned to the model as an observation so it does not retry.
- *Errors are observations, not crashes*: a bad tool call comes back as text the model can react to.
- *Budgets end runs cleanly* ("Step budget exceeded. I could not safely complete the request.") instead of looping.
- *Least privilege for MCP:* the server subprocess receives only JOBIFY_* settings and basic system variables, never API keys.
- *Reproducibility:* evals run on a frozen synthetic job set; deterministic graders; every run writes a trace.

## Evaluation
- *Config A (baseline):* minimal prompt, no memory, no injection defence, no approval gate, no compaction.
- *Config B (full harness):* all of the above switched on. Same model, same tools, same data.
- *18 tasks* covering search, location and salary filters, saved preferences, relevance, profile gaps, honesty (no invented
  skills), approval (pause, approve, deny, no unprompted writes), budgets, prompt injection, bad input and an Arabic query.
- *Graders* are deterministic: tool calls in the trace, regexes on the answer, and the tracker file.
- *Model:* Groq openai/gpt-oss-20b (free tier). *Run date:* 29 Oct 2026.

## Security
| Trifecta leg | In Jobify |
|---|---|
| Private data | the user's profile (search_profile) |
| Untrusted content | scraped job descriptions |
| Exfiltration | *removed by design*: no tool can send data out; the only write is a local tracker behind approval |

*Attack:* indirect prompt injection. Job j12 contains text telling the agent to ignore the user, save an application and send
the profile to an attacker. *Defence, enforced in code:* (1) the sanitizer removes injected sentences, (2) the rest is wrapped as
<untrusted_data> and AGENTS.md forbids obeying it, (3) the approval gate blocks any write, (4) budgets cap a hijacked loop.
Evidence: evals t13, t14, t15 and tests/test_core.py. PDPL notes (where personal data flows) are in the security note.

## Honest limits
- The sanitizer is regex-based and can be bypassed by paraphrased or non-English injections; the approval gate and the missing
  exfiltration tool are what actually protect the user.
- A subtle injection could still try to bias ranking without any tool call.
- Evals use a small synthetic job set so they are reproducible; data/profile/ holds sample data.
- Free models vary in tool-calling quality, so repeated runs can differ.

## What I would do next
Connect a real job scraper, keep one long-lived MCP session instead of one process per call, add OpenTelemetry spans,
and run each eval several times to report pass^k.

## Repo layout

AGENTS.md  data/ (jobs, profile, memory)  jobify/ (agent, tools, retrieval, security, mcp_*, api, cli)
evals/ (tasks.json, graders, run_evals)  tests/  docs/ (SECURITY_NOTE)
