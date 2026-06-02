# 08 · 개발 로드맵 (Week-by-Week) — AI 투자 브리핑 PoC

> SSoT: `TECH-DESIGN.md` v3.2 (**§15 Contract SoT 우선**) · 영역 문서: `00-e2e-flow`~`07-consistency-review`
> 대상: 1인 풀스택 개발자(본인). 가정 작업량 ≈ **주 10~15h**(평일 저녁+주말). 총 **6주 + 1주 버퍼**.
> 작성일: 2026-06-01

---

## 0. 빌드 철학 (왜 이 순서인가)

1. **리스크 우선 수직 슬라이스(risk-first tracer bullet).** 가장 불확실한 것부터 찍는다. 이 PoC 최대 리스크는 "**무료 데이터가 실제로 긁히는가**"이지 UI가 아니다. → 데이터 인입을 1주차에 증명하고, 안 되면 거기서 설계를 튼다(매몰비용 최소).
2. **각 주차는 "검증 가능한 산출물(DoD)"로 끝난다.** "대충 됨"이 아니라 `pytest` 통과·실데이터 적재·금지어 0건 같은 **객관적 게이트**. 게이트 미통과면 다음 주로 안 넘어간다.
3. **계약은 이미 §15에 고정됨.** DTO/색/키/status/런타임은 코딩 중 재논의하지 않는다 — §15를 그대로 구현. 충돌 느끼면 §15를 고치고 한 곳만 바꾼다.
4. **수평이 아니라 수직으로.** "모든 어댑터 완성 → 모든 지표 → 모든 UI"(수평)가 아니라, 1종목이 입력→수집→지표→브리핑→화면까지 **얇게 관통**하는 슬라이스를 먼저 세우고 종목/지표를 늘린다.
5. **테스트는 순수 계산부터.** `metrics/`·`tickers.py`·게이트 로직은 외부 의존 0이라 단위테스트가 싸고 강력하다. 네트워크 의존(어댑터·LLM)은 계약 테스트 + 수동 스모크로.

---

## 1. 마일스톤 ↔ 주차 맵

| 주 | 마일스톤 | 한 줄 목표 | 핵심 모듈 |
|---|---|---|---|
| **W1** | **M1a** 데이터 스파이크 | "삼성전자 시세·재무가 무료로 DB에 들어온다" 증명 | `db.py` `tickers.py` `calendar.py` `sources/kr.py` |
| **W2** | **M1** 데이터 레이어 완성 | KR+US+FX+레짐 30종목 수집 + 백필 | `sources/{us,fx,regime,etf}.py` `collect.py` |
| **W3** | **M2** 지표 엔진 | 통화정규화·5/25·밸류·게이트가 수치로 맞다 | `models.py` `metrics/{portfolio,security}.py` |
| **W4** | **M3** AI 브리핑 | claude -p가 숫자 없는 문장만 생성, 코드가 수치 주입 | `briefing.py` `prompts/briefing.md` `06` 계약 |
| **W5** | **M4** 프론트엔드 | 30초 스캔 대시보드 + 입력 폼 + 보류 표시 | `templates/` `static/` `main.py` |
| **W6** | **M5** 통합·무인운영 | 08:00→08:30 무인 1사이클 성공 | `scripts/` launchd · 알림 · 하드닝 |
| **W7** | (버퍼) dogfooding | 실제 본인 포트폴리오로 며칠 운영·안정화 | 운영·버그픽스·비용 실측 |

> **크리티컬 패스**: W1 → W2 → W3 → W4 → W6. **W5(프론트)는 W3 끝나면 W4와 병렬 가능**(브리핑 DTO=§15.2가 이미 고정이라 화면을 mock doc으로 먼저 만들 수 있음).

---

## Week 0 — 셋업 (W1에 흡수, ~2h)

착수 전 1회. 별도 주차로 잡지 않는다.

