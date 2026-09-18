import os

import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
CACHE_TTL_SECONDS = 10
TELEMETRY_CHANNEL = "telemetry:live"

redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
