# -*- coding: utf-8 -*-
"""
해외출장 자동화 오케스트레이션.

실행 흐름:
  1. 워크쓰루 최근 7일 문서 조회
  2. 해외출장 신청서 → DB insert + BTMS 항공 처리
  3. 해외출장 보고서 → 기존 레코드 update
"""

import logging
from datetime import date

from overseas_trip import crud
from overseas_trip.db import SessionLocal
from overseas_trip.holiday_util import get_last_business_day_of_next_month
from overseas_trip.scraper_btms import run_btms_for_travelers
from overseas_trip.scraper_workthru import run_workthru_scrape

logger = logging.getLogger(__name__)


def run_automation() -> dict:
    """
    전체 자동화 프로세스 실행.
    반환: {"success": int, "skipped": int, "errors": int, "messages": list}
    """
    stats = {"success": 0, "skipped": 0, "errors": 0, "messages": []}

    logger.info("=== 해외출장 자동화 시작 ===")

    # Step 1: 워크쓰루 스크래핑
    try:
        docs = run_workthru_scrape()
    except Exception as e:
        msg = f"워크쓰루 스크래핑 실패: {e}"
        logger.error(msg)
        stats["errors"] += 1
        stats["messages"].append(msg)
        return stats

    applications = [d for d in docs if d["type"] == "application"]
    reports = [d for d in docs if d["type"] == "report"]
    logger.info("조회 결과 - 신청서: %d건, 보고서: %d건", len(applications), len(reports))

    # Step 2: 해외출장 신청서 처리
    for doc in applications:
        try:
            _process_application(doc, stats)
        except Exception as e:
            msg = f"신청서 처리 중 오류: {e}"
            logger.error(msg)
            stats["errors"] += 1
            stats["messages"].append(msg)

    # Step 3: 해외출장 보고서 처리
    for doc in reports:
        try:
            _process_report(doc, stats)
        except Exception as e:
            msg = f"보고서 처리 중 오류: {e}"
            logger.error(msg)
            stats["errors"] += 1
            stats["messages"].append(msg)

    logger.info("=== 자동화 완료 - 성공: %d, 스킵: %d, 오류: %d ===",
                stats["success"], stats["skipped"], stats["errors"])
    return stats


def _process_application(doc: dict, stats: dict) -> None:
    """해외출장 신청서 단건 처리"""
    data = doc["data"]
    doc_status = doc["doc_status"]
    doc_no = data.get("doc_no", "")
    travelers = data.get("travelers", [])

    if not travelers:
        logger.warning("신청서에 출장자 정보 없음 (doc_no=%s)", doc_no)
        stats["skipped"] += 1
        return

    db = SessionLocal()
    try:
        # 출장자별 처리
        btms_inputs = []
        for traveler in travelers:
            name = traveler.get("name", "")

            # 중복 체크: 해외출장품의서 문서번호 + 성명 기준
            existing = crud.get_by_doc_no_and_name(db, doc_no, name)
            if existing:
                logger.info("이미 처리된 레코드 스킵 (doc_no=%s, name=%s)", doc_no, name)
                stats["skipped"] += 1

                # 항공료 이미 수집 완료 → BTMS 스킵
                if existing.ticketing_completed == "발권완료" or existing.airfare is not None:
                    logger.info("항공료 이미 수집완료 - BTMS 스킵 (doc_no=%s, name=%s)", doc_no, name)
                    continue

                # 아직 발권 전 → BTMS 재확인 (발권됐을 수 있음)
                logger.info("항공료 미수집 - BTMS 재확인 진행 (doc_no=%s, name=%s)", doc_no, name)
                btms_inputs.append({
                    "name": name,
                    "start_date": traveler.get("start_date"),
                    "end_date": traveler.get("end_date"),
                    "doc_status": doc_status,
                    "already_exists": True,
                })
                continue

            # DB Insert
            insert_data = {
                "department": traveler.get("department"),
                "position": traveler.get("position"),
                "name": name,
                "country": traveler.get("country"),
                "region": traveler.get("region"),
                "start_date": traveler.get("start_date"),
                "end_date": traveler.get("end_date"),
                "title": data.get("doc_title"),
                "trip_purpose": data.get("trip_purpose"),
                "application_doc_no": doc_no,
                "doc_status": doc_status,
            }
            crud.insert_application(db, insert_data)
            logger.info("신청서 Insert 완료 (doc_no=%s, name=%s)", doc_no, name)
            stats["success"] += 1

            btms_inputs.append({
                "name": name,
                "start_date": traveler.get("start_date"),
                "end_date": traveler.get("end_date"),
                "doc_status": doc_status,
                "already_exists": False,
            })

        # BTMS 처리 (start_date/end_date 있는 것만)
        valid_btms = [b for b in btms_inputs if b.get("start_date") and b.get("end_date")]
        if not valid_btms:
            return

        btms_results = run_btms_for_travelers(valid_btms)

        for btms_res in btms_results:
            name = btms_res.get("name", "")

            # BTMS 매칭 안 됨 → air_status = "예약안함"
            if not btms_res.get("found"):
                msg = f"BTMS 미매칭 → 예약안함 (doc_no={doc_no}, name={name})"
                logger.info(msg)
                stats["messages"].append(msg)
                crud.update_btms_ticketing(db, doc_no, name, {"air_status": "예약안함"})
                continue

            air_status = btms_res.get("air_status", "")

            if air_status == "발권완료":
                ticketing = btms_res.get("ticketing_data", {})
                update_data = {
                    "airfare": ticketing.get("airfare"),
                    "agency_fee": ticketing.get("agency_fee"),
                    "airfare_payment_date": ticketing.get("airfare_payment_date"),
                    "payment_card": "삼성(2894)",
                    "purchase_place": "레드캡투어",
                    "airline": ticketing.get("airline"),
                    "booking_class": ticketing.get("booking_class"),
                    "compliance": btms_res.get("compliance"),
                    "ticketing_completed": "발권완료",
                    "air_status": "발권완료",
                }
                ok = crud.update_btms_ticketing(db, doc_no, name, update_data)
                if ok:
                    logger.info("발권완료 Update 완료 (doc_no=%s, name=%s)", doc_no, name)
                    stats["success"] += 1
                else:
                    logger.warning("발권완료 Update 대상 레코드 없음 (doc_no=%s, name=%s)", doc_no, name)
            else:
                # 예약완료 / 발권요청 등 → air_status만 업데이트
                crud.update_btms_ticketing(db, doc_no, name, {"air_status": air_status})
                logger.info("air_status Update (doc_no=%s, name=%s, status=%s)", doc_no, name, air_status)

    finally:
        db.close()


