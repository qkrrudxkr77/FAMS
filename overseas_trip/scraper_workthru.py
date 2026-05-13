"""
워크쓰루(그룹웨어) 해외출장 신청서/보고서 스크래퍼.

URL: https://portal.bodyfriend.co.kr/approval/work/apprlist/listApprReference.do
조회 조건: 기안일 오늘 기준 7일 전 ~ 오늘, 분류 = 공통
"""

import logging
import os
import re
from datetime import date, datetime, timedelta
from typing import Optional

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Page, TimeoutError as PWTimeoutError

logger = logging.getLogger(__name__)

WORKTHRU_URL = os.getenv("WORKTHRU_URL", "https://portal.bodyfriend.co.kr/approval/work/apprlist/listApprReference.do")
WORKTHRU_ID = os.getenv("WORKTHRU_ID", "qkrrudxkr77")
WORKTHRU_PW = os.getenv("WORKTHRU_PW", "body123@")

# 상세 페이지의 양식명 (p.title > em 태그 안에 일정하게 표시됨)
# 사용자가 작성한 문서 제목은 자유 형식이라 신뢰 불가, 상세 페이지의 양식명으로 분류한다.
FORM_NAME_APPLICATION = "해외출장 신청서"
FORM_NAME_REPORT = "해외출장 보고서"


def _parse_date(raw: str) -> Optional[date]:
    """워크쓰루 날짜 문자열을 date 객체로 변환. 포맷 확인 후 필요시 수정."""
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d", "%Y년 %m월 %d일"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    logger.warning("날짜 파싱 실패: %s", raw)
    return None


def _parse_amount(raw: str) -> Optional[float]:
    """금액 문자열(콤마, 원 포함)을 float으로 변환"""
    cleaned = re.sub(r"[^\d.]", "", raw.strip())
    if cleaned:
        try:
            return float(cleaned)
        except ValueError:
            pass
    return None


def _login(page: Page) -> None:
    page.goto(WORKTHRU_URL, wait_until="networkidle")
    # 로그인 폼 확인 (실제 필드: j_username / password, 버튼: <a id='btnSubmit'>)
    try:
        page.wait_for_selector("input[name='j_username']", timeout=8000)
    except PWTimeoutError:
        logger.info("로그인 폼 없음 - 이미 로그인된 상태로 간주")
        return

    page.fill("input[name='j_username']", WORKTHRU_ID)
    page.fill("input[name='password']", WORKTHRU_PW)

    # 로그인 버튼: <a id="btnSubmit">로그인</a> - form의 onsubmit으로 goLogin() 호출
    # 클릭 후 페이지 이동을 기다림
    with page.expect_navigation(wait_until="networkidle", timeout=30000):
        page.click("#btnSubmit")
    logger.info("로그인 완료. 현재 URL: %s", page.url)


def _get_approval_frame(page: Page):
    """
    포털은 실제 콘텐츠를 iframe 안에 로드한다 (mainFrameUrl 파라미터 방식).
    결재 목록 페이지가 로드된 frame을 반환. 없으면 메인 page 반환.
    """
    logger.info("현재 페이지 URL: %s", page.url)
    logger.info("전체 frame 수: %d", len(page.frames))
    for i, frame in enumerate(page.frames):
        logger.info("  frame[%d] url=%s name=%s", i, frame.url, frame.name)

    # mainFrameUrl 파라미터가 URL에 있으면 iframe이 있다는 의미
    for frame in page.frames:
        if frame == page.main_frame:
            continue
        if "listApprReference" in frame.url or "apprlist" in frame.url or "approval" in frame.url:
            logger.info("결재 목록 iframe 선택: %s", frame.url)
            return frame

    # iframe URL이 비어있을 수 있으니 메인 외 첫 번째 프레임 시도
    sub_frames = [f for f in page.frames if f != page.main_frame]
    if sub_frames:
        logger.info("URL 매칭 실패. 첫 sub-frame 사용: %s", sub_frames[0].url)
        return sub_frames[0]

    logger.warning("iframe 없음 - 메인 페이지 사용")
    return page