- [ ] `python3.12 -m venv .venv` + `requirements.txt`(`fastapi uvicorn jinja2 pykrx finance-datareader opendartreader pandas-datareader yfinance pandas-market-calendars python-dotenv pytest`).
- [ ] 폴더 스캐폴드(04 §0 모듈맵 그대로): `app/{main,config,db,models,tickers,calendar,collect,briefing}.py`, `app/sources/`, `app/metrics/`, `app/templates/`, `app/static/`, `app/prompts/`, `scripts/`, `tests/`.
- [ ] `.env.example` + `.gitignore`(`.venv`, `data/`, `.env`). **`data/`는 iCloud/Dropbox 폴더 밖**(05 §0, 금융정보 유출 방지).
- [ ] API 키 발급: `FINNHUB_API_KEY` `FMP_API_KEY` `DART_API_KEY` `NAVER_CLIENT_ID/SECRET` `SEC_USER_AGENT`(="name email"), 선택 `ECOS_API_KEY`. **claude -p는 구독 로그인이면 키 불필요**(§15.1).
- [ ] `claude -p "ping" --output-format json` 로컬에서 1회 실행 확인(설치·인증 점검).
- **DoD:** `uvicorn app.main:app`이 빈 200을 반환 + `pytest`가 0개 테스트로 green.

---

## Week 1 — M1a · 데이터 스파이크 (최대 리스크 제거)

> **목표:** "무료 데이터가 진짜 긁히는가"를 **삼성전자(005930) 한 종목**으로 끝까지 증명. 여기서 막히면 설계를 튼다.

### 작업
- [ ] `db.py`: `connect()`(WAL·FK·busy_timeout, 05 §0) + `init_schema()`(05 §1 DDL 전체). `MAX(trade_date)` 조회 헬퍼(`latest_price/funda/fx`, 05 §3).
- [ ] `tickers.py`: `to_source()` 변환 표(04 §5.1: `005930→005930.KS` 등) + `CORE_ETF_WHITELIST` frozenset + `classify_category()`.
- [ ] `calendar.py`: `pandas_market_calendars` XKRX/XNYS, `is_trading_day`/`prev_trading_day`/`expected_trade_date`(04 §6).
- [ ] `sources/kr.py`: `ohlcv()`(pykrx/FDR 조정 윈도우 fresh fetch → close_raw/adj/52주/sma200), `fundamentals()`(pykrx 5년 PER/PBR/배당 → percentile), `headlines()`(네이버). **조정 윈도우 통째 재계산**(05 §1.3 stale 방지).
- [ ] `sources/regime.py` KR 절반(KOSPI 지수 PBR, pykrx)만 먼저.

### DoD (검증 게이트)
- [ ] `python -c "from app.sources.kr import KrSource; print(KrSource().ohlcv('005930'))"` → close_raw·52주·sma200이 **실수치**로 출력.
- [ ] `fundamentals('005930')` → PER/PBR/배당 + `per_pctile_5y`(5년 백필 OK).
- [ ] 위를 `db.upsert_*`로 적재 후 `latest_price(conn,'005930')`가 row 반환.
- [ ] `tests/test_tickers.py`: `to_source` 변환 표 케이스 전부 통과.
- [ ] `validate_response`가 빈 응답을 `EmptyResponseError`로 올림(빈 CSV를 OK로 오인 안 함, 05 §1.8).

### 리스크 & 대응
- pykrx/FDR가 특정 종목·기간에서 빈 DF 반환 → `@retry(3)` + `validate_response`로 조용한 실패 차단. **5년 percentile이 안 나오면** → 절대 PER만 쓰는 degrade 경로 즉시 확인(W3 의존성).

---

## Week 2 — M1 · 데이터 레이어 완성

> **목표:** KR에 더해 US·FX·레짐을 붙이고 **collect 배치 1회**로 30종목치 캐시를 채운다. 무료 한도·백필 분할이 실제로 도는지 확인.

### 작업
- [ ] `sources/us.py`: 시세 **Stooq(1차)→yfinance(2차)→Finnhub /quote(보조)**, 펀더 **FMP 무료 5년**, 뉴스 Finnhub, 재무 SEC EDGAR(보조). (04 §7.3 — Finnhub candle 안 씀.)
- [ ] `sources/fx.py`: **ECB(1차, 키 불필요)→yfinance(2차)**, ECOS는 키 있을 때만 보조(04 §7.4, §15 H3 정정).
- [ ] `sources/regime.py` US 절반(Shiller CAPE: Yale `ie_data.xls`→multpl). `RegimeRow`→`market_regime` 매핑(`as_of→trade_date`, 04 §4.2).
- [ ] `sources/etf.py`: KR pykrx PDF / US 발행사 CSV(코어 판정 보조).
- [ ] `collect.py`: `run_collect()` + `_collect_market`/`_collect_fx`/`_collect_regime`(04 §8), `TokenBucket` rate limiter, `_status_of`(OK/PARTIAL/FAIL/BACKFILL/OK_HOLIDAY), `missing_tickers`=**JSON 배열**(05 §1.8), `collect_run` upsert.
- [ ] **백필 모드**(`--backfill`): 과거 시계열 한 번에, FMP percentile만 250req/day **며칠 분할**(`status='BACKFILL'`).

