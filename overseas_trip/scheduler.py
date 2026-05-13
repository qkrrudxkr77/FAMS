"""
APScheduler 1시간 주기 자동화 스케줄러.

수동 트리거: POST /api/trigger 엔드포인트 사용.
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from overseas_trip.automation import run_automation

logger = logging.getLogger(__name__)

scheduler = None


def start_scheduler():
    """
    APScheduler 시작 (1시간 주기).

    작동 방식:
      - 서버 시작 시 1시간 후 첫 실행
      - 이후 1시간 간격으로 반복 실행
    """
    global scheduler
    scheduler = BackgroundScheduler(timezone="Asia/Seoul")
    scheduler.add_job(
        run_automation,
        trigger="interval",
        hours=1,
        id="overseas_trip_job",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("스케줄러 시작 완료 (1시간 주기)")


def stop_scheduler():
    """APScheduler 종료"""
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown()
        logger.info("스케줄러 종료")
