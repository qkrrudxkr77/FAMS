"""
BTMS 페이지 구조 디버그 스크립트.
실행: python -m overseas_trip.debug_btms

테스트 시나리오: 한승일 + 출장기간 (2026-03-30 ~ 2026-04-03)
"""

import os
from datetime import date
from pathlib import Path
from playwright.sync_api import sync_playwright

BTMS_URL = os.getenv("BTMS_URL", "https://btms4.redcap.co.kr/page/BT_WR_0210")
BTMS_ID = os.getenv("BTMS_ID", "bdffinance@bodyfriend.co.kr")
BTMS_PW = os.getenv("BTMS_PW", "body123!")

OUT_DIR = Path("debug_output_btms")
OUT_DIR.mkdir(exist_ok=True)

TEST_NAME = "한승일"
TEST_START = date(2026, 3, 30)
TEST_END = date(2026, 4, 3)


def save(page, name: str):
    page.screenshot(path=str(OUT_DIR / f"{name}.png"), full_page=True)
    (OUT_DIR / f"{name}.html").write_text(page.content(), encoding="utf-8")
    print(f"  → 저장됨: debug_output_btms/{name}.png / .html")


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=400)
        page = browser.new_page()

        # 네트워크 요청 추적용 리스트 (타이핑 시점에만 활성화)
        captured_requests = []
        capturing = {"on": False}

        def on_request(req):
            if not capturing["on"]:
                return
            # static asset은 제외
            url = req.url
            if any(ext in url for ext in [".png", ".jpg", ".css", ".woff", ".svg", ".ico", ".gif"]):
                return
            captured_requests.append({"method": req.method, "url": url, "post_data": req.post_data})

        page.on("request", on_request)

        print("1) BTMS 접속...")
        page.goto(BTMS_URL, wait_until="networkidle", timeout=30000)
        save(page, "01_initial")
        print(f"   현재 URL: {page.url}")

        # 로그인 폼 탐색
        print("2) 입력 필드 탐색...")
        inputs = page.query_selector_all("input")
        print(f"   input 수: {len(inputs)}")
        for el in inputs[:20]:
            print(f"     name={el.get_attribute('name')!r} type={el.get_attribute('type')!r} id={el.get_attribute('id')!r} placeholder={el.get_attribute('placeholder')!r}")

        # 로그인 시도 (실제 필드: LOGIN_ID / PWD)
        print("3) 로그인 시도...")
        page.fill("input[name='LOGIN_ID']", BTMS_ID)
        print("   ID 입력 성공")
        page.fill("input[name='PWD']", BTMS_PW)
        print("   PW 입력 성공")
        page.click("button:has-text('로그인')")
        print("   로그인 버튼 클릭")

        page.wait_for_timeout(3000)
        save(page, "02_after_login")
        print(f"   로그인 후 URL: {page.url}")

        # 종합예약내역 페이지 진입
        print("4) 종합예약내역 페이지 재접속...")
        page.goto(BTMS_URL, wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        save(page, "03_main_page")

        # 페이지 내 입력 필드 탐색
        print("5) 검색 페이지의 input 탐색...")
        inputs = page.query_selector_all("input")
        print(f"   input 수: {len(inputs)}")
        for el in inputs[:30]:
            name = el.get_attribute("name") or ""
            el_id = el.get_attribute("id") or ""
            el_type = el.get_attribute("type") or ""
            placeholder = el.get_attribute("placeholder") or ""
            try:
                rect = el.bounding_box()
                visible = "보임" if rect else "숨김"
            except Exception:
                visible = "?"
            print(f"     name={name!r} type={el_type!r} id={el_id!r} placeholder={placeholder!r} ({visible})")

        # 버튼 탐색
        print("6) 버튼 탐색...")
        buttons = page.query_selector_all("button, input[type='submit'], input[type='button'], a")
        for btn in buttons[:30]:
            txt = (btn.inner_text() or btn.get_attribute("value") or "").strip()
            cls = btn.get_attribute("class") or ""
            if txt or "search" in cls.lower():
                print(f"     {btn.evaluate('el => el.tagName')}: text={txt!r} class={cls!r}")

        # 출장자명 자동완성 드롭다운 테스트
        print("7) 출장자명 자동완성 테스트...")
        name_field = page.query_selector("input[name='CUSTCO_ESMBR_NO']")
        if name_field:
            print(f"   필드 존재: name={name_field.get_attribute('name')}, readonly={name_field.evaluate('el => el.readOnly')}")
            # jQuery 존재 여부 확인
            has_jquery = page.evaluate("() => typeof window.jQuery !== 'undefined' && !!window.jQuery")
            print(f"   jQuery 존재: {has_jquery}")

            name_field.click()
            page.wait_for_timeout(500)
            capturing["on"] = True

            # composition 이벤트 명시 발생 (한글 IME 시뮬레이션)
            page.evaluate(f"""() => {{
                const el = document.querySelector("input[name='CUSTCO_ESMBR_NO']");
                el.focus();
                el.value = '';
                let accumulated = '';
                for (const ch of '{TEST_NAME}') {{
                    accumulated += ch;
                    el.dispatchEvent(new CompositionEvent('compositionstart', {{bubbles:true, data:''}}));
                    el.value = accumulated;
                    el.dispatchEvent(new CompositionEvent('compositionupdate', {{bubbles:true, data:ch}}));
                    el.dispatchEvent(new CompositionEvent('compositionend', {{bubbles:true, data:ch}}));
                    el.dispatchEvent(new InputEvent('input', {{bubbles:true, data:ch, inputType:'insertCompositionText'}}));
                    el.dispatchEvent(new KeyboardEvent('keyup', {{bubbles:true, key:ch}}));
                }}
            }}""")
            print(f"   composition 후 value: {name_field.evaluate('el => el.value')!r}")
            page.wait_for_timeout(10000)
            capturing["on"] = False

            print(f"   캡처된 네트워크 요청 수: {len(captured_requests)}")
            for req in captured_requests[:20]:
                print(f"     {req['method']} {req['url'][:130]}")
                if req["post_data"]:
                    print(f"       POST: {req['post_data'][:200]}")

            # 자동완성 드롭다운이 나타날 때까지 대기 (최대 8초)
            try:
                # "임직원" 텍스트가 보이는 요소가 나타날 때까지 대기
                page.wait_for_function(
                    f"""() => {{
                        const all = document.querySelectorAll('*');
                        for (const el of all) {{
                            const txt = el.textContent || '';
                            if (txt.includes('임직원') && txt.includes('{TEST_NAME}') && el.offsetParent !== null && el.children.length < 5) {{
                                return true;
                            }}
                        }}
                        return false;
                    }}""",
                    timeout=8000
                )
                print("   자동완성 드롭다운 감지됨!")
            except Exception as e:
                print(f"   자동완성 드롭다운 대기 실패: {e}")
            page.wait_for_timeout(500)
            save(page, "04_after_type_name")

            # 자동완성 후보의 정확한 셀렉터 분석 (조건 완화)
            print("   '임직원' + 'TEST_NAME' 포함 visible 요소 검색:")
            candidates = page.evaluate(f"""
                () => {{
                    const result = [];
                    const all = document.querySelectorAll('*');
                    for (const el of all) {{
                        const txt = el.textContent || '';
                        // 임직원 + 이름 + 너무 큰 컨테이너 제외 (텍스트 길이 < 200)
                        if (txt.includes('임직원') && txt.includes('{TEST_NAME}') && el.offsetParent !== null && txt.length < 200) {{
                            // 자식 div 깊이 체크 - 너무 깊은 컨테이너 제외
                            const childCount = el.querySelectorAll('*').length;
                            result.push({{
                                tag: el.tagName,
                                cls: el.className,
                                id: el.id,
                                text: txt.trim().substring(0, 120),
                                childCount: childCount,
                                parentTag: el.parentElement ? el.parentElement.tagName : '',
                                parentCls: el.parentElement ? el.parentElement.className : '',
                            }});
                            if (result.length >= 15) break;
                        }}
                    }}
                    return result;
                }}
            """)
            for c in candidates:
                print(f"     [{c['childCount']}] <{c['tag']} class={c['cls']!r} id={c['id']!r}> parent=<{c['parentTag']} class={c['parentCls']!r}> text={c['text']!r}")

            # 자동완성 항목 클릭 + 출장기간 입력 + 검색
            print("9) 자동완성 클릭 + 검색 실행...")
            # visible한 button-layer만 (display!=none 이고 화면에 보이는)
            items = page.evaluate_handle("""
                () => {
                    const result = [];
                    for (const el of document.querySelectorAll('.button-layer.type2 .list li a')) {
                        if (el.offsetParent !== null) result.push(el);
                    }
                    return result;
                }
            """)
            all_items = page.query_selector_all(".button-layer.type2 .list li a")
            visible_items = [it for it in all_items if it.is_visible()]
            print(f"   전체 {len(all_items)}, visible {len(visible_items)}")
            if visible_items:
                items = visible_items
                # 자동완성 항목 먼저 클릭 (fill하면 드롭다운 닫힘)
                items[0].click()
                page.wait_for_timeout(500)
                # 그 다음 출장기간 설정
                page.fill("input[name='TERM_FROM']", TEST_START.strftime("%Y-%m-%d"))
                page.fill("input[name='TERM_TO']", TEST_END.strftime("%Y-%m-%d"))
                page.wait_for_timeout(500)
                save(page, "05_after_select_name")
                # 검색하기 클릭
                page.click("button:has-text('검색하기')")
                page.wait_for_timeout(2000)
                page.wait_for_timeout(2000)
                save(page, "06_after_search")

                # 결과 테이블 파싱
                print("10) 결과 테이블 탐색...")
                tables = page.query_selector_all("table")
                for i, tbl in enumerate(tables[:15]):
                    ths = tbl.query_selector_all("th")
                    header_texts = [th.inner_text().strip() for th in ths]
                    if "출장자명" in " ".join(header_texts):
                        trs = tbl.query_selector_all("tbody tr")
                        print(f"   [결과 테이블 {i}] 헤더: {header_texts}")
                        print(f"   tbody 행수: {len(trs)}")
                        for j, tr in enumerate(trs[:5]):
                            tds = tr.query_selector_all("td")
                            cell_texts = [td.inner_text().strip()[:50] for td in tds]
                            print(f"   행 [{j}]: {cell_texts}")
                        break

                # ============= 발권완료 모달 디버그 =============
                print("11) 발권완료 셀 클릭 → 모달 분석...")
                # '발권완료' 텍스트 클릭 (결과 행의 항공 컬럼)
                try:
                    page.click("text='발권완료'", timeout=5000)
                    print("   발권완료 클릭 성공")
                except Exception as e:
                    print(f"   발권완료 클릭 실패: {e}")

                # 모달 오픈 대기 (예약상세내역 텍스트)
                try:
                    page.wait_for_function(
                        "() => Array.from(document.querySelectorAll('*')).some(el => (el.textContent||'').trim()==='예약상세내역' && el.offsetParent!==null)",
                        timeout=15000
                    )
                    print("   모달 오픈 감지!")
                except Exception as e:
                    print(f"   모달 감지 실패: {e}")
                page.wait_for_timeout(2000)
                save(page, "07_modal_open")

                # 모달 안의 frame 수 확인
                print(f"   현재 frame 수: {len(page.frames)}")
                for i, f in enumerate(page.frames):
                    print(f"     frame[{i}] url={f.url}")

                # 모달 iframe 선택
                modal_frame = None
                for f in page.frames:
                    if "reservation/flight" in f.url or "/front/" in f.url:
                        modal_frame = f
                        break
                if not modal_frame:
                    modal_frame = page
                    print("   모달 iframe 못 찾음 - page 사용")
                else:
                    print(f"   모달 iframe 선택: {modal_frame.url[:80]}")

                # 모달 안의 테이블 탐색
                print("12) 모달 안 테이블 헤더 + 첫 행:")
                tables = modal_frame.query_selector_all("table")
                for i, tbl in enumerate(tables):
                    ths = tbl.query_selector_all("th")
                    header_texts = [th.inner_text().strip() for th in ths]
                    header_str = " | ".join(header_texts)
                    if not header_str:
                        continue
                    # 의미있는 헤더가 있는 테이블만
                    if any(kw in header_str for kw in ["항공료", "발권일", "탑승항공사", "클래스", "편명", "구간"]):
                        trs = tbl.query_selector_all("tbody tr")
                        print(f"   [모달 테이블 {i}] 헤더: {header_texts}")
                        for j, tr in enumerate(trs[:3]):
                            tds = tr.query_selector_all("td")
                            cell_texts = [td.inner_text().strip()[:60] for td in tds]
                            print(f"     행 [{j}]: {cell_texts}")

                # 탭 클릭 시도 (modal_frame 안에서)
                print("13) '요금/티켓정보' 탭 클릭...")
                try:
                    clicked = modal_frame.evaluate("""() => {
                        const els = document.querySelectorAll('a, button, li, span, div');
                        for (const el of els) {
                            if ((el.textContent||'').trim() === '요금/티켓정보' && el.offsetParent !== null) {
                                el.click();
                                return el.tagName + '.' + el.className;
                            }
                        }
                        return null;
                    }""")
                    print(f"   탭 클릭: {clicked}")
                except Exception as e:
                    print(f"   탭 클릭 실패: {e}")
                page.wait_for_timeout(2000)
                save(page, "08_modal_fare_tab")

                # 요금/티켓 탭 후 테이블 다시 확인
                print("14) 요금/티켓 탭의 테이블:")
                tables = modal_frame.query_selector_all("table")
                for i, tbl in enumerate(tables):
                    ths = tbl.query_selector_all("th")
                    header_texts = [th.inner_text().strip() for th in ths]
                    header_str = " | ".join(header_texts)
                    if any(kw in header_str for kw in ["항공료", "발권일", "취급수수료"]):
                        trs = tbl.query_selector_all("tbody tr")
                        print(f"   [테이블 {i}] 헤더: {header_texts}")
                        for j, tr in enumerate(trs[:3]):
                            tds = tr.query_selector_all("td")
                            cell_texts = [td.inner_text().strip()[:60] for td in tds]
                            print(f"     행 [{j}]: {cell_texts}")

                # 마일리지 탭
                print("15) '여권/마일리지정보' 탭 클릭...")
                modal_frame.evaluate("""() => {
                    for (const el of document.querySelectorAll('a, button, li, span, div')) {
                        if ((el.textContent||'').trim() === '여권/마일리지정보' && el.offsetParent !== null) {
                            el.click();
                            return;
                        }
                    }
                }""")
                page.wait_for_timeout(2000)
                save(page, "09_modal_mileage_tab")
                print("16) 마일리지 탭의 테이블:")
                tables = modal_frame.query_selector_all("table")
                for i, tbl in enumerate(tables):
                    ths = tbl.query_selector_all("th")
                    header_texts = [th.inner_text().strip() for th in ths]
                    header_str = " | ".join(header_texts)
                    if any(kw in header_str for kw in ["탑승항공사", "마일리지", "여권"]):
                        trs = tbl.query_selector_all("tbody tr")
                        print(f"   [테이블 {i}] 헤더: {header_texts}")
                        for j, tr in enumerate(trs[:3]):
                            tds = tr.query_selector_all("td")
                            cell_texts = [td.inner_text().strip()[:60] for td in tds]
                            print(f"     행 [{j}]: {cell_texts}")

        # 날짜 필드 readonly 체크
        print("8) 출장기간 필드 readonly 확인...")
        for sel in ["input[name='TERM_FROM']", "input[name='TERM_TO']"]:
            info = page.evaluate(f"() => {{ const e=document.querySelector(\"{sel}\"); return e ? {{readonly: e.readOnly, value: e.value, type: e.type}} : null; }}")
            print(f"   {sel}: {info}")

        print("\n완료. debug_output_btms/ 폴더의 스크린샷과 HTML을 확인하세요.")
        page.wait_for_timeout(2000)
        browser.close()


if __name__ == "__main__":
    run()
