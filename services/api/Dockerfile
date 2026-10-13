# Build from the repository root (the API reads mcp/registry.json and
# prompts/ relative to the repo layout):
#   docker build -f services/api/Dockerfile -t helixos-api .

FROM python:3.12-slim AS deps
WORKDIR /build
COPY services/api/pyproject.toml ./
# Install only the declared dependencies; the app runs from source (see below)
# so its repo-relative lookups keep working.
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" > requirements.txt \
    && python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app/services/api \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HELIX_ENV=production \
    PORT=8000
RUN useradd --system --uid 10001 --no-create-home helix
COPY --from=deps /opt/venv /opt/venv
WORKDIR /app/services/api
COPY services/api/helixos ./helixos
COPY mcp/registry.json /app/mcp/registry.json
COPY prompts /app/prompts
USER helix
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request as u; u.urlopen('http://127.0.0.1:%s/health' % os.getenv('PORT', '8000'), timeout=3)"]
# One process: AI sessions/runs are held in memory per process until they are
# persisted, so do not add workers or scale beyond one instance yet.
# No --proxy-headers: uvicorn would trust the client-controlled leftmost
# X-Forwarded-For entry. Rate limiting reads the header itself, from the right,
# using HELIX_TRUSTED_PROXY_HOPS (1 behind Cloud Run's front end).
CMD ["sh", "-c", "exec uvicorn helixos.main:app --host 0.0.0.0 --port ${PORT} --no-access-log"]
