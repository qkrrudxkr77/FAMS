# -*- coding: utf-8 -*-
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DB_HOST = os.getenv("DB_HOST", "body-test3.c8ktl8xfhswf.ap-northeast-2.rds.amazonaws.com")
DB_PORT = os.getenv("DB_PORT", "8882")
DB_USER = os.getenv("DB_USER", "admin")
DB_PASSWORD = os.getenv("DB_PASSWORD", "qkelvmfpswm!")
DB_NAME = os.getenv("DB_NAME", "fams")

DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"

engine = create_engine(DATABASE_URL, pool_pre_ping=True, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """DB 및 테이블 초기화 (fams DB 없으면 생성 후 테이블 생성)"""
    # fams DB 없을 경우 생성
    root_url = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}?charset=utf8mb4"
    root_engine = create_engine(root_url, pool_pre_ping=True)
    with root_engine.connect() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
        conn.commit()
    root_engine.dispose()

    from overseas_trip.models import Base as OTBase
    OTBase.metadata.create_all(bind=engine)

    # 기존 테이블 마이그레이션: 누락된 컬럼 추가
    _migrate_missing_columns()


def _migrate_missing_columns():
    """기존 테이블에 누락된 컬럼 추가 (멱등)"""
    new_columns = [
        ("air_status", "VARCHAR(20) NULL COMMENT 'BTMS 항공 상태 (예약안함/예약완료/발권요청/발권완료)'"),
    ]
    with engine.connect() as conn:
        for col_name, col_def in new_columns:
            result = conn.execute(text("""
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_schema = :db AND table_name = 'overseas_trip_expense' AND column_name = :col
            """), {"db": DB_NAME, "col": col_name})
            if result.scalar() == 0:
                conn.execute(text(f"ALTER TABLE overseas_trip_expense ADD COLUMN {col_name} {col_def}"))
                conn.commit()
