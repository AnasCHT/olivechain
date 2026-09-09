FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY olivechain/ olivechain/
COPY frontend/ frontend/
COPY demo/ demo/
COPY scripts/docker-entrypoint.sh serve.py ./
RUN chmod +x docker-entrypoint.sh

# ledger + registry and off-chain evidence live on volumes
VOLUME ["/app/data", "/app/evidence_store"]

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if b'ok' in urllib.request.urlopen('http://localhost:8000/health', timeout=3).read() else 1)"

ENTRYPOINT ["./docker-entrypoint.sh"]
