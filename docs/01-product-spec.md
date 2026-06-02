# 01 · 서비스 기획서 — AI 투자 브리핑

> SSoT: `TECH-DESIGN.md` v3.1 · E2E: `00-e2e-flow.md`
> 작성 주체: 시니어 PM · 작성일: 2026-06-01
> 본 문서는 **무엇을·왜·언제** 만드는지를 정의한다. **어떻게**(스키마·소스·게이트 알고리즘)는 SSoT가 SoT이며, 본 문서는 SSoT와 모순될 수 없다. 충돌 시 SSoT 우선.

---

## 1. 비전 · 문제 정의 · 타깃

### 1.1 비전
> "매일 아침, 내 실제 보유 포트폴리오를 기준으로 **무엇을 점검해야 하는지** 30초 안에 알려주는 개인용 투자 브리핑."

매매 지시("사라/팔아라")가 아니라 **맥락·점검 항목**을 준다. 숫자는 코드가 계산하고, LLM은 그 숫자를 사람이 읽을 문장으로 바꿀 뿐이다(SSoT §1.1).

### 1.2 문제 정의
1인 투자자(KR+US 주식/ETF + 달러현금 보유)가 매일 겪는 마찰:
- **분산 정보**: 시세·밸류에이션·52주 위치·환율이 여러 앱에 흩어져 있고, 한국+미국이 섞이면 환율 때문에 비중 계산이 틀린다.
- **수작업 비중 계산**: 자산군(주식 vs 현금)·코어(ETF) vs 새틀(개별주) 비중을 매일 손으로 못 맞춘다.
- **노이즈**: 2% 종목의 매일 깜빡임, "지금 사라" 식 자극적 정보. 정작 **점검 필요 종목**이 묻힌다.
- **잘못된 자동화 신뢰**: 환율 미반영·액면분할·부분 데이터 실패가 **에러 없이 틀린 숫자**를 낸다(SSoT §1.6 — "틀린 숫자가 빈칸보다 위험").

### 1.3 타깃 사용자
| 구분 | 내용 |
|---|---|
| **Primary (PoC)** | 개발자 본인 1명. KR+US 주식/ETF + 달러예금 보유. `user_id=1` 고정. |
| **Secondary (검증 후 SaaS)** | 동일 프로파일의 KR 개인 투자자. **단 규제상 유료·개별 자문은 투자자문업 등록 필수**(SSoT §12) → SaaS는 비즈니스가 아니라 **규제 게이트** 통과 여부가 선결. |

핵심 가정: **PoC는 본인용 → 규제 비해당**(타인·영업·대가 미충족, SSoT §12). 이 가정이 깨지는 순간(타인 제공·유료) SaaS 로드맵의 법적 전제가 바뀐다.

---

## 2. 사용자 스토리

> 형식: `As a <역할>, I want <행위>, so that <가치>` · AC = 수용 기준(검증 가능).

### US-1 보유자산 입력 (S1)
As a 사용자, I want 종목코드·수량·통화(달러예금은 평가액 직접입력)를 입력·저장, so that 내 실제 포트폴리오 기준으로 브리핑을 받는다.
- **AC1** `GET /holdings` 폼에서 행별 `canonical_ticker, quantity, avg_price?, ccy, category?, target_pct?` 입력. 달러예금은 `value_manual + ccy='USD'`(quantity NULL).
- **AC2** `POST /holdings` 저장 시 `tracking`(auto/manual)·`asset_class`(equity/cash)·`instrument`(stock/etf/cash) 자동 매핑(SSoT §4, E2E S1).
- **AC3** `target_pct`는 "전부 수동 or 전부 자동" 배타. 일부만 채우면 **400 reject**. 전부 수동이면 합=100% 검증(SSoT §6, E2E G5).
- **AC4** `category` 미지정 시 코어 ETF 화이트리스트 자동판정, 명시 시 사용자값 우선. 결과를 `holdings.category`에 영속화(E2E G4).

### US-2 매일 자동 수집·브리핑 (S2/S3/S6)
As a 사용자, I want 매일 08:30 KST에 브리핑이 자동 생성, so that 내가 데이터를 모으지 않아도 된다.
- **AC1** 08:00 수집(`run_collect.py`) → 08:30 생성(`run_briefing.py`), 월~금만(SSoT §9).
- **AC2** 휴장일은 `OK_HOLIDAY`로 정상 skip, 신선도 배너 오발동 금지(SSoT §4·§9).
- **AC3** 수집 실패 시 ntfy.sh/Telegram 무료 푸시(SSoT §9).

