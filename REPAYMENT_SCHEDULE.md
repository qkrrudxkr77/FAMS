# 상환/수령 스케줄 기능

## 개요

FAMS 9090 앱의 상환/수령 스케줄 기능은 재무회계팀의 자금 흐름(대출 상환, 카드 결제, 금융상품 만기)을 한눈에 관리할 수 있는 메뉴입니다. 

현재 1차 범위: **신차입금현황.xlsx 업로드 → 상환 스케줄 목록/캘린더 표시**

---

## 엑셀 구조

### 입력 파일: `新차입금현황(BF&MC)_202605.xlsx`

- **비밀번호**: `7`
- **시트명**: `상환스케줄` (정확한 이름 필수)
- **구조**: 가로 배치 (블록 반복)

#### 블록 레이아웃 (각 차입금당 6 데이터 행 + 1 빈 행)

```
R(n)   A=대출명("농협은행 140억 대출")  B="회차"      C=빈     D~=1,2,3,...
R(n+1) A=빈                              B="납입일"   C=실행일  D~=회차별 납입일
R(n+2) A=빈                              B="원금"     C=초기액  D~=회차별 원금
R(n+3) A=빈                              B="이자"     C=빈      D~=회차별 이자
R(n+4) A=빈                              B="원리금"   C=빈      D~=회차별 원리금
R(n+5) A=빈                              B="미회수원금" C=초기  D~=회차별 미회수원금
R(n+6) (빈 행 구분자)
```

- **블록 식별**: `A != None AND B == "회차"` 인 행
- **회차 데이터 시작**: D 컬럼(index 4)부터 (**C 컬럼은 스킵**, 대출 실행일/초기액)
- **회차 개수**: 블록마다 0~72회차 다양
- **중복 대출명**: 가능 (예: "농협은행 70억 대출" 2건 = 별개 인스턴스 → `block_index`로 구분)

---

## 데이터 모델

### `LoanRepayment` 테이블

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | Integer (PK) | 자동 증분 |
| `block_index` | Integer | 엑셀 내 블록 순서 (중복 대출명 구분용) |
| `loan_name` | String(200) | 대출명 (예: "농협은행 140억 대출") |
| `installment_no` | Integer | 회차 (1, 2, 3, ...) |
| `original_due_date` | Date | 엑셀 원본 납입일 |
| `adjusted_due_date` | Date | 영업일 조정 후 납입일 (주말/공휴일 → 다음 영업일) |
| `principal` | Decimal(18,2) | 원금 |
| `interest` | Decimal(18,2) | 이자 |
| `total_payment` | Decimal(18,2) | 원리금 (원금 + 이자) |
| `remaining_principal` | Decimal(18,2) | 미회수 원금 |
| `uploaded_at` | DateTime | 업로드 시간 |

**인덱스**:
- `(adjusted_due_date)` — 캘린더 조회 최적화
- `(loan_name, block_index)` — 대출별 필터 최적화

---

## 파일 구조

### 백엔드 (`overseas_trip/`)

| 파일 | 역할 |
|------|------|
| `models.py` | `LoanRepayment` 모델 정의 |
| `crud.py` | DB 조회/저장 함수 |
| `excel_parser.py` | 신차입금현황 엑셀 파싱 |
| `holiday_util.py` | 영업일 조정 유틸 (`next_business_day`) |
| `main.py` | FastAPI 라우트 4개 |
| `templates/repayment_schedule.html` | 목록/캘린더 UI |
| `templates/index.html` | 사이드바 메뉴 추가 |

### 핵심 함수

#### `excel_parser.py`

```python
def parse_repayment_schedule(file_bytes: bytes, password: str = "7") -> list[dict]
```

- 신차입금현황 엑셀 → dict 리스트 변환
- 비밀번호 복호화 (msoffcrypto) 또는 일반 파일 로드 모두 지원
- 블록 단위 파싱: `A!=None AND B=="회차"` 행 검색
- C 컬럼 스킵, D 컬럼부터 데이터 추출
- 각 회차마다 dict 반환:
  ```python
  {
    "block_index": int,
    "loan_name": str,
    "installment_no": int,
    "original_due_date": date,
    "principal": float,
    "interest": float,
    "total_payment": float,
    "remaining_principal": float
  }
  ```

#### `holiday_util.py`

```python
def next_business_day(d: date) -> date
```

- 주어진 날짜가 주말(토/일) 또는 공휴일이면 다음 영업일로 조정
- 한국 공휴일 기준 (`holidays.KR()`)
- 예: 2026-05-30(토) → 2026-06-01(월)

#### `crud.py` (상환 스케줄 관련)

```python
replace_all_loan_repayments(db: Session, rows: list[dict]) -> int
```
- 기존 모든 데이터 삭제 후 새 행 일괄 INSERT
- `adjusted_due_date = next_business_day(original_due_date)` 자동 계산

