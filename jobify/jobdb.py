"""The job database + application tracker. Exposed to the agent through MCP (jobify/mcp_server.py)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from . import config
from .retrieval import tokenize


def load_jobs() -> list[dict]:
    return json.loads(config.jobs_path().read_text(encoding="utf-8"))


def _summary(j: dict) -> dict:
    keys = ("id", "title", "company", "location", "salary_sar", "experience_years", "required_skills")
    return {k: j.get(k) for k in keys}


def search_jobs(query: str = "", location: str = "", limit: int = 5) -> dict:
    """Keyword search over title/skills/description. Returns summaries only (no descriptions)."""
    jobs = load_jobs()
    q = set(tokenize(query))
    loc_tokens = set(tokenize(location))
    known = {t for j in jobs for t in tokenize(j["location"])}
    active = loc_tokens & known  # country-level text like "Saudi Arabia" does not filter

    scored = []
    for j in jobs:
        jl = set(tokenize(j["location"]))
        if active and not (jl & active) and "remote" not in jl:
            continue
        title = set(tokenize(j["title"]))
        skills = set(tokenize(" ".join(j.get("required_skills", []) + j.get("preferred_skills", []))))
        desc = set(tokenize(j.get("description", "")))
        score = 2 * len(q & title) + 1.5 * len(q & skills) + len(q & desc) if q else 1
        if score > 0:
            scored.append((score, j))
    scored.sort(key=lambda x: (-x[0], x[1]["id"]))
    limit = max(1, min(int(limit or 5), 10))
    top = [_summary(j) for _, j in scored[:limit]]
    return {"count": len(top), "jobs": top}


def get_job(job_id: str) -> dict:
    for j in load_jobs():
        if j["id"] == job_id:
            return j
    return {"error": f"job '{job_id}' not found"}


def list_applications() -> list[dict]:
    p = config.applications_path()
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def save_application(job_id: str, cover_letter: str, notes: str = "") -> dict:
    """WRITE action. The harness must obtain user approval before this is called."""
    job = get_job(job_id)
    if "error" in job:
        return job
    apps = list_applications()
    entry = {
        "application_id": f"app{len(apps) + 1:03d}",
        "job_id": job_id,
        "job_title": job["title"],
        "company": job["company"],
        "cover_letter": cover_letter,
        "notes": notes,
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    apps.append(entry)
    p = config.applications_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(apps, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "saved", "application_id": entry["application_id"]}
