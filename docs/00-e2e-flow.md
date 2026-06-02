# 00 · End-to-End Flow Trace — AI 투자 브리핑 PoC

> SSoT: `TECH-DESIGN.md` v3.1 (3라운드 검증 완료)
> 목적: 보유자산 입력 순간 → 다음날 08:30 KST 브리핑 표시까지 **실행 가능한 end-to-end flow**가 끊김 없이 완결되는지 trace.
> 상태: **그린필드** (코드 0줄, `investbrief/`에 docs만 존재). 본 문서는 *설계-수준* trace — 인터페이스/데이터 계약이 실제로 연결되는지 검증.
> 작성일: 2026-06-01

---

## 0. 전제 / 범위 노트

- 코드가 아직 없으므로 본 trace는 SSoT의 모듈 경계·DB 스키마·통화/조정가/환율/게이트 규칙이 **서로 모순 없이 닫히는지(closure)**를 검증한다.
- "동작하겠지"가 아니라 **끊긴 인터페이스·미정의 계약·순환·day-0 공백**을 적극 노출하는 것이 목표.

---

## 1. 완결 E2E 시퀀스 (Happy Path)

아래는 SSoT 결정사항을 충실히 반영한 정상 흐름. 각 단계 = **입력 → 처리 → 출력 → 저장(테이블)**.

### S1. 보유자산 입력·저장 (T0, 사용자 행위)
- **입력(UI)**: `GET /holdings` 폼 → 종목별 `canonical_ticker`, `quantity`, `avg_price`(선택), `ccy`, `category`(선택), `target_pct`(선택). 달러예금은 `value_manual`+`ccy='USD'` 직접 입력.
- **처리(`main.py` POST /holdings)**: 행별로 `tracking` 결정 — 시세조회 대상은 `auto`(quantity 필수, market·canonical_ticker 필수), 달러예금은 `manual`(value_manual 필수, quantity NULL). `asset_class` 매핑: stock/etf→`equity`, cash→`cash`. `instrument` = stock|etf|cash.
- **출력**: 검증된 holdings 행 set.
- **저장**: `holdings` (user_id=1 고정). `settings`(월적립금·base_currency·밴드·한도)는 `GET/POST /settings`에서 별도 저장.
- **불변식**: target_pct는 "전부 수동 or 전부 자동" 배타. 전부 수동이면 합 100% 검증(§6).

### S2. 초기 백필 (T0+, day-0 부트스트랩 · 정상 cron과 분리)
- **입력**: holdings의 auto 종목 canonical_ticker 목록 + market(KR/US).
- **처리(`collect.py` bulk 모드)**: pykrx/FDR/Stooq가 과거 시계열을 한 번에 반환 → 200일·52주·SMA200 day-0 즉시 확보. FMP percentile만 250req/day 한도로 며칠 분할 → `per_pctile_5y` NULL + `collect_run.status='BACKFILL'`.
- **출력**: 시계열·펀더멘털·환율 시드.
- **저장**: `price_snapshot`(close_adj/close_raw/52주/SMA200), `fundamentals_snapshot`, `fx_snapshot`, `market_regime`, `collect_run(market, status='BACKFILL'|'OK')`.

### S3. 야간/조간 수집 (D+1 08:00 KST, cron 월~금)
- **입력**: holdings auto 종목 + 캘린더 판정(오늘이 KR/US 거래일인가).
- **처리(`scripts/run_collect.py`→`collect.py`)**: 시장별로 수집.
  - `calendar.py`: 오늘이 거래일 아니면 해당 market `status='OK_HOLIDAY'`로 정상 skip.
  - `sources/kr|us|fx|etf`: `@retry(3)` · 종목 단위 격리 · rate limiter · **응답 유효성 검증(행수>0 + 최신일자 일치)** — 빈 CSV 조용한 실패를 OK로 오인 금지.
  - **조정가 fresh 재계산**: SMA200·52주·percentile은 캐시 누적이 아니라 **소스에서 조정 윈도우를 통째로 다시 받아 그 자리에서 재계산**(배당/분할 소급변경 흡수).
- **출력**: 시장별 수집 결과 + 신선도 메타.
- **저장**: `price_snapshot`·`fundamentals_snapshot`·`news_snapshot`·`fx_snapshot`·`market_regime` upsert + **`collect_run(trade_date, market, status, n_ok, n_fail, missing_tickers)`** 기록 (market ∈ {KR,US,FX}).
- **실패 시**: ntfy.sh/Telegram 무료 푸시 알림.

