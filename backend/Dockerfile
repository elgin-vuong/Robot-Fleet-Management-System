# Single image for all three Python run modes: API server, telemetry
# consumer, and simulator. They share the same dependencies and code; only
# the container command differs (see docker-compose.yml / k8s manifests).
FROM python:3.13-slim

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --no-create-home app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/

RUN chown -R app:app /app
USER app

# Imports are rooted at backend.app.* / backend.simulator.* (see
# pyproject.toml's pythonpath = ["."]), so the app must run from /app.
ENV PYTHONPATH=/app

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=2).status == 200 else 1)"

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
