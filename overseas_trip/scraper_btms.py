# -*- coding: utf-8 -*-
"""
BTMS(출장관리시스템) 종합예약내역 스크래퍼.

URL: https://btms4.redcap.co.kr/page/BT_WR_0210
로그인: bdffinance@bodyfriend.co.kr / body123!

주요 기능:
  - 출장자명 + 출장기간으로 검색 → 일치 행 탐색
  - 항공 컬럼 값 확인 (예약완료 / 발권요청 / 발권완료)
  - 발권완료 팝업에서 항공료, 수수료, 발권일, 항공사, 예약등급 추출
  - 예약완료 + 문서상태 '완료' 시 자동 결제처리 (예약완료 → 발권요청)
"""

import logging
import os
import re
from datetime import date
from typing import Optional

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Page, BrowserContext, TimeoutError as PWTimeoutError

logger = logging.getLogger(__name__)

BTMS_URL = os.getenv("BTMS_URL", "https://btms4.redcap.co.kr/page/BT_WR_0210")
BTMS_ID = os.getenv("BTMS_ID", "bdffinance@bodyfriend.co.kr")
BTMS_PW = os.getenv("BTMS_PW", "body123!")


def _parse_date(raw: str) -> Optional[date]:
    from datetime import datetime
    raw = raw.strip()
    # BTMS 날짜 포맷 - 실제 화면 확인 후 필요시 추가
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    # "2026-05-12(화)" 같은 형태 처리
    m = re.match(r"(\d{4}-\d{2}-\d{2})", raw)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except ValueError:
            pass
    logger.warning("BTMS 날짜 파싱 실패: %s", raw)
    return None


def _parse_amount(raw: str) -> Optional[float]:
    cleaned = re.sub(r"[^\d.]", "", raw.strip())
    if cleaned:
        try:
            return float(cleaned)
        except ValueError:
            pass
    return None


def _login(page: Page) -> None:
    """BTMS 로그인. 실제 필드: LOGIN_ID / PWD, 버튼: '로그인'"""
    page.goto(BTMS_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)

    try:
        page.wait_for_selector("input[name='LOGIN_ID']", timeout=5000)
    except PWTimeoutError:
        logger.info("BTMS 이미 로그인된 상태로 간주")
        return

    page.fill("input[name='LOGIN_ID']", BTMS_ID)
    page.fill("input[name='PWD']", BTMS_PW)
    page.click("button:has-text('로그인')")
    # 로그인 후 페이지 전환 대기 (URL이 BT_WS_0010에서 벗어날 때까지)
    try:
        page.wait_for_url(lambda url: "BT_WS_0010" not in url, timeout=10000)
    except PWTimeoutError:
        logger.warning("BTMS 로그인 후 페이지 전환 timeout - 현재 URL: %s", page.url)
    page.wait_for_timeout(2000)
    logger.info("BTMS 로그인 완료. URL: %s", page.url)