### S4. 신선도 게이트 평가 (D+1 08:30, `briefing.py` 진입)
- **입력**: `collect_run`의 시장별 최신 status.
- **처리(게이트)**:
  - FX `FAIL` → **US 전체 보류**(NULL 분모 제외 금지, 산출 거부).
  - US `FAIL` → US 종목만 분모 제외 + 배너, KR 정상 브리핑.
  - KR·US·FX 모두 미갱신 → 생성 거부("데이터 미갱신" 배너).
  - `BACKFILL`/`OK_HOLIDAY`는 **차단 아님** → 정상 진행 + 라벨.
- **출력**: 진행 가능 market 집합 + 보류/제외 종목 명시.

### S5. 지표 엔진 (`metrics/`, 순수 계산)
- **입력**: holdings + 각 종목 `MAX(trade_date)` row(price·funda·fx 모두 동일 규칙) + settings.
- **처리**:
  - **통화 정규화**: `value_base = quantity * close_raw * (fx if US else 1)`. 현금도 base 환산해 분모 포함. **fx 결측 시 US 평가액 산출 거부**(S4와 일관).
  - `portfolio.py`: ① drift+5/25(작은 쪽, 자산군 단위 집계, micro_weight_floor 억제) ② 코어(ETF 화이트리스트)-새틀 ⑥ DCA(드리프트 우선).
  - `security.py`: ③ valuation(양면 라벨·음수PER 제외) ④ trend(close_adj 기준·맥락용) ⑤ regime(CAPE/KOSPI PBR).
  - 소수종목/자동목표 엣지 → 플래그 억제.
- **출력**: 종목별 dict + 포트폴리오 dict (보류/제외 명시, **수치는 코드 계산값**).
- **저장**: 없음(메모리). 캐시는 S3 산출물을 읽기만.

### S6. LLM 브리핑 생성 (`briefing.py` → AI CLI)
- **입력**: S5의 정제 dict (숫자 포함, 그러나 LLM에는 **문장·라벨 생성만** 요청).
- **처리**:
  - [Claude 호출 1] 종목별 브리핑/트렌드/투자포인트 (임계 초과 시 8~10개 배치 분할).
  - [Claude 호출 2] 포트폴리오: 리밸런싱 검토구간·DCA·비중 코멘트.
  - 시스템 프롬프트 `prompts/briefing.md`(면책·톤·few-shot) + 캐시-퍼스트.
- **출력**: structured JSON(문장·라벨만, 수치 슬롯은 placeholder).

### S7. 검증 게이트 + 슬롯 주입
- **입력**: LLM JSON + S5 수치.
- **처리**: (a) 금지어 린터(정규식) → 검출 시 재생성/차단. (b) 응답 종목 수 == 입력 종목 수(누락분 "처리 실패" 카드). 이후 **코드가 수치 슬롯에 계산값 직접 주입**(echo 대조 reject 루프 폐기).
- **출력**: 최종 브리핑 content_json.
- **저장**: `briefing(briefing_date, content_json, model, created_at)` — date 단독 PK 아님(이력 보존).

### S8. 대시보드 렌더 (`GET /`)
- **입력**: 오늘 `briefing_date` 중 `MAX(created_at)` row + 각 캐시 `as_of_date`.
- **처리**: 신선도 배지(시세/펀더/환율 기준일 차이) → 요약뷰(점검 필요 종목만 펼침) → 종목 카드 → 리밸런싱/DCA.
- **출력**: SSR HTML.

**→ 정상 경로 closure**: S1 저장 → S2/S3 캐시 적재 → S4 게이트 → S5 계산 → S6/S7 브리핑 저장 → S8 표시. 테이블 키(canonical_ticker, trade_date, market)와 통화/조정가 규칙은 단계 간 일관.

---

## 2. 발견된 GAP (수정안 포함)

> 심각도: **BLOCKER**(실행 불가/치명) · **HIGH**(틀린 숫자·핵심 흐름 끊김) · **MEDIUM**(엣지/운영) · **LOW**(문서/명료성)