def _process_report(doc: dict, stats: dict) -> None:
    """해외출장 보고서 단건 처리"""
    data = doc["data"]
    doc_no = data.get("doc_no", "")
    doc_date = data.get("doc_date")
    travelers = data.get("travelers", [])

    if not travelers:
        logger.warning("보고서에 출장자 정보 없음 (doc_no=%s)", doc_no)
        stats["skipped"] += 1
        return

    db = SessionLocal()
    try:
        for traveler in travelers:
            name = traveler.get("name", "")
            department = traveler.get("department", "")
            position = traveler.get("position", "")
            start_date = traveler.get("start_date")
            end_date = traveler.get("end_date")

            if not all([name, department, start_date, end_date]):
                logger.warning("보고서 매칭 정보 불충분 (doc_no=%s, name=%s)", doc_no, name)
                stats["skipped"] += 1
                continue

            # 기존 레코드 탐색
            row = crud.find_for_report(db, department, name, position, start_date, end_date)
            if not row:
                msg = f"보고서 매칭 레코드 없음 (name={name}, {start_date}~{end_date})"
                logger.warning(msg)
                stats["messages"].append(msg)
                stats["skipped"] += 1
                continue

            # 이미 보고서 처리된 레코드 스킵
            if row.report_doc_no and row.report_doc_no not in ("", None):
                logger.info("보고서 이미 처리된 레코드 스킵 (id=%d, name=%s)", row.id, name)
                stats["skipped"] += 1
                continue

            # 일비지급일 계산 (기안일 익월 말일 기준 영업일)
            daily_allowance_date = None
            if doc_date:
                daily_allowance_date = get_last_business_day_of_next_month(doc_date)

            update_data = {
                "accommodation": traveler.get("accommodation"),
                "transportation": traveler.get("transportation"),
                "meal_expense": traveler.get("meal_expense"),
                "other_expense": traveler.get("other_expense"),
                "daily_allowance": traveler.get("daily_allowance"),
                "report_doc_no": doc_no,
                "daily_allowance_date": daily_allowance_date,
            }
            crud.update_report(db, row.id, update_data)
            logger.info("보고서 Update 완료 (id=%d, doc_no=%s, name=%s)", row.id, doc_no, name)
            stats["success"] += 1

    finally:
        db.close()