```python
list_loan_repayments(
    db: Session,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    loan_name: Optional[str] = None
) -> list[LoanRepayment]
```
- `adjusted_due_date` 기준 필터 조회

```python
get_loan_repayments_by_month(db: Session, year: int, month: int) -> list[LoanRepayment]
```
- 캘린더용: 해당 월의 모든 항목

```python
get_distinct_loan_names(db: Session) -> list[str]
```
- 필터 드롭다운용: distinct 대출명 (사전순)

### 라우트 (`main.py`)

#### `GET /repayment-schedule`
페이지 렌더 (목록 뷰 기본 표시)
- 컨텍스트:
  - `today_year`, `today_month`: 현재 년/월 (캘린더 초기화용)
  - `loan_names`: 대출명 리스트

#### `POST /api/repayment-schedule/upload`
엑셀 파일 업로드 (multipart)
- 요청: `multipart/form-data` with `file` field
- 응답:
  ```json
  {
    "success": true,
    "inserted_count": 2300
  }
  ```
- 에러:
  ```json
  {
    "success": false,
    "message": "시트 '상환스케줄'가 엑셀에 없습니다."
  }
  ```

#### `GET /api/repayment-schedule`
목록 JSON (필터 지원)
- 쿼리: `?from_date=2026-05-01&to_date=2026-06-30&loan_name=농협은행`
- 응답:
  ```json
  {
    "items": [
      {
        "id": 1,
        "block_index": 1,
        "loan_name": "농협은행 140억 대출",
        "installment_no": 1,
        "original_due_date": "2026-05-15",
        "adjusted_due_date": "2026-05-15",
        "principal": 10000000.0,
        "interest": 500000.0,
        "total_payment": 10500000.0,
        "remaining_principal": 1000000000.0
      }
    ]
  }
  ```

#### `GET /api/repayment-schedule/calendar`
날짜별 그룹 JSON (캘린더용)
- 쿼리: `?year=2026&month=5`
- 응답:
  ```json
  {
    "by_date": {
      "2026-05-15": [
        {
          "id": 1,
          "loan_name": "농협은행 140억 대출",
          "installment_no": 1,
          "total_payment": 10500000.0,
          ...
        }
      ]
    }
  }
  ```

---

## UI 레이아웃

### 페이지 헤더
- 제목: "상환/수령 스케줄"
- 뷰 토글: [목록형] [캘린더형] (기본: 목록형)
- 버튼: "엑셀 업로드" (file input)

### 목록 뷰 (기본)

**구조**: 날짜별 섹션 스크롤 레이아웃

```
━━━━━━━━━━━━━━━━━━━━━━━━
  2026년 5월 15일 오늘
  지출 −                123,456,789 원
━━━━━━━━━━━━━━━━━━━━━━━━
  │ 농협은행 140억 대출 · 1회차
  │                  10,500,000 원
  │
  │ 원금        10,000,000
  │ 이자          500,000
  │ 원리금     10,500,000
  │ 미회수원금  1,000,000,000
  │
━━━━━━━━━━━━━━━━━━━━━━━━
  2026년 5월 16일
  지출 −                 987,654,321 원
━━━━━━━━━━━━━━━━━━━━━━━━
  │ [대출 카드들...]
```

**초기 로드**: 오늘 날짜 섹션으로 자동 스크롤 (없으면 가장 가까운 미래 날짜)

### 캘린더 뷰

**구조**: 월 그리드 (7열 × 5-6행)

- 셀: 날짜, 항목 개수 badge, 총액 미리보기
- 셀 클릭: 우측 사이드 패널에 상세 표시
- 월 네비: [◀ 이전] [오늘] [다음 ▶]
- 오늘 셀: 하늘색 배경
- 선택 셀: 파란 인세트 테두리

---

## 프로세스 플로우

### 1. 엑셀 업로드

```
[사용자]
   ↓
   파일 선택 → POST /api/repayment-schedule/upload
   ↓
[서버]
   ├─ 파일 bytes 읽기
   ├─ parse_repayment_schedule() 호출
   │  ├─ msoffcrypto로 비밀번호 복호화 시도
   │  │  (실패 시 일반 파일로 로드)
   │  ├─ openpyxl로 "상환스케줄" 시트 로드
   │  ├─ 블록 단위 파싱 (B=="회차" 행 검색)
   │  ├─ C 컬럼 스킵, D 컬럼부터 데이터 추출
   │  └─ dict 리스트 반환
   ├─ crud.replace_all_loan_repayments()
   │  ├─ DELETE FROM loan_repayment
   │  ├─ next_business_day() 으로 adjusted_due_date 계산
   │  └─ 일괄 INSERT
   ├─ JSON 응답: {success: true, inserted_count: N}
   └─ 클라이언트 페이지 새로고침
   ↓
[화면] 목록 뷰 새로 로드, 토스트 "N건 등록 완료"
```

### 2. 목록 뷰 로드

