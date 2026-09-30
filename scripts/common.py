"""Shared logic: parse the real resume (index.html) into a skill tree, then ATS-score jobs and sift outliers."""
import json
import re
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent

# canonical skill names (alias -> canonical); aliases are also searched for in resume prose
CANON = {"amazon web services": "aws", "k8s": "kubernetes", "postgres": "postgresql", "mongo": "mongodb",
         "node": "node.js", "nodejs": "node.js", "elastic": "elasticsearch", "ci-cd": "ci/cd", "js": "javascript",
         "red hat enterprise linux": "rhel", "open stack": "openstack"}
TEXT_ALT = {}
for _a, _c in CANON.items():
    TEXT_ALT.setdefault(_c, []).append(_a)

# how strongly each evidence source counts toward an ATS keyword hit
WEIGHTS = {"matrix": 1.0, "credential": 1.0, "implied": 0.8, "text": 0.6}
AMBIGUOUS = {"go", "r", "c", "rest"}          # too noisy to find in prose
SKIP_CARDS = ("origins", "game servers", "gaming", "creative")       # matrix cards that are not professional skills
SKIP_LABELS = ("experience", "education")
CERT_KEYWORDS = {"aws certified": ["aws"], "solutions architect": ["aws"], "cloud practitioner": ["aws"],
                 "mongodb": ["mongodb", "nosql"], "linux": ["linux"], "red hat": ["linux", "rhel"],
                 "rhce": ["linux", "rhel"], "rhcsa": ["linux", "rhel"], "lpic": ["linux"], "cpanel": ["cpanel"],
                 "whm": ["cpanel"], "plesk": ["plesk"], "imunify360": ["imunify360", "security"],
                 "disaster recovery": ["disaster recovery"], "network": ["networking"]}
IMPLIES = {"mysql": "sql", "postgresql": "sql", "mongodb": "nosql", "redis": "nosql", "dynamodb": "nosql",
           "galera": "clustering", "pxc": "clustering", "rhel": "linux", "lamp": "linux", "lemp": "linux"}


def norm(s):
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"\s+", " ", s).strip(" .;:-").lower()
    return CANON.get(s, s)


def split_items(text):
    out = []
    for piece in re.split(r"\s*(?:·|,|;|\s/\s|\s\|\s)\s*", text):
        piece = re.sub(r"^(and|&)\s+", "", piece.strip())
        if 1 < len(piece) <= 40 and len(piece.split()) <= 4 and ". " not in piece:
            out.append(norm(piece))
    return [p for p in out if p]


def count_term(term, text):
    if term in AMBIGUOUS:
        return 0
    n = 0
    for t in [term] + TEXT_ALT.get(term, []):
        n += len(re.findall(r"(?<![\w+#])" + re.escape(t) + r"(?![\w+#])", text, re.I))
    return n


def cert_skills(name):
    low, found = name.lower(), []
    for kw, sk in CERT_KEYWORDS.items():
        if kw in low:
            found += [s for s in sk if s not in found]
    return found


