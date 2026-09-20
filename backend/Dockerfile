# Single image for all three Python run modes: API server, telemetry
# consumer, and simulator. They share the same dependencies and code; only
# the container command differs (see docker-compose.yml / k8s manifests).
FROM python:3.13-slim

# Set by .github/workflows/docker.yml at build time to the commit SHA being
# built — baked into the image (not passed in at deploy time) since it's a
# property of what's IN the image, immutable for the image's lifetime.
# Exposed at runtime via GET /health's "version" field.
ARG GIT_SHA=unknown
ENV GIT_SHA=${GIT_SHA}

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --no-create-home app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/

# backend/app/database.py etc. import as `backend.app...` — this matches
# how the app is already run locally (`python -m backend.app.main`,
# `python -m backend.simulator.run`), so no import-path changes needed.
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

EXPOSE 8000

# Default command runs the API. Worker task definitions override this
# with ["python", "-m", "backend.app.consumers.telemetry_consumer"] or
# ["python", "-m", "backend.simulator.run"].
RUN chown -R app:app /app
USER app

# Imports are rooted at backend.app.* / backend.simulator.* (see
# pyproject.toml's pythonpath = ["."]), so the app must run from /app.
ENV PYTHONPATH=/app

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=2).status == 200 else 1)"

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
