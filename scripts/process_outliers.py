#!/usr/bin/env python3
"""ATS-score every job against the resume skill graph, then sift for outliers.

Usage: process_outliers.py [--offline] [--min-score 55] [--max-missing 2]
Scores from Neo4j (run parse_and_ingest.py first) unless --offline / Neo4j unreachable.
Writes web/analysis.json, which the dashboard reads.
"""
import argparse
import json
import os
from datetime import datetime, timezone
from common import ROOT, parse_resume, load_jobs, job_terms, have_weights, score_job

CYPHER = """
MATCH (j:Job)-[r:REQUIRES]->(s:Skill)
OPTIONAL MATCH (c:Candidate {id:$cid})-[h:HAS_SKILL]->(s)
RETURN j.id AS id, j.title AS title, j.company AS company, j.location AS location,
       collect({skill:s.name, critical:r.critical, w:h.weight}) AS reqs
"""


def from_neo4j(cid):
    from neo4j import GraphDatabase
    auth = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "changeme123"))
    with GraphDatabase.driver(os.getenv("NEO4J_URI", "bolt://localhost:7687"), auth=auth) as d:
        d.verify_connectivity()
        rows = d.execute_query(CYPHER, cid=cid, database_=os.getenv("NEO4J_DATABASE", "neo4j"))[0]
    jobs, have = [], {}
    for r in rows:
        jobs.append({"id": r["id"], "title": r["title"], "company": r["company"], "location": r["location"],
                     "required": [{"skill": q["skill"], "critical": q["critical"]} for q in r["reqs"]]})
        have.update({q["skill"]: q["w"] for q in r["reqs"] if q["w"] is not None})
    return jobs, have


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--min-score", type=float, default=55.0, help="minimum ATS score (50-60 typical)")
    ap.add_argument("--max-missing", type=int, default=2)
    a = ap.parse_args()
    file_jobs = load_jobs()
    cand = parse_resume(extra_terms=job_terms(file_jobs))
    jobs, have, source = file_jobs, have_weights(cand["skills"]), "offline"
    if not a.offline:
        try:
            jobs, have = from_neo4j(cand["id"])
            source = "neo4j"
        except Exception as exc:
            print(f"Neo4j unavailable ({exc}); falling back to offline mode")
    scored = sorted((score_job(j, have, a.min_score, a.max_missing) for j in jobs),
                    key=lambda r: (-r["ats_score"], len(r["missing"])))
    out = {"generated": datetime.now(timezone.utc).isoformat(), "source": source, "candidate": cand["name"],
           "thresholds": {"min_score": a.min_score, "max_missing": a.max_missing},
           "skills": sorted(({"name": k, **v} for k, v in cand["skills"].items()), key=lambda x: (x["category"], x["name"])),
           "credentials": cand["credentials"], "experiences": cand["experiences"], "jobs": scored}
    path = ROOT / "web" / "analysis.json"
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"[{source}] {len(out['skills'])} skills | {len(scored)} jobs scored | "
          f"{sum(j['outlier'] for j in scored)} outliers | {sum(j['strict_match'] for j in scored)} strict -> {path}")


if __name__ == "__main__":
    main()
