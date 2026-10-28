"""FastAPI service. Run: uvicorn jobify.api:app --reload   (MOCK=1 for offline, USE_MCP=1 for MCP)

POST /chat      {"message": "...", "config": "B"}  -> answer, or a pending write that needs approval
POST /approve   {"session_id": "...", "approved": true}
GET  /trace/{session_id}   full event trace (also written to traces/<id>.jsonl)
GET  /health
"""
from __future__ import annotations

import os
import uuid

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from . import config
from .agent import Agent, RunResult
from .llm import make_llm
from .tools import ToolBox

app = FastAPI(title="Jobify Agent")
SESSIONS: dict[str, dict] = {}
TRACE_DIR = config.ROOT / "traces"


class ChatIn(BaseModel):
    message: str
    config: str = "B"


class ApproveIn(BaseModel):
    session_id: str
    approved: bool


def _respond(sid: str, res: RunResult) -> dict:
    res.trace.save(TRACE_DIR / f"{sid}.jsonl")
    SESSIONS[sid]["state"] = res.state
    return {"session_id": sid, "answer": res.answer, "status": res.stopped, "pending": res.pending,
            "steps": res.trace.steps, "tool_calls": res.trace.tool_calls,
            "est_cost_usd": round(res.trace.cost, 6)}


@app.get("/health")
def health():
    return {"ok": True, "mock": os.getenv("MOCK") == "1", "mcp": os.getenv("USE_MCP") == "1"}


@app.post("/chat")
def chat(body: ChatIn):
    cfg = config.CONFIG_A if body.config.upper().startswith("A") else config.CONFIG_B
    agent = Agent(make_llm(cfg.model), ToolBox(use_mcp=os.getenv("USE_MCP") == "1"), cfg)
    sid = uuid.uuid4().hex[:8]
    SESSIONS[sid] = {"agent": agent, "state": None}
    return _respond(sid, agent.run(body.message, approve=None))


@app.post("/approve")
def approve(body: ApproveIn):
    s = SESSIONS.get(body.session_id)
    if not s or not s["state"]:
        raise HTTPException(404, "no pending approval for this session")
    return _respond(body.session_id, s["agent"].resume(s["state"], body.approved))


@app.get("/trace/{session_id}")
def trace(session_id: str):
    s = SESSIONS.get(session_id)
    if not s:
        raise HTTPException(404, "unknown session")
    p = TRACE_DIR / f"{session_id}.jsonl"
    return {"events": p.read_text(encoding="utf-8").splitlines() if p.exists() else []}
