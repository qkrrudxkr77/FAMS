import redis.asyncio as aioredis

from app.core.config import settings

_pool: aioredis.Redis | None = None

REFRESH_KEY = "fams:refresh_token:{email}"
PREV_REFRESH_KEY = "fams:prev_refresh_token:{email}"


def get_redis() -> aioredis.Redis:
    global _pool
    if _pool is None:
        _pool = aioredis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            decode_responses=True,
        )
    return _pool


async def set_refresh_token(email: str, token: str) -> None:
    r = get_redis()
    key = REFRESH_KEY.format(email=email)
    ttl = settings.refresh_token_expiry // 1000  # ms → seconds
    await r.set(key, token, ex=ttl)


async def get_refresh_token(email: str) -> str | None:
    r = get_redis()
    return await r.get(REFRESH_KEY.format(email=email))


async def set_prev_refresh_token(email: str, token: str) -> None:
    """토큰 로테이션 시 1분 유예 기간 보관"""
    r = get_redis()
    await r.set(PREV_REFRESH_KEY.format(email=email), token, ex=60)


async def get_prev_refresh_token(email: str) -> str | None:
    r = get_redis()
    return await r.get(PREV_REFRESH_KEY.format(email=email))


async def delete_refresh_token(email: str) -> None:
    r = get_redis()
    await r.delete(REFRESH_KEY.format(email=email))
    await r.delete(PREV_REFRESH_KEY.format(email=email))