### DoD
- [ ] 본인 보유 종목(KR+US 섞어 ~10개) `run_collect(mode="backfill")` → 각 시장 `collect_run` row가 **OK 또는 BACKFILL**, `missing_tickers` 빈 배열 근접.
- [ ] FX row 적재 + `latest_fx` 반환. ECB 실패 시 yfinance 폴백 동작 확인.
- [ ] 휴장일에 돌리면 `OK_HOLIDAY`로 정상 skip(배너 오발동 X).
- [ ] FMP 한도 소진 시 다음날 이어받기(백필 status 유지) — 로그로 확인.
- [ ] `tests/test_collect.py`: `_status_of` 분기 + `validate_response` 단위테스트.

### 리스크
- US EOD publish 지연(겨울 EST) → `expected_trade_date`가 US=직전거래일이라 흡수. FMP 무료 250/day가 30종목×5년이면 빠듯 → 백필 분할 + degrade(현재 PER vs 자기 5년 평균) 폴백 준비.

---

## Week 3 — M2 · 지표 엔진 (순수 계산, 테스트 강하게)

> **목표:** 외부 의존 없는 계산 로직을 `pytest`로 못박는다. 통화정규화·5/25·게이트는 **틀리면 치명**이라 여기서 단위테스트 커버리지를 최대로.

### 작업
- [ ] `models.py`: §15.2 DTO 전량(`SecurityCard`/`SecurityLLMOut`/`BriefingDoc`/`HoldExcluded`/`FreshnessBadge`/`HoldingRow`/`OHLCV`/`Funda`/`FxRate`/`RegimeRow`/`PricedHolding`) + Protocol. **frozen dataclass.**
- [ ] `build_priced(conn, holdings, fx_ok, us_ok)`(04 §9.1): 통화정규화(base=KRW), fx 결측 시 USD **산출 거부**(분모 제외 아님), US FAIL 시 `us_ok=False` 강제 보류.
- [ ] `metrics/portfolio.py`: `auto_targets`(평가액 안 받음=순환차단), `drift`(① 자산군 단위 5/25 **작은 쪽** + micro_floor 억제), `core_sat`(② 30% 한도), `asset_alloc`(1층+G6 보류), `dca`(⑥ 드리프트 우선).
- [ ] `metrics/security.py`: `change_pct(ohlcv, prev_close)`, `valuation`(③ 양면 라벨, per_pctile NULL→warmup, 음수PER 제외), `trend`(④ 52주·sma200 gap), `regime`(⑤ 한 줄).
- [ ] 게이트: `evaluate_gate`(blocked/fx_ok/us_ok) + `collect_complete_today`(08:00→08:30 핸드오프 선검사, 04 §10.2).

### DoD
- [ ] `pytest tests/test_metrics.py --cov=app/metrics` **커버리지 ≥ 85%**(testing.md).
- [ ] 핵심 케이스 테스트: ① 5/25 "작은 쪽" 트리거(절대 5%p vs 상대 25% 중 먼저), ② fx FAIL 시 USD 자산 보류·KR만 100% 정규화 **안 됨**(전역오염 회귀 테스트), ③ 자동목표 순환차단(평가액 없이 그룹균등), ④ per_pctile NULL → warmup 라벨, ⑤ 음수 PER 제외.
- [ ] `build_priced`가 보류 종목을 `status`로 표시하되 **분모에서 빼지 않음**.

### 리스크
- 5/25 집계 단위(개별 종목 vs 자산군) 혼동 → §6/§15.6이 SoT. 테스트로 "자산군 단위 집계 후 플래그" 고정.

---

## Week 4 — M3 · AI 브리핑 (claude -p)

