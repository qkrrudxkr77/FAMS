from fastapi import APIRouter, Depends
from fastapi.requests import Request
from fastapi.templating import Jinja2Templates

from app.auth.schemas import ApiResponse, LoginUser
from app.core.dependencies import get_current_user

router = APIRouter(tags=["overseas_trip"])
templates = Jinja2Templates(directory="templates")


@router.get("/overseas-trip")
async def page(request: Request):
    return templates.TemplateResponse(
        "overseas_trip/index.html",
        {"request": request, "page_title": "해외출장관리 — FAMS"},
    )


@router.get("/api/overseas-trip", response_model=ApiResponse)
async def api_stub(current_user: LoginUser = Depends(get_current_user)):
    """해외출장관리 API — 추후 구현 예정"""
    return ApiResponse.ok(data=[], message="해외출장관리 기능은 개발 예정입니다.")
