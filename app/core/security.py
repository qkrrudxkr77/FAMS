from datetime import datetime, timezone, timedelta
from jose import jwt, JWTError
from jose.exceptions import ExpiredSignatureError

from app.core.config import settings


def _ms_to_delta(ms: int) -> timedelta:
    return timedelta(milliseconds=ms)


def validate_workthrough_token(token: str) -> dict:
    """Workthrough SSO JWT 검증 — workthroughSecretKey 사용"""
    try:
        payload = jwt.decode(
            token.strip(),
            settings.workthrough_secret_key,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
        return payload
    except ExpiredSignatureError:
        raise ValueError("만료된 Workthrough 토큰입니다.")
    except JWTError as e:
        raise ValueError(f"유효하지 않은 Workthrough 토큰입니다: {e}")


def create_access_token(claims: dict) -> str:
    """FAMS Access Token 생성 (12시간)"""
    now = datetime.now(timezone.utc)
    payload = {
        **claims,
        "iss": settings.jwt_issuer,
        "iat": now,
        "exp": now + _ms_to_delta(settings.access_token_expiry),
    }
    return jwt.encode(payload, settings.fams_secret_key, algorithm="HS256")


def create_refresh_token(claims: dict) -> str:
    """FAMS Refresh Token 생성 (14일)"""
    now = datetime.now(timezone.utc)
    payload = {
        **claims,
        "iss": settings.jwt_issuer,
        "iat": now,
        "exp": now + _ms_to_delta(settings.refresh_token_expiry),
    }
    return jwt.encode(payload, settings.fams_secret_key, algorithm="HS256")


def decode_fams_token(token: str) -> dict:
    """FAMS 토큰 검증 및 클레임 반환"""
    try:
        payload = jwt.decode(
            token,
            settings.fams_secret_key,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
        return payload
    except ExpiredSignatureError:
        raise ValueError("만료된 토큰입니다.")
    except JWTError as e:
        raise ValueError(f"유효하지 않은 토큰입니다: {e}")
