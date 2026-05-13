from datetime import datetime
from sqlalchemy import Column, Integer, String, Date, DateTime, Text, DECIMAL, UniqueConstraint
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
