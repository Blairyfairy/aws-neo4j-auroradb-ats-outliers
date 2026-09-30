# aws-neo4j-auradb

Parses **your real resume (`index.html`)** into a Neo4j skill graph, ATS-scores job postings against it, and sifts out **outlier** jobs: strong matches that miss only 1-2 non-critical skills. Runs on AWS ECS Fargate against Neo4j AuraDB, with a glassmorphism dashboard.

## Pipeline

1. **Parse** (`scripts/common.py`): reads `index.html` with BeautifulSoup, nothing hardcoded.
   - `.matrix-card` blocks become the skill tree (headings such as *Databases* become categories; the Origins and Gaming/Creative cards are skipped).
   - `.cert-card` and `.tt-course` entries become credentials; keywords map them to skills (e.g. "MongoDB for DBAs" -> `mongodb`).
   - `.timeline-item` entries become experience nodes, linked to skills found in their text.
   - Skills mentioned only in prose (e.g. Docker, Terraform) are kept as weaker evidence.
2. **Ingest** (`scripts/parse_and_ingest.py`): writes the graph to Neo4j:
   `(Candidate)-[:HAS_SKILL {source,weight,evidence}]->(Skill)-[:IN_CATEGORY]->(Category)`, `(Credential)-[:VALIDATES]->(Skill)`, `(Experience)-[:USED]->(Skill)`, `(Job)-[:REQUIRES {critical}]->(Skill)`.
3. **ATS score** (`scripts/process_outliers.py`): per job, weighted keyword coverage x 100. Critical skills count double. Evidence weights: matrix/credential 1.0, implied 0.8, prose-only 0.6.
4. **Sift outliers**: ATS score >= `--min-score` (default 55; use 50-60), 1 to `--max-missing` (default 2) missing skills, none critical. Output: `web/analysis.json`.

## Files

| Path | Purpose |
|---|---|
| `index.html` | Source resume (the page being parsed) |
| `data/jobs.json` | Sample postings with required skills and a `critical` flag; replace with real postings |
| `scripts/` | `common.py`, `parse_and_ingest.py`, `process_outliers.py` |
| `web/` | Dashboard (`index.html`, `app.js`, `style.css`) plus a prebuilt `analysis.json` |
| `docker/Dockerfile.app` | Image: ingest into AuraDB, score, serve on 8080 |
| `terraform/` | ECS Fargate app + ALB, AuraDB credentials in Secrets Manager |
| `.env.example` | AuraDB connection variables |
| `build_zip.py` | Packages the repo into `dist/aws-neo4j-auradb.zip` (no `__MACOSX` / `.DS_Store`) |

## Database: Neo4j AuraDB on AWS

The graph lives in a managed **Neo4j AuraDB** instance (create one at console.neo4j.io and choose AWS as the cloud). Copy `.env.example` to `.env`, fill in the URI (`neo4j+s://<dbid>.databases.neo4j.io`) and the generated password, and export them. The scripts read `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` and `NEO4J_DATABASE`.

## Run locally

```bash
pip install -r requirements.txt
python scripts/process_outliers.py --offline       # no database needed
python -m http.server 8080                         # open http://localhost:8080/web/

set -a; source .env; set +a                        # AuraDB credentials
python scripts/parse_and_ingest.py && python scripts/process_outliers.py --min-score 60 --max-missing 1
```
The dashboard sliders re-sift outliers in the browser from `analysis.json`. A local Neo4j also works: `docker run -d -p 7687:7687 -e NEO4J_AUTH=neo4j/changeme123 neo4j:5-community`.

## Deploy to AWS

```bash
aws ecr create-repository --repository-name aws-neo4j-auradb
docker build -f docker/Dockerfile.app -t <acct>.dkr.ecr.<region>.amazonaws.com/aws-neo4j-auradb:latest .
docker push <acct>.dkr.ecr.<region>.amazonaws.com/aws-neo4j-auradb:latest
cd terraform && terraform init
terraform apply -var 'app_image=<ecr-uri>:latest' -var 'neo4j_uri=neo4j+s://<dbid>.databases.neo4j.io' -var 'neo4j_password=<aura-password>'
```
Open the `dashboard_url` output. Terraform stores the AuraDB credentials in Secrets Manager and injects them into the Fargate task. The task reaches AuraDB over the public internet with TLS; for private connectivity use an AuraDB Virtual Dedicated Cloud tier with AWS PrivateLink. The ALB is HTTP-only (add ACM for HTTPS), and the default VPC in `us-west-2` is assumed. Note that `terraform.tfstate` will contain the password, so use an encrypted remote backend.

## Notes

Images referenced by `index.html` (e.g. `BlairPageImages/`) are not bundled; the parser only needs the HTML. Update `data/jobs.json` with real postings to get meaningful outliers.