### US-3 정확한 비중 (S5)
As a 사용자, I want 한국+미국+달러현금이 **환율 정규화된 단일 통화(KRW)** 비중으로 보이게, so that 자산배분을 신뢰한다.
- **AC1** `value_base = quantity * close_raw * (fx if US else 1)`, 현금도 base 환산해 분모 포함(SSoT §4).
- **AC2** **fx 결측 시 USD 평가대상 전체(US 종목 + USD 현금) 일괄 보류** + 1층 배분 "산출 보류" 라벨(E2E G6). NULL 분모 제외 금지.
- **AC3** 1종목/자동목표 엣지 → 드리프트·5/25·30% 플래그 억제(SSoT §6).

### US-4 점검 우선 요약 (S8)
As a 사용자, I want 30초 스캔으로 "오늘 점검 필요" 종목만 보이게, so that 노이즈에 시달리지 않는다.
- **AC1** 기본 요약뷰: 5/25 플래그·신고저 종목만 펼침, 나머지·양면 라벨 접힘/hover(SSoT §8).
- **AC2** 신선도 배지(시세=`MAX(price_snapshot.trade_date)` vs 기대거래일 / 펀더=`report_date` / 환율=`MAX(fx_snapshot.trade_date)`), 종목별 최악값 집계(E2E G10).
- **AC3** 오늘 `briefing_date` 중 `MAX(created_at)` row 렌더(SSoT §8).

### US-5 안전한 톤 (S7)
As a 사용자, I want 모든 산출물에 면책 + 단정 매매지시 금지, so that 규제·오인 위험이 없다.
- **AC1** 금지어 린터("매수/매도하세요·지금 기회·반드시") 정규식 검출 시 재생성/차단(SSoT §7).
- **AC2** ③valuation은 "5년 하위 X%ile (저평가 또는 디레이팅 — 펀더멘털 확인)" 양면 라벨(SSoT §6).
- **AC3** 면책 문자열 항상 포함(M3 검증 assert).

### US-6 데이터 신뢰 (S4/S7)
As a 사용자, I want 데이터가 부분 실패해도 **틀린 숫자가 아니라 보류/배너**로 보이게, so that 잘못된 비중에 속지 않는다.
- **AC1** 캐시 row 0건 종목 = "데이터 준비중" 보류(분모 제외 아님, 카드 placeholder)(E2E G3).
- **AC2** `per_pctile_5y IS NULL` → "5년 percentile 워밍업 중(절대 PER만)" degrade 라벨(E2E G3).
- **AC3** LLM 응답↔holdings는 `canonical_ticker` echo로 left-join, 미매칭/중복 → "처리 실패" 카드(E2E G2).

---

## 3. 기능 명세 (MoSCoW)

> 우선순위: **Must**=PoC 출시 필수 · **Should**=PoC 내 강력 권장 · **Could**=여유 시 · **Won't**=PoC 범위 밖.

### Must (PoC 필수 — M1a~M5 핵심)
| ID | 기능 | 근거(SSoT/E2E) | 인터페이스 핵심 |
|---|---|---|---|
| F-01 | 보유자산 CRUD + tracking/asset_class/category 자동매핑 | §4, E2E S1/G4 | `POST /holdings` |
| F-02 | target_pct 수동/자동 배타 + 합100% 검증 | §6, E2E G5 | POST validation, 위반 시 400 |
| F-03 | day-0 bulk 백필 (200일·52주 즉시, FMP percentile 분할) | §9, E2E S2 | `collect.py` bulk 모드, `status='BACKFILL'` |
| F-04 | 시장별 야간 수집 + collect_run 게이트 메타 | §4·§9, E2E S3 | `collect_run(trade_date,market,status,...)` |
| F-05 | 통화 정규화 비중 (주식+현금, fx 게이트) | §4·§6, E2E G6 | `value_base`, fx FAIL→USD 자산 보류 |
| F-06 | 지표 5종 ①drift/5·25 ②core-sat ③valuation ④trend ⑤regime ⑥dca | §6 | `portfolio.py`/`security.py` 순수계산 |
| F-07 | 자동 목표비중 런타임 산출(순환차단) | §6, E2E G5 | `auto_targets(holdings_without_value)->dict[ct,pct]` |
| F-08 | LLM 브리핑 (문장·라벨만) + 어댑터 | §2·§7, E2E G1 | `LLMClient.generate(prompt,schema)->dict` |
| F-09 | 검증 게이트 (금지어 린터 + ct echo join + 수치 슬롯주입) | §7, E2E G2 | 슬롯 주입, 미매칭 "처리 실패" |
| F-10 | content_json 스키마 = `BriefingDoc` DTO | E2E G11 | `models.py` frozen dataclass |
| F-11 | 대시보드 렌더 (요약뷰 + 신선도 배지) | §8, E2E S8/G10 | `GET /` MAX(created_at) |
| F-12 | 면책 + 규제 가드레일(금지어 린터) | §7·§12 | 전 산출물 고정 면책 |
| F-13 | 스케줄러 (launchd SoT, cron fallback) + 백필→cron 핸드오프 | §9, E2E G9 | M5 체크리스트 |

