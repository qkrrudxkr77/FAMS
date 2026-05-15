# -*- coding: utf-8 -*-
"""
웹 캐시 대시보드 금융상품 크롤러.

경로: 맞춤보고서 - 자금일보 - 자금현황 - 3. 금융상품외(가용): 인출가능상품
"""

import asyncio
from datetime import date
from typing import Optional
from playwright.async_api import async_playwright, Page
from bs4 import BeautifulSoup


async def crawl_financial_products(
    username: str = "mjsong@bodyfriend.co.kr",
    password: str = "7979"
) -> list[dict]:
    """
    웹 캐시 대시보드에서 금융상품 데이터 추출.

    반환: [{
        "product_code": "상품코드",
        "company_name": "한국투자증권",
        "product_name": "IMA 금융상품",
        "amount": 1000000.0,
        "original_maturity_date": date(2026, 12, 25),
    }, ...]
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            # 1. 로그인 페이지 접근
            await page.goto("https://www.wdashboard.co.kr/cbrd_main.act", wait_until="networkidle")

            # 2. ID/PW 입력 (페이지 구조에 따라 수정 필요)
            await page.fill("input[name='userId']", username)
            await page.fill("input[name='password']", password)
            await page.click("button:has-text('로그인')")
            await page.wait_for_load_state("networkidle")

            # 3. 맞춤보고서 → 자금일보 → 자금현황 네비게이션
            # 메뉴 클릭 (구조에 따라 선택자 조정)
            await page.click("text=맞춤보고서")
            await page.wait_for_timeout(500)

            await page.click("text=자금일보")
            await page.wait_for_timeout(500)

            await page.click("text=자금현황")
            await page.wait_for_load_state("networkidle")

            # 4. 금융상품 섹션까지 스크롤
            await page.evaluate("""
                () => {
                    const text = document.body.innerText;
                    if (text.includes('3. 금융상품외')) {
                        const elem = Array.from(document.querySelectorAll('*'))
                            .find(e => e.textContent.includes('3. 금융상품외'));
                        if (elem) elem.scrollIntoView();
                    }
                }
            """)
            await page.wait_for_timeout(1000)

            # 5. 현재 HTML 파싱 (테이블 구조 파악)
            html = await page.content()
            products = _parse_financial_table(html)

            if not products:
                print("⚠️ 금융상품 데이터를 찾지 못했습니다. 페이지 구조를 다시 확인하세요.")
                print(f"페이지 소스 길이: {len(html)} bytes")
                # 디버그: 페이지 텍스트 일부 출력
                soup = BeautifulSoup(html, 'html.parser')
                text_sample = soup.get_text()[:500]
                print(f"페이지 텍스트 샘플:\n{text_sample}")

            return products

        finally:
            await context.close()
            await browser.close()


def _parse_financial_table(html: str) -> list[dict]:
    """
    금융상품 테이블 파싱.
    웹 대시보드의 실제 테이블 구조에 맞춰 파싱 로직 구현.
    """
    soup = BeautifulSoup(html, 'html.parser')
    products = []

    # 테이블 찾기 (구조에 따라 선택자 조정)
    # 예상: <table class="financial-product-table"> 또는 특정 ID
    table = soup.find('table', class_=['financial', 'product', 'table'])

    if not table:
        # 다른 선택자 시도
        table = soup.find('table', id=['product_table', 'financial_table'])

    if not table:
        # 모든 테이블 중에서 "금융상품" 텍스트 포함된 것 찾기
        for t in soup.find_all('table'):
            if '금융상품' in t.get_text() or '종료일' in t.get_text():
                table = t
                break

    if not table:
        return []

    # tbody 찾기
    tbody = table.find('tbody')
    if not tbody:
        tbody = table

    rows = tbody.find_all('tr')

    for row in rows[1:]:  # 헤더 행 제외
        cells = row.find_all('td')
        # 실제 테이블 구조: 은행(0) 계좌명(1) 상품명(2) 전일잔액(3) 증가(4) 감소(5) 당일잔액(6) 비고(7)
        if len(cells) < 8:
            continue

        try:
            company_name = cells[0].get_text(strip=True)        # 은행 (표시에 사용)
            account_name = cells[1].get_text(strip=True)        # 계좌명 (표시에 사용)
            product_name_raw = cells[2].get_text(strip=True)    # 상품명 (코드 생성에만 사용)
            amount_str = cells[6].get_text(strip=True)          # 당일잔액
            bigo_str = cells[7].get_text(strip=True)            # 비고 (만기일 포함)

            # 표시명은 계좌명을 사용: "농협 현대해상화재보험 금융상품 수령"
            product_name = account_name

            # 금액 파싱 (쉼표 제거)
            amount = float(amount_str.replace(',', '').strip())

            # 비고에서 만기일 추출 ("START~END(설명)" 형식)
            maturity_date = _parse_date_from_bigo(bigo_str)
            if not maturity_date:
                continue

            # 상품 코드 생성 (회사+계좌+상품 조합으로 유니크하게)
            product_code = f"{company_name}_{account_name}_{product_name_raw}".replace(' ', '')

            products.append({
                "product_code": product_code,
                "company_name": company_name,
                "product_name": product_name,
                "amount": amount,
                "original_maturity_date": maturity_date,
            })

        except (IndexError, ValueError):
            continue

    return products


def _parse_date_from_bigo(bigo: str) -> Optional[date]:
    """
    비고 컬럼에서 만기일(종료일) 추출.
    형식 예:
      "2024.06.21~2027.06.21(2년남 3년만기)"  → 2027.06.21
      "2026.02.02~2026.12.02, 수익률 연 9.2%" → 2026.12.02
      "2026.04.07~2028.10.10, 수익률 연 4%"   → 2028.10.10
    """
    if not bigo:
        return None
    if '~' in bigo:
        after = bigo.split('~', 1)[1].strip()
        # "(", ",", " " 이전까지 날짜 부분만 추출
        for sep in ['(', ',', ' ']:
            if sep in after:
                after = after.split(sep)[0].strip()
        return _parse_date(after)
    # "~" 없으면 전체에서 날짜 파싱 시도
    candidate = bigo.split('(')[0].split(',')[0].strip()
    return _parse_date(candidate)


def _parse_date(date_str: str) -> Optional[date]:
    """
    날짜 문자열 파싱.
    예: "2026.12.25", "12.25" (연도는 현재 년도 또는 내년)
    """
    if not date_str:
        return None

    date_str = date_str.strip()
    parts = date_str.split('.')

    try:
        if len(parts) == 3:  # YYYY.MM.DD
            year = int(parts[0])
            month = int(parts[1])
            day = int(parts[2])
        elif len(parts) == 2:  # MM.DD (연도는 현재 또는 내년)
            from datetime import datetime
            month = int(parts[0])
            day = int(parts[1])
            current_date = datetime.now().date()
            # 만기일이 현재 날짜보다 과거면 내년
            year = current_date.year
            test_date = date(year, month, day)
            if test_date < current_date:
                year += 1
        else:
            return None

        return date(year, month, day)

    except (ValueError, IndexError):
        return None
