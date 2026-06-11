# Ballast (InvestBrief) — 제품 정의·벤치마킹·Next Level 전략

> 작성: 2026-06-11 · 작성 관점: IT 서비스 기획 (제품 전략)
> 입력: 코드베이스 전수 분석 + 국내·해외 유사 서비스 웹 리서치
> 정본 명세: `docs/01-product-spec.md` · `04-backend.md` · `05-database.md` · `06-ai-agent.md`

---

## 1. 이 프로젝트는 무엇인가 — 제품 정의

### 1.1 한 줄 정의

> **"매일 아침, 내 실제 보유 포트폴리오 기준으로 오늘 무엇을 점검해야 하는지 30초 안에 알려주는 개인용 AI 투자 브리핑."**

카테고리로 분류하면 **Personal Portfolio Intelligence** — 로보어드바이저(매매 대행)도, 트레이딩 터미널(차트·호가)도, 뉴스레터(범용 시황)도 아니다. "내 보유 자산"을 렌즈로 시장 데이터를 필터링해 **읽을거리가 아닌 점검 목록**을 만들어주는 서비스다.

### 1.2 해결하는 문제

KR+US 혼합 장기투자자가 매일 겪는 4가지 마찰:

| 마찰 | Ballast의 해법 |
|------|---------------|
| 시세·밸류·환율 정보가 여러 앱에 분산 | 전 소스(pykrx·DART·yfinance·FMP·SEC·ECB)를 로컬 SQLite로 통합 |
| KR+US+USD현금의 환율 정규화 비중 계산이 수작업 | KRW 단일통화 자동 정규화 + 5/25 드리프트 자동 플래그 |
| "지금 사라" 식 자극·노이즈 정보 | AI는 매매 지시 대신 양면 라벨·점검 문장만 생성 (금지어 린트) |
| 자동화가 틀린 숫자를 조용히 출력하는 문제 | 신선도 게이트·빈 응답 거부·보류 카드 — "틀린 숫자보다 빈칸" |

### 1.3 차별화된 설계 철학 (이 제품의 진짜 자산)

코드 분석에서 확인된, 경쟁 서비스 대부분이 갖지 못한 원칙들:

1. **숫자는 코드, 문장은 AI** — LLM이 수치를 생성하지 못하게 `RAW_NUMBER` 린터로 강제하고, 코드가 계산한 값을 슬롯에 주입. LLM 환각으로 인한 숫자 오류가 구조적으로 불가능.
2. **데이터 정직성 게이트** — fx 결측 시 0으로 위장하지 않고 산출 거부, 부분 실패는 "보류 카드"로 노출.
3. **운영 비용 극단 최적화** — 무료 데이터 소스 + `claude -p` CLI 어댑터로 월 ₩1,500~4,700 수준의 LLM 비용.
4. **무인 운영 완결성** — launchd 08:00 수집 → 08:30 브리핑, 실패 시 ntfy/Telegram 알림, E2E 무인 사이클 검증 완료.

### 1.4 현재 상태 (2026-06 기준)

- W1~W6 마일스톤 전량 완료, **PoC 기능 완성 → dogfooding 단계**.
- 성공 기준: "2주 연속 매일 아침 실제로 본다 + 비중 수기검증 불일치 0건 + 30초 스캔 가능".
- 명시적 제약: 단일 사용자(`user_id=1`), 로컬 SQLite 평문, 인증 없음(127.0.0.1 경계), EOD 데이터만, 손익 표시 없음, 모바일/푸시 브리핑 알림 없음.

---

## 2. 벤치마킹 — 국내·해외 유사 서비스

### 2.1 해외

