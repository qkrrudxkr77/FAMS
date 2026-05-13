from fastapi import APIRouter
from fastapi.responses import Response

from app.core.hr_db import find_member_by_email
from app.core.works_api import fetch_user_photo

router = APIRouter(prefix="/api/members", tags=["members"])


@router.get("/photo")
async def member_photo(email: str):
    """프로필 사진 — email로 user_id 조회 후 WORKS API에서 이미지 반환"""
    member = await find_member_by_email(email)
    if not member or not member.dept_id:
        return Response(status_code=404)

    # hr_users.user_id 직접 조회
    user_id = await _get_user_id_by_email(email)
    if not user_id:
        return Response(status_code=404)

    data = fetch_user_photo(user_id)
    if not data:
        return Response(status_code=404)

    return Response(content=data, media_type="image/jpeg",
                    headers={"Cache-Control": "max-age=3600"})


async def _get_user_id_by_email(email: str) -> str | None:
    from app.core.hr_db import get_pool
    import aiomysql
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT user_id FROM hr_users WHERE LOWER(email) = LOWER(%s) AND is_deleted = 0 LIMIT 1",
                (email,),
            )
            row = await cur.fetchone()
    return row["user_id"] if row else None