### G1 [BLOCKER] AI 호출 메커니즘 모순: 프로젝트 브리프 "claude -p CLI" vs SSoT "Anthropic SDK"
- **where**: S6 / SSoT §2(LLM=Anthropic SDK), §7(structured JSON·cache_control), 프로젝트 지시("claude -p headless print 모드 CLI").
- **issue**: SSoT는 **Anthropic SDK**(temperature=0, `cache_control: ephemeral`, structured JSON 스키마)를 전제로 §7 전체(캐싱·JSON 강제)를 설계. 그러나 실제 구현 의도는 **`claude -p` CLI**. CLI headless 모드는 (1) temperature 고정 제어, (2) `cache_control` 명시적 prompt caching, (3) structured JSON 스키마 강제(tool/`--output-format json`은 *transport* JSON일 뿐 *content* 스키마 보장 아님)를 SDK처럼 보장하지 못한다. → §7의 "structured JSON으로 문장·라벨만, 수치는 코드 주입" 계약이 **인터페이스 레벨에서 미연결**. day-0에 호출 어댑터 자체가 정의 안 됨.
- **fix**: 둘 중 하나로 **SSoT를 확정**: (A) Anthropic SDK 유지 → 브리프의 "claude -p" 표현을 SDK로 정정. (B) `claude -p` 채택 → §2/§7을 CLI 제약에 맞춰 재작성: `claude -p --output-format json --system-prompt-file prompts/briefing.md` 호출, content JSON 스키마는 **프롬프트 지시 + 코드측 Pydantic 파싱·실패 시 재호출**로 강제, 캐싱은 CLI 세션 캐시에 위임(불명확하면 비용표 §13 재산출). 어느 쪽이든 `briefing.py`에 단일 `LLMClient` Protocol(`generate(prompt, schema)->dict`) 어댑터를 두어 전환 비용 0으로.

### G2 [BLOCKER] 종목별 브리핑 JSON ↔ holdings 행 매핑 키 미정의
- **where**: S6→S7 (b) "응답 종목 수 == 입력 종목 수" 검증 / 수치 슬롯 주입.
- **issue**: LLM 응답을 어떤 키로 holdings 행/슬롯에 되붙이는지 미정. `canonical_ticker`가 자연키지만, 배치 분할(8~10개) 시 응답 순서·중복·누락을 ticker로 join해야 안전. SSoT는 "종목 수 일치"만 명시하고 **join 키·중복/순서 처리·LLM이 ticker를 변형(예 005930→"삼성전자")했을 때 매칭 실패**를 미규정. → 수치 슬롯 오주입(엉뚱한 종목에 다른 종목 수치) 위험 = "조용히 틀린 값"(§설계원칙 6 위반).
- **fix**: LLM 응답 스키마에 `canonical_ticker`를 **필수 echo 필드**로 두되 *식별자일 뿐 수치 아님*. 코드는 ticker로 left-join(holdings 기준), 미매칭/중복 ticker는 즉시 "처리 실패" 카드. 배치 분할 시에도 ticker join이라 순서 무관. (이 echo는 §7이 폐기한 "수치 echo 대조"와 다름 — 식별자 echo는 허용.)

### G3 [HIGH] day-0 부트스트랩: 백필 진행 중 첫 브리핑 가능 여부 / 게이트 상호작용 공백
- **where**: S2 / S4 게이트.
- **issue**: 최초 가입 후 FMP percentile 백필이 "며칠" 걸리는 동안 `status='BACKFILL'`. §11 검증은 "BACKFILL은 차단 아님"이라 브리핑은 진행되나, **percentile NULL인 상태에서 ③ valuation 양면 라벨이 무엇을 표시할지** 미정(NULL→ "5년 데이터 워밍업 중" 라벨? 아니면 항목 숨김?). 또한 **price/funda 백필이 아직 첫 종목만 끝난 시점**(일부 ticker는 아직 row 없음)에 S5가 `MAX(trade_date)` 조회 시 **row 0건 종목**을 어떻게 처리하는지 미정 → KeyError/0분모 위험.
- **fix**: (1) S5에 "캐시 row 0건 종목 = `status` 무관 **'데이터 준비중' 보류**" 명시(보류 종목은 분모 제외가 아니라 *비중 미산출·브리핑 카드만 placeholder*). (2) ③ valuation: `per_pctile_5y IS NULL` → "5년 percentile 워밍업 중(절대 PER만 표시)" degrade 라벨(§5 degrade 규칙과 연결). (3) day-0 첫 브리핑은 "초기 데이터 적재중" 글로벌 배너 허용.