| 서비스 | 포지션 | 핵심 기능 | Ballast 대비 시사점 |
|--------|--------|----------|---------------------|
| **Robinhood Cortex Digests** (Gold 구독) | 가장 직접적인 경쟁 모델 | 보유종목 기준 AI 다이제스트, 하루 수회 + 뉴스 발생 시 갱신, 향후 이벤트(실적·매크로 촉매) 예고. 출시 후 수십만 명 사용, 만족도 95% | "내 포트폴리오 렌즈 브리핑"이라는 컨셉 자체가 시장 검증됨. 차이: Cortex는 **하루 수회 + 이벤트 트리거**, Ballast는 1일 1회 |
| **Reflexivity** (구 Toggle AI) | 기관급 투자 인텔리전스 | 지식그래프 + LLM으로 시나리오 테스트·2차 파급효과 분석. IBKR 주도 $30M Series B, **Microsoft 365 Copilot 플러그인**으로 배포 채널 확장 | "내 서비스 안에 가두기"가 아니라 **사용자가 이미 있는 곳(Copilot·브로커)으로 침투**하는 배포 전략 |
| **Fiscal.ai** (구 FinChat) | 재무데이터 특화 코파일럿 | S&P 데이터 직결 10만+ 기업, 출처 인용 강제, 금융 벤치마크에서 범용 챗봇 능가. 2026-06부터 **ChatGPT 공식 앱** 입점 | "범용 LLM + 검증된 데이터 주입"이 차별화 공식 — Ballast의 슬롯 주입 철학과 동일 계열. 출처 인용 UI는 차용 가치 높음 |
| **Simply Wall St** | 비주얼 리서치 + 포트폴리오 트래커 | 스노우플레이크 시각화, 내러티브 기반 밸류에이션, 무료 트래커로 유입 → 구독 전환 | 밸류에이션을 **그림 한 장**으로 압축하는 정보 설계. Ballast의 "30초 스캔" 목표와 직결 |
| **Finimize / Morning Brew** | 데일리 금융 뉴스레터 | "3분 브리핑" 포맷, 2026년 들어 프로필 기반 AI 요약 개인화 추세 | 뉴스레터의 한계 = 비개인화. Ballast는 이미 보유 기반 개인화를 갖췄으므로 **전달 채널(이메일·푸시)** 만 약점 |

### 2.2 국내

| 서비스 | 포지션 | 핵심 기능 | Ballast 대비 시사점 |
|--------|--------|----------|---------------------|
| **토스증권 AI** (MAU 550만) | 브로커리지 내장 AI | ① 시그널(내 주식이 왜 움직였는지), ② AI 어닝콜 실시간 번역, ③ 증시 캘린더 | "왜 움직였나(Why)" 설명이 국내 사용자 최대 수요. Ballast 카드에 **변동 귀인(attribution)** 슬롯 추가 검토 가치 |
| **미래에셋증권** | 증권사 리서치 자동화 | AI 에이전트가 실적 발표 후 5시간 걸리던 기업분석 리포트를 5~15분 내 발간 | 기관도 "LLM 리포트 자동 생성"으로 이동 — 개인용 시장의 빈 공간은 **'리포트'가 아니라 '내 포트폴리오 문맥'** |
| **KB증권 Stock AI** | MTS 내 양방향 AI | 생성형 AI 맞춤 투자 정보 Q&A | 대화형 인터페이스가 표준화 중. Ballast는 현재 단방향(브리핑만) |
| **핀트(fint) / 파운트 / 콴텍** | 로보어드바이저 (일임) | AI가 직접 운용, 국내·미국주식·연금·IRP | 일임형은 규제(투자일임업) 게이트가 높음. Ballast의 "조언 아닌 점검" 포지션은 규제 회피가 아니라 **다른 카테고리** |
| **알파스퀘어** | 올인원 트레이딩 플랫폼 | 계좌 없이 쓰는 정보·분석, 멀티디바이스 | "브로커 비종속 + 가입장벽 낮음" 포지션이 유효함을 증명 |
| **라씨 매매비서 / 씽크풀** | AI 매매신호 | 전 종목 실시간 AI 매매신호 | Ballast의 안티테제 — 단정적 신호 남발. 차별화 메시지("신호가 아니라 점검")의 대조군 |

### 2.3 벤치마킹 종합 — 시장의 3가지 흐름

1. **포트폴리오 렌즈가 표준이 된다**: Robinhood Cortex·토스 시그널 모두 "범용 시황 → 내 보유 기준"으로 이동. Ballast는 컨셉상 이미 선두 그룹과 같은 줄에 서 있다.
2. **챗봇 → 에이전틱 AI**: 2026년 자산관리 트렌드는 질문에 답하는 AI가 아니라 **능동적으로 감시하고 선제 알림하는 AI**(Deloitte·InvestSuite 전망). 1일 1회 배치는 곧 구식 UX가 된다.
3. **배포 채널의 외부화**: Reflexivity→MS Copilot, Fiscal.ai→ChatGPT 앱. "내 웹앱으로 와라"가 아니라 사용자가 있는 채널로 브리핑을 밀어넣는 방향.

그리고 **Ballast만의 빈 공간(white space)**: 위 서비스 전부가 갖지 못한 조합 — ① KR+US 혼합 통화정규화 포트폴리오, ② 숫자 환각이 구조적으로 불가능한 LLM 파이프라인, ③ 브로커 비종속·로컬 프라이버시(데이터가 내 기기를 떠나지 않음), ④ 월 ₩5천 미만 운영비.

