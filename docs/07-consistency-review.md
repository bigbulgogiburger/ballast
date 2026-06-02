# 07 · 교차 정합성 리뷰 — AI 투자 브리핑 PoC

> 작성: 테크리드 · 작성일: 2026-06-01 (v3.1 기준)
> 대상: `TECH-DESIGN.md` · `00-e2e-flow.md`(E2E) · `01`~`06`

> ⚠️ **SUPERSEDED — 이 문서는 §15 신설(v3.2) 이전의 진단 기록이다.**
> 아래 C1~C10이 식별한 충돌은 전부 **TECH-DESIGN §15 Contract SoT**로 정본화되어 02~06 문서에 반영·해소되었다(2026-06-01 일괄 정정).
> **정본 = §15. 이 문서의 개별 "fix 권고"는 더 이상 따르지 말 것** — 일부(특히 C2)는 §15.3과 정반대다(아래 각 항목의 ✅ 정정 결과 참조). 본 문서는 "무엇이 왜 충돌했는가"의 이력으로만 보존한다.

---

## 종합 판정: ~~FIX_NEEDED~~ → **RESOLVED (§15로 정본화 완료)**

정상 경로(S1→S8)의 데이터·게이트·통화 규칙은 6개 문서에서 SSoT와 일관되게 반영됐고, E2E의 11개 gap(G1~G11)도 각 영역 문서에 빠짐없이 인용·해소안이 들어갔다. 당시 BLOCKER였던 DTO 4벌 모순(C1)·등락색 충돌(C2)·settings 키명 불일치(C3) 등은 **§15 Contract SoT 신설로 단일 정본화**되어 02~06에 반영 완료됐다. 아래 각 항목은 이력이며, ✅로 현재 정본 결과를 덧붙인다.

---

## C1 [BLOCKER] `BriefingDoc` / `SecurityCard` DTO가 4개 문서에서 상이 — 단일 SoT 부재

**docs**: 02-design §7 · 03-frontend §3.1 · 04-backend §4.4 · 06-ai-agent §1.3
**issue**: `models.py`에 한 벌만 있어야 할 DTO가 네 문서에서 필드 집합·이름·`status` enum 값·`regime` 위치까지 다르게 정의됨. 각자 자기 정의대로 구현하면 직렬화(briefing.py)↔역직렬화(main.py)↔렌더(Jinja2) 계약이 깨진다.

`SecurityCard` 비교:

| 필드 영역 | 02-design | 03-frontend | 04-backend | 06-ai-agent |
|---|---|---|---|---|
| 등락 | `change_pct` | `weight_pct`+`drift_pct` | `metrics`(dict 통합) | — |
| 밸류 | `valuation_label`+`per_pctile_band` | `valuation_band`+`per`+`per_pctile_5y` | `valuation_label` | `valuation_note` |
| 추세 | `trend_label` | `trend_label` | `trend_label` | — |
| 레짐 | `regime_label`(카드별) | — | — | — |
| 문장 | `narrative` | `summary`+`detail` | `narrative` | `headline`+`valuation_note`+`investment_point` |
| 플래그/펼침 | `flagged` | `needs_attention`+`flag_525` | `flags: list[str]` | — |
| status enum | `ok`/`hold`/`degrade` | `ok`/`pending`/`excluded`/`warmup` | `ok`/`data_pending`/`held` | `ok`/`data_pending`/`fx_held`(입력측) |
| 뉴스 | — | `headlines` | — | `headlines`(입력측) |

- `status` enum이 4벌 다름 → 템플릿 분기(`{% if sec.status == 'pending' %}`)와 metrics가 채우는 값(`data_pending`)이 안 맞으면 보류 종목이 정상 카드로 렌더되거나(틀린 숫자) 누락된다.
- `regime_label`을 02-design은 SecurityCard 카드별로, 04-backend는 `BriefingDoc` top-level로, 06-ai는 `PortfolioInput`에만 두고 출력 DTO에 아예 없음. → 레짐 한 줄이 어디서 렌더될지 미정.
- 06-ai의 `SecurityCard`는 **LLM 출력(문장만)** 정의이고, 03-frontend/04-backend의 `SecurityCard`는 **슬롯 주입 후 최종(수치 포함)** 정의다. 같은 이름의 다른 DTO를 한 `models.py`에 둘 수 없다.

