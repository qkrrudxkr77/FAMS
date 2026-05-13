from app.core import redis_client
from app.core.hr_db import find_member_by_email
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_fams_token,
    validate_workthrough_token,
)


def _build_claims(email: str, name: str = "", dept_name: str = "", position_name: str = "",
                  level_name: str = "", dept_id: str | None = None) -> dict:
    return {
        "sub": email,
        "name": name,
        "deptName": dept_name,
        "positionName": position_name,
        "levelName": level_name,
        "deptId": dept_id,
    }


async def login(workthrough_token: str) -> tuple[str, str]:
    """
    Workthrough SSO 토큰 검증 → FAMS 토큰 발급
    반환: (access_token, refresh_token)
    """
    payload = validate_workthrough_token(workthrough_token)

    email: str = payload.get("email") or payload.get("sub") or ""
    if not email:
        raise ValueError("Workthrough 토큰에 email 정보가 없습니다.")
    email = email.strip().lower()

    # HR DB에서 사용자 정보 조회 (repo-hub와 동일)
    member = await find_member_by_email(email)
    name = member.name if member else ""
    dept_name = member.dept_name if member else ""
    position_name = member.position_name if member else ""
    level_name = member.level_name if member else ""
    dept_id = member.dept_id if member else None

    claims = _build_claims(email, name, dept_name, position_name, level_name, dept_id)
    access_token = create_access_token(claims)
    refresh_token = create_refresh_token(claims)

    await redis_client.set_refresh_token(email, refresh_token)

    return access_token, refresh_token


async def reissue(refresh_token: str) -> tuple[str, str]:
    """리프레시 토큰으로 새 토큰 쌍 발급"""
    try:
        payload = decode_fams_token(refresh_token)
    except ValueError as e:
        raise ValueError(f"리프레시 토큰 검증 실패: {e}")

    email: str = payload.get("sub", "")
    if not email:
        raise ValueError("토큰에 email 정보가 없습니다.")

    stored = await redis_client.get_refresh_token(email)
    prev_stored = await redis_client.get_prev_refresh_token(email)

    if refresh_token not in (stored, prev_stored):
        raise ValueError("유효하지 않은 리프레시 토큰입니다.")

    claims = _build_claims(
        email=email,
        name=payload.get("name", ""),
        dept_name=payload.get("deptName", ""),
        position_name=payload.get("positionName", ""),
        level_name=payload.get("levelName", ""),
        dept_id=payload.get("deptId"),
    )

    new_access = create_access_token(claims)
    new_refresh = create_refresh_token(claims)

    # 로테이션: 기존 토큰을 1분 유예로 보관
    await redis_client.set_prev_refresh_token(email, refresh_token)
    await redis_client.set_refresh_token(email, new_refresh)

    return new_access, new_refresh


async def logout(email: str) -> None:
    await redis_client.delete_refresh_token(email)