---

## 3. Next Level — 단계별 전략

전제: 현 단계의 정의된 성공 기준(dogfooding 2주 검증)을 통과한 뒤 착수한다. 각 레벨은 독립적으로 가치를 내며, 앞 레벨 없이 뒤 레벨로 건너뛰지 않는다.

### Level 1 — "보는 것"에서 "도착하는 것"으로 (개인용 완성, ~1개월)

지금의 최대 UX 결함은 브리핑이 완성돼도 **사용자가 찾아가야** 한다는 것. Finimize류 뉴스레터의 유일한 강점(도착성)을 흡수한다.

| 항목 | 내용 | 근거 |
|------|------|------|
| **브리핑 완료 푸시** | 08:30 브리핑 생성 성공 시 ntfy/Telegram으로 "오늘의 헤드라인 1줄 + 플래그 개수 + 링크" 발송. 기존 `app/notify.py` 인프라 재사용 — 실패 알림만 있는 현재를 성공 알림으로 확장 | 도착성 없는 데일리 제품은 습관 형성 실패 (모든 뉴스레터 서비스의 교훈) |
| **변동 귀인(Why) 슬롯** | 카드에 "전일 대비 큰 변동 시 관련 헤드라인 연결" — 토스 시그널의 핵심 수요. 이미 수집 중인 뉴스 헤드라인과 가격 데이터의 조인이므로 신규 소스 불필요 | 토스 시그널·Robinhood Cortex 공통 기능 |
| **이벤트 캘린더 카드** | 보유 종목의 실적 발표일(DART 공시 일정·SEC 캘린더)을 "이번 주 예정" 카드로 — Cortex의 "upcoming catalysts" | Cortex Digests 차별 요소 |
| **모바일 뷰 최적화** | 아침 30초 스캔의 실제 디바이스는 폰. 현 터미널 UI의 반응형 보강 | dogfooding에서 즉시 체감될 항목 |

### Level 2 — 배치에서 에이전트로 (제품 차별화, 1~3개월)

2026년 시장 기준선이 "에이전틱"으로 이동 중. Ballast의 게이트·검증 인프라는 이 전환에 유리하다 — 이미 "능동 감시"의 뼈대(신선도 게이트, collect_run, 알림)가 있다.

| 항목 | 내용 |
|------|------|
| **장중 트리거 브리핑** | 1일 1회 → "보유 종목 ±N% 변동·공시 발생 시" 미니 브리핑 추가 생성. Cortex의 "refresh when news breaks" 대응. 비용 가드(일 호출 상한)는 기존 config 패턴으로 |
| **대화형 후속 질문** | 브리핑 카드에서 "이 종목 더 물어보기" — 해당 종목의 검증된 수치·헤드라인만 컨텍스트로 주입한 1회성 Q&A. KB Stock AI·Fiscal.ai의 양방향성 흡수하되, **숫자 슬롯 주입 원칙 유지** |
| **주간/월간 리뷰 에이전트** | 일일 브리핑의 시계열을 메타 분석 — "이번 달 드리프트 추이, 반복 플래그, DCA 집행 여부". 데이터는 이미 briefings 테이블에 축적 중 |
| **출처 인용 UI** | 모든 AI 문장에 근거 데이터(수집일·소스) 툴팁 — Fiscal.ai가 증명한 신뢰 장치이자, Ballast의 정직성 철학을 **보이게** 만드는 작업 |

### Level 3 — 1인용에서 "각자의 1인용"으로 (확장, 3~6개월+)

