import redis

CACHE_HOST = "localhost"
CACHE_PORT = 6379
CACHE_TTL_SECONDS = 10

redis_client = redis.Redis(host=CACHE_HOST, port=CACHE_PORT, decode_responses=True)
