from datetime import date
from typing import Optional
from sqlalchemy.orm import Session
from overseas_trip.models import OverseasTripExpense


def get_by_doc_no_and_name(db: Session, application_doc_no: str, name: str) -> Optional[OverseasTripExpense]:
    """해외출장품의서 문서번호 + 성명 기준으로 레코드 반환 (없으면 None)"""
    return db.query(OverseasTripExpense).filter(
        OverseasTripExpense.application_doc_no == application_doc_no,
        OverseasTripExpense.name == name,
    ).first()


def exists_by_doc_no_and_name(db: Session, application_doc_no: str, name: str) -> bool:
    """해외출장품의서 문서번호 + 성명 기준으로 중복 레코드 존재 여부 확인"""
    return get_by_doc_no_and_name(db, application_doc_no, name) is not None


def insert_application(db: Session, data: dict) -> OverseasTripExpense:
    """해외출장 신청서 기본 정보 Insert"""
    row = OverseasTripExpense(**data)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_btms_ticketing(db: Session, application_doc_no: str, name: str, data: dict) -> bool:
    """BTMS 발권완료 팝업 데이터로 해당 레코드 Update"""
    row = db.query(OverseasTripExpense).filter(
        OverseasTripExpense.application_doc_no == application_doc_no,
        OverseasTripExpense.name == name,
    ).first()
    if not row:
        return False
    for key, value in data.items():
        setattr(row, key, value)
    db.commit()
    return True


def find_for_report(
    db: Session,
    department: str,
    name: str,
    position: str,
    start_date: date,
    end_date: date,
) -> Optional[OverseasTripExpense]:
    """해외출장 보고서 매칭: 부서+성명+직위+시작일+종료일 기준으로 레코드 탐색"""
    return db.query(OverseasTripExpense).filter(
        OverseasTripExpense.department == department,
        OverseasTripExpense.name == name,
        OverseasTripExpense.position == position,
        OverseasTripExpense.start_date == start_date,
        OverseasTripExpense.end_date == end_date,
    ).first()


def update_report(db: Session, row_id: int, data: dict) -> bool:
    """해외출장 보고서 데이터로 해당 레코드 Update"""
    row = db.query(OverseasTripExpense).filter(OverseasTripExpense.id == row_id).first()
    if not row:
        return False
    for key, value in data.items():
        setattr(row, key, value)
    db.commit()
    return True


def get_all(db: Session, name: str = "", department: str = "", start_from: str = "", start_to: str = "") -> list:
    """전체 레코드 조회 (검색 필터 지원)"""
    q = db.query(OverseasTripExpense)
    if name:
        q = q.filter(OverseasTripExpense.name.like(f"%{name}%"))
    if department:
        q = q.filter(OverseasTripExpense.department.like(f"%{department}%"))
    if start_from:
        q = q.filter(OverseasTripExpense.start_date >= start_from)
    if start_to:
        q = q.filter(OverseasTripExpense.start_date <= start_to)
    return q.order_by(OverseasTripExpense.id.desc()).all()


def search_all(db: Session, q: str = "", start_from: str = "", start_to: str = "") -> list:
    """통합 검색: 부서/성명/국가/지역 어디든 매칭"""
    from sqlalchemy import or_
    query = db.query(OverseasTripExpense)
    if q:
        kw = f"%{q}%"
        query = query.filter(or_(
            OverseasTripExpense.name.like(kw),
            OverseasTripExpense.department.like(kw),
            OverseasTripExpense.country.like(kw),
            OverseasTripExpense.region.like(kw),
        ))
    if start_from:
        query = query.filter(OverseasTripExpense.start_date >= start_from)
    if start_to:
        query = query.filter(OverseasTripExpense.start_date <= start_to)
    return query.order_by(OverseasTripExpense.id.desc()).all()


def get_by_id(db: Session, row_id: int) -> Optional[OverseasTripExpense]:
    return db.query(OverseasTripExpense).filter(OverseasTripExpense.id == row_id).first()


def create_row(db: Session, data: dict) -> OverseasTripExpense:
    """수동 행 추가"""
    row = OverseasTripExpense(**data)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_row(db: Session, row_id: int, data: dict) -> bool:
    """수동 행 수정 (웹 UI)"""
    row = db.query(OverseasTripExpense).filter(OverseasTripExpense.id == row_id).first()
    if not row:
        return False
    for key, value in data.items():
        setattr(row, key, value)
    db.commit()
    return True


def cancel_row(db: Session, row_id: int) -> bool:
    """취소 버튼: 해외출장보고서 컬럼과 취소/변경 컬럼을 '취소'로 업데이트"""
    row = db.query(OverseasTripExpense).filter(OverseasTripExpense.id == row_id).first()
    if not row:
        return False
    row.report_doc_no = "취소"
    row.cancel_change = "취소"
    db.commit()
    return True