> **목표:** LLM은 **문장·라벨만**, 코드가 숫자를 박는다. 환각·금지어·종목 누락이 0이 되는 것을 증명.

### 작업
- [ ] `briefing.py` `ClaudeCLIClient`(06 §5.1): `claude -p --bare --model claude-sonnet-4-5 --append-system-prompt <고정> --output-format json --json-schema <schema>` subprocess. envelope의 `structured_output` 파싱, exit≠0 처리.
- [ ] `prompts/briefing.md`: 역할·톤·하드규칙(숫자는 `{placeholder}`만, ct echo, 금지어), 양면 라벨 규칙, **few-shot good/bad**(06 §6). (← 아직 미작성 책임공백, 여기서 작성.)
- [ ] `SECURITY_SCHEMA`(comment/trend_note/investment_points)·`PORTFOLIO_SCHEMA`(rebalance/dca/weight_note) (06 §2, §15.2 정합).
- [ ] `run_securities(client, items)→(list[SecurityLLMOut], list[HoldExcluded])` + `run_portfolio` (06 §5.2): 배치 분할·ct 조인(G2)·금지어 린트(`BANNED`)·텍스트 슬롯주입.
- [ ] `assemble_briefing(metrics, sec_llm, sec_failed, port_comment, gate)→BriefingDoc` (04 §10.3): **수치는 코드가** 박아 최종 `SecurityCard`/`BriefingDoc` 조립.
- [ ] `disclaimer` 고정 상수 위치 확정(`config.py` 상수 권장, 책임공백 해소).
- [ ] `run_briefing` 파이프라인 전체 + `_save_blocked_briefing`(banner).

### DoD (M3 검증, SSoT §11)
- [ ] 실제 브리핑 1건 생성 후 assert: **금지어 0건**(BANNED) + **면책 문자열 포함** + **LLM 출력에 raw 숫자 0개**(RAW_NUMBER 린터).
- [ ] ct join: LLM이 종목 누락/중복/변형 시 `failed` 카드 + `holds_excluded` 등재(정상 종목은 영향 0).
- [ ] 보류 종목(`hold_status != 'ok'`)은 LLM 미호출 + status 카드.
- [ ] `total_cost_usd` 로깅 → 10종목 일 비용 실측이 §13 표(~$0.05) 근방.

### 리스크
- `--json-schema`/`--append-system-prompt` 실제 CLI 동작은 검증됨(1차 workflow). 다만 구독 플랜의 headless 과금 정책 변동 가능 → API 키 경로 폴백 준비(§15.1).

---

## Week 5 — M4 · 프론트엔드 (W4와 병렬 가능)

> **목표:** 30초 스캔 대시보드. **mock `BriefingDoc`(§15.2)로 먼저 화면을 세우고** W4 실데이터로 교체 → 백엔드 안 기다림.

