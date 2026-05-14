"""
Workthrough SSO 토큰 검증 및 FAMS JWT 발급.

Workthrough에서 아래 과정을 거침:
1. 사용자가 워크쓰루에서 "FAMS 접근" 버튼 클릭
2. Workthrough가 JWT 토큰 생성 (email, empNo 포함)
3. 사용자를 http://localhost:9090/api/token/login?token=<TOKEN> 으로 리다이렉트
4. FAMS에서 토큰 검증 후 세션 설정
5. FAMS UI로 리다이렉트
"""

import logging
import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Workthrough 토큰 검증용 시크릿 (repo-hub와 동일)
WORKTHROUGH_SECRET = 'WorkthrouthSSOToken^%@#&A3812_129273023_12978130A'
WORKTHROUGH_ALGORITHM = 'HS256'

# FAMS 토큰 발급용 시크릿 (내부용)
FAMS_SECRET = 'FAMS_SECRET_KEY_2026'
FAMS_ALGORITHM = 'HS256'
FAMS_ACCESS_TOKEN_EXPIRE_HOURS = 24
FAMS_REFRESH_TOKEN_EXPIRE_DAYS = 14


class WorkthroughTokenPayload:
    """Workthrough 토큰 페이로드"""
    def __init__(self, email: str, empNo: Optional[str] = None):
        self.email = email
        self.empNo = empNo


def validate_workthrough_token(token: str) -> WorkthroughTokenPayload:
    """
    Workthrough 토큰 검증 및 페이로드 추출.

    Args:
        token: Workthrough JWT 토큰

    Returns:
        WorkthroughTokenPayload 객체

    Raises:
        jwt.InvalidTokenError: 토큰 검증 실패
    """
    try:
        payload = jwt.decode(
            token,
            WORKTHROUGH_SECRET,
            algorithms=[WORKTHROUGH_ALGORITHM]
        )

        # email, empNo 추출 (repo-hub처럼 공백 제거 및 대소문자 무시 처리)
        email = None
        empNo = None

        for key, value in payload.items():
            key_lower = key.strip().lower()
            if key_lower == 'email':
                email = value
            elif key_lower == 'empno':
                empNo = value

        if not email:
            raise ValueError("Email claim not found in Workthrough token")

        logger.info(f"Workthrough token validated: email={email}, empNo={empNo}")
        return WorkthroughTokenPayload(email=email, empNo=empNo)

    except jwt.ExpiredSignatureError:
        logger.error("Workthrough token expired")
        raise
    except jwt.InvalidTokenError as e:
        logger.error(f"Invalid Workthrough token: {e}")
        raise


def create_fams_access_token(
    email: str,
    name: Optional[str] = None,
    dept_name: Optional[str] = None,
    position_name: Optional[str] = None,
    level_name: Optional[str] = None,
) -> str:
    """
    FAMS Access Token 생성 (repo-hub RepoHubTokenPayload와 동일 구조).

    Args:
        email: 사용자 이메일
        name: 이름 (Works API에서 조회)
        dept_name: 부서명
        position_name: 직책 (부장, 팀장 등)
        level_name: 직급 (선임, 수석 등)

    Returns:
        JWT Access Token
    """
    now = datetime.utcnow()
    expire = now + timedelta(hours=FAMS_ACCESS_TOKEN_EXPIRE_HOURS)

    payload = {
        'email': email,
        'name': name or '',
        'dept_name': dept_name or '',
        'position_name': position_name or '',
        'level_name': level_name or '',
        'iat': now,
        'exp': expire,
        'type': 'access'
    }

    token = jwt.encode(
        payload,
        FAMS_SECRET,
        algorithm=FAMS_ALGORITHM
    )

    logger.info(f"FAMS Access Token created: email={email}, name={name}, dept={dept_name}")
    return token


def create_fams_refresh_token(email: str) -> str:
    """
    FAMS Refresh Token 생성.

    Args:
        email: 사용자 이메일

    Returns:
        JWT Refresh Token
    """
    now = datetime.utcnow()
    expire = now + timedelta(days=FAMS_REFRESH_TOKEN_EXPIRE_DAYS)

    payload = {
        'email': email,
        'iat': now,
        'exp': expire,
        'type': 'refresh'
    }

    token = jwt.encode(
        payload,
        FAMS_SECRET,
        algorithm=FAMS_ALGORITHM
    )

    logger.info(f"FAMS Refresh Token created: email={email}")
    return token


def verify_fams_token(token: str) -> Dict[str, Any]:
    """
    FAMS 토큰 검증 및 페이로드 추출.

    Args:
        token: FAMS JWT 토큰

    Returns:
        토큰 페이로드

    Raises:
        jwt.InvalidTokenError: 토큰 검증 실패
    """
    try:
        payload = jwt.decode(
            token,
            FAMS_SECRET,
            algorithms=[FAMS_ALGORITHM]
        )
        return payload

    except jwt.ExpiredSignatureError:
        logger.error("FAMS token expired")
        raise
    except jwt.InvalidTokenError as e:
        logger.error(f"Invalid FAMS token: {e}")
        raise


def get_current_user_email(token: Optional[str]) -> Optional[str]:
    """
    토큰에서 사용자 이메일 추출.

    Args:
        token: FAMS JWT 토큰

    Returns:
        사용자 이메일 (토큰 없거나 검증 실패 시 None)
    """
    if not token:
        return None

    try:
        payload = verify_fams_token(token)
        return payload.get('email')
    except jwt.InvalidTokenError:
        return None