def _set_date_range(frame) -> None:
    """
    기안일 조회 기간: 오늘 기준 N일 전 ~ 오늘 (환경변수 WORKTHRU_LOOKBACK_DAYS, 기본 7일).
    실제 필드명: searchStartDate / searchEndDate, 포맷: YYYY.MM.DD
    필드가 readonly이므로 JS로 직접 값 설정 후 change 이벤트 발생.
    """
    lookback_days = int(os.getenv("WORKTHRU_LOOKBACK_DAYS", "60"))
    today = date.today()
    start = today - timedelta(days=lookback_days)
    logger.info("워크쓰루 조회 기간 설정: %s ~ %s (lookback=%d일)", start, today, lookback_days)
    fmt = "%Y.%m.%d"
    start_str = start.strftime(fmt)
    end_str = today.strftime(fmt)

    frame.evaluate(f"""
        () => {{
            const s = document.querySelector("input[name='searchStartDate']");
            const e = document.querySelector("input[name='searchEndDate']");
            if (s) {{
                s.removeAttribute('readonly');
                s.value = '{start_str}';
                s.dispatchEvent(new Event('change', {{bubbles: true}}));
            }}
            if (e) {{
                e.removeAttribute('readonly');
                e.value = '{end_str}';
                e.dispatchEvent(new Event('change', {{bubbles: true}}));
            }}
        }}
    """)
    logger.info("날짜 범위 설정: %s ~ %s", start_str, end_str)


def scrape_document_list(page: Page) -> list[dict]:
    """
    워크쓰루 목록 페이지에서 분류='공통'이고 제목이 TARGET_TITLES인 문서 목록을 반환.

    실제 테이블 헤더 (디버그 확인):
      idx 0: (체크박스)  1: No.  2: 문서번호  3: 분류  4: 확인여부
      idx 5: 그룹사여부  6: 문서 제목  7: 기안자  8: 기안부서
      idx 9: 기안일  10: 완료일  11: 문서상태

    반환: [{"title": str, "doc_status": str, "href": str, "onclick": str}, ...]
    """
    _login(page)
    page.goto(WORKTHRU_URL, wait_until="networkidle")

    # 포털이 iframe으로 콘텐츠를 감싸는 경우 frame을 가져옴
    frame = _get_approval_frame(page)

    _set_date_range(frame)

    # 검색 버튼 (실제 확인: a:has-text('검색'))
    frame.click("a:has-text('검색')", timeout=5000)
    frame.wait_for_load_state("networkidle")

    soup = BeautifulSoup(frame.content(), "html.parser")
    docs = []

    # 문서 목록 테이블: 헤더에 '문서 제목'이 있는 테이블
    target_table = None
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        if "문서 제목" in headers and "분류" in headers:
            target_table = table
            break

    if not target_table:
        logger.warning("워크쓰루 문서 목록 테이블을 찾지 못했습니다.")
        return docs

    tbody = target_table.find("tbody")
    if not tbody:
        logger.warning("워크쓰루 테이블에 tbody가 없습니다.")
        return docs

    all_rows = tbody.find_all("tr")
    logger.info("문서 목록 테이블 전체 행수: %d", len(all_rows))


    for row in all_rows:
        cells = row.find_all("td")
        if len(cells) < 12:
            continue

        # 실제 열 인덱스 기반 추출
        category = cells[3].get_text(strip=True)   # 분류
        title_cell = cells[6]                        # 문서 제목
        doc_status = cells[11].get_text(strip=True) # 문서상태

        # 분류 = '공통'인 행만 처리
        if category != "공통":
            continue

        # 분류='공통'인 모든 문서 후보 수집 (실제 양식 분류는 상세 페이지에서 확인)
        # 링크 구조: <a href="#a" onclick="getApprDetail('도큐ID','');" title="...">...</a>
        link_tag = title_cell.find("a") if title_cell.find("a") else None
        # td.subject 안에 a 태그가 있는 형태인지 다시 확인
        if not link_tag:
            subject_cell = row.find("td", class_="subject")
            if subject_cell:
                link_tag = subject_cell.find("a")
        if not link_tag:
            continue

        link_text = link_tag.get_text(strip=True)
        onclick = link_tag.get("onclick", "")

        # onclick에서 문서 ID 추출 (getApprDetail('도큐ID','...'))
        m = re.search(r"getApprDetail\(\s*['\"]([^'\"]+)['\"]", onclick)
        appr_id = m.group(1) if m else ""

        docs.append({
            "doc_status": doc_status,
            "onclick": onclick,
            "appr_id": appr_id,
            "link_text": link_text,
        })

    logger.info("워크쓰루 조회 결과: %d건 (공통/신청서|보고서)", len(docs))
    return docs