```
[사용자] 목록형 버튼 클릭
   ↓
[클라이언트] loadListGrouped() 호출
   ├─ GET /api/repayment-schedule
   ├─ items 배열 수신
   ├─ 날짜별 그룹핑
   │  {
   │    "2026-05-15": [item1, item2],
   │    "2026-05-16": [item3]
   │  }
   ├─ 날짜순 정렬 (sort)
   ├─ 각 섹션 렌더:
   │  - 날짜 헤더 (YYYY년 M월 D일 [오늘])
   │  - "지출 −" 레이블 + 총액
   │  - 개별 대출 카드 (원금/이자/원리금/미회수원금)
   ├─ DOM에 삽입
   └─ 오늘 섹션으로 scrollIntoView()
   ↓
[화면] 오늘 날짜 기준으로 스크롤된 목록
```

### 3. 캘린더 뷰 로드

```
[사용자] 캘린더형 버튼 클릭
   ↓
[클라이언트] loadCalendar() 호출
   ├─ 현재 년/월 기준
   ├─ GET /api/repayment-schedule/calendar?year=2026&month=5
   ├─ by_date 객체 수신
   ├─ 월 그리드 렌더
   │  ├─ 첫 날짜의 weekday 계산 (0=일)
   │  ├─ 이전 달 날짜로 시작 행 채우기
   │  ├─ 이번 달 날짜 (1~31)
   │  │  ├─ 항목 있으면 badge + 총액 표시
   │  │  ├─ 오늘이면 배경색 표시
   │  │  ├─ 클릭 → selectDate(key) → renderDayPanel()
   │  └─ 다음 달 날짜로 끝 행 채우기 (7의 배수)
   └─ DOM에 삽입
   ↓
[화면] 이번 달 캘린더 + 우측 사이드 패널
```

### 4. 영업일 조정

```
업로드 시점:
  original_due_date = 엑셀 원본 납입일 (예: 2026-05-30 토요일)
         ↓
   next_business_day(2026-05-30)
         ↓
   2026-05-30이 토요일? → 예 ➜ 2026-05-31 일요일 확인
   2026-05-31이 일요일? → 예 ➜ 2026-06-01 월요일 확인
   2026-06-01이 영업일? → 예 ➜ adjusted_due_date = 2026-06-01
```

- UI 표시: `adjusted_due_date` 기준 (영업일)
- DB 보존: `original_due_date` (원본)
- 공휴일 변경 시: 재계산 함수 필요 (미구현, 2차 예정)

---

## 에러 처리

### 엑셀 업로드 실패 시나리오

| 상황 | 에러 메시지 | 원인 |
|------|-----------|------|
| 시트 없음 | "시트 '상환스케줄'가 엑셀에 없습니다." | 시트명 오타 또는 워크북 손상 |
| 블록 구조 이상 | "엑셀에서 회차 데이터를 찾지 못했습니다." | 헤더 행 라벨 검증 실패 (납입일/원금/이자/원리금/미회수원금) |
| 파일 손상 | (msoffcrypto 오류) | ZIP 구조 손상 또는 호환성 문제 |

### 인증

모든 라우트는 `auth_middleware`로 보호됨:
- 쿠키 없음 → 401 응답 (스타일된 인증 페이지)
- JWT 토큰 검증 필요

---

## 데이터 통계

### 샘플 파일 (`新차入金現況(BF&MC)_202605.xlsx`)

| 항목 | 수치 |
|------|------|
| 대출 블록 수 | 95개 |
| 총 회차 수 | 2,300+ |
| 대출명 종류 | ~50개 |
| 최대 회차 | ~72회차 |
| 기간 | ~2026-05 ~ 2027-12 |

---

## 향후 개선 (2차 이후)

- [ ] 카드 결제대금 크롤링 (자동 반영)
- [ ] 금융상품 만기 데이터 수동 입력/관리
- [ ] 웍스 알림 연동
- [ ] 공휴일 변경 시 일괄 재계산 함수
- [ ] 상환 현황 대시보드 (완료율, 누적액 등)
- [ ] 대출별 상환 시뮬레이션 (예상 이자)

---

## 의존성

```
openpyxl==3.1.5              # 엑셀 파싱
msoffcrypto-tool==5.4.2      # 비밀번호 복호화
sqlalchemy>=2.0              # ORM
fastapi>=0.104               # 웹 프레임워크
holidays>=0.34               # 한국 공휴일
```

---

## 테스트 체크리스트

- [x] 비밀번호 파일 업로드 (원본 엑셀)
- [x] 비밀번호 없는 파일 업로드 (시트 추출 파일)
- [x] 목록 뷰: 날짜별 스크롤, 오늘 자동 포커스
- [x] 캘린더 뷰: 월 네비, 셀 클릭, 패널 표시
- [x] 영업일 조정: 토/일 및 공휴일 → 다음 영업일
- [x] 인증: 쿠키 없음 → 401 페이지
- [x] 전체 교체: 두 번째 업로드 시 이전 데이터 삭제 확인

---

마지막 업데이트: 2026-05-14
