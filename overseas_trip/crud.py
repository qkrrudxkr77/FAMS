# -*- coding: utf-8 -*-
from datetime import date
from typing import Optional
from sqlalchemy.orm import Session
from overseas_trip.models import OverseasTripExpense, LoanRepayment, FinancialProduct
from overseas_trip.holiday_util import next_business_day


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
    return query.order_by(
        OverseasTripExpense.daily_allowance_date.asc(),
        OverseasTripExpense.start_date.asc(),
        OverseasTripExpense.end_date.asc()
    ).all()


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
    """취소 버튼: 취소/변경 컬럼만 '취소'로 업데이트 (보고서 번호는 유지)"""
    row = db.query(OverseasTripExpense).filter(OverseasTripExpense.id == row_id).first()
    if not row:
        return False
    row.cancel_change = "취소"
    db.commit()
    return True


# ─────────────────────────────────────────────
# 차입금 상환 스케줄 (loan_repayment)
# ─────────────────────────────────────────────

def replace_all_loan_repayments(db: Session, rows: list[dict]) -> int:
    """
    상환스케줄 전체 교체: 기존 데이터 모두 삭제 후 새 행 일괄 INSERT.
    rows[i]에 original_due_date가 있으면 adjusted_due_date를 계산해 함께 저장.
    """
    db.query(LoanRepayment).delete()
    objects = []
    for r in rows:
        orig = r["original_due_date"]
        adjusted = next_business_day(orig)
        objects.append(LoanRepayment(
            block_index=r["block_index"],
            loan_name=r["loan_name"],
            installment_no=r["installment_no"],
            original_due_date=orig,
            adjusted_due_date=adjusted,
            principal=r.get("principal"),
            interest=r.get("interest"),
            total_payment=r.get("total_payment"),
            remaining_principal=r.get("remaining_principal"),
        ))
    db.bulk_save_objects(objects)
    db.commit()
    return len(objects)


def list_loan_repayments(
    db: Session,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    loan_name: Optional[str] = None,
) -> list[LoanRepayment]:
    """기간/대출명 필터로 상환 스케줄 조회 (adjusted_due_date 기준)"""
    q = db.query(LoanRepayment)
    if from_date:
        q = q.filter(LoanRepayment.adjusted_due_date >= from_date)
    if to_date:
        q = q.filter(LoanRepayment.adjusted_due_date <= to_date)
    if loan_name:
        q = q.filter(LoanRepayment.loan_name == loan_name)
    return q.order_by(
        LoanRepayment.adjusted_due_date.asc(),
        LoanRepayment.loan_name.asc(),
        LoanRepayment.installment_no.asc(),
    ).all()


def get_loan_repayments_by_month(db: Session, year: int, month: int) -> list[LoanRepayment]:
    """캘린더용: 해당 월의 adjusted_due_date 기반 전체 항목"""
    from calendar import monthrange
    last_day = monthrange(year, month)[1]
    return list_loan_repayments(
        db,
        from_date=date(year, month, 1),
        to_date=date(year, month, last_day),
    )


def get_distinct_loan_names(db: Session) -> list[str]:
    """필터 드롭다운용: distinct 대출명 (사전순)"""
    rows = db.query(LoanRepayment.loan_name).distinct().order_by(LoanRepayment.loan_name.asc()).all()
    return [r[0] for r in rows]


# ─────────────────────────────────────────────
# 금융상품 만기상환 (financial_product)
# ─────────────────────────────────────────────

def replace_all_financial_products(db: Session, rows: list[dict]) -> int:
    """
    금융상품 전체 교체: 기존 데이터 모두 삭제 후 새 행 일괄 INSERT.
    rows[i]에 original_maturity_date가 있으면 adjusted_maturity_date를 계산해 함께 저장.
    """
    db.query(FinancialProduct).delete()
    objects = []
    for r in rows:
        orig = r["original_maturity_date"]
        adjusted = next_business_day(orig)
        objects.append(FinancialProduct(
            product_code=r["product_code"],
            company_name=r["company_name"],
            product_name=r["product_name"],
            amount=r["amount"],
            original_maturity_date=orig,
            adjusted_maturity_date=adjusted,
            is_active=1,
        ))
    db.bulk_save_objects(objects)
    db.commit()
    return len(objects)


def list_financial_products(
    db: Session,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    company_name: Optional[str] = None,
) -> list[FinancialProduct]:
    """기간/회사명 필터로 금융상품 조회 (adjusted_maturity_date 기준)"""
    q = db.query(FinancialProduct).filter(FinancialProduct.is_active == 1)
    if from_date:
        q = q.filter(FinancialProduct.adjusted_maturity_date >= from_date)
    if to_date:
        q = q.filter(FinancialProduct.adjusted_maturity_date <= to_date)
    if company_name:
        q = q.filter(FinancialProduct.company_name == company_name)
    return q.order_by(
        FinancialProduct.adjusted_maturity_date.asc(),
        FinancialProduct.company_name.asc(),
        FinancialProduct.product_name.asc(),
    ).all()


def get_financial_products_by_month(db: Session, year: int, month: int) -> list[FinancialProduct]:
    """캘린더용: 해당 월의 adjusted_maturity_date 기반 전체 항목"""
    from calendar import monthrange
    last_day = monthrange(year, month)[1]
    return list_financial_products(
        db,
        from_date=date(year, month, 1),
        to_date=date(year, month, last_day),
    )


def get_distinct_company_names(db: Session) -> list[str]:
    """필터 드롭다운용: distinct 회사명 (사전순)"""
    rows = db.query(FinancialProduct.company_name).distinct().filter(
        FinancialProduct.is_active == 1
    ).order_by(FinancialProduct.company_name.asc()).all()
    return [r[0] for r in rows]