def _get_form_name(page_or_frame) -> str:
    """
    상세 페이지의 양식명 추출. <p class="title"><em>해외출장 신청서</em></p>
    iframe 내부에 있을 수 있으니 모든 frame을 순회하며 탐색.
    """
    # page 객체인 경우 frame 리스트 접근
    frames = []
    if hasattr(page_or_frame, "frames"):
        frames = list(page_or_frame.frames)
    else:
        # frame 자체인 경우 - frame.page.frames 접근
        try:
            frames = list(page_or_frame.page.frames)
        except Exception:
            frames = [page_or_frame]

    for f in frames:
        try:
            html = f.content()
        except Exception:
            continue
        soup = BeautifulSoup(html, "html.parser")
        p_title = soup.select_one("p.title em")
        if p_title:
            text = p_title.get_text(strip=True)
            if text:
                return text
    return ""


def _get_content_frame(page_or_frame):
    """
    상세 페이지의 실제 콘텐츠가 있는 frame을 반환.
    p.title em이 있는 frame을 우선 선택. 없으면 입력받은 frame 반환.
    """
    frames = []
    if hasattr(page_or_frame, "frames"):
        frames = list(page_or_frame.frames)
    else:
        try:
            frames = list(page_or_frame.page.frames)
        except Exception:
            return page_or_frame
    for f in frames:
        try:
            if f.evaluate("() => !!document.querySelector('p.title em')"):
                return f
        except Exception:
            continue
    return page_or_frame


def _click_document_link(frame, doc: dict) -> None:
    """
    문서 링크 클릭. onclick="getApprDetail('docId','')" 패턴을 직접 JS로 호출한다.
    """
    appr_id = doc.get("appr_id", "")
    onclick = doc.get("onclick", "")
    if appr_id:
        # getApprDetail 함수 직접 호출
        frame.evaluate(f"getApprDetail('{appr_id}', '')")
    elif onclick:
        # onclick 전체 실행
        frame.evaluate(onclick)
    else:
        raise ValueError("문서 ID 없음 - 클릭 불가")

    # 상세 페이지 로드 대기: p.title em이 나타날 때까지 (최대 10초)
    try:
        frame.wait_for_selector("p.title em", timeout=10000)
    except PWTimeoutError:
        # 양식명 요소가 나타나지 않으면 일반 대기
        frame.wait_for_load_state("networkidle", timeout=5000)


def _dump_all_tables(page_or_frame, doc_no_hint: str = "") -> None:
    """디버그: 페이지 내 핵심 테이블의 HTML 저장"""
    try:
        soup = BeautifulSoup(page_or_frame.content(), "html.parser")
        # '부서명' 헤더를 가진 테이블의 HTML 전체 저장
        for i, t in enumerate(soup.find_all("table")):
            headers = [th.get_text(strip=True) for th in t.find_all("th")]
            if "부서명" in headers and "시작일자" in headers:
                safe_hint = doc_no_hint.replace(":", "_").replace("/", "_").replace(" ", "_")[:50]
                path = f"/tmp/table_{safe_hint}_t{i}.html"
                with open(path, "w", encoding="utf-8") as fp:
                    fp.write(str(t))
                logger.info("  [덤프] 핵심 테이블[%d] HTML 저장: %s", i, path)
                break
    except Exception as e:
        logger.warning("테이블 덤프 실패: %s", e)