### G4 [HIGH] 코어/새틀 화이트리스트의 저장 위치·관리 주체 미정의
- **where**: S5 ② core-sat / SSoT §6(광범위 지수 ETF만 화이트리스트로 코어).
- **issue**: "VOO/SPY/VTI/KODEX200/TIGER S&P500…" 화이트리스트가 **어디 저장**되는지(코드 상수? settings 테이블? 별도 테이블?) 미정. holdings에 `category`(core|satellite|NULL) 컬럼은 있으나, **누가 채우는가** — 사용자 입력? 화이트리스트 자동판정? 둘 다면 충돌 규칙은? SSoT는 "화이트리스트 자동 + 미등록은 NULL 플래그"를 말하지만 사용자가 직접 category를 줄 수도 있어(S1) **자동 vs 수동 우선순위 미정**.
- **fix**: 화이트리스트는 `tickers.py` 인근 코드 상수(`CORE_ETF_WHITELIST: frozenset[str]`)로 두고, S1 저장 시 `category` 미지정이면 화이트리스트 자동판정(매칭→core, 미매칭 ETF→NULL "확인 필요", 개별주→satellite), 사용자가 명시하면 사용자값 우선. 판정 결과를 holdings.category에 영속화(매 계산 재판정 비용 회피).

### G5 [HIGH] 자동 목표비중 산출 시점·저장 위치 (순환논리 차단의 실제 강제 지점)
- **where**: S5 ① drift / SSoT §6("현재 평가액을 입력에 넣지 않음, 함수 시그니처로 강제").
- **issue**: target_pct 미설정(자동) 시 2단계 산출(그룹목표→그룹내 균등)을 **언제** 하는지 미정. S1 저장 시 계산해 holdings.target_pct에 박으면 종목 추가/삭제마다 stale. S5 런타임 계산이면 함수 시그니처에 현재 평가액이 안 들어가게 강제해야(순환 차단). **자동/수동 배타(§6)** 판정도 어느 레이어인지 미정 → 혼재 입력 시 어디서 reject?
- **fix**: 자동 목표비중은 **S5 런타임 산출**(holdings에 영속화 안 함, NULL 유지). 시그니처: `auto_targets(holdings_without_value) -> dict[ct,pct]` — 입력에 평가액 타입 자체를 안 받게(순환 컴파일-차단). 배타 검증은 S1(POST /holdings) validation에서 "target_pct가 일부만 채워짐 → 400 reject", 전부 수동이면 합100% 검증.

### G6 [HIGH] 현금(달러예금) 환율 정규화가 fx 게이트와 충돌
- **where**: S5 통화정규화 / SSoT §4(현금도 base 환산해 분모 포함) + 게이트(fx FAIL→US 보류).
- **issue**: 달러예금(cash, USD, value_manual)은 **US 종목이 아니지만 USD**라 fx가 필요. fx FAIL 시 게이트는 "US 종목 보류"라 표현했는데, **USD 현금도 같이 보류되는가?** 명시 없음. 현금이 분모에서 빠지면 ① 자산군 배분(주식 vs 현금)이 통째로 왜곡(1층 배분 = 핵심). 반대로 현금만 남기고 US 주식 빼면 비중 기준 불일치.
- **fix**: 게이트 규칙을 "**USD 평가 대상 전체(US 종목 + USD 현금)**가 fx에 의존 → fx FAIL 시 USD 자산 일괄 보류 + 1층 자산배분 비중 '산출 보류' 라벨"로 명시. KRW 현금/KR 주식만으로의 부분 비중은 "현금배분 일부 보류" 배너와 함께 표시하거나, USD 비중이 유의미하면 전체 1층 배분 보류(임계는 settings).

### G7 [MEDIUM] `news_snapshot`이 브리핑 파이프라인에 연결 안 됨
- **where**: S5/S6 / SSoT §4 news_snapshot, §5 NewsSource, §6 지표표.
- **issue**: 뉴스를 수집(S3)·저장하지만, **S5 지표엔진·S6 LLM 입력 dict 어디에도 뉴스가 들어간다는 명시 없음**(§6 지표표는 ①~⑥ 모두 가격/펀더/레짐만). 뉴스가 "종목별 투자포인트"에 쓰일 의도면 인터페이스가 끊김; 안 쓸 거면 수집이 낭비.
- **fix**: S6 [Claude 호출 1] 입력 dict에 종목별 `headlines: list[{title,url,source}]`(헤드라인+링크만, 본문 없음) 슬롯 추가 명시. LLM은 헤드라인을 **맥락 참고만**(새 사실 생성 금지·§7 프롬프트). 또는 PoC 범위에서 뉴스 drop을 SSoT에 명시.

