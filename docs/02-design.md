# 02 · 디자인 명세 — AI 투자 브리핑 PoC

> 영역: 프로덕트 디자인 / 프론트엔드 명세
> 원천: `design.md`(Cursor 톤) 리브랜딩 + 기능색·밀도 토큰 신규 정의
> 정합 기준(SSoT): `TECH-DESIGN.md` v3.2 (**DTO·색·키·런타임 정본 = §15 Contract SoT, 충돌 시 §15 우선**) §4 §6 §7 §8 §15 · `00-e2e-flow.md`(BLOCKER G1·G2, HIGH 해소안)
> 스택: FastAPI + Jinja2(SSR) · 바닐라 CSS(토큰 → CSS 변수) · SPA 아님
> 토큰 참조 형식: `design.md`와 동일하게 `{group.token}` 표기 사용

이 문서는 구현자가 그대로 따라 만들 수 있는 수준의 **디자인 시스템 + 화면 레이아웃 + 컴포넌트 스펙**이다.
숫자/상태/필드명은 SSoT의 데이터 모델(§4)·지표 출력(§6)·브리핑 DTO(`00-e2e-flow.md`)에서 가져왔다. 추측한 곳은 없으며, 표시 라벨은 SSoT 문구를 그대로 인용한다.

---

## 0. 디자인 원칙 (SSoT §8 반영)

1. **`design.md` 톤은 텍스트에만.** 헤더·면책·브리핑 내러티브 텍스트는 Cursor의 editorial cream 톤을 그대로 계승. (SSoT §8 "design.md는 헤더·면책·브리핑 내러티브 텍스트에만 적용")
2. **고밀도 수치표는 별도 밀도 서브시스템.** 30종목 표는 `tabular-nums` + 작은 행간. editorial 토큰과 분리. (SSoT §8)
3. **등락/경고 기능색은 신규 정의.** `design.md`에는 `{colors.semantic-success}`·`{colors.semantic-error}`만 있고 주가 등락 전용 색 체계·밀도 토큰이 없음 → 신규 정의가 필요(색 토큰 교체만으론 부족, SSoT §8 명시).
4. **요약 뷰 기본, 펼침으로 상세.** 매일 전체 브리핑이지만 화면은 30초 스캔 가능하게 — "오늘 점검 필요" 종목만 펼침. (SSoT §8)
5. **틀린 숫자가 빈칸보다 위험.** 보류/제외/데이터 준비중은 회색 placeholder로 명시(빈칸 금지). (SSoT §1.6, `00-e2e-flow.md` HIGH-H1)
6. **숫자는 템플릿이 신뢰하는 DTO에서만.** Jinja2는 `BriefingDoc` frozen dataclass 필드만 읽고, LLM 원문을 직접 렌더하지 않는다. (SSoT §7, `00-e2e-flow.md` LOW-L2/BLOCKER G2)

---

## 1. 리브랜딩 (design.md → 투자 대시보드)

### 1.1 교체 매핑

| design.md 원소 | 투자 브리핑 결정 | 근거 |
|---|---|---|
| Cursor Orange `{colors.primary}` #f54e00 | **Brief Teal `{colors.primary}` #0c8599** (제품색, SSoT §15.3) | 등락 빨강(상승)·파랑(하락)과 충돌 않는 청록 CTA. 등락색을 행동색으로 오인 방지 |
| Primary Active #d04200 | **Brief Teal Active `{colors.primary-active}` #0a6e7f** | 누름 상태(Teal 계열, 03 tokens.css `--c-primary-active`와 일치) |
| Cursor 워드마크 | **워드마크 "Ballast"** (한글 병기 "밸러스트", CursorGothic→Inter 400, ink색, 좌측 nav) | §8 워드마크 리브랜딩 |
| AI-timeline 펄(5 pastel) | **신선도·상태 펄로 재용도화**(§5.4) — 색 값은 유지하되 의미를 데이터 신선도/수집상태로 교체 | §8 "타임라인 펄 교체" |
| IDE-mockup 카드 | **종목 카드 / 포트폴리오 카드**로 대체(코드 mockup 없음) | 제품 성격 |

