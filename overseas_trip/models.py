# -*- coding: utf-8 -*-
from datetime import datetime
from sqlalchemy import Column, Integer, String, Date, DateTime, Text, DECIMAL, UniqueConstraint, Index
from sqlalchemy.sql import func
from overseas_trip.db import Base


class OverseasTripExpense(Base):
    """해외출장 비용 관리 테이블"""
    __tablename__ = "overseas_trip_expense"
    __table_args__ = (
        UniqueConstraint("application_doc_no", "name", name="uq_doc_name"),
        {"comment": "해외출장 비용 자동화 관리 테이블 - 워크쓰루 신청서/보고서 및 BTMS 데이터 통합"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="PK")
    department = Column(String(100), nullable=True, comment="부서")
    position = Column(String(50), nullable=True, comment="직위")
    name = Column(String(50), nullable=True, comment="성명(출장자)")
    country = Column(String(100), nullable=True, comment="국가")
    region = Column(String(100), nullable=True, comment="지역")
    start_date = Column(Date, nullable=True, comment="출장 시작일")
    end_date = Column(Date, nullable=True, comment="출장 종료일")
    title = Column(String(200), nullable=True, comment="해외출장 신청서 제목")
    trip_purpose = Column(String(10), nullable=True, comment="출장목적 첫 글자 (A/B/C 등)")

    # 문서번호
    application_doc_no = Column(String(100), nullable=True, comment="해외출장품의서 문서번호 (중복 판단 기준)")
    report_doc_no = Column(String(100), nullable=True, comment="해외출장보고서 문서번호 (보고서 처리 후 기입, 취소 시 '취소')")
    doc_status = Column(String(20), nullable=True, comment="워크쓰루 문서상태 (진행중/완료)")

    # 일비
    daily_allowance_date = Column(Date, nullable=True, comment="일비 지급일 (보고서 기안일 익월 말일 기준 영업일)")
    daily_allowance = Column(DECIMAL(15, 2), nullable=True, comment="출장일비 (보고서 정산기준 신청금액)")
    report_approval_date = Column(Date, nullable=True, comment="보고서 승인 완료일 (수동 입력)")

    # 수동 입력 항목
    personal_expense = Column(DECIMAL(15, 2), nullable=True, comment="개인경비 (수동 입력)")
    refund_amount = Column(DECIMAL(15, 2), nullable=True, comment="환불액 (수동 입력)")
    cancel_change = Column(String(200), nullable=True, comment="취소/변경 내역 (수동 입력, 취소 버튼 클릭 시 '취소' 기입)")
    violation_reason = Column(Text, nullable=True, comment="규정위반사유 (수동 입력)")
    memo = Column(Text, nullable=True, comment="비고 (수동 입력)")

    # 항공 정보 - BTMS 발권완료 팝업 추출
    airfare = Column(DECIMAL(15, 2), nullable=True, comment="항공료 (BTMS 요금정보 항공료 합계)")
    agency_fee = Column(DECIMAL(15, 2), nullable=True, comment="여행사수수료 (BTMS 요금정보 취급수수료)")
    airfare_payment_date = Column(Date, nullable=True, comment="항공료결제일 (BTMS 발권정보 발권일)")
    payment_card = Column(String(50), nullable=True, comment="결제카드 (하드코딩: 삼성(2894))")
    purchase_place = Column(String(100), nullable=True, comment="구매처 (하드코딩: 레드캡투어)")
    airline = Column(String(200), nullable=True, comment="항공사 (BTMS 마일리지정보 탑승항공사)")
    booking_class = Column(String(100), nullable=True, comment="예약등급 (BTMS 고객요청여정 클래스, 이코노미/비즈니스 형태)")
    compliance = Column(String(200), nullable=True, comment="규정 (BTMS 출장규정 준수여부 열 값)")
    ticketing_completed = Column(String(20), nullable=True, comment="발권완료 여부 (하드코딩: 발권완료)")
    air_status = Column(String(20), nullable=True, comment="BTMS 항공 상태 (예약안함/예약완료/발권요청/발권완료)")

    # 보고서 출장금액 - 보고서 정산기준 신청금액 행 추출
    accommodation = Column(DECIMAL(15, 2), nullable=True, comment="숙박비 (보고서 정산기준 신청금액)")
    transportation = Column(DECIMAL(15, 2), nullable=True, comment="교통비 (보고서 정산기준 신청금액)")
    meal_expense = Column(DECIMAL(15, 2), nullable=True, comment="식대 (보고서 정산기준 신청금액)")
    other_expense = Column(DECIMAL(15, 2), nullable=True, comment="기타비용 비자/여행자보험/e-sim (보고서 정산기준 신청금액)")

    created_at = Column(DateTime, server_default=func.now(), comment="생성일시")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="수정일시")


class LoanRepayment(Base):
    """차입금 상환 스케줄 (신차입금현황 엑셀 '상환스케줄' 탭 1회차당 1행)"""
    __tablename__ = "loan_repayment"
    __table_args__ = (
        Index("ix_loan_repayment_adjusted", "adjusted_due_date"),
        Index("ix_loan_repayment_loan", "loan_name", "block_index"),
        {"comment": "차입금 회차별 상환 스케줄 — 신차입금현황 엑셀 업로드 시 전체 교체"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="PK")
    block_index = Column(Integer, nullable=False, comment="엑셀 내 블록 순서 (중복 대출명 구분)")
    loan_name = Column(String(200), nullable=False, comment="대출명 (예: 농협은행 140억 대출)")
    installment_no = Column(Integer, nullable=False, comment="회차 번호")
    original_due_date = Column(Date, nullable=False, comment="엑셀 원본 납입일")
    adjusted_due_date = Column(Date, nullable=False, comment="영업일 조정 후 납입일 (주말/공휴일이면 다음 영업일)")
    principal = Column(DECIMAL(18, 2), nullable=True, comment="원금")
    interest = Column(DECIMAL(18, 2), nullable=True, comment="이자")
    total_payment = Column(DECIMAL(18, 2), nullable=True, comment="원리금")
    remaining_principal = Column(DECIMAL(18, 2), nullable=True, comment="미회수 원금")
    uploaded_at = Column(DateTime, server_default=func.now(), comment="업로드 일시")


class FinancialProduct(Base):
    """금융상품 만기상환 (웹 캐시 대시보드 자동 크롤링)"""
    __tablename__ = "financial_product"
    __table_args__ = (
        Index("ix_financial_product_maturity", "adjusted_maturity_date"),
        Index("ix_financial_product_company", "company_name"),
        {"comment": "금융상품 만기상환 — 웹 캐시 대시보드 자동 크롤링"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="PK")
    product_code = Column(String(100), nullable=False, unique=True, comment="상품코드 (회사명_상품명)")
    company_name = Column(String(200), nullable=False, comment="은행/증권사명")
    product_name = Column(String(200), nullable=False, comment="금융상품명 (예: IMA 금융상품)")
    amount = Column(DECIMAL(18, 2), nullable=False, comment="잔액")
    original_maturity_date = Column(Date, nullable=False, comment="원본 만기일 (웹 크롤링 원본)")
    adjusted_maturity_date = Column(Date, nullable=False, comment="영업일 조정 후 만기일 (주말/공휴일이면 다음 영업일)")
    is_active = Column(Integer, default=1, comment="활성 여부 (1=활성, 0=비활성)")
    synced_at = Column(DateTime, server_default=func.now(), comment="동기화 일시")
