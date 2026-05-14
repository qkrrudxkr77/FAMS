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
from urllib.parse import urlencode

from fastapi import FastAPI, Depends, Form, Request, HTTPException, status, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from overseas_trip.automation import run_automation
from overseas_trip.db import get_db, init_db
from overseas_trip.scheduler import start_scheduler, stop_scheduler
from overseas_trip import crud
from overseas_trip.auth import validate_workthrough_token, create_fams_access_token, create_fams_refresh_token, verify_fams_token, get_current_user_email
from overseas_trip.excel_parser import parse_repayment_schedule
import jwt
from datetime import date, datetime as dt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _unauthorized_html(title: str, message: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>인증 필요 — FAMS</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;700&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Noto Sans KR', -apple-system, sans-serif;
      background: #0f1729;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .card {{
      background: #ffffff;
      width: 400px;
      padding: 48px 52px;
      text-align: center;
    }}
    .icon-wrap {{
      width: 56px;
      height: 56px;
      background: #eef4ff;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      margin: 0 auto 24px;
    }}
    .accent {{
      width: 36px;
      height: 3px;
      background: #1c69d4;
      margin: 0 auto 28px;
    }}
    h1 {{
      font-size: 20px;
      font-weight: 700;
      color: #1a1a1a;
      margin-bottom: 12px;
      letter-spacing: -0.01em;
    }}
    p {{
      font-size: 14px;
      font-weight: 300;
      color: #6b6b6b;
      line-height: 1.6;
    }}
    .badge {{
      display: inline-block;
      margin-top: 32px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 1.5px;
      text-transform: uppercase;
      color: #9a9a9a;
    }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon-wrap">
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#1c69d4" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
      </svg>
    </div>
    <div class="accent"></div>
    <h1>{title}</h1>
    <p>{message}</p>
    <div class="badge">FAMS · 재무회계관리시스템</div>
  </div>
</body>
</html>"""

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
# 인증 미들웨어 (세션 쿠키 기반)
# ─────────────────────────────────────────────

_authenticated_users = {}  # email -> token 매핑 (간단한 인메모리 세션)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """
    모든 요청에서 인증 확인.
    - /api/token/login, /static/* 은 인증 불필요
    - 나머지는 session_token 쿠키 또는 Authorization 헤더 필요
    """
    path = request.url.path

    # 인증이 필요 없는 경로
    if path.startswith("/static/") or path == "/api/token/login" or path == "/favicon.ico":
        return await call_next(request)

    # 쿠키에서 session_token 추출
    session_token = request.cookies.get("session_token")

    if not session_token:
        # Authorization 헤더에서 Bearer 토큰 확인
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            session_token = auth_header[7:]

    if not session_token:
        logger.warning(f"Unauthorized access attempt: {path}")
        return HTMLResponse(content=_unauthorized_html("인증이 필요합니다", "워크쓰루에서 FAMS 버튼을 통해 접근해주세요."), status_code=401)

    # 토큰 검증
    try:
        payload = verify_fams_token(session_token)
        request.state.user_email = payload.get("email")
        request.state.user_name = payload.get("name")
    except jwt.InvalidTokenError:
        logger.warning(f"Invalid token: {path}")
        response = HTMLResponse(content=_unauthorized_html("세션이 만료되었습니다", "워크쓰루에서 FAMS 버튼을 통해 다시 접근해주세요."), status_code=401)
        response.delete_cookie("session_token")
        return response

    response = await call_next(request)
    return response


def get_current_user(request: Request) -> str:
    """
    현재 인증된 사용자의 이메일 반환.
    미들웨어에서 검증을 거친 후 호출됨.
    """
    user_email = getattr(request.state, "user_email", None)
    if not user_email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return user_email


# ─────────────────────────────────────────────
# 인증 라우트
# ─────────────────────────────────────────────

@app.get("/api/token/login")
async def token_login(token: str):
    """
    Workthrough SSO 토큰으로 FAMS 세션 생성.

    흐름:
    1. Workthrough에서 사용자를 이 URL로 리다이렉트 (token 파라미터 포함)
    2. 토큰 검증
    3. session_token 쿠키를 RedirectResponse에 직접 설정
    4. / 으로 리다이렉트
    """
    try:
        # Workthrough 토큰에서 ? 이후 제거 (쿼리 파라미터 정리)
        if '?' in token:
            token = token.split('?')[0]

        # Workthrough 토큰 검증
        wt_payload = validate_workthrough_token(token)

        # FAMS Access Token 생성
        access_token = create_fams_access_token(email=wt_payload.email)

        # RedirectResponse에 직접 쿠키 설정 (response 파라미터에 설정하면 쿠키가 사라짐)
        redirect = RedirectResponse(url="/", status_code=302)
        redirect.set_cookie(
            key="session_token",
            value=access_token,
            max_age=24 * 3600,  # 24시간
            httponly=False,
            # secure=True,  # HTTPS only (production에서만)
            samesite="lax"
        )

        logger.info(f"User logged in: {wt_payload.email}")
        return redirect

    except jwt.InvalidTokenError as e:
        logger.error(f"Token login failed: {e}")
        return HTMLResponse(
            content="<h2>토큰 인증 실패</h2><p>유효하지 않거나 만료된 토큰입니다. 워크쓰루에서 다시 접근해주세요.</p>",
            status_code=401
        )
    except Exception as e:
        logger.error(f"Login error: {e}")
        return HTMLResponse(
            content=f"<h2>로그인 오류</h2><p>{str(e)}</p>",
            status_code=400
        )


@app.get("/api/logout")
async def logout():
    """로그아웃 (쿠키 삭제)"""
    response = HTMLResponse(
        content="<h2>로그아웃 완료</h2><p>워크쓰루에서 FAMS 버튼을 통해 다시 접근해주세요.</p>",
        status_code=200
    )
    response.delete_cookie("session_token")
    return response


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


@app.post("/api/row")
async def create_row_json(
    request: Request,
    db: Session = Depends(get_db),
):
    """신규 행 추가 (JSON API - 테이블 내 인라인 추가용)"""
    body = await request.json()
    data = _form_to_dict(body)
    row = crud.create_row(db, data)
    # 모든 컬럼을 dict로 변환 (datetime은 문자열로)
    from datetime import date, datetime
    row_dict = {}
    for col in row.__table__.columns:
        val = getattr(row, col.name)
        if isinstance(val, (date, datetime)):
            row_dict[col.name] = val.isoformat() if val else None
        else:
            row_dict[col.name] = val
    return JSONResponse({
        "success": True,
        "id": row.id,
        "row": row_dict
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


@app.patch("/api/row/{row_id}")
async def patch_row_inline(row_id: int, request: Request, db: Session = Depends(get_db)):
    """인라인 편집 저장 (JSON PATCH)"""
    body = await request.json()
    data = _form_to_dict(body)
    ok = crud.update_row(db, row_id, data)
    return JSONResponse({"success": ok})


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
# 상환/수령 스케줄 (차입금 상환 스케줄)
# ─────────────────────────────────────────────

@app.get("/repayment-schedule", response_class=HTMLResponse)
def repayment_schedule_page(request: Request, db: Session = Depends(get_db)):
    """상환/수령 스케줄 페이지 (목록 + 캘린더)"""
    today = dt.now()
    loan_names = crud.get_distinct_loan_names(db)
    return templates.TemplateResponse("repayment_schedule.html", {
        "request": request,
        "today_year": today.year,
        "today_month": today.month,
        "loan_names": loan_names,
    })


@app.post("/api/repayment-schedule/upload")
async def upload_repayment_schedule(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """신차입금현황 엑셀 업로드 → 상환스케줄 탭 파싱 → 전체 교체"""
    try:
        file_bytes = await file.read()
        parsed = parse_repayment_schedule(file_bytes, password="7")
        if not parsed:
            return JSONResponse({"success": False, "message": "엑셀에서 회차 데이터를 찾지 못했습니다."}, status_code=400)
        count = crud.replace_all_loan_repayments(db, parsed)
        logger.info(f"상환스케줄 업로드 완료: {count}건")
        return JSONResponse({"success": True, "inserted_count": count})
    except Exception as e:
        logger.exception("상환스케줄 업로드 실패")
        return JSONResponse({"success": False, "message": str(e)}, status_code=400)


def _row_to_dict(row) -> dict:
    return {
        "id": row.id,
        "block_index": row.block_index,
        "loan_name": row.loan_name,
        "installment_no": row.installment_no,
        "original_due_date": row.original_due_date.isoformat() if row.original_due_date else None,
        "adjusted_due_date": row.adjusted_due_date.isoformat() if row.adjusted_due_date else None,
        "principal": float(row.principal) if row.principal is not None else None,
        "interest": float(row.interest) if row.interest is not None else None,
        "total_payment": float(row.total_payment) if row.total_payment is not None else None,
        "remaining_principal": float(row.remaining_principal) if row.remaining_principal is not None else None,
    }


@app.get("/api/repayment-schedule")
def list_repayment_schedule(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    loan_name: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """목록 뷰용 JSON 리스트 (기간/대출명 필터)"""
    def _parse_date(s: Optional[str]) -> Optional[date]:
        if not s:
            return None
        try:
            return dt.strptime(s, "%Y-%m-%d").date()
        except ValueError:
            return None

    rows = crud.list_loan_repayments(
        db,
        from_date=_parse_date(from_date),
        to_date=_parse_date(to_date),
        loan_name=loan_name or None,
    )
    return JSONResponse({"success": True, "items": [_row_to_dict(r) for r in rows]})


@app.get("/api/repayment-schedule/calendar")
def calendar_repayment_schedule(year: int, month: int, db: Session = Depends(get_db)):
    """캘린더 뷰용: 날짜별 그룹 JSON"""
    rows = crud.get_loan_repayments_by_month(db, year, month)
    by_date: dict[str, list[dict]] = {}
    for r in rows:
        key = r.adjusted_due_date.isoformat()
        by_date.setdefault(key, []).append(_row_to_dict(r))
    return JSONResponse({"success": True, "year": year, "month": month, "by_date": by_date})


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