> Cursor Orange는 완전히 제거하고 Brief Teal(#0c8599)로 일원화. 등락색(빨강/파랑)을 CTA로 쓰지 않는다 — 행동 유도와 시장 등락 표시를 색으로 분리(금융 UI 필수). 1차 행동색은 Teal 하나만 유지(design.md "단일 CTA color" 원칙 계승). Indigo는 하락 파랑과 가까워 폐기.

### 1.2 계승 (변경 없음)

- 캔버스 `{colors.canvas}` #f7f7f4 (warm cream, 순백 금지)
- 잉크 `{colors.ink}` #26251e (warm near-black)
- Hairline-only depth (드롭섀도 금지)
- Display weight 400 (editorial, bold 금지) — **단, 수치표/배지는 예외(아래 §3.2)**
- `{rounded.md}` 8px CTA · `{rounded.lg}` 12px 카드
- 80px 섹션 리듬 (`{spacing.section}`)
- 폰트: 본문 **Inter 400**(CursorGothic substitute, letter-spacing -1.5% on display) · 숫자/티커 **JetBrains Mono**(code surface 계승 → 수치표로 재용도)

---

## 2. 신규 기능색 (Finance Semantic Tokens)

`design.md` Semantic 그룹을 확장한다. **등락 전용**과 **상태/경고**를 분리한다. (SSoT §8 "등락 빨강/초록·경고 기능색 신규 정의")

### 2.1 등락 색 (Price Movement) — `{colors.move-*}`

**한국 관습(상승=빨강, 하락=파랑)** 을 채택한다(SSoT §15.3 정본). 주 사용자가 한국인이고 국내 증권앱 관례에 익숙 → 직관 일치. 색 의미는 KR/US 종목 구분 없이 동일 적용(시장별로 뒤집지 않음).

| 토큰 | 값 | 의미 |
|---|---|---|
| `{colors.move-up}` | **#d92d4e** (빨강) | 상승 (+), 양(+) 드리프트 |
| `{colors.move-up-soft}` | #fbe6ec | 상승 배경 |
| `{colors.move-down}` | **#1971c2** (파랑) | 하락 (−), 음(−) 드리프트 |
| `{colors.move-down-soft}` | #e7f0fb | 하락 배경 |
| `{colors.move-flat}` | #807d72 (= muted) | 0.0% / 변동 미미 / `micro_weight_floor` 미만 억제 |

> ⚠️ 자산배분 바(§5.5)는 등락색 비사용 → 별도 `{colors.alloc-*}` 중립 토큰. 등락색은 수치/방향만.

> 등락색은 **수치/방향 표시에만**. CTA·링크·헤더에 절대 사용 금지(design.md "secondary action color 금지" 원칙 계승). 등락색은 텍스트색 + 좌측 4px 보더 + soft 배경으로만 노출.

### 2.2 상태/경고 색 (Status) — `{colors.status-*}`

브리핑·게이트·신선도 상태용. 등락색과 시각적으로 구분(채도 낮춤).

| 토큰 | 값 | 의미 (SSoT 출처) |
|---|---|---|
| `{colors.status-warn}` | #b8740f (warm amber) | 경고: 5/25 플래그, N일 연속 fallback, satellite 30% 초과 (§6 ①②, §8) |
| `{colors.status-warn-soft}` | #fbf0dd | 경고 배경 |
| `{colors.status-hold}` | #807d72 (muted) | 보류: fx 결측 US 보류, row 0건 "데이터 준비중" (§7 게이트, H1) |
| `{colors.status-hold-soft}` | #efeee8 (= surface-strong) | 보류 placeholder 배경 |
| `{colors.status-degrade}` | #8a7fc2 (muted lavender) | degrade 라벨: `per_pctile_5y` NULL "5년 워밍업 중" (H1) |
| `{colors.status-info}` | #0c8599 (= primary Teal) | 정보 배너: "초기 적재중", BACKFILL |
| `{colors.status-fail}` | #b3243f (deep red, 채도↓) | 처리 실패 카드 (LLM 미매칭/중복, G2) — 상승 빨강과 채도로 구분 |

> `move-flat`·`status-hold`는 같은 muted 계열이나 용도 분리(전자=등락 0, 후자=데이터 없음). 라벨로 구분.

---

## 3. 밀도 토큰 (Density Subsystem)

30종목 고밀도 수치표 전용. editorial 텍스트 토큰과 **물리적으로 분리된 CSS 클래스 네임스페이스**(`.dense-*`)로 운영. (SSoT §8 "고밀도 수치표는 별도 데이터 밀도 서브시스템")

### 3.1 밀도 spacing — `{density.*}`

| 토큰 | 값 | 용도 |
|---|---|---|
| `{density.row-h}` | 36px | 테이블 행 높이(터치 타깃 below — 데스크톱 우선 PoC) |
| `{density.row-h-touch}` | 44px | 모바일 행 높이(WCAG AA) |
| `{density.cell-pad-x}` | 12px | 셀 좌우 패딩 |
| `{density.cell-pad-y}` | 8px | 셀 상하 패딩 |
| `{density.line}` | 1.35 | 수치 행간(본문 1.5보다 타이트) |
| `{density.gap}` | 8px | 카드 간 gap(editorial 16–24px보다 좁게) |

### 3.2 밀도 typography — `{typography.dense-*}`

JetBrains Mono · `font-variant-numeric: tabular-nums` 강제(자리수 흔들림 방지). display 400 원칙의 **예외 구역**.

| 토큰 | Size | Weight | LH | 특성 | 용도 |
|---|---|---|---|---|---|
| `{typography.dense-num}` | 14px | 500 | 1.35 | tabular-nums, JetBrains Mono | 평가액·비중·드리프트 셀 |
| `{typography.dense-num-strong}` | 14px | 600 | 1.35 | tabular-nums | 강조 수치(목표 vs 현재 차이) |
| `{typography.dense-ticker}` | 13px | 500 | 1.35 | JetBrains Mono, letter-spacing 0 | canonical_ticker 표시 |
| `{typography.dense-label}` | 11px | 600 | 1.4 | uppercase, 0.6px tracking | 컬럼 헤더(= caption-uppercase 재사용) |
| `{typography.dense-name}` | 14px | 400 | 1.35 | Inter | 종목명(name) |

```css
/* 모든 수치 셀에 강제 */
.dense-num, .dense-num-strong, .dense-ticker {
  font-family: "JetBrains Mono", monospace;
  font-variant-numeric: tabular-nums;
}
```

---

## 4. 화면 레이아웃

라우트는 SSoT §8을 그대로 따른다.

| 라우트 | 템플릿 | 메서드 |
|---|---|---|
| `GET /` | `dashboard.html` | 브리핑 표시 (오늘 `briefing_date` 중 `MAX(created_at)` row) |
| `GET /holdings` · `POST /holdings` | `holdings.html` | 보유종목 입력/편집 |
| `GET /settings` · `POST /settings` | `settings.html` | 월 적립금·기준통화·한도·밴드 |
| `POST /api/regenerate` | — | 개발용, 127.0.0.1 한정(UI 버튼은 settings 하단에만) |

공통 셸: 좌측 워드마크 + nav(대시보드 / 보유자산 / 설정), height 64px(`top-nav` 계승), 배경 `{colors.canvas}`. 최대 콘텐츠 폭 1200px(`design.md` 계승). 모든 페이지 하단에 면책 블록(§5.6) 고정.

### 4.1 대시보드 (`GET /`)

수직 스택, 위→아래 스캔. (SSoT §8 순서: 신선도 배지 → 포트폴리오 요약 → 종목 카드 → 리밸런싱/DCA)

```
┌─ top-nav (워드마크 · 대시보드/보유자산/설정) ───────────────┐
├─ [전역 배너 zone] (조건부)                                   │
│   · "초기 적재중" 배너 (day-0, status=BACKFILL 글로벌)  H1   │
│   · "데이터 미갱신" 배너 (KR·US·FX 모두 미갱신 → 생성거부) §7 │
│   · "USD 자산 일괄 보류 · 1층 배분 산출 보류" 배너 (fx FAIL) H4│
├─ [신선도 배지 행] freshness-badge (§5.4)                     │
│   시세: 어제 / 펀더멘털: 3개월 전(report_date) / 환율: 어제  │
├─ [포트폴리오 요약 카드] portfolio-summary-card (§5.2)        │
│   · 1층: 주식 vs 현금 자산배분 바 (asset-alloc-bar)          │
│   · 2층: 코어(ETF) vs 새틀(개별주) 바                        │
│   · 포트폴리오 코멘트(LLM 호출2 문장, 수치는 코드 주입)      │
├─ [오늘 점검 필요] 펼침 기본 (요약뷰, §6 인터랙션)            │
│   · 5/25 플래그·신고저 종목 카드만 펼침                      │
├─ [전체 종목] 접힘 기본 → 클릭 시 펼침                        │
│   · security-card (§5.1) 리스트 또는 dense-table(§5.5 토글) │
│   · 보류/제외/데이터 준비중 종목은 placeholder 카드          │
├─ [리밸런싱 / DCA] rebalance-card (§5.3)                      │
│   · 리밸런싱 검토구간 + "목표 회복 신규자금 후보"            │
├─ [면책 블록] disclaimer-block (§5.6) 고정                    │
└──────────────────────────────────────────────────────────────┘
```

**데이터 출처:** 템플릿은 `BriefingDoc` DTO(§7=§15.2) 하나만 신뢰. 카드 렌더는 `doc.securities[]`·`doc.asset_allocation`·`doc.portfolio_comment`·`doc.holds_excluded[]`·`doc.disclaimer`·`doc.as_of`·`doc.regime_label`·`doc.banner`로 분기.

### 4.2 보유자산 (`/holdings`)

테이블 + 인라인 편집 폼. dense subsystem 적용. 자산군별 그룹 헤더(개별주 / ETF / 달러현금 — SSoT §4 "화면은 개별주/ETF/달러로 표시").

```
┌─ 보유자산                                  [+ 종목 추가]  ──┐
│  그룹: 개별주 (stock)                                       │
│   ┌──────────────────────────────────────────────────────┐ │
│   │ 티커     종목명      수량   평단(현지)  통화  목표비중  ⋮│ │ ← dense-table
│   │ 005930   삼성전자    100    71,000 KRW  KRW   [auto]   ⋮│ │
│   └──────────────────────────────────────────────────────┘ │
│  그룹: ETF (etf) — core/satellite 자동판정 표시             │
│   │ VOO     S&P500 ETF  10     —          USD   core      ⋮│ │
│  그룹: 달러현금 (cash, manual)                              │
│   │ —       USD 예금     —      —          USD   $5,000    ⋮│ │ ← value_manual
└──────────────────────────────────────────────────────────────┘
```

**입력 폼 필드 (POST /holdings, SSoT §4 holdings 스키마):**

| 필드 | 입력 컴포넌트 | 비고 |
|---|---|---|
| `tracking` | 라디오 `auto` / `manual` | manual 선택 시 quantity 숨김, value_manual+ccy 노출 |
| `canonical_ticker` | text-input (auto만) | `005930`, `VOO`, `BRK.B` 형식 |
| `name` | text-input | |
| `quantity` | number (auto만) | |
| `value_manual` + `ccy` | number + select(KRW/USD) (manual만) | 달러예금 |
| `avg_price` | number (선택, auto) | **현지통화 참고표시만** — 손익/수익률 표시 안 함(SSoT M-avg_price gap: PoC 범위 밖) |
| `category` | select `자동판정` / `core` / `satellite` | 기본 "자동판정"; 사용자 명시 시 사용자값 우선(H2) |
| `target_pct` | number (선택) | **수동/자동 배타**: 일부만 입력 시 POST validation reject(H3) |

**category 자동판정 로직 표시(H2, SSoT §6):** 저장 시 `tickers.py`의 코어 화이트리스트 frozenset 매칭 → 매칭=core, 미매칭 ETF=NULL("분류 미정—확인 필요" 칩), 개별주=satellite. 결과를 `holdings.category`에 영속화. UI는 자동판정 결과를 회색 칩으로, 사용자 명시값은 잉크 칩으로 구분.

**POST 검증 피드백(SSoT §6 "target_pct 합계 검증 + 수동/자동 배타"):**
- 수동 목표비중 혼재(일부만 입력) → `{colors.semantic-error}` 인라인 에러 "목표비중은 전부 수동 또는 전부 자동만 허용".
- 전부 수동인데 합 ≠ 100% → "합계 100%가 아닙니다 (현재 NN%)".

### 4.3 설정 (`/settings`)

단순 폼 (SSoT §4 settings 키). 한 컬럼.

| 라벨 | key | 기본값 |
|---|---|---|
| 월 적립금 | `monthly_contribution` | 0 |
| 기준통화 | `base_currency` | `KRW` |
| 새틀라이트 한도(%) | `satellite_limit_pct` | 30 |
| 리밸런싱 밴드(절대 %p) | `rebalance_band_abs` | 5 |
| 리밸런싱 밴드(상대 %) | `rebalance_band_rel` | 25 |
| 미세비중 하한(%p) | `micro_weight_floor` | 1.0 |
| USD 비중 임계(1층 보류 트리거 %) | `usd_cash_gate_threshold` | 5.0 |

> settings 키·기본값 정본 = §15.5.

하단: 개발용 "지금 재생성"(`POST /api/regenerate`) 버튼 — 127.0.0.1 한정.

---

## 5. 컴포넌트 스펙

### 5.1 종목 카드 `security-card`

종목별 브리핑 1장. 펼침/접힘 단위. (SSoT §6 ③④⑤ 출력 + §7 호출1 문장)

- 컨테이너: `feature-card` 계승 — bg `{colors.surface-card}`, 1px `{colors.hairline}`, `{rounded.lg}` 12px, padding 20px.
- 좌측 4px 상태 보더: 5/25 플래그면 `{colors.status-warn}`, 정상이면 hairline.

```
┌─[4px warn 보더] ─────────────────────────────────────┐
│ 005930  삼성전자          ▲ +1.2%        [▾ 펼침]      │ ← dense-ticker · dense-name · move-up
│ ─────────────────────────────────────────────────── │
│ ③밸류에이션: 5년 하위 18%ile                          │ ← §6 ③ 양면 라벨 그대로
│   (저평가 또는 디레이팅 — 펀더멘털 확인)               │   chip: per_pctile band
│ ④추세: 52주 고점 대비 −8% · 200SMA 위 (맥락용)        │ ← §6 ④ "매매신호 아님"
│ ⑤레짐: KOSPI PBR 0.95 (역사적 하단)                   │ ← §6 ⑤ 한 줄
│ ─────────────────────────────────────────────────── │
│ [LLM 문장] 투자포인트 내러티브 (body-md, editorial)    │ ← 호출1 content, 수치 없음
└──────────────────────────────────────────────────────┘
```

**필드 매핑(`doc.securities[i]`, 모두 코드 주입 수치 + LLM 문장):**

**필드명 정본 = §15.2 `SecurityCard`.** 레짐은 카드별이 아니라 **top-level `doc.regime_label`**(§15.2)이라 카드에서는 헤더에서 1회 렌더한 값을 참조만 한다.

| UI 요소 | DTO 필드 (§15.2) | 타입 | 출처 |
|---|---|---|---|
| 식별자 | `canonical_ticker` | str | §4 / G2 echo(LLM이 식별자만 echo) |
| 종목명 | `name` | str | holdings |
| 등락 | `change_pct` | float\|None | 코드 계산(현재 평가용 `close_raw`) |
| 밸류 라벨 | `valuation_label` | str | §6 ③ (NULL→"5년 워밍업 중(절대 PER만)" degrade, H1) |
| 밸류 percentile | `valuation_pctile` | float\|None | §6 ③, NULL이면 `status-degrade` 칩(warmup) |
| 추세 | `week52_pos` · `sma200_gap` | float\|None | §6 ④ |
| 레짐 | (top-level `doc.regime_label`) | str | §6 ⑤ — 카드별 아님 |
| 코멘트/추세문장/포인트 | `comment` · `trend_note` · `investment_points` | str·str·list[str] | §7 호출1 (LLM 문장, 금지어 린터 통과분) |
| 상태 | `status` | enum | §15.4: `ok`\|`data_pending`\|`fx_held`\|`warmup`\|`failed`(아래) |

**상태별 변형(§15.4):**
- `data_pending`(row 0건) / `fx_held`(fx FAIL US 종목): 카드 흐림 + `{colors.status-hold}` 칩 "데이터 준비중 · 비중 미산출"(H1). 수치 placeholder "—".
- `warmup`(`valuation_pctile` NULL/백필 중): 밸류 줄만 `status-degrade` 칩 "5년 워밍업 중(절대 PER만)".
- `failed`(LLM 미매칭/중복): `fail-card`(§5.7) + `holds_excluded`에 등장.

### 5.2 포트폴리오 요약 카드 `portfolio-summary-card`

자산배분 2층 + 코멘트. (SSoT §6 ①② + §4 통화정규화)

- 컨테이너: `feature-card`, padding 24px.
- 코멘트: §7 호출2 LLM 문장(editorial body-md), 수치 슬롯은 코드 주입.

### 5.3 리밸런싱/DCA 카드 `rebalance-card`

- 제목 "리밸런싱 검토구간"(단정 표현 금지 — §12 금지어).
- 5/25 플래그 종목/그룹 목록 + 현재% → 목표% (dense-num).
- DCA: "목표 회복 신규자금 후보"(SSoT §6 ⑥ 표현 강제 — "추가매수 추천" 금지). 펀더멘털 게이트 미통과+하위는 "물타기 위험—제외" 라벨(`status-warn`).
- 자동 목표비중 종목은 "참고용" 칩(`status-info`), 수동 목표만 강한 "리밸런싱" 강조(SSoT §6).

### 5.4 신선도 배지 `freshness-badge` (타임라인 펄 재용도)

`design.md` 타임라인 pastel 펄을 **신선도 상태 펄**로 재정의(§1.1). 펄 모양(`{rounded.pill}`, `{typography.caption-uppercase}`) 계승, 의미만 교체.

배지 입력 계약(`00-e2e-flow.md` LOW-L1):
- 시세 = `MAX(price_snapshot.trade_date)` vs 기대거래일(`calendar.py`)
- 펀더멘털 = `report_date`
- 환율 = `MAX(fx_snapshot.trade_date)`
- 포트폴리오 배지 = 종목별 최악(최고령)값 집계

| 펄 (color 재용도) | 상태 | 라벨 예 |
|---|---|---|
| `timeline-grep`(mint) | 당일/기대일 일치 | "시세: 최신" |
| `timeline-thinking`(peach) | 1~2일 지연(정상 fallback) | "시세: 어제" |
| `timeline-done`(gold) | 펀더멘털 등 구조적 지연 | "펀더멘털: 3개월 전" |
| `status-warn`(amber) | N일 연속 fallback 경고 블록 | "N일 연속 미갱신" |
| `status-hold`(muted) | 보류(fx FAIL) | "환율: 산출 보류" |

```
[시세: 어제]  [펀더멘털: 3개월 전(report_date)]  [환율: 최신]
```
DTO: `doc.as_of` = `{price, funda, fx}` 3키 고정(§15.2). 최악 등급은 `FreshnessBadge.worst_level`(별도 산출, 03-frontend §4)로 표시.

### 5.5 자산배분 바 `asset-alloc-bar`

수평 스택 바. 1층(주식/현금), 2층(코어/새틀). 등락색 아닌 **중립 + 경고색** 사용(배분은 등락이 아님).

```
1층  주식 ████████████████░░░░ 현금         (주식 78% · 현금 22%)
2층  코어 ███████████░░░░░ 새틀              (코어 71% · 새틀 29%)
                              ↑ 30% 한도선(점선, satellite_limit_pct)
```
- 주식 fill `{colors.alloc-equity}`, 현금 fill `{colors.alloc-cash}`, 코어 `{colors.alloc-core}`, 새틀 `{colors.alloc-sat}`(등락색·timeline 펄 재사용 금지, §15.3). 라벨 dense-num.
- 새틀이 `satellite_limit_pct` 초과 시 새틀 구간 `{colors.status-warn}` + "30% 한도 초과" 칩(SSoT §6 ②).
- **fx FAIL 시(H4):** USD 평가대상(US 종목+USD 현금) 일괄 보류 → USD 비중이 `usd_cash_gate_threshold` 이상이면 **1층 바 전체를 `status-hold` 패턴(빗금)으로 그리고 "1층 배분 산출 보류"** 표시. 분모 왜곡 방지(SSoT §4 "fx 결측 시 US 평가액 산출 거부").
- 1종목/자동목표 엣지: 드리프트·30% 플래그 억제, 바는 그리되 플래그 칩 숨김(SSoT §6 "소수 종목 엣지").

필드(§15.2 `asset_allocation` dict): 1층 `{equity_pct, cash_pct}`(보류 시 `equity_pct` None) + 2층 `{core_pct, satellite_pct, satellite_over_limit: bool}`.

### 5.5b 고밀도 표 `dense-table` (전체 종목 토글 뷰)

종목 카드 리스트의 대안 뷰. SSoT §8 "30종목 고밀도 수치표". 컬럼:

| 컬럼 | 정렬 | 타입 토큰 |
|---|---|---|
| 티커 | left | dense-ticker |
| 종목명 | left | dense-name |
| 평가액(base) | right | dense-num |
| 현재% | right | dense-num |
| 목표% | right | dense-num |
| 드리프트 | right | dense-num-strong + `move-up`/`move-down`/`move-flat` |
| 밸류 밴드 | center | 칩 |
| 플래그 | center | warn 점 |

- 행 높이 `{density.row-h}` 36px, `tabular-nums` 강제.
- 보류 종목 행: `status-hold-soft` 배경 + "데이터 준비중" — 수치 셀 "—"(H1, 0분모 회피).
- 드리프트 부호: +는 `move-up`, −는 `move-down`, `|drift| < micro_weight_floor`는 `move-flat`(억제, SSoT §6 ①).

### 5.6 면책 블록 `disclaimer-block`

모든 페이지 하단 고정. (SSoT §1.5 §7 §12 "면책 고정")

- 컨테이너: `{colors.canvas}`, 상단 1px hairline, padding 24px, `{typography.body-sm}` `{colors.muted}`.
- 내용: `doc.disclaimer`(코드 고정 문자열, LLM 생성 아님). 예: "본 자료는 정보 제공·교육 목적이며 투자 자문이나 매매 권유가 아닙니다. 모든 투자 판단과 책임은 본인에게 있습니다."
- 금지어 린터(§7 (a))가 브리핑 본문을 이미 통과시켰음을 전제 — 면책은 추가 안전망.

### 5.7 처리 실패 카드 `fail-card` (G2)

LLM 응답을 `canonical_ticker`로 holdings에 left-join 시 미매칭/중복/누락 종목용. (`00-e2e-flow.md` BLOCKER G2: "미매칭/중복은 즉시 '처리 실패' 카드")

- bg `{colors.status-fail}` soft(#fbe6ec), 좌측 4px `{colors.status-fail}`.
- "○○ 종목 브리핑 처리 실패 — 다음 갱신 시 재시도"(수치 미표시).
- `doc.holds_excluded[]`(canonical_ticker + reason)로 렌더.

---

## 6. 요약 뷰 펼침/접힘 인터랙션 (SSoT §8)

SSR + 점진적 향상. JS 없이도 동작(details/summary), JS 있으면 부드러운 토글.

| 상태 | 기본 | 트리거 | 근거 |
|---|---|---|---|
| "오늘 점검 필요" 섹션 | **펼침** | — | 5/25 플래그·신고저 종목(SSoT §8) |
| "전체 종목" 섹션 | **접힘** | 헤더 클릭 | 30초 스캔(SSoT §8) |
| 개별 종목 카드 양면 라벨 상세 | **접힘** | 카드 `▾` 또는 hover | "나머지·양면 라벨은 접힘/hover"(SSoT §8) |
| 카드↔표 뷰 | 카드 기본 | 토글 버튼 | 고밀도 표는 옵션 |

구현: `<details>` 네이티브 + `.is-flagged` 클래스로 펼침 강제. 펼침 판정은 §15.2 필드에서 **파생**(별도 `flagged` 필드 없음): `sec.rebalance_flag`(5/25) 또는 `sec.status != 'ok'`(보류/워밍업/실패).

```html
<details {{ 'open' if sec.rebalance_flag or sec.status != 'ok' }}>
  <summary>{{ sec.canonical_ticker }} {{ sec.name }} ...</summary>
  ...상세...
</details>
```

---

## 7. 템플릿 데이터 계약 (`BriefingDoc`, SSoT §7 / G2 / L2)

Jinja2가 신뢰하는 유일한 입력. **DTO 정본 = TECH-DESIGN §15.2 / §15.4**(이 문서는 정의를 중복하지 않고 그대로 따른다 — 충돌 시 §15 우선). `briefing.content_json`은 그 `BriefingDoc`의 JSON 직렬화.

§15.2 요지(디자인이 의존하는 필드):
- `SecurityCard`: 수치(`change_pct`·`current_pct`·`target_pct`·`drift`·`rebalance_flag`·`per`·`pbr`·`div_yield`·`valuation_pctile`·`valuation_label`·`week52_pos`·`sma200_gap`) + `status`(§15.4 5값) + LLM 문장(`comment`·`trend_note`·`investment_points`). 식별자는 `canonical_ticker`·`name`·`instrument`·`asset_class`·`category`.
- `BriefingDoc`: `banner`(전역 배너, 정상시 None) · `regime_label`(top-level 1개) · `as_of`(`{price,funda,fx}` 3키) · `asset_allocation`(1층 `{equity_pct,cash_pct}` + 2층 `{core_pct,satellite_pct,satellite_over_limit}`) · `securities` · `holds_excluded: list[HoldExcluded]`(LLM 미매칭/중복만) · `dca` · `portfolio_comment`(`{rebalance_note,dca_note,weight_note}`) · `disclaimer`.
- `HoldExcluded(canonical_ticker, reason)`.

> 모든 수치 필드는 코드 주입(LLM echo 대조 없음, SSoT §7). LLM은 `comment`·`trend_note`·`investment_points`(=`SecurityLLMOut`)와 `portfolio_comment` 문장, `canonical_ticker` 식별자 echo만 생성. 템플릿은 LLM 원문 string을 직접 렌더하지 않고 이 DTO 필드만 출력 → KeyError 방지(L2). 펼침 판정·1층 보류 등은 위 필드에서 파생(§6, §5.5).

---

## 8. 반응형 (design.md 계승 + 밀도 조정)

| 이름 | 폭 | 변화 |
|---|---|---|
| Mobile | <640px | nav 햄버거 / 카드 1-up / dense-table → 카드 강제(가로 스크롤 회피) / 행 높이 `{density.row-h-touch}` 44px / 자산배분 바 풀폭 세로 스택 |
| Tablet | 640–1024px | 카드 2-up / dense-table 핵심 6컬럼만(밸류밴드·플래그 숨김, 카드에서 확인) |
| Desktop | 1024–1280px | 카드 2-up + dense-table 전체 8컬럼 / 1층·2층 바 가로 |
| Wide | >1280px | 콘텐츠 1200px cap(design.md 계승) |

- 등락색·tabular-nums는 전 breakpoint 동일(자리수 흔들림 방지).
- 모바일에서 "오늘 점검 필요" 펼침 유지, "전체 종목" 접힘 유지(스캔 우선).

---

## 9. 구현 체크리스트 (M4 검증, SSoT §11)

- [ ] CSS 변수: `{colors.move-*}`·`{colors.status-*}`·`{density.*}`·`{typography.dense-*}` 전부 `:root`에 정의.
- [ ] 등락색이 CTA/링크/헤더에 미사용(grep `move-up|move-down` → 수치 컨텍스트만).
- [ ] dense 셀 전부 `tabular-nums`.
- [ ] `BriefingDoc` 외 데이터를 템플릿이 직접 읽지 않음(LLM 원문 string 미렌더).
- [ ] 보류/제외/준비중이 빈칸 아닌 placeholder로 표시(H1).
- [ ] 면책 블록 전 페이지 하단 존재.
- [ ] "오늘 점검 필요" 펼침 / "전체 종목" 접힘 기본(SSoT §8).
- [ ] holdings POST 검증 에러 인라인 표시(수동/자동 배타·합100%, H3).
- [ ] fx FAIL 시 1층 바 보류 렌더 + 글로벌 배너(H4).
```
