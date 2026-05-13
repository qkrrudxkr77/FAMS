from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.auth.router import router as auth_router
from app.members.router import router as members_router
from app.overseas_trip.router import router as overseas_trip_router
from app.pages.router import router as pages_router

app = FastAPI(
    title="FAMS — 재무회계관리시스템",
    description="Financial Accounting Management System",
    version="0.1.0",
    docs_url="/docs",
    redoc_url=None,
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# 정적 리소스 편의 경로 (base.html에서 /css, /js, /fonts, /images로 참조)
app.mount("/css", StaticFiles(directory="static/css"), name="css")
app.mount("/js", StaticFiles(directory="static/js"), name="js")
app.mount("/fonts", StaticFiles(directory="static/fonts"), name="fonts")
app.mount("/images", StaticFiles(directory="static/images"), name="images")

app.include_router(pages_router)
app.include_router(auth_router)
app.include_router(members_router)
app.include_router(overseas_trip_router)
