"""LINE WORKS API 연동 — 서비스 계정 토큰 발급 + 프로필 사진 조회"""
import time
import threading
from pathlib import Path
from typing import Optional

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend
import jwt as pyjwt

from app.core.config import settings

# ──────────────────────────────────────────
# RSA Private Key 로드 (서버 시작 시 1회)
# ──────────────────────────────────────────
def _load_private_key():
    key_path = Path(settings.works_private_key_path)
    pem = key_path.read_text()
    return serialization.load_pem_private_key(
        pem.encode(), password=None, backend=default_backend()
    )

try:
    _private_key = _load_private_key()
except Exception as e:
    _private_key = None
    import logging
    logging.getLogger(__name__).warning(f"[WorksApi] Private Key 로드 실패: {e}")


# ──────────────────────────────────────────
# JWT Assertion 생성 (RS256)
# ──────────────────────────────────────────
def _create_assertion() -> str:
    """Service Account JWT Assertion — iss: client_id, sub: service_account_id"""
    now = int(time.time())
    payload = {
        "iss": settings.works_client_id,
        "sub": settings.works_service_account_id,
        "iat": now,
        "exp": now + 3600,
    }
    return pyjwt.encode(payload, _private_key, algorithm="RS256")


# ──────────────────────────────────────────
# Access Token 캐시
# ──────────────────────────────────────────
_token_lock = threading.Lock()
_cached_token: str | None = None
_token_expires_at: float = 0.0


def get_works_access_token() -> str:
    global _cached_token, _token_expires_at

    with _token_lock:
        if _cached_token and time.time() < _token_expires_at:
            return _cached_token

        assertion = _create_assertion()
        resp = httpx.post(
            settings.works_auth_url,
            data={
                "assertion": assertion,
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "client_id": settings.works_client_id,
                "client_secret": settings.works_client_secret,
                "scope": settings.works_scope,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        _cached_token = data["access_token"]
        _token_expires_at = time.time() + settings.works_token_ttl_seconds
        return _cached_token


# ──────────────────────────────────────────
# 프로필 사진 조회
# ──────────────────────────────────────────
def fetch_user_photo(user_id: str) -> Optional[bytes]:
    """
    1단계: Works API → 302 → Location 헤더 추출
    2단계: Location URL에 Bearer 토큰으로 이미지 다운로드
    """
    token = get_works_access_token()
    endpoint = f"{settings.works_base_url}/users/{user_id}/photo"

    try:
        # 1단계: 302 redirect 비활성화로 Location 직접 획득
        resp = httpx.get(
            endpoint,
            headers={"Authorization": f"Bearer {token}"},
            follow_redirects=False,
            timeout=10,
        )
        if resp.status_code != 302:
            return None

        location = resp.headers.get("location")
        if not location:
            return None

        # 2단계: 스토리지 URL에서 이미지 다운로드
        img_resp = httpx.get(
            location,
            headers={"Authorization": f"Bearer {token}"},
            follow_redirects=True,
            timeout=10,
        )
        if img_resp.status_code == 200:
            return img_resp.content

    except Exception:
        pass
    return None
