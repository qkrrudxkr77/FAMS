"""
APScheduler 자동화 스케줄러.

- 해외출장 자동화: 1시간 주기
- 금융상품(수령) 크롤링: 매일 00:01 (Asia/Seoul)
"""

import asyncio
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from overseas_trip.automation import run_automation

logger = logging.getLogger(__name__)

scheduler = None


def _sync_financial_products_job():
    """매일 00:01 실행 — 웹캐시 대시보드 금융상품 크롤링 → DB 저장"""
    try:
        from overseas_trip.web_crawler import crawl_financial_products
        from overseas_trip.db import SessionLocal
        from overseas_trip import crud

        products = asyncio.run(crawl_financial_products())
        if not products:
            logger.warning("금융상품 크롤링 결과 없음")
            return
        db = SessionLocal()
        try:
            count = crud.replace_all_financial_products(db, products)
            logger.info(f"금융상품 자동 크롤링 완료: {count}건")
        finally:
            db.close()
    except Exception:
        logger.exception("금융상품 자동 크롤링 실패")


def start_scheduler():
    """APScheduler 시작"""
    global scheduler
    scheduler = BackgroundScheduler(timezone="Asia/Seoul")

    # 해외출장 자동화 (1시간 주기, 서버 시작 후 1시간 뒤 첫 실행)
    scheduler.add_job(
        run_automation,
        trigger="interval",
        hours=1,
        id="overseas_trip_job",
        replace_existing=True,
        next_run_time=datetime.now() + timedelta(hours=1),
    )

    # 금융상품(수령) 크롤링 (매일 00:01)
    scheduler.add_job(
        _sync_financial_products_job,
        trigger="cron",
        hour=0,
        minute=1,
        id="financial_product_sync_job",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("스케줄러 시작 완료 (해외출장 1시간, 금융상품 매일 00:01)")


def stop_scheduler():
    """APScheduler 종료"""
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown()
        logger.info("스케줄러 종료")