# data-field-description 매핑
FIELD_MAP_TRAVELER = {
    "KOSTL_TXT": "department",     # 부서명
    "PERNR_TXT": "name",            # 출장자(성명)
    "POS_KEY_TXT": "position",      # 직위
    "LAND2": "country",             # 국가
    "FDATE": "start_date",          # 시작일자
    "TDATE": "end_date",            # 종료일자
}
# 신청금액 필드 (보고서/신청서 공통)
FIELD_MAP_AMOUNT = {
    "FL_EXP": "airfare",          # 항공료
    "ROOM_EXP": "accommodation",  # 숙박비
    "TRAN_EXP": "transportation", # 교통비
    "MEAL_EXP": "meal_expense",   # 식대
    "ETC_EXP": "other_expense",   # 기타
    "DAY_EXP": "daily_allowance", # 일비
}


def _extract_doc_no_and_date(soup: BeautifulSoup) -> tuple:
    """문서번호와 기안일자 추출"""
    doc_no = ""
    doc_date = None
    # 문서번호/기안일자 테이블 탐색
    for table in soup.find_all("table"):
        ths = [th.get_text(strip=True) for th in table.find_all("th")]
        if "문서번호" not in ths:
            continue
        tbody = table.find("tbody")
        if not tbody:
            continue
        # 첫 tr 내 th-td 쌍 매핑
        for tr in tbody.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            for i, cell in enumerate(cells):
                txt = cell.get_text(strip=True)
                if cell.name == "th" and "문서번호" in txt and i + 1 < len(cells):
                    doc_no = cells[i + 1].get_text(strip=True)
                if cell.name == "th" and "기안일" in txt and i + 1 < len(cells):
                    doc_date = _parse_date(cells[i + 1].get_text(strip=True))
        if doc_no:
            break
    return doc_no, doc_date


def _extract_travelers_table(soup: BeautifulSoup) -> list:
    """
    '■ 출장자 / 합계금액' 표에서 출장자 정보 추출.
    각 출장자마다 정산금액/신청금액 2개 행이 있고 정보 셀은 rowspan=2.
    data-field-description 속성으로 정확하게 필드 식별.
    """
    travelers = []
    # KOSTL_TXT 셀이 있는 모든 tr를 찾음 (출장자 시작 행)
    # KOSTL_TXT는 출장자 정보 셀에만 있으므로 안전한 식별자
    kostl_cells = soup.select('td[data-field-description="KOSTL_TXT"]')
    logger.info("KOSTL_TXT 셀 개수: %d", len(kostl_cells))

    for kostl_td in kostl_cells:
        # 이 td가 속한 tr (정산금액 행)
        tr = kostl_td.find_parent("tr")
        if not tr:
            continue

        traveler = {}
        # 정산금액 행의 모든 셀에서 traveler 필드 추출
        for c in tr.find_all(["th", "td"]):
            desc = c.get("data-field-description", "")
            val = c.get_text(strip=True)
            if desc in FIELD_MAP_TRAVELER:
                key = FIELD_MAP_TRAVELER[desc]
                if key in ("start_date", "end_date"):
                    traveler[key] = _parse_date(val)
                else:
                    traveler[key] = val

        # 다음 tr (신청금액 행)에서 신청금액 추출
        next_tr = tr.find_next_sibling("tr")
        if next_tr:
            for c in next_tr.find_all(["th", "td"]):
                desc = c.get("data-field-description", "")
                val = c.get_text(strip=True).replace(",", "")
                if desc in FIELD_MAP_AMOUNT:
                    try:
                        traveler[FIELD_MAP_AMOUNT[desc]] = float(val) if val else None
                    except ValueError:
                        traveler[FIELD_MAP_AMOUNT[desc]] = None

        if traveler.get("name"):
            travelers.append(traveler)

    return travelers


