# -*- coding: utf-8 -*-
"""
삼성카드 로그인 페이지 보안 키패드 구조 분석 디버그 스크립트.

실행:
  source .venv/bin/activate
  python -m overseas_trip.debug_samsung_card

목적:
- 보안 키패드의 DOM 구조/iframe/캔버스 여부 파악
- 각 버튼의 selector/data-attribute 확인
- 자동화 가능성 평가
"""

import asyncio
from playwright.async_api import async_playwright

LOGIN_URL = "https://www.samsungcard.com/corporation/main/UHPCCO0101M0.jsp?click=main_header_corp"


async def analyze():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=300)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900},
        )
        page = await context.new_page()

        print("=" * 70)
        print("1단계: 메인 페이지 접속")
        print("=" * 70)
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)
        print(f"현재 URL: {page.url}")
        print(f"타이틀: {await page.title()}")

        print("\n" + "=" * 70)
        print("2단계: 로그인 폼 탐색")
        print("=" * 70)

        # ID/PW input 찾기
        for selector in [
            "input[type='text']",
            "input[type='password']",
            "input[name*='id']",
            "input[id*='id']",
            "input[name*='pw']",
            "input[name*='pass']",
            "input[id*='pw']",
            "input[id*='pass']",
        ]:
            elements = await page.locator(selector).all()
            for i, el in enumerate(elements):
                try:
                    name = await el.get_attribute("name") or ""
                    id_ = await el.get_attribute("id") or ""
                    ph = await el.get_attribute("placeholder") or ""
                    type_ = await el.get_attribute("type") or ""
                    print(f"  [{selector}][{i}] name='{name}' id='{id_}' type='{type_}' placeholder='{ph}'")
                except Exception:
                    pass

        print("\n" + "=" * 70)
        print("3단계: 비밀번호 입력란 클릭 → 보안키패드 열기")
        print("=" * 70)

        # 비밀번호 input 클릭
        pw_input = page.locator("input[type='password']").first
        if await pw_input.count() > 0:
            await pw_input.click()
            print("✅ 비밀번호 입력란 클릭")
            await page.wait_for_timeout(2000)
        else:
            print("❌ 비밀번호 input을 찾지 못함")

        print("\n" + "=" * 70)
        print("4단계: 보안 키패드 DOM 분석")
        print("=" * 70)

        # iframe 체크
        frames = page.frames
        print(f"\n📋 전체 frame 개수: {len(frames)}")
        for i, fr in enumerate(frames):
            print(f"  [{i}] name='{fr.name}' url={fr.url[:100]}")

        # 보안키패드 관련 요소 탐색
        print("\n📋 '보안키패드' 텍스트 찾기:")
        keypad_texts = await page.locator("text=보안키패드").all()
        print(f"  발견 개수: {len(keypad_texts)}")

        # 키패드 컨테이너 후보
        print("\n📋 키패드 컨테이너 후보 selector:")
        for sel in [
            "[class*='keypad']",
            "[class*='Keypad']",
            "[id*='keypad']",
            "[id*='Keypad']",
            "[class*='security']",
            "iframe[src*='keypad']",
            "iframe[id*='keypad']",
            "iframe[src*='security']",
            "div[role='dialog']",
        ]:
            cnt = await page.locator(sel).count()
            if cnt > 0:
                print(f"  ✅ {sel} → {cnt}개 발견")
                for i in range(min(cnt, 3)):
                    el = page.locator(sel).nth(i)
                    try:
                        tag = await el.evaluate("e => e.tagName")
                        cls = await el.get_attribute("class") or ""
                        id_ = await el.get_attribute("id") or ""
                        print(f"     [{i}] <{tag.lower()}> id='{id_}' class='{cls[:80]}'")
                    except Exception as e:
                        print(f"     [{i}] 분석 실패: {e}")

        # 모든 iframe 내부 분석
        print("\n📋 iframe 내부 분석:")
        for i, fr in enumerate(page.frames):
            if fr == page.main_frame:
                continue
            try:
                btn_count = await fr.locator("button").count()
                input_count = await fr.locator("input").count()
                print(f"  [frame {i}] name='{fr.name}' buttons={btn_count} inputs={input_count}")
                if btn_count > 0 or input_count > 0:
                    # 처음 10개 버튼만 샘플링
                    for b in range(min(btn_count, 10)):
                        try:
                            btn = fr.locator("button").nth(b)
                            text = await btn.inner_text()
                            attrs = await btn.evaluate(
                                "e => ({ class: e.className, dataValue: e.dataset.value, dataKey: e.dataset.key, id: e.id })"
                            )
                            print(f"     btn[{b}] text='{text}' attrs={attrs}")
                        except Exception:
                            pass
            except Exception as e:
                print(f"  [frame {i}] 분석 불가: {e}")

        # 메인 페이지의 키패드 버튼 직접 탐색
        print("\n📋 메인 페이지에서 키패드 버튼 후보 (1~9, a~z 텍스트):")
        for sample_text in ["1", "2", "a", "b", "특수", "재배열", "입력완료"]:
            cnt = await page.locator(f"text='{sample_text}'").count()
            if cnt > 0:
                print(f"  '{sample_text}' → {cnt}개 발견")

        print("\n" + "=" * 70)
        print("5단계: HTML 일부 덤프 (보안키패드 주변)")
        print("=" * 70)

        try:
            # 보안키패드 영역 부모 찾아서 HTML 출력
            keypad_area = page.locator("text=보안키패드").first
            if await keypad_area.count() > 0:
                parent_html = await keypad_area.evaluate(
                    "e => { let p = e; for (let i=0; i<4; i++) p = p.parentElement; return p.outerHTML.substring(0, 5000); }"
                )
                print(parent_html)
            else:
                print("(보안키패드 텍스트가 메인 페이지에 없음 - iframe 내부일 가능성)")
        except Exception as e:
            print(f"HTML 덤프 실패: {e}")

        print("\n" + "=" * 70)
        print("분석 완료. 30초 후 브라우저 자동 종료.")
        print("=" * 70)
        await page.wait_for_timeout(30000)
        await context.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(analyze())
