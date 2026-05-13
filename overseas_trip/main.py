"""
해외출장 비용 자동화 FastAPI 앱.

실행:
  cd overseas_trip
  uvicorn overseas_trip.main:app --host 0.0.0.0 --port 9090 --reload

접속: http://localhost:9090
"""

import logging
import threading
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from overseas_trip.automation import run_automation
from overseas_trip.db import get_db, init_db
from overseas_trip.scheduler import start_scheduler, stop_scheduler
from overseas_trip import crud

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 워크쓰루 프로필 사진 캐시 (bytes, content-type)
_user_photo_cache: Optional[bytes] = None
_user_photo_content_type: str = "image/jpeg"


def _fetch_user_photo_bg() -> None:
    """백그라운드에서 LINE WORKS API로 프로필 사진을 가져와 캐시에 저장"""
    global _user_photo_cache, _user_photo_content_type
    try:
        from overseas_trip.works_photo import fetch_photo_bytes
        data = fetch_photo_bytes()
        if data:
            if data[:4] == b'\x89PNG':
                _user_photo_content_type = "image/png"
            _user_photo_cache = data
            logger.info("LINE WORKS 프로필 사진 캐시 완료 (%d bytes)", len(data))
        else:
            logger.warning("LINE WORKS 프로필 사진 없음 - 텍스트 아바타 사용")
    except Exception as e:
        logger.warning("프로필 사진 취득 실패: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    # 프로필 사진은 비동기로 백그라운드에서 가져옴 (앱 시작을 막지 않음)
    t = threading.Thread(target=_fetch_user_photo_bg, daemon=True)
    t.start()
    yield
    stop_scheduler()


app = FastAPI(title="해외출장 비용 자동화", lifespan=lifespan)

app.mount(
    "/static",
    StaticFiles(directory=os.path.join(BASE_DIR, "static")),
    name="static",
)
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


# ─────────────────────────────────────────────
# 웹 UI 라우트
# ─────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    q: str = "",
    start_from: str = "",
    start_to: str = "",
    db: Session = Depends(get_db),
):
    rows = crud.search_all(db, q=q, start_from=start_from, start_to=start_to)
    total_airfare = sum((float(r.airfare) for r in rows if r.airfare), 0.0)
    ticketed = sum(1 for r in rows if r.ticketing_completed == "발권완료")
    cancelled = sum(1 for r in rows if r.cancel_change == "취소")
    return templates.TemplateResponse("index.html", {
        "request": request,
        "rows": rows,
        "filters": {"q": q, "start_from": start_from, "start_to": start_to},
        "stats": {
            "total_count": len(rows),
            "total_airfare": total_airfare,
            "ticketed": ticketed,
            "cancelled": cancelled,
        },
    })


@app.get("/row/new", response_class=HTMLResponse)
def new_row_form(request: Request):
    return templates.TemplateResponse("edit.html", {
        "request": request,
        "row": None,
        "action": "/row/new",
    })