**fix**:
1. `models.py`에 **단일 정본 `BriefingDoc`/`SecurityCard`/`PortfolioComment`/`AllocSlice`/`AsOf`/`HoldExcluded`**를 확정하고, 04-backend §4.4를 정본으로 채택(슬롯 주입 후 최종형). 나머지 3개 문서는 "정본 참조"로 교체.
2. LLM **출력** 스키마(06-ai §2 `SECURITY_SCHEMA`: `canonical_ticker`+문장 4필드)는 `SecurityCard`와 **이름을 분리**(예 `SecurityLLMOut`) — 최종 DTO와 혼동 금지.
3. `status` enum 1벌로 통일. 04-backend의 `held`/`degrade`/03-frontend의 `excluded`/`pending`을 매핑.
4. `regime_label` 위치 확정: 시장 단위 거시지표이므로 `BriefingDoc` top-level 1개. 02-design의 카드별 regime 표기는 "포트폴리오 헤더에 1회"로 정정.
5. `holds_excluded` 타입 통일: reason이 있어야 구분 렌더 가능 → `list[HoldExcluded]` 채택.

> ✅ **정본 결과(§15.2/§15.4)**: 단일 정본은 **§15.2**(04 §4.4가 그대로 옮김). LLM 출력 DTO는 **`SecurityLLMOut`**(canonical_ticker, comment, trend_note, investment_points)로 개명. status enum은 **5값** `ok|data_pending|fx_held|warmup|failed`(위 권고의 4값에 `failed` 추가 — LLM 미매칭/중복은 `failed`이며 `holds_excluded`와 연동). `regime_label` top-level, `holds_excluded: list[HoldExcluded]` 확정. 02/03/06은 §15.2 참조로 정렬 완료.

---

## C2 [BLOCKER] 등락색 컨벤션 정면충돌 — 02-design(글로벌) vs 03-frontend(한국)

**docs**: 02-design §2.1 · 03-frontend §6.2
**issue**: 같은 hex 두 색의 의미가 두 문서에서 **반대로** 배정됨.

- 02-design §2.1: "**글로벌 관습(상승=초록, 하락=빨강) 채택**" → `move-up`=#1f8a65(초록), `move-down`=#cf2d56(빨강). 근거까지 명시("미국 종목 분모 큼, 시장별로 뒤집으면 혼란").
- 03-frontend §6.2: `--c-up: #cf2d56`(빨강) "**한국 관례: 상승=빨강**", `--c-down: #1f8a65`(초록).

→ 같은 `tokens.css`를 두 문서가 정반대로 지시. 구현하면 상승이 빨강 또는 초록 중 하나로 잘못 칠해진다(투자 UI 치명).

**fix**(당시): 둘 중 하나로 확정 권고.

> ⚠️ ✅ **이 fix 권고는 폐기되었다.** 당시 인용한 "02-design 글로벌(상승=초록)"은 이미 stale했고(현재 02-design §2.1은 한국 관습), 사용자(한국)가 **한국 관습(상승=빨강/하락=파랑)**을 명시 채택했다.
> **정본 = §15.3**: `move-up`=**#d92d4e(빨강)**, `move-down`=**#1971c2(파랑)**, CTA `primary`=#0c8599(Teal). 02-design·03-frontend tokens.css는 이미 이 값으로 일치한다. **"상승=초록으로 swap" 지시는 따르지 말 것**(투자 UI 치명). 추가 조치 불필요.

---

## C3 [HIGH] USD 게이트 임계 settings 키명 3중 불일치

**docs**: 02-design §4.3 · 04-backend §2 · 05-database §1.2
**issue**: G6(USD 비중 임계 → fx FAIL 시 1층 배분 전체 보류)용 settings 키 이름이 3개 문서에서 다름.

- 02-design §4.3: `usd_hold_threshold`
- 04-backend §2: `usd_gate_threshold_pct` (값 5.0)
- 05-database §1.2: `usd_cash_gate_threshold` (값 '5.0')

→ `settings` 테이블 key는 문자열 PK. 코드가 `usd_gate_threshold_pct`로 읽는데 DB에 `usd_cash_gate_threshold`로 seed되면 KeyError 또는 기본값 폴백 → 게이트 오동작.

**fix**: 키명 1개로 확정(05-database가 스키마 SoT이므로 `usd_cash_gate_threshold` 채택 권고). 04-backend §2·02-design §4.3·§9 체크리스트(H4)를 이 이름으로 통일. 기본값 5.0(%)도 명시.

---

## C4 [HIGH] settings 키 1차 SoT 불일치 — `micro_weight_floor` 등 seed 책임