def _extract_trip_purpose(soup: BeautifulSoup) -> str:
    """
    출장목적 추출. '출장목적' 레이블 옆 셀에서 값을 읽어 맨 앞 알파벳 1글자를 반환.
    예: 'B. 생산 및 품질관리' → 'B'
    """
    # '출장목적' 텍스트가 있는 th/td를 찾아 바로 옆 td의 값을 읽음
    for tag in soup.find_all(string=re.compile(r"출장목적")):
        parent = tag.find_parent(["th", "td", "label", "span", "div"])
        if not parent:
            continue
        # 같은 tr 안 다음 td
        tr = parent.find_parent("tr")
        if tr:
            cells = tr.find_all(["td", "th"])
            for i, cell in enumerate(cells):
                if "출장목적" in cell.get_text():
                    # 바로 옆 셀
                    if i + 1 < len(cells):
                        val = cells[i + 1].get_text(strip=True)
                        m = re.match(r"([A-Z])", val)
                        if m:
                            return m.group(1)
        # tr 구조가 없으면 형제 태그에서 탐색
        nxt = parent.find_next_sibling(["td", "th", "span", "div"])
        if nxt:
            val = nxt.get_text(strip=True)
            m = re.match(r"([A-Z])", val)
            if m:
                return m.group(1)

    # fallback: '출장목적' 레이블 직후 텍스트에서 패턴 매칭
    text = soup.get_text(separator=" ", strip=True)
    m = re.search(r"출장목적\s*([A-Z])\.", text)
    if m:
        return m.group(1)
    return ""


def parse_application_detail(page) -> dict:  # page 또는 frame 모두 허용
    """
    해외출장 신청서 상세 페이지 파싱.
    반환: {"doc_no": str, "doc_date": date, "trip_purpose": str, "travelers": [{...}, ...]}
    """
    soup = BeautifulSoup(page.content(), "html.parser")
    doc_no, doc_date = _extract_doc_no_and_date(soup)
    trip_purpose = _extract_trip_purpose(soup)
    travelers = _extract_travelers_table(soup)
    logger.info("신청서 파싱 - 문서번호=%s, 출장목적=%s, 출장자 %d명", doc_no, trip_purpose, len(travelers))
    return {
        "doc_no": doc_no,
        "doc_date": doc_date,
        "trip_purpose": trip_purpose,
        "travelers": travelers,
    }


def parse_report_detail(page) -> dict:  # page 또는 frame 모두 허용
    """
    해외출장 보고서 상세 페이지 파싱. 신청서와 동일한 표 구조를 가지지만 출장자가 여러 명일 수 있음.
    반환: {"doc_no": str, "doc_date": date, "travelers": [{...}, ...]}
    """
    soup = BeautifulSoup(page.content(), "html.parser")
    doc_no, doc_date = _extract_doc_no_and_date(soup)
    travelers = _extract_travelers_table(soup)
    logger.info("보고서 파싱 - 문서번호=%s, 기안일=%s, 출장자 %d명", doc_no, doc_date, len(travelers))
    return {
        "doc_no": doc_no,
        "doc_date": doc_date,
        "travelers": travelers,
    }


def run_workthru_scrape() -> list[dict]:
    """
    워크쓰루 전체 스크래핑 실행.
    반환: [{"type": "application"|"report", "doc_status": str, "data": dict}, ...]
    """
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        try:
            docs = scrape_document_list(page)
        except Exception as e:
            logger.error("워크쓰루 목록 조회 실패: %s", e)
            browser.close()
            return results

        # 문서 상세 진입 시에도 동일한 frame 사용
        frame = _get_approval_frame(page)

        logger.info("상세 진입 대상 문서: %d건", len(docs))
        # 디버그용 dump 경로
        dump_idx = 0

        for doc in docs:
            link_text = doc.get("link_text", "")
            try:
                _click_document_link(frame, doc)

                # 클릭 후 페이지가 안정될 때까지 대기
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except PWTimeoutError:
                    pass

                # 상세 페이지의 실제 콘텐츠 frame 탐지
                detail_frame = _get_content_frame(page)
                form_name = _get_form_name(page)
                logger.info("문서 양식명: %r (link_text=%r)", form_name, link_text)

                # 디버그: HTML 덤프 (양식명 못 찾았을 때)
                if not form_name:
                    dump_path = f"/tmp/workthru_detail_{dump_idx}.html"
                    try:
                        with open(dump_path, "w", encoding="utf-8") as fp:
                            fp.write(detail_frame.content())
                        logger.info("상세 페이지 HTML 덤프 저장: %s", dump_path)
                        dump_idx += 1
                    except Exception:
                        pass

                if form_name == FORM_NAME_APPLICATION:
                    _dump_all_tables(detail_frame, "신청서:" + link_text[:30])
                    data = parse_application_detail(detail_frame)
                    data["doc_title"] = link_text
                    results.append({
                        "type": "application",
                        "doc_status": doc["doc_status"],
                        "data": data,
                    })
                elif form_name == FORM_NAME_REPORT:
                    _dump_all_tables(detail_frame, "보고서:" + link_text[:30])
                    data = parse_report_detail(detail_frame)
                    data["doc_title"] = link_text
                    results.append({
                        "type": "report",
                        "doc_status": doc["doc_status"],
                        "data": data,
                    })

            except Exception as e:
                logger.error("문서 처리 실패 (link_text=%s): %s", link_text, e)

            # 다음 문서를 위해 목록 페이지로 직접 이동 (go_back은 frame 이슈 발생)
            try:
                page.goto(WORKTHRU_URL, wait_until="networkidle")
                frame = _get_approval_frame(page)
                _set_date_range(frame)
                frame.click("a:has-text('검색')", timeout=5000)
                frame.wait_for_load_state("networkidle")
            except Exception as e:
                logger.error("목록 페이지 복귀 실패: %s", e)
                break

        browser.close()

    return results