def _type_name_with_composition(page: Page, name: str) -> None:
    """
    BTMS combo의 출장자명 입력은 composition 이벤트를 통해 트리거된다.
    한글 IME처럼 compositionstart/update/end + input(insertCompositionText) 이벤트 발생.
    글자별로 딜레이를 두어 자동완성 드롭다운이 반응할 시간을 줌.
    """
    # 페이지 컴포넌트 로드 대기 (페이지 전환 후 컴포넌트가 동적 등록됨)
    try:
        page.wait_for_selector("input[name='CUSTCO_ESMBR_NO']", timeout=15000)
    except PWTimeoutError:
        raise RuntimeError("출장자명 input[name='CUSTCO_ESMBR_NO'] 로드 timeout")
    page.wait_for_timeout(1000)

    field = page.query_selector("input[name='CUSTCO_ESMBR_NO']")
    if not field:
        raise RuntimeError("출장자명 input[name='CUSTCO_ESMBR_NO'] 찾을 수 없음")
    field.click()
    page.wait_for_timeout(500)

    # 기존 값 초기화
    page.evaluate("() => { const el = document.querySelector(\"input[name='CUSTCO_ESMBR_NO']\"); el.value = ''; }")

    # 글자별로 composition 이벤트 발생 + 200ms 딜레이 (자동완성 반응 시간 확보)
    acc = ""
    for ch in name:
        acc += ch
        page.evaluate(f"""(data) => {{
            const el = document.querySelector("input[name='CUSTCO_ESMBR_NO']");
            el.focus();
            el.value = data.acc;
            el.dispatchEvent(new CompositionEvent('compositionstart', {{bubbles:true, data:''}}));
            el.dispatchEvent(new CompositionEvent('compositionupdate', {{bubbles:true, data:data.ch}}));
            el.dispatchEvent(new CompositionEvent('compositionend', {{bubbles:true, data:data.acc}}));
            el.dispatchEvent(new InputEvent('input', {{bubbles:true, data:data.ch, inputType:'insertCompositionText'}}));
            el.dispatchEvent(new Event('input', {{bubbles:true}}));
            el.dispatchEvent(new KeyboardEvent('keyup', {{bubbles:true, key:data.ch}}));
        }}""", {"acc": acc, "ch": ch})
        page.wait_for_timeout(200)


def _set_period(page: Page, start_date: date, end_date: date) -> None:
    """출장기간 입력. TERM_FROM / TERM_TO 직접 fill 가능."""
    page.fill("input[name='TERM_FROM']", start_date.strftime("%Y-%m-%d"))
    page.fill("input[name='TERM_TO']", end_date.strftime("%Y-%m-%d"))