**docs**: 05-database §1.2(코드 day-0 seed, config.py 기본값) · 04-backend §2(settings 테이블 기본값 나열)
**issue**: settings 기본값을 누가 day-0에 seed하는지 두 문서가 모두 "config.py 기본값"이라 하나, 04-backend §2는 7개 키를 나열하고 05-database §1.2는 7개 키(다른 집합 — `usd` 키명 다름) 나열. `monthly_contribution` 기본값도 04는 미명시, 05는 `'0'`. 한쪽이 빠진 키를 seed 안 하면 metrics가 KeyError.

**fix**: settings 키·기본값 정본 테이블을 **05-database §1.2 1곳**으로 고정하고 04-backend·02-design은 참조. seed 시점(day-0 init_schema 직후) 명시.

---

## C5 [HIGH] `as_of` dict 키 집합 불일치 — 배지 입력 계약 흔들림

**docs**: 02-design §7(`AsOf{price,funda,fx,worst}`) · 03-frontend §3.1(`as_of: dict {price,funda,fx}`) · 04-backend §4.4(`as_of: dict {price,funda,fx,regime}`) · 06-ai §1.3(`{price,funda,fx}`) · 05-database §1.9(`as_of: dict`)
**issue**: `as_of`에 `worst`(02), `regime`(04)이 들어가거나 빠짐. 03-frontend 신선도 배지는 `worst_level`(별도 `FreshnessBadge`)로 산출하고, 04-backend `freshness_badges()`는 `FreshnessBadge` DTO를 따로 반환(`content_json`의 as_of와 별개). → 배지가 `doc.as_of.worst`를 읽는지 `badge.worst_level`을 읽는지 미정. 또한 main.py 컨텍스트 키도 03=`badge`(단수), 04=`badges`(복수)로 불일치.

**fix**:
1. `as_of` dict 키 = `{price, funda, fx}` 3개로 고정(regime/worst 제외). `worst`는 `FreshnessBadge`가 별도 산출(04-backend §6.3 정본).
2. 배지는 `content_json.as_of`(브리핑 생성 시점)가 아니라 **렌더 시점 `freshness_badges(conn)` 별도 호출**로 일원화(04-backend §1.3·§6.3 채택). 02-design의 `doc.as_of.worst`·03의 `badge` vs 04의 `badges` 컨텍스트 키명 통일.

---

## C6 [HIGH] `FreshnessBadge` DTO 필드명 불일치

**docs**: 03-frontend §4.1 · 04-backend §6.3
**issue**: 같은 `FreshnessBadge`를 다르게 정의.

- 03-frontend: `price_age_days:int`, `funda_label:str`, `fx_age_days:int`, `worst_level:str`, `consecutive_fallback:bool`
- 04-backend: `price_as_of:str`, `price_expected:str`, `price_stale_days:int`, `funda_as_of:str`, `fx_as_of:str`, `consecutive_fallback:int`

→ 템플릿(03)은 `badge.price_age_days`·`badge.worst_level`·`badge.consecutive_fallback`(bool)을 읽는데, 백엔드(04)는 `price_stale_days`·`worst_level` 없음·`consecutive_fallback`(int)을 채움. 렌더 KeyError + `{% if badge.consecutive_fallback %}`가 int 0/N으로 동작차.

**fix**: `FreshnessBadge` 1벌 확정. 03-frontend가 실제 렌더 소비자이므로 03 필드명(`price_age_days`, `funda_label`, `fx_age_days`, `worst_level`, `consecutive_fallback: bool`) 채택 권고. 04-backend `freshness_badges()` 반환형을 이에 맞춰 정정(내부에서 `as_of` vs `expected` 차이를 days로 환산, worst_level 산출).

---

## C7 [MEDIUM] `--c-warn` / status-warn hex 불일치

