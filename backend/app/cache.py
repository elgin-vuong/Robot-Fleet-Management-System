import os

import redis

# Defaults to the local docker-compose Redis (no auth/TLS). In AWS this is
# set to a rediss://:<token>@<endpoint>:6379 URL pointing at ElastiCache —
# redis-py's from_url() picks up TLS and the embedded AUTH token from the
# scheme/URL alone, so no other code needs to change. See
# infrastructure/terraform/secrets.tf and README "Secrets management".
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
CACHE_TTL_SECONDS = 10
TELEMETRY_CHANNEL = "telemetry:live"

redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
