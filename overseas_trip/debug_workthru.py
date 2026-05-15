# -*- coding: utf-8 -*-
"""
워크쓰루 페이지 구조 디버그 스크립트.
실행: python -m overseas_trip.debug_workthru
스크린샷과 HTML을 저장해서 실제 페이지 구조를 확인한다.
"""

import os
import sys
from datetime import date, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright

WORKTHRU_URL = os.getenv("WORKTHRU_URL", "https://portal.bodyfriend.co.kr/approval/work/apprlist/listApprReference.do")
WORKTHRU_ID = os.getenv("WORKTHRU_ID", "qkrrudxkr77")
WORKTHRU_PW = os.getenv("WORKTHRU_PW", "body123@")

OUT_DIR = Path("debug_output")
OUT_DIR.mkdir(exist_ok=True)


def save(page, name: str):
    page.screenshot(path=str(OUT_DIR / f"{name}.png"), full_page=True)
    (OUT_DIR / f"{name}.html").write_text(page.content(), encoding="utf-8")
    print(f"  → 저장됨: debug_output/{name}.png / .html")


def run():
    with sync_playwright() as p:
        # headless=False: 브라우저 창을 띄워서 눈으로 확인 가능
        browser = p.chromium.launch(headless=False, slow_mo=500)
        page = browser.new_page()

        print("1) 워크쓰루 접속 중...")
        page.goto(WORKTHRU_URL, wait_until="networkidle", timeout=30000)
        save(page, "01_initial")
        print(f"   현재 URL: {page.url}")

        # 로그인 폼 탐색
        print("2) 로그인 시도...")
        inputs = page.query_selector_all("input")
        print(f"   발견된 input 개수: {len(inputs)}")
        for el in inputs:
            print(f"     name={el.get_attribute('name')!r}  type={el.get_attribute('type')!r}  id={el.get_attribute('id')!r}")

        # 일반적인 로그인 필드 시도
        logged_in = False
        for id_sel in ["input[name='userId']", "input[id='userId']", "input[name='id']", "input[id='id']", "input[type='text']"]:
            try:
                page.fill(id_sel, WORKTHRU_ID, timeout=2000)
                print(f"   ID 입력: {id_sel}")
                logged_in = True
                break
            except Exception:
                continue

        for pw_sel in ["input[name='userPwd']", "input[id='userPwd']", "input[name='password']", "input[type='password']"]:
            try:
                page.fill(pw_sel, WORKTHRU_PW, timeout=2000)
                print(f"   PW 입력: {pw_sel}")
                break
            except Exception:
                continue

        for btn_sel in ["button[type='submit']", "input[type='submit']", "button:has-text('로그인')", ".btn-login"]:
            try:
                page.click(btn_sel, timeout=2000)
                print(f"   로그인 버튼 클릭: {btn_sel}")
                break
            except Exception:
                continue

        page.wait_for_load_state("networkidle")
        save(page, "02_after_login")
        print(f"   로그인 후 URL: {page.url}")

        # 목록 페이지로 이동
        print("3) 목록 페이지 접근...")
        if page.url != WORKTHRU_URL:
            page.goto(WORKTHRU_URL, wait_until="networkidle")
        save(page, "03_list_page")

        # 날짜 필드 탐색
        print("4) 날짜 입력 필드 탐색...")
        today = date.today()
        start = today - timedelta(days=7)
        inputs = page.query_selector_all("input")
        for el in inputs:
            name = el.get_attribute("name") or ""
            el_id = el.get_attribute("id") or ""
            el_type = el.get_attribute("type") or ""
            placeholder = el.get_attribute("placeholder") or ""
            if any(k in (name + el_id + placeholder).lower() for k in ["date", "dt", "from", "to", "start", "end", "기간", "일자"]):
                print(f"     날짜 후보: name={name!r} id={el_id!r} type={el_type!r} placeholder={placeholder!r}")

        # 검색 버튼 탐색
        print("5) 검색 버튼 탐색...")
        buttons = page.query_selector_all("button, input[type='submit'], input[type='button']")
        for btn in buttons:
            txt = (btn.inner_text() or btn.get_attribute("value") or "").strip()
            cls = btn.get_attribute("class") or ""
            if txt or "search" in cls.lower() or "btn" in cls.lower():
                print(f"     버튼: text={txt!r} class={cls!r}")

        # 테이블 구조 탐색
        print("6) 테이블 구조 탐색...")
        tables = page.query_selector_all("table")
        print(f"   테이블 개수: {len(tables)}")
        for i, tbl in enumerate(tables):
            ths = tbl.query_selector_all("th")
            header_texts = [th.inner_text().strip() for th in ths]
            trs = tbl.query_selector_all("tbody tr")
            print(f"   테이블[{i}] - 헤더: {header_texts} / tbody 행수: {len(trs)}")

        # 검색 실행 시도
        print("7) 검색 실행 시도...")
        for sel in ["button.btn-search", "input[value='검색']", "button:has-text('검색')", "#btnSearch", "a:has-text('검색')"]:
            try:
                page.click(sel, timeout=2000)
                page.wait_for_load_state("networkidle")
                print(f"   검색 클릭: {sel}")
                break
            except Exception:
                continue

        save(page, "04_after_search")

        print("8) 검색 후 테이블 재탐색...")
        tables = page.query_selector_all("table")
        print(f"   테이블 개수: {len(tables)}")
        for i, tbl in enumerate(tables):
            ths = tbl.query_selector_all("th")
            header_texts = [th.inner_text().strip() for th in ths]
            trs = tbl.query_selector_all("tbody tr")
            print(f"   테이블[{i}] - 헤더: {header_texts} / tbody 행수: {len(trs)}")
            if trs:
                first_tr = trs[0]
                tds = first_tr.query_selector_all("td")
                print(f"     첫 행 셀값: {[td.inner_text().strip() for td in tds]}")

        print("\n완료. debug_output/ 폴더의 스크린샷과 HTML을 확인하세요.")
        input("엔터를 누르면 브라우저를 닫습니다...")
        browser.close()


if __name__ == "__main__":
    run()