### G8 [MEDIUM] `avg_price` 통화 vs base_currency — 수익률/평단 표시 미정
- **where**: S1/S8 / SSoT §4(avg_price 현지통화).
- **issue**: avg_price는 현지통화(USD 종목이면 USD)인데, 대시보드가 평가손익/수익률을 보여줄지, 보여준다면 base(KRW) 환산인지 현지인지 미정. 매입 시점 환율 미보관 → KRW 환산 손익은 부정확(현재 fx로 환산하면 환차손익 혼입).
- **fix**: PoC는 **수익률/평단 손익 표시를 범위 밖으로 명시**(SSoT §6에 손익 지표 없음 — 일관). 평단은 참고 표시만(현지통화, 손익 미계산). 추후 lots/매입환율 도입 시 확장.

### G9 [MEDIUM] `regenerate` / cron / launchd 의 day-0 등록 흐름 공백
- **where**: S3 스케줄 / SSoT §9.
- **issue**: §9는 cron과 launchd(절전 wake)를 병기하나 **어느 것이 SoT인지**, day-0에 백필 완료를 어떻게 감지해 정상 cron으로 전환하는지(S2→S3 핸드오프) 자동화 미정. 수동이면 그 절차 미문서화.
- **fix**: M5에 "백필 완료 판정 = 모든 auto 종목 price/funda row 존재 + percentile BACKFILL 해제 → 그 다음 영업일부터 cron 활성" 체크리스트 명시. launchd를 macOS SoT로 고정(cron은 fallback 문서), `caffeinate`/`pmset` wake 설정을 M5 산출물에 포함.

### G10 [LOW] 신선도 배지 입력 = 각 캐시 as_of_date vs collect_run trade_date 일원화
- **where**: S8 / SSoT §8 신선도 배지, §4 조회규칙(MAX(trade_date)).
- **issue**: 배지는 "캐시 as_of_date"를 쓰는데 캐시 PK는 (canonical_ticker, trade_date)이고 funda는 report_date 별도. 표시 기준일이 `MAX(trade_date)`인지 `report_date`인지 종목별로 섞일 때 배지 산출 함수 입력 계약이 느슨.
- **fix**: 배지 입력을 명시 — 시세=`MAX(price_snapshot.trade_date)` vs 오늘 기대 거래일(calendar), 펀더=`report_date`, 환율=`MAX(fx_snapshot.trade_date)`. 종목별 최악값(가장 오래된)을 포트폴리오 배지로 집계.

### G11 [LOW] `briefing.content_json` 스키마 미정의 → S8 렌더 계약 느슨
- **where**: S7 저장 → S8 렌더.
- **issue**: content_json 내부 구조(종목 카드 배열·포트폴리오 섹션·보류/제외 마커·면책)가 미정. S8 Jinja2 템플릿과의 계약이 없으면 렌더-시 KeyError.
- **fix**: `models.py`에 `BriefingDoc`(frozen dataclass): `securities: list[SecurityCard]`, `portfolio: PortfolioComment`, `holds_excluded: list[ct]`, `disclaimer: str`, `as_of: dict` 를 정의하고 JSON 직렬화. 템플릿은 이 DTO만 신뢰.

---

## 3. 종합 판정

- **정상 경로(S1→S8)는 SSoT 결정사항(환율 정규화·시장별 게이트·조정가 fresh 재계산·5/25 작은쪽·코어-새틀·LLM 슬롯주입·금지어 린터·규제 가드레일) 위에서 논리적으로 닫힌다.** 캐시 키(canonical_ticker, trade_date, market)와 통화/조정가 규칙은 단계 간 일관.
- 그러나 **실행을 막는 BLOCKER 2건**: G1(AI 호출 메커니즘이 브리프 "claude -p" vs SSoT "SDK"로 모순 → §7 JSON/캐싱 계약 미연결) · G2(LLM 응답↔holdings join 키 미정 → 수치 오주입 위험).
- **HIGH 4건**(G3 day-0 백필 중 NULL/0건 처리, G4 화이트리스트 저장·주체, G5 자동목표 산출 시점, G6 USD 현금-fx 게이트 충돌)은 "조용히 틀린 숫자"를 낼 수 있어 코드 착수 전 인터페이스 확정 필요.
- 권고 순서: **G1→G2 확정(브리핑 어댑터 계약) → G5/G4(metrics 시그니처) → G6(게이트 USD 일원화) → G3(부트스트랩 보류 규칙)** 후 M1a 착수.