def _search_traveler(page: Page, name: str, start_date: date, end_date: date) -> bool:
    """
    출장자명 + 출장기간으로 BTMS 검색. 자동완성 항목 선택 후 검색하기 버튼 클릭.
    반환: True (자동완성 선택 성공) / False (검색 결과 없음)
    """
    page.goto(BTMS_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    # 출장자명 입력 (composition 이벤트) → 자동완성 → 항목 선택 후에 기간 입력
    _type_name_with_composition(page, name)

    # 자동완성 드롭다운 대기 (visible 드롭다운에 임직원 항목이 나타날 때까지)
    try:
        page.wait_for_function(
            """() => {
                for (const el of document.querySelectorAll('.button-layer.type2 .list li a')) {
                    if (el.offsetParent !== null && (el.textContent || '').includes('임직원')) {
                        return true;
                    }
                }
                return false;
            }""",
            timeout=8000
        )
    except PWTimeoutError:
        logger.warning("BTMS 자동완성 드롭다운 미표시 - 이름: %s", name)
        return False

    # 보이는 항목 중 이름이 정확히 일치하는 것 선택
    items = page.query_selector_all(".button-layer.type2 .list li a")
    visible_items = [item for item in items if item.is_visible()]
    logger.info("BTMS 자동완성 visible 항목 수: %d", len(visible_items))

    target = None
    for item in visible_items:
        text = item.inner_text() or ""
        # "임직원 | 한승일 | (주)바디프랜드 | ..." 형식
        parts = [p.strip() for p in text.split("|")]
        if len(parts) >= 2 and parts[1] == name:
            target = item
            break
    if not target and visible_items:
        target = visible_items[0]

    if not target:
        logger.warning("BTMS 자동완성 visible 항목 없음 - 이름: %s", name)
        return False

    target.click()
    page.wait_for_timeout(500)

    # 출장기간 설정 (자동완성 클릭 후)
    _set_period(page, start_date, end_date)
    page.wait_for_timeout(500)

    # 검색하기 버튼 클릭
    page.click("button:has-text('검색하기')")
    page.wait_for_timeout(3000)
    return True


def _find_matching_row(page: Page, start_date: date, end_date: date) -> Optional[dict]:
    """
    BTMS 종합예약내역 검색 결과 테이블에서 출장기간이 정확히 일치하는 행 탐색.

    실제 컬럼 인덱스 (디버그 확인):
      0: 번호
      1: 사업장/부서
      2: 출장자명
      3: 출장기간 (예: "2026-03-30~2026-04-03")
      4: 여정
      5: 신청자명
      6: 항공 (예약완료/발권완료/신규예약)
      7: 출장규정준수여부 (항공의)
      8: 호텔
      9: 출장규정준수여부 (호텔의)
      10: 렌터카, 11: 비자, 12: 보험, 13: 로밍, 14: 품의상태 등

    반환: {"air_status": str, "compliance": str, "row_index": int} or None
    """
    IDX_PERIOD = 3
    IDX_AIR = 6
    IDX_COMPLIANCE = 7

    soup = BeautifulSoup(page.content(), "html.parser")

    # '출장자명' 헤더를 가진 결과 테이블 찾기
    target_table = None
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        if "출장자명" in headers and "출장기간" in headers:
            target_table = table
            break

    if not target_table:
        logger.debug("BTMS 결과 테이블을 찾지 못함")
        return None

    tbody = target_table.find("tbody")
    if not tbody:
        return None

    for idx, tr in enumerate(tbody.find_all("tr")):
        cells = tr.find_all("td")
        if len(cells) < 8:
            continue

        # 출장기간 셀 (예: "2026-03-30~2026-04-03" or "2026-03-30 ~ 2026-04-03")
        period_text = cells[IDX_PERIOD].get_text(strip=True)
        if "~" not in period_text and "∼" not in period_text:
            continue
        parts = re.split(r"[~∼]", period_text)
        if len(parts) != 2:
            continue
        row_start = _parse_date(parts[0])
        row_end = _parse_date(parts[1])

        if row_start != start_date or row_end != end_date:
            continue

        air_status = cells[IDX_AIR].get_text(strip=True)
        compliance = cells[IDX_COMPLIANCE].get_text(strip=True)

        return {
            "air_status": air_status,
            "compliance": compliance,
            "row_index": idx,
        }

    return None


def _click_air_link(page: Page, row_index: int, link_text: str) -> None:
    """종합예약내역 테이블 특정 행의 항공 링크 클릭"""
    links = page.query_selector_all(f"table tbody tr:nth-child({row_index + 1}) a")
    for link in links:
        if link_text in (link.inner_text() or ""):
            link.click()
            return
    # 폴백: 텍스트로 검색
    page.click(f"a:has-text('{link_text}')", timeout=5000)


def _process_payment(page: Page, row_index: int) -> bool:
    """
    예약완료 + 문서상태 '완료' 시 결제처리 자동화.
    플로우:
      1. 예약완료 링크 클릭 → 예약상세내역 모달
      2. '결제' 버튼 클릭 → 요금규정 모달
      3. 약관 체크박스 체크 → '다음단계' 클릭
      4. '결제요청' 클릭 → confirm 다이얼로그 자동 수락
      5. 완료 모달 '확인' 클릭 → 닫기
    성공 시 True (이후 BTMS 항공 상태는 '발권요청'으로 변함)
    """
    try:
        # 1. 예약완료 링크 클릭
        _click_air_link(page, row_index, "예약완료")
        page.wait_for_function(
            """() => {
                for (const el of document.querySelectorAll('*')) {
                    if ((el.textContent || '').trim() === '예약상세내역' && el.offsetParent !== null) return true;
                }
                return false;
            }""",
            timeout=15000
        )
        page.wait_for_timeout(1500)
        logger.info("[결제] 예약상세내역 모달 오픈")

        frame = _get_modal_frame(page)

        # 2. '결제' 버튼 클릭 (data-desc='결제' 자식 span 보유)
        clicked = frame.evaluate("""() => {
            const btns = document.querySelectorAll('button');
            for (const b of btns) {
                if (b.querySelector('[data-desc="결제"]')) { b.click(); return true; }
            }
            return false;
        }""")
        if not clicked:
            raise RuntimeError("'결제' 버튼을 찾을 수 없음")
        page.wait_for_timeout(2000)
        logger.info("[결제] '결제' 버튼 클릭")

        # 3. 요금규정 단계: 체크박스 체크 + '다음단계' 클릭
        frame.evaluate("""() => {
            document.querySelectorAll('input[type="checkbox"]').forEach(c => { if (!c.checked) c.click(); });
        }""")
        page.wait_for_timeout(500)

        frame.evaluate("""() => {
            const btns = document.querySelectorAll('button');
            for (const b of btns) {
                if (b.getAttribute('data-desc') === '_다음단계') { b.click(); return; }
            }
        }""")
        page.wait_for_timeout(2000)
        logger.info("[결제] '다음단계' 클릭")

        # 4. 결제 단계: confirm 다이얼로그 자동 수락 + '결제요청' 클릭
        page.once("dialog", lambda dialog: dialog.accept())
        frame.evaluate("""() => {
            const btns = document.querySelectorAll('button');
            for (const b of btns) {
                if ((b.textContent || '').trim() === '결제요청') { b.click(); return; }
            }
        }""")
        page.wait_for_timeout(3000)
        logger.info("[결제] '결제요청' 클릭 + confirm 자동 수락")

        # 5. 완료 모달: '확인' 클릭
        frame.evaluate("""() => {
            const btns = document.querySelectorAll('button');
            for (const b of btns) {
                if ((b.textContent || '').trim() === '확인') { b.click(); return; }
            }
        }""")
        page.wait_for_timeout(1500)
        logger.info("[결제] 완료 모달 '확인' 클릭")

        return True
    except Exception as e:
        logger.error("[결제] 결제처리 실패: %s", e)
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        return False


def _get_modal_frame(page: Page):
    """
    BTMS 발권완료 모달 콘텐츠가 로드된 iframe 반환.
    URL 패턴: /front/#/reservation/flight?...
    """
    for frame in page.frames:
        if "reservation/flight" in frame.url or "/front/" in frame.url:
            return frame
    # fallback: 메인 외 첫 sub-frame
    subs = [f for f in page.frames if f != page.main_frame]
    return subs[0] if subs else page


def _click_modal_tab(frame, tab_text: str) -> None:
    """모달 내 탭 클릭. iframe 안에서 작동."""
    frame.evaluate(f"""(text) => {{
        const els = document.querySelectorAll('a, button, li, span, div');
        for (const el of els) {{
            const t = (el.textContent || '').trim();
            if (t === text && el.offsetParent !== null) {{
                el.click();
                return true;
            }}
        }}
        return false;
    }}""", tab_text)
    frame.wait_for_timeout(1500)


def parse_ticketing_modal(page: Page, target_name: str = "") -> dict:
    """
    발권완료 모달에서 항공 정보 추출.
    모달 콘텐츠는 iframe(/front/#/reservation/flight)에 있음.
    동행자가 있는 경우 모달 안에 여러 탑승자 행이 있으므로, target_name으로 해당 행 매칭.

    탭별 위치:
      - 예약정보(기본): 고객요청여정 → 클래스 열 (예약등급)
      - 요금/티켓정보: 요금정보 → 항공료 합계 + 취급수수료, 발권 정보 → 발권일
      - 여권/마일리지정보: 마일리지 정보 → 탑승항공사 (한국어 이름으로 매칭)
    """
    result = {
        "airfare": None,
        "agency_fee": None,
        "airfare_payment_date": None,
        "airline": None,
        "booking_class": None,
    }

    # 모달 iframe 가져오기
    modal_frame = _get_modal_frame(page)
    logger.info("BTMS 모달 frame URL: %s", getattr(modal_frame, "url", "(main page)")[:100])

    # --- 예약정보 탭 (기본)에서 예약등급 추출 ---
    soup = BeautifulSoup(modal_frame.content(), "html.parser")
    result["booking_class"] = _extract_booking_class(soup)

    # --- 여권/마일리지정보 탭에서 한국어 이름으로 row_index 찾기 ---
    _click_modal_tab(modal_frame, "여권/마일리지정보")
    soup = BeautifulSoup(modal_frame.content(), "html.parser")

    target_row_idx = 0  # 기본값
    target_airline = None
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        if "탑승항공사" not in headers:
            continue
        name_idx = next((i for i, h in enumerate(headers) if h in ("출장자", "성명", "이름")), 0)
        airline_idx = next((i for i, h in enumerate(headers) if "탑승항공사" in h), None)
        if airline_idx is None:
            continue
        tbody = table.find("tbody")
        if not tbody:
            continue
        rows = tbody.find_all("tr")
        for i, tr in enumerate(rows):
            cells = tr.find_all("td")
            if name_idx >= len(cells):
                continue
            row_name = cells[name_idx].get_text(strip=True)
            if target_name and row_name == target_name:
                target_row_idx = i
                if airline_idx < len(cells):
                    target_airline = cells[airline_idx].get_text(strip=True)
                break
        else:
            # 매칭 못 찾으면 첫 행 사용
            if rows:
                cells = rows[0].find_all("td")
                if airline_idx < len(cells):
                    target_airline = cells[airline_idx].get_text(strip=True)
        break
    result["airline"] = target_airline
    logger.info("BTMS 마일리지 매칭 (이름=%s): row_idx=%d, airline=%s", target_name, target_row_idx, target_airline)

    # --- 요금/티켓정보 탭에서 동일 row_idx의 데이터 추출 ---
    _click_modal_tab(modal_frame, "요금/티켓정보")
    soup = BeautifulSoup(modal_frame.content(), "html.parser")

    # 요금정보 테이블 (헤더: 탑승자/항공료/유류할증료/항공료 합계/취급수수료)
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        header_text = " ".join(headers)
        if "항공료 합계" not in header_text and "항공료합계" not in header_text:
            continue
        airfare_idx = next((i for i, h in enumerate(headers) if "항공료 합계" in h or "항공료합계" in h), None)
        fee_idx = next((i for i, h in enumerate(headers) if "취급수수료" in h), None)
        tbody = table.find("tbody")
        if not tbody:
            continue
        rows = tbody.find_all("tr")
        if target_row_idx < len(rows):
            cells = rows[target_row_idx].find_all("td")
            if airfare_idx is not None and airfare_idx < len(cells):
                result["airfare"] = _parse_amount(cells[airfare_idx].get_text(strip=True))
            if fee_idx is not None and fee_idx < len(cells):
                result["agency_fee"] = _parse_amount(cells[fee_idx].get_text(strip=True))
        break

    # 발권 정보 테이블 (헤더: 탑승자/구간/발권일/티켓번호/티켓상태)
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        if "발권일" not in headers or "티켓번호" not in headers:
            continue
        idx = next((i for i, h in enumerate(headers) if "발권일" in h), None)
        tbody = table.find("tbody")
        if not tbody or idx is None:
            continue
        rows = tbody.find_all("tr")
        if target_row_idx < len(rows):
            cells = rows[target_row_idx].find_all("td")
            if idx < len(cells):
                result["airfare_payment_date"] = _parse_date(cells[idx].get_text(strip=True))
        break

    return result


def parse_ticketing_popup(page: Page) -> dict:
    """
    발권완료 팝업에서 항공 정보 추출.
    반환: {
        "airfare": float,
        "agency_fee": float,
        "airfare_payment_date": date,
        "airline": str,
        "booking_class": str,
    }
    """
    # 팝업 열릴 때까지 대기
    page.wait_for_load_state("networkidle")
    soup = BeautifulSoup(page.content(), "html.parser")
    result = {
        "airfare": None,
        "agency_fee": None,
        "airfare_payment_date": None,
        "airline": None,
        "booking_class": None,
    }

    # --- 요금/티켓정보 탭 클릭 ---
    for sel in ["[class*='tab']:has-text('요금')", "button:has-text('요금/티켓')", "li:has-text('요금/티켓')", "a:has-text('요금')"]:
        try:
            page.click(sel, timeout=3000)
            page.wait_for_load_state("networkidle")
            soup = BeautifulSoup(page.content(), "html.parser")
            break
        except Exception:
            continue

    # 요금정보 섹션 - 항공료 합계, 취급수수료
    for tag in soup.find_all(string=re.compile(r"항공료\s*합계|항공료합계")):
        parent = tag.parent
        val = parent.find_next("td") if parent else None
        if val:
            result["airfare"] = _parse_amount(val.get_text(strip=True))
        break

    for tag in soup.find_all(string=re.compile(r"취급수수료")):
        parent = tag.parent
        val = parent.find_next("td") if parent else None
        if val:
            result["agency_fee"] = _parse_amount(val.get_text(strip=True))
        break

    # 발권 정보 섹션 - 발권일
    for tag in soup.find_all(string=re.compile(r"발권일")):
        parent = tag.parent
        val = parent.find_next("td") if parent else None
        if val:
            result["airfare_payment_date"] = _parse_date(val.get_text(strip=True))
        break

    # --- 여권/마일리지정보 탭 클릭 ---
    for sel in ["[class*='tab']:has-text('마일리지')", "button:has-text('마일리지')", "a:has-text('마일리지')", "li:has-text('여권')"]:
        try:
            page.click(sel, timeout=3000)
            page.wait_for_load_state("networkidle")
            soup = BeautifulSoup(page.content(), "html.parser")
            break
        except Exception:
            continue

    # 마일리지 정보 섹션 - 탑승항공사
    airlines = []
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        if "탑승항공사" in " ".join(headers):
            col_idx = next((i for i, h in enumerate(headers) if "탑승항공사" in h), None)
            if col_idx is not None:
                tbody = table.find("tbody")
                if tbody:
                    for tr in tbody.find_all("tr"):
                        cells = tr.find_all("td")
                        if col_idx < len(cells):
                            airlines.append(cells[col_idx].get_text(strip=True))
    result["airline"] = ", ".join(set(filter(None, airlines)))

    # 고객요청여정 - 클래스 열 파싱 (팝업 기본 탭 또는 공통 섹션에 있을 수 있음)
    # 팝업 첫 탭으로 돌아가서 파싱
    for sel in ["[class*='tab']:first-child", "button.tab:first-child"]:
        try:
            page.click(sel, timeout=2000)
            page.wait_for_load_state("networkidle")
            soup = BeautifulSoup(page.content(), "html.parser")
            break
        except Exception:
            continue

    booking_classes = _extract_booking_class(soup)
    result["booking_class"] = booking_classes

    return result


def _extract_booking_class(soup: BeautifulSoup) -> str:
    """
    고객요청여정 섹션 클래스 열에서 예약등급 추출.
    가는편/오는편 클래스가 같으면 하나만, 다르면 '/' 로 연결.
    예: 이코노미(H), 이코노미(S) → 이코노미
        이코노미(S), 비즈니스(Z) → 이코노미/비즈니스
    """
    classes = []
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        header_text = " ".join(headers)
        if "클래스" not in header_text and "편명" not in header_text:
            continue
        col_idx = next((i for i, h in enumerate(headers) if "클래스" in h), None)
        if col_idx is None:
            continue
        tbody = table.find("tbody")
        if tbody:
            for tr in tbody.find_all("tr"):
                cells = tr.find_all("td")
                if col_idx < len(cells):
                    cls_text = cells[col_idx].get_text(strip=True)
                    # "이코노미(H)" → "이코노미"
                    m = re.match(r"([^(]+)", cls_text)
                    if m:
                        classes.append(m.group(1).strip())
        break

    if not classes:
        return ""

    unique = list(dict.fromkeys(classes))  # 순서 유지하며 중복 제거
    return "/".join(unique)


def process_btms_for_traveler(
    page: Page,
    name: str,
    start_date: date,
    end_date: date,
    doc_status: str,
) -> dict:
    """
    단일 출장자에 대해 BTMS 조회 및 항공 처리 실행.
    반환: {
        "found": bool,
        "air_status": str,         # "예약완료" or "발권완료" or ""
        "compliance": str,
        "ticketing_data": dict,    # 발권완료인 경우 추출 데이터
        "payment_done": bool,      # 결제처리 완료 여부
    }
    """
    result = {
        "found": False,
        "air_status": "",
        "compliance": "",
        "ticketing_data": {},
        "payment_done": False,
    }

    search_ok = _search_traveler(page, name, start_date, end_date)
    logger.info("BTMS 검색 결과 (이름=%s): search_ok=%s", name, search_ok)
    row_info = _find_matching_row(page, start_date, end_date)
    logger.info("BTMS 매칭 행 (이름=%s): %s", name, row_info)

    if not row_info:
        logger.warning("BTMS에서 일치하는 행 없음 - 출장자: %s, %s ~ %s", name, start_date, end_date)
        return result

    result["found"] = True
    result["air_status"] = row_info["air_status"]
    result["compliance"] = row_info["compliance"]
    logger.info("BTMS 항공 상태: %r, 규정: %r (이름=%s)", row_info["air_status"], row_info["compliance"], name)

    if row_info["air_status"] == "예약완료":
        if doc_status == "진행중":
            # 승인 대기 중 - 아무 작업 없이 스킵
            logger.info("예약완료 + 진행중 상태 - 대기 (출장자: %s)", name)
        elif doc_status == "완료":
            # 결제처리 자동화: 예약완료 → 발권요청
            logger.info("예약완료 + 완료 상태 - 결제처리 시작 (출장자: %s)", name)
            ok = _process_payment(page, row_info["row_index"])
            result["payment_done"] = ok
            if ok:
                # 결제 후 BTMS 항공 상태는 '발권요청'으로 변경됨
                result["air_status"] = "발권요청"
                logger.info("결제처리 완료 → air_status=발권요청 (출장자: %s)", name)
            else:
                logger.warning("결제처리 실패 - air_status 유지: 예약완료 (출장자: %s)", name)

    elif row_info["air_status"] == "발권완료":
        try:
            # 발권완료 링크 클릭 → modal 오픈 (popup이 아니라 같은 페이지의 모달)
            _click_air_link(page, row_info["row_index"], "발권완료")
            # 모달이 뜰 때까지 대기: '예약상세내역' 제목이 보일 때까지
            page.wait_for_function(
                """() => {
                    for (const el of document.querySelectorAll('*')) {
                        if ((el.textContent || '').trim() === '예약상세내역' && el.offsetParent !== null) return true;
                    }
                    return false;
                }""",
                timeout=15000
            )
            page.wait_for_timeout(1500)
            logger.info("BTMS 발권완료 모달 오픈 (이름=%s)", name)

            ticketing_data = parse_ticketing_modal(page, target_name=name)
            logger.info("BTMS 발권 데이터 추출 (이름=%s): %s", name, ticketing_data)
            result["ticketing_data"] = ticketing_data

            # 모달 닫기 (X 버튼)
            try:
                page.click("[class*='close'], button:has-text('×'), button[aria-label*='close' i]", timeout=2000)
            except Exception:
                # ESC로 닫기 시도
                page.keyboard.press("Escape")
            page.wait_for_timeout(500)

        except Exception as e:
            logger.error("발권완료 모달 처리 실패 (출장자: %s): %s", name, e)

    return result


def run_btms_for_travelers(travelers_info: list[dict]) -> list[dict]:
    """
    여러 출장자에 대해 BTMS 처리 일괄 실행.
    travelers_info: [{"name": str, "start_date": date, "end_date": date, "doc_status": str}, ...]
    """
    results = []
    headless = os.getenv("BTMS_HEADLESS", "false").lower() != "false"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        _login(page)

        for info in travelers_info:
            try:
                r = process_btms_for_traveler(
                    page,
                    info["name"],
                    info["start_date"],
                    info["end_date"],
                    info["doc_status"],
                )
                r["name"] = info["name"]
                results.append(r)
            except Exception as e:
                logger.error("BTMS 처리 실패 (출장자: %s): %s", info.get("name"), e)
                results.append({"name": info.get("name"), "found": False, "error": str(e)})

        browser.close()
    return results