### Should
| ID | 기능 | 근거 |
|---|---|---|
| F-14 | 종목별 헤드라인을 LLM 호출1 입력 dict에 맥락 슬롯 추가(`headlines:[{title,url,source}]`) | E2E G7 |
| F-15 | 수집 실패 무료 푸시 알림(ntfy.sh/Telegram) | §9 |
| F-16 | 신선도 N일 연속 fallback 경고 블록 | §8 |
| F-17 | DCA 펀더멘털 게이트("물타기 위험—제외") | §6 |

### Could
| ID | 기능 | 근거 |
|---|---|---|
| F-18 | `POST /api/regenerate` 수동 재생성(127.0.0.1 바인딩 한정) | §8 |
| F-19 | ETF 구성(PDF/CSV) 기반 룩스루 비중 | §5 |
| F-20 | 음수PER/적자 종목 별도 라벨 강화 | §6 |

### Won't (PoC 범위 밖 — 명시적 제외)
| ID | 제외 | 근거 |
|---|---|---|
| W-01 | **수익률/평단 손익 표시** (매입환율 미보관 → KRW 손익 부정확) | §6 손익지표 없음, E2E G8 — 평단은 현지통화 참고표시만 |
| W-02 | 채권 자산군 | §14 (enum만 보존, 미사용) |
| W-03 | 주문 실행 자동화(제안까지만) | §12 |
| W-04 | 멀티유저·인증·결제 | SaaS 로드맵 |
| W-05 | SPA·실시간 시세·차트 | §2 SSR 단일페이지 |
| W-06 | LangChain/FinRobot/풀 OpenBB | §2 비도입 |

---

## 4. 화면 흐름 (유저 저니)

### 4.1 라우트 (SSoT §8)
| 라우트 | 페이지 | 비고 |
|---|---|---|
| `GET /` | 대시보드 | 신선도 배지 → 포트폴리오 요약 → 종목 카드 → 리밸런싱/DCA |
| `GET/POST /holdings` | 보유종목 입력/편집 | F-01/02/04 |
| `GET/POST /settings` | 설정 | 월적립금·base_currency·한도·밴드·micro_weight_floor |
| `POST /api/regenerate` | (개발용) | 127.0.0.1 한정 |

### 4.2 저니 — 온보딩 (day-0)
```
/holdings 입력 → POST 저장(검증: 배타·합100%·category 자동판정)
  → [수동/야간] collect.py bulk 백필 (200일 즉시 / FMP percentile 며칠 분할 BACKFILL)
  → 첫 브리핑: "초기 데이터 적재중" 글로벌 배너 + percentile NULL 종목 "워밍업 중" 라벨 (E2E G3)
  → 백필 완료(모든 auto 종목 row 존재 + BACKFILL 해제) → 익영업일 정상 cron 활성 (E2E G9)
```

### 4.3 저니 — 일상 (D+1)
```
08:00 수집 → collect_run 시장별 status 기록
08:30 게이트 평가:
   ├ FX FAIL        → USD 자산(US종목+USD현금) 일괄 보류 + 1층 배분 "산출 보류" 라벨
   ├ US FAIL        → US 종목만 제외 + 배너, KR 정상 브리핑
   ├ 전부 미갱신     → 생성 거부 "데이터 미갱신" 배너
   └ BACKFILL/HOLIDAY → 정상 진행 + 라벨
   → 지표계산 → LLM(문장만) → 검증게이트(금지어·ct echo) → 슬롯주입 → briefing 저장
사용자 /  접속:
   신선도 배지(시세/펀더/환율 최악값) → 요약뷰(점검필요만 펼침) → hover로 상세
```

---

