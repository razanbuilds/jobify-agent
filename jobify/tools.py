"""Tool specs (OpenAI function format) and the ToolBox that dispatches them.

search_jobs / get_job / save_application  -> the job database, optionally over MCP (use_mcp=True)
search_profile                            -> local retrieval over data/profile/*.md
"""
from __future__ import annotations

import json

from . import jobdb
from .retrieval import ProfileIndex

WRITE_TOOLS = {"save_application"}          # need human approval
EXTERNAL_TOOLS = {"search_jobs", "get_job"}  # return third-party text -> untrusted
MCP_TOOLS = {"search_jobs", "get_job", "save_application"}


def _spec(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties, "required": required}}}


SPECS = [
    _spec("search_jobs",
          "Search the job database. Returns job summaries (id, title, company, location, salary, required skills). "
          "Use get_job for the full description.",
          {"query": {"type": "string", "description": "keywords, e.g. 'data analyst power bi'"},
           "location": {"type": "string", "description": "city such as Riyadh, Jeddah, Dammam or Remote (optional)"},
           "limit": {"type": "integer", "description": "max results, default 5"}}, ["query"]),
    _spec("get_job", "Get the full record of one job by id (e.g. 'j01').",
          {"job_id": {"type": "string"}}, ["job_id"]),
    _spec("search_profile",
          "Search the user's own profile (education, experience, projects, skills). Use it before claiming "
          "the user has any skill or experience.",
          {"query": {"type": "string"}, "k": {"type": "integer", "description": "chunks to return, default 3"}},
          ["query"]),
    _spec("save_application",
          "WRITE ACTION: save a tailored application to the tracker. Requires user approval; "
          "only call it when the user asked to save/apply.",
          {"job_id": {"type": "string"}, "cover_letter": {"type": "string"}, "notes": {"type": "string"}},
          ["job_id", "cover_letter"]),
]


class ToolBox:
    def __init__(self, use_mcp: bool = False):
        self.use_mcp = use_mcp
        self._index: ProfileIndex | None = None

    def specs(self) -> list[dict]:
        return SPECS

    def call(self, name: str, args: dict) -> str:
        if name == "search_profile":
            self._index = self._index or ProfileIndex()
            res = self._index.search(str(args.get("query", "")), k=int(args.get("k", 3) or 3))
            return json.dumps({"results": res}, ensure_ascii=False)
        if name in MCP_TOOLS:
            if self.use_mcp:
                from .mcp_client import call_tool
                return call_tool(name, args)
            return json.dumps(getattr(jobdb, name)(**args), ensure_ascii=False)
        raise ValueError(f"unknown tool '{name}'")
