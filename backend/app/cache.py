import os

import redis

CACHE_HOST = os.getenv("CACHE_HOST", "localhost")
CACHE_PORT = int(os.getenv("CACHE_PORT", "6379"))
CACHE_TTL_SECONDS = 10
TELEMETRY_CHANNEL = "telemetry:live"

redis_client = redis.Redis(host=CACHE_HOST, port=CACHE_PORT, decode_responses=True)
