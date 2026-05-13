from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.schemas import LoginUser
from app.core.security import decode_fams_token

_bearer = HTTPBearer(auto_error=False)


def _build_login_user(payload: dict) -> LoginUser:
    return LoginUser(
        email=payload.get("sub", ""),
        name=payload.get("name", ""),
        dept_name=payload.get("deptName", ""),
        position_name=payload.get("positionName", ""),
        level_name=payload.get("levelName", ""),
        dept_id=payload.get("deptId"),
    )


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> LoginUser:
    """JwtFilter 대응 — Bearer 헤더 또는 access_token 쿠키에서 토큰 추출"""
    token = None
    if credentials:
        token = credentials.credentials
    if not token:
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="인증이 필요합니다.")

    try:
        payload = decode_fams_token(token)
        return _build_login_user(payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