def parse_resume(path=ROOT / "index.html", extra_terms=()):
    """Return candidate dict: skills{name:{category,source,evidence}}, credentials[], experiences[]."""
    soup = BeautifulSoup(Path(path).read_text(encoding="utf-8"), "html.parser")
    for t in soup(["script", "style", "svg"]):
        t.decompose()
    h1 = soup.select_one("h1")
    name = h1.get_text(strip=True) if h1 else "Candidate"
    corpus = re.sub(r"\s+", " ", soup.get_text(" "))
    skills, cert_lines = {}, []

    def add(n, cat, src):
        if n and (n not in skills or WEIGHTS[src] > WEIGHTS[skills[n]["source"]]):
            skills[n] = {"category": cat, "source": src, "evidence": 0}

    # 1) matrix cards -> skill tree (headings like "Databases (since 2005)" become sub-categories)
    for card in soup.select(".matrix-card"):
        tt = card.select_one(".card-toggle span")
        title = tt.get_text(" ", strip=True) if tt else ""
        if any(k in title.lower() for k in SKIP_CARDS):
            continue
        cat = re.sub(r"^[^\w]+", "", title).strip() or "General"
        body, cur = card.select_one(".card-content"), cat
        for el in (body.select("p, li") if body else []):
            txt, strong = el.get_text(" ", strip=True), el.find("strong")
            stxt = strong.get_text(" ", strip=True) if strong else ""
            if el.name == "p" and strong and stxt == txt:
                cur = cat + " / " + re.sub(r"\(.*?\)", "", txt).strip()
                continue
            if el.name == "li" and strong:
                label = re.sub(r"^[^\w]+|:$", "", stxt)
                if any(k in label.lower() for k in SKIP_LABELS):
                    continue
                if "certif" in label.lower():
                    cert_lines.append(txt[len(stxt):])
                    continue
                for it in split_items(txt[len(stxt):]):
                    add(it, cat + " / " + label, "matrix")
            elif len(txt) < 200 and not txt.endswith("."):
                for it in split_items(txt):
                    add(it, cur, "matrix")

    # 2) credentials: certification cards + technical training courses
    creds, seen = [], set()

    def add_cred(nm, issued="", expires="", cid="", year=""):
        if nm and nm.lower() not in seen:
            seen.add(nm.lower())
            creds.append({"name": nm, "issued": issued, "expires": expires, "credential_id": cid,
                          "year": year, "skills": cert_skills(nm)})

    for c in soup.select(".cert-card"):
        h = c.select_one(".course-title, h3")
        blob = c.get_text(" ", strip=True)
        g = lambda k: (re.search(k + r":\s*([^|]+?)(?:\s*\||\s*$|\s+Credential|\s+Expires)", blob) or [None, ""])[1].strip()
        add_cred(h.get_text(" ", strip=True) if h else "", g("Issued"), g("Expires"), g("Credential ID"))
    for y in soup.select(".tt-year"):
        yt = y.select_one(".tt-year-title")
        for c in y.select(".tt-course"):
            b = c.find("b")
            add_cred(b.get_text(" ", strip=True) if b else "", year=yt.get_text(strip=True) if yt else "")
    for line in cert_lines:
        for it in re.split(r"\s*·\s*", line):
            add_cred(re.sub(r"\(.*?\)", "", it).strip())
    for c in creds:
        for s in c["skills"]:
            add(s, "Credentials", "credential")

    # 3) implied skills, then prose evidence for every known/target term
    for s in list(skills):
        if s in IMPLIES:
            add(IMPLIES[s], "Implied", "implied")
    vocab = set(skills) | {norm(t) for t in extra_terms}
    for t in vocab:
        n = count_term(t, corpus)
        if n and t not in skills:
            add(t, "Mentioned in experience", "text")
        if t in skills:
            skills[t]["evidence"] = n

    # 4) experience timeline
    exps = []
    for it in soup.select(".timeline-item"):
        det, d = it.select_one(".job-details"), it.select_one(".timeline-date")
        p = det.find("p") if det else None
        roles = [h.get_text(" ", strip=True) for h in it.find_all("h4") if "selected projects" not in h.get_text().lower()]
        company = p.get_text(" ", strip=True) if p else ""
        if not (company or roles):
            continue
        text = re.sub(r"\s+", " ", it.get_text(" "))
        exps.append({"id": re.sub(r"\W+", "-", (company + (d.get_text() if d else "")).lower()).strip("-")[:80],
                     "company": company, "dates": d.get_text(" ", strip=True) if d else "", "roles": roles,
                     "skills": sorted(t for t in vocab if count_term(t, text))})
    return {"id": re.sub(r"\W+", "-", name.lower()), "name": name, "skills": skills,
            "credentials": creds, "experiences": exps}


def have_weights(skills):
    return {k: WEIGHTS[v["source"]] for k, v in skills.items()}


def load_jobs(path=ROOT / "data" / "jobs.json"):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def job_terms(jobs):
    return {norm(r["skill"]) for j in jobs for r in j["required"]}


def score_job(job, have, min_score=55.0, max_missing=2):
    """ATS score = weighted keyword coverage (critical skills count double, prose-only evidence counts less).
    Outlier = score >= min_score, 1..max_missing missing skills, none of them critical."""
    req = [(norm(r["skill"]), bool(r.get("critical"))) for r in job["required"]]
    tot = sum(2 if c else 1 for _, c in req) or 1
    got = sum((2 if c else 1) * have.get(s, 0) for s, c in req)
    matched = [{"skill": s, "weight": have[s]} for s, _ in req if have.get(s, 0) > 0]
    missing = [{"skill": s, "critical": c} for s, c in req if have.get(s, 0) <= 0]
    ats = round(100 * got / tot, 1)
    outlier = ats >= min_score and 1 <= len(missing) <= max_missing and not any(m["critical"] for m in missing)
    return {"id": job["id"], "title": job["title"], "company": job["company"], "location": job.get("location", ""),
            "ats_score": ats, "matched": matched, "missing": missing, "strict_match": not missing, "outlier": outlier}
