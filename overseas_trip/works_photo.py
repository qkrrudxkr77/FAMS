"""
LINE WORKS API를 통한 프로필 사진 취득.

repo-hub(001_HR팀) 동일 Service Account 자격증명 사용.
흐름:
  1. RSA Private Key로 JWT assertion 생성 (RS256)
  2. POST /oauth2/v2.0/token → access_token 발급
  3. GET /users/{userId}/photo  → 302 → Location 헤더 추출
  4. GET Location URL (Bearer 포함) → 이미지 바이트 반환
"""

import logging
import os
import time
from typing import Optional

import jwt
import requests
from cryptography.hazmat.primitives.serialization import load_pem_private_key

logger = logging.getLogger(__name__)

WORKS_AUTH_URL = "https://auth.worksmobile.com/oauth2/v2.0/token"
WORKS_BASE_URL = "https://www.worksapis.com/v1.0"
WORKS_CLIENT_ID = os.getenv("WORKS_CLIENT_ID", "grJwjauDqqYgpSK1qyYZ")
WORKS_CLIENT_SECRET = os.getenv("WORKS_CLIENT_SECRET", "_0J4owH7es")
WORKS_SERVICE_ACCOUNT_ID = os.getenv("WORKS_SERVICE_ACCOUNT_ID", "313ks.serviceaccount@bodyfriend.co.kr")
WORKS_PRIVATE_KEY_PATH = os.getenv(
    "WORKS_PRIVATE_KEY_PATH",
    "/Users/body/Desktop/BodyFriend/Repositories/ai-solution-project/001_HR팀/repo-hub/secrets/private_20260421171835.key",
)
WORKS_SCOPE = "directory.read,user.read"
WORKS_DOMAIN_IDS = [int(x) for x in os.getenv("WORKS_DOMAIN_IDS", "229352,230291").split(",")]

# 사이드바에 표시할 사용자 email (환경변수로 덮어쓰기 가능)
FAMS_SIDEBAR_USER_EMAIL = os.getenv("FAMS_SIDEBAR_USER_EMAIL", "marinhoon@bodyfriend.co.kr")


def _load_private_key():
    with open(WORKS_PRIVATE_KEY_PATH, "rb") as f:
        return load_pem_private_key(f.read(), password=None)


def _create_jwt_assertion(private_key) -> str:
    now = int(time.time())
    payload = {
        "iss": WORKS_CLIENT_ID,
        "sub": WORKS_SERVICE_ACCOUNT_ID,
        "iat": now,
        "exp": now + 3600,
    }
    return jwt.encode(payload, private_key, algorithm="RS256")


def _get_access_token() -> str:
    private_key = _load_private_key()
    assertion = _create_jwt_assertion(private_key)

    resp = requests.post(
        WORKS_AUTH_URL,
        data={
            "assertion": assertion,
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "client_id": WORKS_CLIENT_ID,
            "client_secret": WORKS_CLIENT_SECRET,
            "scope": WORKS_SCOPE,
        },
        timeout=15,
    )
    resp.raise_for_status()
    token = resp.json().get("access_token")
    logger.info("[WorksPhoto] Access Token 발급 완료")
    return token


def _find_user_id_by_email(token: str, email: str) -> Optional[str]:
    headers = {"Authorization": f"Bearer {token}"}
    for domain_id in WORKS_DOMAIN_IDS:
        cursor = None
        while True:
            params = {"domainId": domain_id, "count": 100}
            if cursor:
                params["cursor"] = cursor
            resp = requests.get(
                f"{WORKS_BASE_URL}/users",
                headers=headers,
                params=params,
                timeout=15,
            )
            if not resp.ok:
                logger.warning("[WorksPhoto] /users 조회 실패: domainId=%d status=%d", domain_id, resp.status_code)
                break
            data = resp.json()
            for user in data.get("users", []):
                if user.get("email") == email:
                    uid = user.get("userId")
                    logger.info("[WorksPhoto] userId 발견: email=%s userId=%s", email, uid)
                    return uid
            cursor = (data.get("responseMetaData") or {}).get("nextCursor")
            if not cursor:
                break
    logger.warning("[WorksPhoto] email로 userId를 찾지 못함: %s", email)
    return None


def fetch_photo_bytes(email: Optional[str] = None) -> Optional[bytes]:
    """LINE WORKS API로 email 사용자 프로필 사진 바이트 반환. email 생략 시 FAMS_SIDEBAR_USER_EMAIL 사용."""
    target_email = email or FAMS_SIDEBAR_USER_EMAIL
    try:
        token = _get_access_token()
        user_id = _find_user_id_by_email(token, target_email)
        if not user_id:
            return None

        # 302 redirect → Location 헤더 추출
        resp = requests.get(
            f"{WORKS_BASE_URL}/users/{user_id}/photo",
            headers={"Authorization": f"Bearer {token}"},
            allow_redirects=False,
            timeout=15,
        )

        if resp.status_code == 302:
            location = resp.headers.get("Location")
            if not location:
                return None
            logger.info("[WorksPhoto] 사진 스토리지 URL: %s", location[:80])
            photo_resp = requests.get(
                location,
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )
            if photo_resp.ok:
                logger.info("[WorksPhoto] 사진 취득 완료: %d bytes", len(photo_resp.content))
                return photo_resp.content
            logger.warning("[WorksPhoto] 스토리지 응답 오류: status=%d", photo_resp.status_code)
        elif resp.status_code == 404:
            logger.info("[WorksPhoto] 사진 미등록 사용자: %s", target_email)
        else:
            logger.warning("[WorksPhoto] 사진 API 오류: status=%d", resp.status_code)
    except Exception as e:
        logger.warning("[WorksPhoto] 사진 취득 실패: %s", e)
    return None
