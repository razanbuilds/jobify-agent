"""Turn a jamee export (JSON list or CSV) into a frozen snapshot: data/jobs_real.json

  python scripts/snapshot_from_jamee.py path/to/jamee_export.json
  JOBIFY_JOBS=data/jobs_real.json python -m jobify.cli     # use it for the demo

Edit FIELD_MAP so the right-hand names match your jamee columns/keys.
Evals keep using data/jobs.json (synthetic, reproducible) - do not point them at live data.
"""
import csv
import json
import re
import sys
from pathlib import Path

FIELD_MAP = {  # our field        -> your jamee field
    "title": "title",
    "company": "company",
    "location": "location",
    "salary_sar": "salary",
    "description": "description",
    "skills": "skills",
}
MAX_JOBS = 60


def load(path: Path) -> list[dict]:
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    return json.loads(path.read_text(encoding="utf-8"))


def main(src: str) -> None:
    rows, seen, out = load(Path(src)), set(), []
    for r in rows:
        g = {k: r.get(v) for k, v in FIELD_MAP.items()}
        key = (str(g["title"]).lower(), str(g["company"]).lower(), str(g["location"]).lower())
        if not g["title"] or key in seen:
            continue
        seen.add(key)
        skills = g["skills"] if isinstance(g["skills"], list) else [s.strip() for s in str(g["skills"] or "").split(",") if s.strip()]
        sal = re.sub(r"[^\d]", "", str(g["salary_sar"] or ""))
        out.append({
            "id": f"j{len(out) + 1:03d}", "title": g["title"], "company": g["company"] or "Unknown",
            "location": g["location"] or "Unknown", "salary_sar": int(sal) if sal else None,
            "experience_years": None, "required_skills": skills, "preferred_skills": [],
            "description": str(g["description"] or "")[:1500],
        })
        if len(out) >= MAX_JOBS:
            break
    dest = Path(__file__).resolve().parent.parent / "data" / "jobs_real.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(out)} jobs to {dest}")


if __name__ == "__main__":
    main(sys.argv[1])
