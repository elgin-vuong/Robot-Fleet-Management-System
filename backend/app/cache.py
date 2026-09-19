import os

import redis

# REDIS_URL wins if set (e.g. local bare dev, or a full external connection
# string). Otherwise build it from CACHE_HOST/CACHE_PORT — what
# docker-compose.yml and infrastructure/k8s/configmap.yaml actually set —
# falling back to localhost for bare local dev with none of these set.
REDIS_URL = os.getenv("REDIS_URL") or "redis://{host}:{port}".format(
    host=os.getenv("CACHE_HOST", "localhost"),
    port=os.getenv("CACHE_PORT", "6379"),
)
CACHE_TTL_SECONDS = 10
TELEMETRY_CHANNEL = "telemetry:live"

redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