**docs**: 02-design §2.2(`status-warn` #b8740f) · 03-frontend §6.2(`--c-warn` #c08532) · 03-frontend `--alloc-sat` #c08532
**issue**: 경고색이 02=`#b8740f`(amber), 03=`#c08532`. 자산배분 바 새틀 한도초과·신선도 경고가 두 색으로 갈림. 또 02-design은 `move-*`/`status-*` 토큰 그룹을 풍부히(soft 배경 포함) 정의했으나 03-frontend tokens.css에는 `move-up-soft`·`status-hold`·`status-degrade`·`status-info`·`status-fail` 등이 빠져 02 컴포넌트 스펙(5.1 hold/degrade 칩, 5.7 fail-card)이 참조할 변수가 없음.

**fix**: 경고색 hex 1개로 확정. `tokens.css`(03-frontend §6.2)에 02-design §2가 정의한 토큰 전체(`*-soft`, `status-hold/degrade/info/fail`)를 누락 없이 옮긴다. 02-design이 색 SoT이므로 02 값 채택, 03은 그 CSS 변수 구현으로 일치.

---

## C8 [MEDIUM] `holds_excluded` 의미·타입 + reason 분류 불일치

**docs**: 02-design §5.7(`HoldExcluded{ct,reason}`, reason∈fx_fail/row_zero/llm_unmatched/llm_duplicate) · 03-frontend §3.1(`list[str]`) · 04-backend §4.4(`list[str]`) · 06-ai §1.3(`list[str]`)
**issue**: 02만 reason 포함 구조체, 나머지는 `list[str]`. reason이 없으면 "환율 보류" vs "LLM 처리 실패" vs "데이터 준비중"을 화면에서 구분 못 함 → 사용자가 원인을 모름. 또한 보류 종목을 `securities[].status`로도 표현(C1)·`holds_excluded`로도 표현 → **이중 표현, 어느 쪽이 SoT인지 미정**(같은 종목이 양쪽에 들어가면 중복 렌더).

**fix**: 보류/제외 종목 표현을 **`securities[].status`(카드 placeholder) 단일 경로로 통일**하고, `holds_excluded`는 "holdings에 있으나 LLM 응답에서 누락/중복된 처리 실패 ct"만 담는 것으로 의미 한정(G2 전용). reason 포함 `list[HoldExcluded]` 채택(C1-5와 연동).

---

## C9 [MEDIUM] 자산배분 색 토큰 출처 불일치 (move-up-soft vs alloc-*)

**docs**: 02-design §2.1(자산배분 바 fill = `move-up-soft`)·§5.5(주식 fill `{colors.ink}`, 현금 `surface-strong`) vs 03-frontend §5(`--alloc-equity`/`--alloc-cash`/`--alloc-core`/`--alloc-sat` 별도 토큰)
**issue**: 02-design은 자산배분 바를 등락색 soft(§2.1) 또는 ink/surface(§5.5)로 칠하라 하고(문서 내부도 §2.1 vs §5.5 미세 불일치), 03-frontend는 `--alloc-*` 전용 토큰을 새로 정의. → 자산배분 바 색이 3가지 후보. 등락색을 배분 바에 쓰면 02-design §2.1 주석("등락색은 수치/방향에만, CTA·배경 금지")과도 충돌.

**fix**: 자산배분 바는 **등락색 비사용**(02-design §5.5·03-frontend §5 일치점)으로 확정하고 `--alloc-*` 전용 토큰 사용(03 안). 02-design §2.1의 "move-up-soft = 자산배분 바 fill" 문구 삭제.

---

## C10 [LOW] 03-metrics 문서 부재 — 04-backend가 위임한 SoT가 없음

**docs**: 04-backend §0·§9·§13("상세는 03-metrics") · 05-database §7("metrics/(04)")
**issue**: 04-backend가 metrics 내부 알고리즘을 "03-metrics 문서가 별도 SoT"라며 반복 위임하나, `docs/`에 03-metrics 파일이 없다(03은 03-frontend). 지표 5종의 정밀 계산(5/25 작은쪽 집계 단위, percentile degrade 공식 등)을 **아무 문서도 책임지지 않음** → SSoT §6에만 의존. 또 05-database는 frontend를 07, backend를 04로 번호를 다르게 참조(번호 체계 혼선).

**fix**: (a) metrics 상세 SoT를 SSoT §6로 명시하거나 별도 `03-metrics.md`(또는 04-backend §9 확장)로 책임 귀속. (b) 문서 상호참조 번호를 실제 파일명(01~07)에 맞춰 정정(05-database "(02)models/(04)metrics/(06)briefing/(07)frontend" 표기 오류).

---

## E2E gap 반영 점검 (G1~G11) — **모두 반영됨**

| gap | 반영 문서 | 비고 |
|---|---|---|
| G1 claude -p vs SDK | 06-ai §0(확정 B), 04-backend §5(LLMClient) | claude -p로 SSoT 정정·매핑표 완비 |
| G2 ct echo join | 04-backend §10.3, 06-ai §4, 05-db §5, 01-spec US-6/F-09 | left-join·중복/누락 처리 일관 |
| G3 day-0 보류/워밍업 | 04 §9.1 build_priced, 05 §3.1/§4.3, 06 §3, 03 status, 01 US-6 | row 0건/per_pctile NULL 일관 |
| G4 화이트리스트 | 04 §5.2 `CORE_ETF_WHITELIST`, 05 §1.1, 03 §2.4, 01 US-1/F-01 | tickers.py frozenset 일관 |
| G5 자동목표 런타임 | 04 §1.4/§9.2 `auto_targets(holdings_without_value)`, 05 §1.1, 03 §2.4, 01 F-07 | 순환차단 시그니처 일관 |
| G6 USD현금 fx 게이트 | 04 §9.1/§10.2, 05 §1.5, 03 alloc_l1_held, 02 §5.5, 01 US-3 | 단 임계 키명 불일치(C3) |
| G7 뉴스 슬롯 | 04 §10.4, 05 §1.6, 06 §1.2 headlines, 01 F-14(Should) | 맥락참고만 일관 |
| G8 평단 손익 범위밖 | 03 F7, 05 §1.1, 01 W-01 | 일관 |
| G9 백필→cron 핸드오프 | 04 §8.5/§11, 05 §4.3, 01 F-13 | launchd SoT 일관 |
| G10 신선도 배지 입력 | 04 §6.3, 05 §3.3, 03 §4, 02 §5.4, 01 US-4 | 단 DTO 필드명 불일치(C5/C6) |
| G11 content_json 스키마 | 04 §4.4, 05 §1.9, 03 §3.1, 02 §7, 06 §1.3 | **DTO 4벌 모순(C1)** |

> E2E gap 자체는 모든 영역 문서가 인지·인용했다. 문제는 **G10/G11을 반영하는 과정에서 각 문서가 DTO를 독립적으로 재정의해 필드가 갈라진 것**(C1·C5·C6). gap은 닫혔으나 인터페이스 구체화가 분기했다.

---

## SSoT 충돌 점검 — **없음(정정은 합의된 것)**

- 06-ai §0의 "claude -p 확정"은 SSoT §2/§7(SDK 전제)와 표면상 충돌하나, **프로젝트 지시·E2E G1이 명시적으로 SSoT 정정을 요구**한 사항이며 매핑표로 의미 보존 → 합의된 정정(충돌 아님).
- temperature=0 미지원도 "숫자 코드주입으로 결정성 달성" 논리로 SSoT §7 의도 보존.
- 그 외 스키마·게이트·통화·조정가 규칙은 6개 문서 모두 SSoT §4/§6/§7과 일치.

---

## 책임 공백(아무 문서도 안 지는 부분)

1. **metrics 내부 알고리즘**(C10) — 03-metrics 부재. SSoT §6 외 정밀 SoT 없음.
2. **`prompts/briefing.md` 실제 본문** — 06-ai §6이 구성만 기술. few-shot/면책 전문은 미작성(M3 착수 전 필요).
3. **`disclaimer` 고정 문자열 정본** — 02 §5.6에 예시, 06 §6에 "코드 상수"라 하나 어느 모듈 상수인지(models.py? config.py?) 미정.
4. **LLM 응답이 입력보다 많은 종목을 반환**하는 경우(extra ct) — 06 §4은 미매칭/중복/누락만 다룸. 입력에 없는 ct를 LLM이 추가하면 left-join에서 자연 탈락하나 명시 없음(LOW).

---

## 권고 조치 순서 (코드 착수 전) — ✅ 전부 §15로 정본화 완료

| 항목 | 정본 결과 |
|---|---|
| C1 (DTO·status·LLM출력명) | §15.2/§15.4 — `SecurityLLMOut`/`SecurityCard` 분리, status 5값, 02/03/06 참조 정렬 |
| C2 (등락색) | §15.3 — 한국 관습(상승=빨강/하락=파랑) 확정. "초록 swap" 폐기 |
| C3/C4 (settings 키·기본값) | §15.5 — `usd_cash_gate_threshold` 등 1벌 |
| C5/C6 (as_of·FreshnessBadge) | §15.2 — as_of 3키, badge는 03 필드명(`price_age_days`·`worst_level`·`consecutive_fallback:bool`) |
| C7/C9 (토큰·alloc 색) | §15.3 — `--c-warn`=#b8740f, status-* 전량 03 tokens.css 이전, alloc-* 전용 |
| C8 (holds_excluded) | §15.2 — `list[HoldExcluded]`, 보류는 `securities[].status` 단일경로 |
| C10 (metrics SoT) | §15.6 — metrics 정본 = TECH-DESIGN §6 (별도 문서 없음), 상호참조 번호 정정 |

> 정상 경로 closure·E2E gap·SSoT 정합은 이미 확보됐고, DTO/토큰/키명의 단일 SoT화도 **§15로 완료**. **M1a 착수 가능.**