def get_user_photo_bytes() -> Optional[bytes]:
    """
    워크쓰루 포털에서 현재 로그인 계정의 프로필 사진을 바이트로 반환.
    로그인 후 이미 portalMain.do에 위치 - 메인+iframe 전체를 탐색.
    실패 시 None 반환.
    """
    keywords = ['photo', 'profile', 'avatar', 'emp', 'mypage', 'member', 'userimg']

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            _login(page)
            # mainFrameUrl 파라미터 없이 포털 메인만 로드 → 헤더/프로필 영역 탐색
            page.goto(
                "https://portal.bodyfriend.co.kr/portal/main/portalMain.do",
                wait_until="networkidle",
                timeout=20000,
            )
            # iframe 로드 대기 (동적 렌더링)
            page.wait_for_timeout(3000)

            # 메인 프레임 + 모든 iframe에서 프로필 사진 img 탐색
            photo_src = None
            for frame in page.frames:
                try:
                    src = frame.evaluate("""
                        (keywords) => {
                            const imgs = [...document.querySelectorAll('img')];
                            for (const img of imgs) {
                                const raw = img.getAttribute('src') || '';
                                const lower = raw.toLowerCase();
                                if (keywords.some(k => lower.includes(k))) {
                                    return img.src || raw;
                                }
                            }
                            const els = [...document.querySelectorAll('[style]')];
                            for (const el of els) {
                                const s = el.getAttribute('style') || '';
                                const m = s.match(/url\\(['"']?([^'"')]+)['"']?\\)/i);
                                if (m) {
                                    const u = m[1].toLowerCase();
                                    if (keywords.some(k => u.includes(k))) return m[1];
                                }
                            }
                            return null;
                        }
                    """, keywords)
                    if src:
                        logger.info("프로필 사진 발견 (frame=%s): %s", frame.url[:60], src[:80])
                        photo_src = src
                        break
                except Exception:
                    continue

            if not photo_src:
                # 디버그: 전체 img src 목록 출력
                try:
                    all_srcs = page.evaluate("""
                        () => [...document.querySelectorAll('img')]
                              .map(i => i.getAttribute('src'))
                              .filter(Boolean)
                    """)
                    logger.warning("프로필 사진 탐색 실패. 메인프레임 img src 목록: %s", all_srcs[:15])
                except Exception:
                    pass
                logger.warning("워크쓰루 프로필 사진 URL을 찾지 못했습니다.")
                return None

            if not photo_src.startswith("http"):
                photo_src = "https://portal.bodyfriend.co.kr" + photo_src

            logger.info("워크쓰루 프로필 사진 URL: %s", photo_src)
            resp = page.request.get(photo_src)
            if resp.ok:
                return resp.body()
            logger.warning("프로필 사진 응답 오류: status=%s", resp.status)
        except Exception as e:
            logger.warning("워크쓰루 프로필 사진 취득 실패: %s", e)
        finally:
            browser.close()
    return None