@app.post("/row/new")
def create_row(
    request: Request,
    department: Optional[str] = Form(None),
    position: Optional[str] = Form(None),
    name: Optional[str] = Form(None),
    country: Optional[str] = Form(None),
    region: Optional[str] = Form(None),
    start_date: Optional[str] = Form(None),
    end_date: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    trip_purpose: Optional[str] = Form(None),
    application_doc_no: Optional[str] = Form(None),
    report_doc_no: Optional[str] = Form(None),
    doc_status: Optional[str] = Form(None),
    daily_allowance_date: Optional[str] = Form(None),
    daily_allowance: Optional[str] = Form(None),
    report_approval_date: Optional[str] = Form(None),
    personal_expense: Optional[str] = Form(None),
    refund_amount: Optional[str] = Form(None),
    cancel_change: Optional[str] = Form(None),
    violation_reason: Optional[str] = Form(None),
    memo: Optional[str] = Form(None),
    airfare: Optional[str] = Form(None),
    agency_fee: Optional[str] = Form(None),
    airfare_payment_date: Optional[str] = Form(None),
    payment_card: Optional[str] = Form(None),
    purchase_place: Optional[str] = Form(None),
    airline: Optional[str] = Form(None),
    booking_class: Optional[str] = Form(None),
    compliance: Optional[str] = Form(None),
    ticketing_completed: Optional[str] = Form(None),
    accommodation: Optional[str] = Form(None),
    transportation: Optional[str] = Form(None),
    meal_expense: Optional[str] = Form(None),
    other_expense: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    data = _form_to_dict(locals())
    crud.create_row(db, data)
    return RedirectResponse("/", status_code=303)


@app.get("/row/{row_id}/edit", response_class=HTMLResponse)
def edit_row_form(request: Request, row_id: int, db: Session = Depends(get_db)):
    row = crud.get_by_id(db, row_id)
    if not row:
        return HTMLResponse("레코드 없음", status_code=404)
    return templates.TemplateResponse("edit.html", {
        "request": request,
        "row": row,
        "action": f"/row/{row_id}/edit",
    })


@app.post("/row/{row_id}/edit")
def update_row(
    request: Request,
    row_id: int,
    department: Optional[str] = Form(None),
    position: Optional[str] = Form(None),
    name: Optional[str] = Form(None),
    country: Optional[str] = Form(None),
    region: Optional[str] = Form(None),
    start_date: Optional[str] = Form(None),
    end_date: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    trip_purpose: Optional[str] = Form(None),
    application_doc_no: Optional[str] = Form(None),
    report_doc_no: Optional[str] = Form(None),
    doc_status: Optional[str] = Form(None),
    daily_allowance_date: Optional[str] = Form(None),
    daily_allowance: Optional[str] = Form(None),
    report_approval_date: Optional[str] = Form(None),
    personal_expense: Optional[str] = Form(None),
    refund_amount: Optional[str] = Form(None),
    cancel_change: Optional[str] = Form(None),
    violation_reason: Optional[str] = Form(None),
    memo: Optional[str] = Form(None),
    airfare: Optional[str] = Form(None),
    agency_fee: Optional[str] = Form(None),
    airfare_payment_date: Optional[str] = Form(None),
    payment_card: Optional[str] = Form(None),
    purchase_place: Optional[str] = Form(None),
    airline: Optional[str] = Form(None),
    booking_class: Optional[str] = Form(None),
    compliance: Optional[str] = Form(None),
    ticketing_completed: Optional[str] = Form(None),
    accommodation: Optional[str] = Form(None),
    transportation: Optional[str] = Form(None),
    meal_expense: Optional[str] = Form(None),
    other_expense: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    data = _form_to_dict(locals())
    crud.update_row(db, row_id, data)
    return RedirectResponse("/", status_code=303)


@app.post("/row/{row_id}/cancel")
def cancel_row(row_id: int, db: Session = Depends(get_db)):
    """취소 버튼: 해외출장보고서 + 취소/변경 컬럼을 '취소'로 업데이트"""
    ok = crud.cancel_row(db, row_id)
    if not ok:
        return JSONResponse({"success": False, "message": "레코드 없음"}, status_code=404)
    return JSONResponse({"success": True})


# ─────────────────────────────────────────────
# 자동화 수동 트리거 API
# ─────────────────────────────────────────────

_automation_lock = threading.Lock()
_automation_running = False


@app.post("/api/trigger")
def trigger_automation():
    """자동화 수동 실행 (테스트용). 이미 실행 중이면 409 반환."""
    global _automation_running
    if _automation_running:
        return JSONResponse({"success": False, "message": "이미 자동화 실행 중입니다."}, status_code=409)

    def _run():
        global _automation_running
        with _automation_lock:
            _automation_running = True
            try:
                result = run_automation()
                logger.info("수동 트리거 완료: %s", result)
            except Exception as e:
                logger.error("수동 트리거 오류: %s", e)
            finally:
                _automation_running = False

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return JSONResponse({"success": True, "message": "자동화 시작됨. 로그를 확인하세요."})


@app.get("/api/status")
def get_status():
    """현재 자동화 실행 상태 확인"""
    return JSONResponse({"running": _automation_running})


@app.get("/api/user-photo")
def get_user_photo():
    """워크쓰루 프로필 사진 프록시. 캐시 없으면 204 반환"""
    if _user_photo_cache:
        return Response(
            content=_user_photo_cache,
            media_type=_user_photo_content_type,
            headers={"Cache-Control": "max-age=3600"},
        )
    return Response(status_code=204)


@app.post("/api/refresh-photo")
def refresh_user_photo():
    """프로필 사진 강제 재취득"""
    t = threading.Thread(target=_fetch_user_photo_bg, daemon=True)
    t.start()
    return JSONResponse({"success": True, "message": "사진 재취득 시작됨"})


# ─────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────

_DATE_FIELDS = {"start_date", "end_date", "daily_allowance_date", "airfare_payment_date", "report_approval_date"}
_DECIMAL_FIELDS = {
    "daily_allowance", "personal_expense", "refund_amount",
    "airfare", "agency_fee", "accommodation", "transportation", "meal_expense", "other_expense",
}
_EXCLUDE = {"request", "row_id", "db"}


def _form_to_dict(local_vars: dict) -> dict:
    """폼 값을 DB 저장용 dict로 변환 (빈 문자열 → None, 날짜/금액 타입 변환)"""
    from datetime import date as date_type
    from datetime import datetime

    result = {}
    for k, v in local_vars.items():
        if k in _EXCLUDE:
            continue
        if isinstance(v, str):
            v = v.strip() or None
        if v is None:
            result[k] = None
            continue
        if k in _DATE_FIELDS and isinstance(v, str):
            for fmt in ("%Y-%m-%d", "%Y.%m.%d"):
                try:
                    result[k] = datetime.strptime(v, fmt).date()
                    break
                except ValueError:
                    continue
            else:
                result[k] = None
        elif k in _DECIMAL_FIELDS and isinstance(v, str):
            import re
            cleaned = re.sub(r"[^\d.]", "", v)
            result[k] = float(cleaned) if cleaned else None
        else:
            result[k] = v
    return result
