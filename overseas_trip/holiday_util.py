from datetime import date, timedelta
import holidays

KR_HOLIDAYS = holidays.KR()


def get_last_business_day_of_next_month(base_date: date) -> date:
    """
    기준일의 익월 말일을 구하고, 주말/공휴일이면 앞으로 당겨서 영업일 반환.
    예: 기안일이 2026-04-15이면 익월 말일 = 2026-05-31, 주말이면 05-29(금) 반환.
    """
    # 익월 1일 계산
    if base_date.month == 12:
        next_month_first = date(base_date.year + 1, 1, 1)
    else:
        next_month_first = date(base_date.year, base_date.month + 1, 1)

    # 익월 말일 = 익익월 1일 - 1일
    if next_month_first.month == 12:
        month_after_next_first = date(next_month_first.year + 1, 1, 1)
    else:
        month_after_next_first = date(next_month_first.year, next_month_first.month + 1, 1)

    last_day = month_after_next_first - timedelta(days=1)

    # 주말/공휴일이면 앞으로 당김
    while last_day.weekday() >= 5 or last_day in KR_HOLIDAYS:
        last_day -= timedelta(days=1)

    return last_day


def next_business_day(d: date) -> date:
    """
    주어진 날짜가 주말/공휴일이면 다음 영업일로 미룬다.
    이미 영업일이면 그대로 반환.
    예: 2026-05-30(토) → 2026-06-01(월)
    """
    while d.weekday() >= 5 or d in KR_HOLIDAYS:
        d += timedelta(days=1)
    return d
