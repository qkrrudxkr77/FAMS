from urllib.parse import quote

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from app.auth import service
from app.auth.schemas import ApiResponse, LoginUser, TokenData
from app.core.dependencies import get_current_user

router = APIRouter(tags=["auth"])


@router.get("/api/token/login")
async def login(token: str, response: Response):
    """
    Workthrough SSO JWT 검증 후 FAMS 토큰 발급.
    GET /api/token/login?token=<WORKTHROUGH_JWT>
    """
    # Workthrough URL에 붙는 extra query param 제거 (?uuId=... 등)
    clean_token = token.split("?")[0].strip()

    try:
        access_token, refresh_token = await service.login(clean_token)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    redirect = RedirectResponse(url=f"/dashboard?at={quote(access_token)}", status_code=302)
    redirect.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        max_age=14 * 24 * 60 * 60,
        path="/",
        samesite="lax",
    )
    return redirect


@router.get("/api/token/reissue")
async def reissue(refresh_token: str | None = Cookie(default=None)):
    """
    리프레시 토큰 쿠키로 새 Access/Refresh 토큰 발급.
    GET /api/token/reissue
    """
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="리프레시 토큰이 없습니다.")

    try:
        new_access, new_refresh = await service.reissue(refresh_token)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    response = Response(
        content=ApiResponse.ok(TokenData(access_token=new_access)).model_dump_json(),
        media_type="application/json",
    )
    response.set_cookie(
        key="refresh_token",
        value=new_refresh,
        httponly=True,
        max_age=14 * 24 * 60 * 60,
        path="/",
        samesite="lax",
    )
    return response


@router.get("/api/logout", response_model=ApiResponse)
async def logout(
    response: Response,
    current_user: LoginUser = Depends(get_current_user),
):
    """GET /api/logout — repo-hub와 동일한 경로"""
    await service.logout(current_user.email)
    response.delete_cookie("refresh_token", path="/")
    return ApiResponse.ok(message="로그아웃 되었습니다.")