## 5. MVP 범위 ↔ 마일스톤 (M1a~M5)

> SSoT §11 매핑 준수. 각 M의 **Exit 기준 = SSoT 검증 + 본 문서가 명시한 인터페이스 확정**.

| M | 산출 (모듈) | Must 기능 | Exit 검증 (SSoT §11 + 본 spec) |
|---|---|---|---|
| **M1a** | KR 데이터 레이어 (`sources/kr`,`tickers`,`collect`,`db`,`calendar`,`models`) | F-01,F-03,F-04 | KR 1~2종목 시세·펀더·뉴스 + day-0 bulk 200일 적재, collect_run **OK(데이터 실재: 행수>0·최신일자 일치)**. **선결: E2E G4(화이트리스트 `CORE_ETF_WHITELIST: frozenset` in tickers.py)·G5(POST 배타검증) 인터페이스 확정** |
| **M1b** | US+FX 레이어 (`sources/us`,`fx`) | F-05 | US 시세(Stooq)·FMP percentile + 환율 적재, **fx 결측 시 USD 자산(US종목+USD현금) 보류 동작**(E2E G6) |
| **M2** | 지표 엔진 (`portfolio`,`security`) | F-06,F-07 | 손계산 대조 일치 + **(주식+현금) 비중 합=100%** + 1종목 플래그 억제. `auto_targets` 시그니처에 평가액 미포함(E2E G5) |
| **M3** | LLM 브리핑 (`briefing`,`prompts`) | F-08,F-09,F-10,F-12 | **수치 LLM 0개(코드 주입) + 면책 포함 + 금지어 0건(assert)** + ct echo join 미매칭→"처리 실패". **선결: E2E G1(`LLMClient` Protocol 어댑터)·G2(ct echo 키)·G11(`BriefingDoc` DTO)** |
| **M4** | 웹 대시보드 (`main`,`templates`) | F-11 | 브라우저 입력→표시 + 신선도 배지 + 요약뷰 펼침/접힘 |
| **M5** | 스케줄러 | F-13 | **수동 트리거 1회로 오늘 briefing row 생성** 후 cron 등록. launchd SoT + caffeinate/pmset + 백필→cron 핸드오프 체크리스트(E2E G9) |

**MVP = M1a~M5 전부의 Must 기능.** Should(F-14~17)는 M3/M4/M5에 끼워넣되 Exit 차단 아님.

### 5.1 권고 인터페이스 확정 순서 (코드 착수 전, E2E §3)
`G1→G2(브리핑 어댑터) → G5/G4(metrics 시그니처) → G6(게이트 USD 일원화) → G3(부트스트랩 보류)` 확정 후 M1a 착수.

---

## 6. 성공 지표 ("쓸만함" 판정)

> PoC는 사용자 1명 → 정량 KPI보다 **신뢰성·정확성 게이트 + 본인 지속사용**으로 판정.

### 6.1 정확성 게이트 (Pass/Fail — 출시 차단)
| 지표 | 목표 | 측정 |
|---|---|---|
| 비중 정합성 | (주식+현금) base 비중 합 **= 100%** (fx 정상 시) | M2 손계산 대조 |
| LLM 수치 주입 | 브리핑 내 **LLM 생성 수치 = 0개** (전부 코드 주입) | M3 assert |
| 금지어 | 단정 매매지시 **0건** | M3 금지어 린터 assert |
| 면책 | 모든 브리핑에 면책 문자열 **포함** | M3 assert |
| 오주입 차단 | ct echo 미매칭/중복 종목은 수치 미표시("처리 실패") | M3 join 테스트 |
| 조용한 실패 차단 | 빈 CSV·0건 row를 OK로 오인 0건 | collect_run 데이터 실재 검증 |

### 6.2 신뢰성 지표 (운영)
| 지표 | 목표 |
|---|---|
| 일 브리핑 생성 성공률 | 거래일 중 ≥ 95% (수집 게이트 통과 시) |
| 신선도 정직성 | fallback/보류를 **틀린 숫자 대신 라벨**로 100% 노출 |
| 비용 | Sonnet 고정 시 30종목 월 ≤ ₩5,000(SSoT §13) |

### 6.3 "쓸만함" 최종 판정 (PoC → SaaS 검증 진입 조건)
- 본인이 **2주 연속 매일 아침 실제로 본다** (지속사용).
- 비중·밸류에이션이 **수기 검증과 불일치 0건** (신뢰).
- "오늘 점검 필요" 요약이 **30초 내 스캔 가능**하다고 본인이 판단(노이즈 제거).
- 위 3개 충족 시에만 SaaS 규제 검토(§12) 착수.

