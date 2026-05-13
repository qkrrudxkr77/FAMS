"""
APScheduler 10분 주기 자동화 스케줄러.

# TODO: 검증 완료 후 아래 주석 해제하여 스케줄러 활성화
# 테스트 단계에서는 주석 처리 상태로 유지.
# 수동 트리거: POST /api/trigger 엔드포인트 사용.
"""

import logging

# from apscheduler.schedulers.background import BackgroundScheduler
# from overseas_trip.automation import run_automation

logger = logging.getLogger(__name__)

# scheduler = None


def start_scheduler():
    """
    APScheduler 시작 (현재 주석 처리 - 검증 완료 후 활성화).

    활성화 방법:
      1. 이 파일 상단 import 주석 해제
      2. 아래 scheduler 변수 및 코드 주석 해제
      3. main.py의 lifespan 이벤트에서 start_scheduler() 호출

    작동 방식:
      - 서버 시작 시 즉시 1회 run_automation() 실행
      - 이후 10분 간격으로 반복 실행
    """
    # global scheduler
    # scheduler = BackgroundScheduler(timezone="Asia/Seoul")
    # scheduler.add_job(
    #     run_automation,
    #     trigger="interval",
    #     minutes=10,
    #     id="overseas_trip_job",
    #     replace_existing=True,
    # )
    # scheduler.start()
    # logger.info("스케줄러 시작 완료 (10분 주기)")

    logger.info("스케줄러 비활성화 상태 - 수동 트리거(/api/trigger)로 테스트 가능")


def stop_scheduler():
    """APScheduler 종료"""
    # global scheduler
    # if scheduler and scheduler.running:
    #     scheduler.shutdown()
    #     logger.info("스케줄러 종료")
    pass
