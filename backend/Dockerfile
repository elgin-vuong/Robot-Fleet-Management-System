# Single image for three ECS task definitions: the FastAPI API, the
# telemetry-consumer worker, and the simulator worker. Which one runs is
# decided entirely by the container `command` in each ECS task definition
# (see infrastructure/terraform/modules/compute/services.tf) — not by
# anything baked into this image. Build once, deploy three ways.
#
# Build from the REPO ROOT (not from backend/), since the build context
# needs both backend/ and the top-level package layout main.py imports
# expect (backend.app.main, backend.simulator.run, etc.):
#   docker build -f backend/Dockerfile -t <tag> .

FROM python:3.10-slim AS base

WORKDIR /app

# System deps for psycopg2 (compiled from source unless wheels are
# available for this base image/arch) and general TLS support.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

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
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