---

## 7. 비기능 요구 (NFR)

### 7.1 성능
- 대시보드 `GET /`는 **캐시만 읽음**(수집·계산은 배치) → SSR 응답 < 500ms 목표(SQLite 단일 사용자, SSoT §1.2).
- LLM 호출은 배치 시점(08:30)에만. 종목 임계 초과 시 8~10개 배치 분할(SSoT §7).

### 7.2 신뢰성
- 비공식 소스는 깨진다고 가정: `@retry(3)`·종목 단위 격리·rate limiter(토큰버킷)·최신거래일 fallback(SSoT §5).
- **응답 유효성 검증**: 행수>0 + 최신일자 일치(빈 CSV 조용한 실패 OK 오인 금지)(SSoT §4).
- 조정가 stale 방지: SMA200·52주·percentile은 매 수집 시 fresh 윈도우 재계산(SSoT §4).
- 게이트: fx FAIL→USD 자산 보류, US FAIL→US 제외, 전부 미갱신→생성 거부(SSoT §7, E2E G6).
- 노트북 절전: launchd `StartCalendarInterval` + caffeinate/pmset wake(SSoT §9, M5).

### 7.3 보안 (PoC)
- `data/ballast.db`는 **iCloud/Dropbox 동기화 폴더 밖 + .gitignore**(SSoT §3·§13).
- API 키는 `.env`(git ignore)(SSoT §10).
- 서버 **127.0.0.1 바인딩**, `/api/regenerate`도 로컬 한정(SSoT §8).
- `user_id=1` 고정이되 스키마에 미리 심어 SaaS 대비(SSoT §2·§4).

---

## 8. 면책 / 규제 정책

### 8.1 PoC (개인용) — 비해당
- 근거: **타인 대상·영업(계속·반복·영리)·대가 요건 미충족** → 자문업/유사투자자문업 정의 미진입(SSoT §12). 미국 IAA 동일.
- 그래도 모든 산출물에 **면책 고정 + 금지어 린터**로 톤 강제(SSoT §7·§12). 주문 실행 자동화 절대 금지(제안까지만).

### 8.2 SaaS화 (규제 게이트 — 비즈니스 선결조건)
- 본질이 **개인 맞춤 비중·타이밍 = 1:1 자문** → 2024.8.14 개정 자본시장법상 **유사투자자문 예외 배제** → **투자자문업 등록 외 합법 경로 없음**(무등록 시 형사처벌). "유사투자자문 신고 우회" 폐기(SSoT §12).
- "교육/시뮬레이션 면책 포지셔닝" 과신 금지 — 규제는 라벨 아닌 실질 판단. 면책은 민사 책임만 일부 경감.
- 미국 사용자 유료 제공 시 SEC RIA 등록 + state 등록 → **지역 차단 또는 등록 검토**.
- PIPA: 보유종목·평단·자산은 금융 개인정보 → 수집동의·암호화·파기 + **SQLite 평문 저장 시정** 필수.
- 데이터 ToS 개별 검토(yfinance/Yahoo 상업 재배포 금지 등) → 유료/정식 라이선스 교체.

---

## 9. 향후 로드맵

| 단계 | 내용 | 전제 조건 |
|---|---|---|
| **R0 (PoC 출시)** | M1a~M5 Must 기능 | 본 spec |
| **R1 (PoC 보강)** | Should(F-14 뉴스맥락·F-15 푸시·F-16 신선도경고·F-17 DCA게이트) + Could(F-18 재생성) | R0 안정 |
| **R2 (정확도 확장)** | 룩스루 ETF 비중(F-19)·채권 자산군(W-02 해제)·lots/매입환율 기반 손익(W-01 해제) | 본인 지속사용 검증(§6.3) |
| **R3 (SaaS 검증)** | 멀티유저·인증·결제 설계 | **규제 게이트(§8.2) 통과 — 투자자문업 등록/지역전략 확정 없이는 진입 금지** |
| **R4 (SaaS 운영)** | PIPA 준수·DB 암호화·ToS 라이선스 교체·SEC/state 등록 | R3 법적 확정 |

> R3 진입은 기술이 아니라 **법적·비즈니스 결정**. PoC 검증(§6.3) 성공이 R3 착수의 필요조건이지 충분조건이 아니다.