핵심 판단: **중앙 SaaS화는 최선의 길이 아닐 수 있다.** 개인 맞춤 비중 제시는 투자자문업 등록 게이트에 걸리고(스펙 §Won't 명시), yfinance 등 데이터 ToS가 상업 재배포를 금지하며, 금융정보 중앙 보관은 PIPA 부담을 만든다. 세 가지 장벽을 모두 우회하는 경로가 있다:

| 경로 | 내용 | 장점 |
|------|------|------|
| **A. Self-hosted 배포 (권장 1순위)** | `ops/install.sh`를 일반화한 오픈소스/유료 라이선스 배포 — 각자 자기 기기에서 자기 데이터로 실행. "로컬 프라이버시 투자 브리핑"이라는 고유 포지션 | 자문업 규제 비대상(도구 제공), 데이터 ToS 개인 사용 범위, 운영비 0. 노트북 절전 의존 문제는 Docker/라즈베리파이/저가 VPS 가이드로 해소 |
| **B. 채널 침투형** | Reflexivity·Fiscal.ai 패턴 — 웹앱이 아니라 Telegram 봇/이메일/MCP 서버로 브리핑 제공. "Ballast를 Claude·ChatGPT에서 호출"하는 MCP 어댑터는 기술적으로 근거리 | 별도 프론트 투자 없이 배포 채널 확보 |
| **C. 중앙 SaaS** | 인증·멀티테넌트·유료 데이터 라이선스·자문업 검토 후 진행 | 가장 비싸고 느림 — A/B로 수요 검증 후에만 |

### 지키는 것 (Won't — 레벨 무관)

- 매매 신호·단정 지시 생성 (라씨류와의 차별선이자 규제선)
- 자동 매매 집행 (일임업)
- LLM의 수치 생성 허용 (제품의 근간)
- 실시간 호가·차트 경쟁 (트레이딩 터미널과 싸우지 않는다)

---

## 4. 성공 지표 (레벨별 KPI)

| 레벨 | North Star | 보조 지표 |
|------|-----------|----------|
| 현재 (dogfooding) | 14일 연속 아침 열람 | 비중 수기검증 불일치 0건, 30초 내 스캔 |
| Level 1 | 푸시→열람 전환율 ≥ 70% | 브리핑 생성 성공률 ≥ 99%, 모바일 스캔 30초 |
| Level 2 | 주당 후속 질문 ≥ 3회 (능동 사용) | 트리거 브리핑 오발률 < 10%, LLM 비용 월 ₩10,000 이내 |
| Level 3 | 외부 설치 사용자 10명 → 100명 | 설치 완료율, 2주 리텐션 (자기 기준과 동일 잣대) |

---

## 5. 참고 소스

- Robinhood — [Cortex Digests](https://robinhood.com/us/en/support/articles/cortex-digests/) · [YES/NO 이벤트 발표](https://robinhood.com/us/en/newsroom/robinhood-presents-yes-no-event/) · [TipRanks 분석](https://www.tipranks.com/news/robinhood-cortex-digests-a-unique-way-to-stay-updated-with-ai-powered-portfolio-insights)
- Reflexivity — [Series B $30M (FinTech Futures)](https://www.fintechfutures.com/ai-in-fintech/ai-co-pilot-solution-reflexivity-raises-30m-series-b-led-by-greycroft-and-ibkr) · [MS 365 Copilot 연동](https://sg.finance.yahoo.com/news/reflexivity-brings-real-time-portfolio-110000418.html) · [toggle.ai](https://toggle.ai/)
- Fiscal.ai — [리뷰 2026 (MatchMyBroker)](https://www.matchmybroker.com/tools/fiscal-ai-review) · [EU Investing Hub 리뷰](https://www.euinvestinghub.com/articles/fiscal-ai-review)
- [Simply Wall St](https://simplywall.st/) · [Finimize](https://finimize.com/)
- 토스증권 — [AI 캠페인](https://www.tossinvest.com/ai-campaign) · [헤럴드경제 투자서비스대상](https://biz.heraldcorp.com/article/10738724)
- 국내 증권사 AI — [증권사 AI 고도화 (Daum)](https://v.daum.net/v/q2v9ntRuBN) · [한투 '지금 시장은?' 1000만뷰](https://m.megaeconomy.co.kr/news/amp.html?ncode=1065581146817477) · [증권플러스 콘텐츠 전략 (thebell)](https://m.thebell.co.kr/m/newsview.asp?svccode=00&newskey=202601131424334840104543)
- [핀트](https://www.fint.co.kr/) · [알파스퀘어](https://alphasquare.co.kr/) · [라씨 매매비서](https://play.google.com/store/apps/details?id=com.thinkpool.mobile.trade) · [자본시장연구원 — 금융투자업 AI 특허 분석](https://www.kcmi.re.kr/report/report_view?report_no=2249)
- 에이전틱 AI 트렌드 — [Deloitte 2026 예측](https://www.deloitte.com/us/en/insights/industry/financial-services/financial-services-industry-predictions/2026/agentic-ai-wealth-management-productivity.html) · [InvestSuite 2026 자산관리 트렌드](https://www.investsuite.com/insights/blogs/top-wealth-management-trends-in-2026-the-shift-to-agentic-ai-and-private-markets)
