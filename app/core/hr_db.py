"""MySQL HR DB 연동 — repo-hub repohub DB (hr_users / hr_org_units / hr_user_org_units)"""
from dataclasses import dataclass
from typing import Optional

import aiomysql

from app.core.config import settings

_pool: aiomysql.Pool | None = None


async def get_pool() -> aiomysql.Pool:
    global _pool
    if _pool is None:
        _pool = await aiomysql.create_pool(
            host=settings.mysql_host,
            port=settings.mysql_port,
            db=settings.mysql_db,
            user=settings.mysql_user,
            password=settings.mysql_password,
            charset="utf8mb4",
            minsize=1,
            maxsize=5,
            autocommit=True,
        )
    return _pool


@dataclass
class MemberInfo:
    email: str
    name: str
    dept_name: str
    position_name: str
    level_name: str
    dept_id: str | None


async def find_member_by_email(email: str) -> Optional[MemberInfo]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                """
                SELECT u.email,
                       CONCAT(u.last_name, u.first_name) AS name,
                       o.org_unit_name                   AS dept_name,
                       uo.position_name,
                       uo.level_name,
                       uo.org_unit_id                    AS dept_id
                FROM hr_users u
                LEFT JOIN hr_user_org_units uo
                       ON u.user_id = uo.user_id AND uo.is_primary = 1
                LEFT JOIN hr_org_units o
                       ON uo.org_unit_id = o.org_unit_id
                WHERE LOWER(u.email) = LOWER(%s)
                  AND u.is_deleted = 0
                LIMIT 1
                """,
                (email,),
            )
            row = await cur.fetchone()

    if not row:
        return None
    return MemberInfo(
        email=row["email"] or email,
        name=row["name"] or "",
        dept_name=row["dept_name"] or "",
        position_name=row["position_name"] or "",
        level_name=row["level_name"] or "",
        dept_id=row["dept_id"],
    )