### 작업
- [ ] `static/css/tokens.css`: §15.3 색 정본(등락 한국관습 #d92d4e/#1971c2, CTA Teal #0c8599, status-* 전량, alloc-*, density) (03 §6.2).
- [ ] `templates/dashboard.html`: 헤더+면책+regime → banner → 신선도 배지 → 자산배분 바(1·2층) → 요약뷰 종목(`<details open>`=status≠ok·rebalance_flag) → 리밸런싱/DCA → 면책 (02 §4.1, 03 §3.2).
- [ ] `templates/holdings.html` + `POST /holdings` 검증(03 §2.4): target_pct 배타·합100%·중복 ct, instrument별 활성 필드, 실패 시 400+상태보존 재렌더.
- [ ] `templates/settings.html`(§15.5 키), `main.py` 라우트(`/`,`/holdings`,`/settings`,`/api/regenerate` 127.0.0.1 한정).
- [ ] placeholder/fail 카드, `build_freshness_badge`(컨텍스트 키 `badge` 단수), 자산배분 stack-bar(CSS only).

### DoD (M4 체크리스트, 03 §9)
- [ ] 보류/제외/워밍업이 **빈칸 아닌 placeholder**(H1).
- [ ] 등락색이 CTA/링크/헤더에 미사용(grep `move-up|move-down`=수치 컨텍스트만). 상승=빨강.
- [ ] dense 셀 전부 `tabular-nums`. 면책 전 페이지 하단.
- [ ] holdings POST 검증 에러 인라인 표시(배타·합100%).
- [ ] JS 꺼도 펼침/접힘(`<details>`)·폼 동작.
- [ ] **모바일/데스크톱 둘 다** 깨지지 않음(반응형, 02 §8).

---

## Week 6 — M5 · 통합 · 무인 운영 · 하드닝

> **목표:** 사람 손 없이 08:00 수집 → 08:30 브리핑이 도는 1사이클을 성공시킨다. 실패가 조용히 묻히지 않게.

### 작업
- [ ] `scripts/run_collect.py`(`--backfill` 인자) · `scripts/run_briefing.py`(`make_llm_client()` 팩토리).
- [ ] **launchd** `StartCalendarInterval`(월~금 08:00/08:30) + `caffeinate`/`pmset` wake(절전 대응, 04 §11.2). cron은 fallback 문서화.
- [ ] **day-0 백필 → 정상 cron 핸드오프(G9)**: 백필 완료 판정(모든 auto 종목 row + percentile BACKFILL 해제) → 익영업일 daily 활성.
- [ ] 실패 알림: market FAIL 시 ntfy.sh/Telegram 무료 푸시 1회(04 §8.7).
- [ ] 보안 점검: `127.0.0.1` 바인딩 강제(`0.0.0.0` 금지), `data/` 동기화 폴더 밖, `.env` 미커밋.
- [ ] E2E 리허설: 빈 DB → 백필 → 첫 브리핑(day-0 배너) → 익일 daily.

### DoD
- [ ] **무인 1사이클**: launchd가 깨워 08:00 수집·08:30 브리핑 생성, 대시보드에 오늘 브리핑 표시.
- [ ] 일부러 FX 차단 → US 자산 보류 배너 + 1층 배분 보류 정상 동작(분모 오염 X).
- [ ] collect FAIL 시 푸시 도착.
- [ ] `collect_complete_today` 미완 시 브리핑이 전날값으로 오판정 안 하고 보류.

---

## Week 7 — 버퍼 · Dogfooding

> 새 기능 금지. 실제 본인 포트폴리오로 **며칠 운영**하며 신뢰를 쌓는 주.

- [ ] 실 보유자산 입력 후 3~5 영업일 무인 운영 관찰.
- [ ] 신선도 배지·fallback·degrade 라벨이 실제로 의미 있게 뜨는지.
- [ ] 비용 실측(일/월) vs §13 표 대조.
- [ ] 버그·문구·금지어 린터 오탐 수정. 면책/규제 표현 최종 점검(본인용=자문업 무관 포지션 유지).
- [ ] (선택) 회고 → SaaS 전환 시 막힐 지점 메모(멀티유저·KIS 연동 등).

---

## 2. 의존성 그래프 (요약)

```
W1 db/tickers/calendar/sources.kr ──┐
                                    ├─► W2 collect(US/FX/regime) ──► W3 metrics/게이트 ──┬─► W4 briefing(claude -p) ──► W6 통합/무인
W1 (스파이크가 데이터 가정 검증) ───┘                                                   └─► W5 frontend(mock→실데이터) ─┘
```
- **W3 완료 = 분기점**: W4(AI)와 W5(프론트)를 §15.2 계약 기반으로 **병렬** 진행 가능.
- W5는 mock `BriefingDoc`으로 W4 이전에 착수해도 무방(계약 고정됨).

## 3. 횡단 규율 (매 주차 공통)

- **커밋**: 작은 단위, conventional commits(`feat/fix/refactor/test`). 주차 끝마다 DoD 통과 태그.
- **테스트 우선순위**: 순수 계산(metrics/tickers/게이트) = 단위테스트 필수 / 어댑터·LLM = 계약 테스트 + 수동 스모크.
- **§15가 흔들리면**: 코드 곳곳을 고치지 말고 §15 한 곳을 고친 뒤 의존 문서를 따라 맞춘다.
- **범위 방어**: 손익/수익률(G8)·증권사 연동·멀티유저는 **PoC 범위 밖**. 끌려가지 않는다.

## 4. "이번 주 안 하는 것"(스코프 컷 명시)

KIS/미래에셋 API 연동 · 알림 고도화 · 백테스트 · 푸시 외 채널 · 다국어 · 인증/회원 · 차트 시각화(라인/캔들) · 세금/환전 계산. → **전부 PoC 이후.**
