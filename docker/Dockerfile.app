FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY index.html ./index.html
COPY data ./data
COPY scripts ./scripts
COPY web ./web
ENV PYTHONUNBUFFERED=1
EXPOSE 8080
# Ingest into Neo4j, compute outliers, then serve the dashboard at /web/
CMD ["sh", "-c", "python scripts/parse_and_ingest.py && python scripts/process_outliers.py; python -m http.server 8080"]
