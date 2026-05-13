from fastapi import APIRouter
from fastapi.requests import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="templates")


@router.get("/")
async def root():
    return RedirectResponse(url="/login", status_code=302)


@router.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse(
        "auth/login.html",
        {"request": request, "page_title": "로그인 — FAMS"},
    )


@router.get("/dashboard")
async def dashboard(request: Request):
    return templates.TemplateResponse(
        "dashboard/index.html",
        {"request": request, "page_title": "대시보드 — FAMS"},
    )
