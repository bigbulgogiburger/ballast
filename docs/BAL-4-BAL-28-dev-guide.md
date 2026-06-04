# [BAL-28] assemble_briefing + run_briefing 파이프라인 — slice dev-guide

> 부모: `docs/BAL-4-dev-guide.md` · Wave2 · 소유: `app/briefing.py`(BAL-27과 공유) + `app/config.py`(disclaimer)

### 0. Touched Files
- **수정**: `app/briefing.py` (assemble_briefing, run_briefing, build_*_inputs, build_security_card, _save_blocked_briefing)
- **수정**: `app/config.py` (DISCLAIMER 상수)
- **수정 가능**: `app/db.py` (insert_briefing/headlines_map/holdings 헬퍼 부재 시 추가 — named param)
- 읽기: 04 §10.1·§10.3, `app/metrics/*`(W3), `app/metrics/gate.py`(evaluate_gate/collect_complete_today), `app/models.py`(SecurityCard/BriefingDoc)

### 1. 작업 범위 (04 §10.3 assemble + §10.1 run_briefing)
```python
# app/config.py
DISCLAIMER = "본 브리핑은 정보 제공·교육 목적이며 투자 권유가 아닙니다. …"  # 고정 상수

# app/briefing.py
def assemble_briefing(metrics, sec_llm, sec_failed, port_comment, gate) -> BriefingDoc:
    # ct로 SecurityLLMOut↔metrics 병합 → SecurityCard (수치=metrics 코드값, 텍스트=LLM).
    # LLM 누락분(sec_failed)은 status='failed' 카드 + holds_excluded.
    # disclaimer=config.DISCLAIMER 박음. regime_label top-level, as_of 3키, asset_allocation 1·2층.
def run_briefing(conn, llm, user_id=1) -> int:
    # 선검사 collect_complete_today → 미완 시 _save_blocked_briefing.
    # gate=evaluate_gate. blocked→_save_blocked_briefing(banner).
    # priced=build_priced. metrics 산출. sec_inputs/port_input 조립(보류 제외).
    # run_securities/run_portfolio(06). assemble_briefing. db.insert_briefing.
def _save_blocked_briefing(conn, gate) -> int:   # banner doc 저장
def build_security_inputs(metrics, news) -> list[SecurityInput]   # 보류 hold_status 포함
def build_portfolio_input(metrics) -> PortfolioInput
def build_security_card(m, llm_out, gate) -> SecurityCard         # 수치 코드 주입
```
SecurityInput/PortfolioInput DTO는 briefing.py에 정의(06 §1.2): SecurityInput(canonical_ticker, name, hold_status, slots:dict, ...), PortfolioInput(prompt, slots).

### 2. 인수조건 (★ M3 DoD)
- [ ] 최종 BriefingDoc에 **LLM raw 숫자 0개** + **면책(disclaimer) 포함**
- [ ] blocked 시 banner doc 저장
- [ ] 보류 종목 status 카드(LLM 미호출), holds_excluded는 G2(LLM 미매칭/중복)만
- [ ] total_cost_usd 로깅 (envelope 비용 — logging 모듈, print 금지)

### 3. 위험·확인사항
- **run_all_metrics(§10.1) 부재 가능**: W3은 개별 metric 함수만. metrics 통합 객체(securities 리스트 + portfolio 결과)를 build하는 최소 어댑터 필요 여부 확인 → 없으면 build. 과도하면 범위를 assemble까지로 좁히고 run_briefing은 최소 통합으로.
- **db 헬퍼**: insert_briefing/headlines_map/holdings(HoldingRow 반환) 부재 시 추가. SQL named param only.
- 면책·금지어·raw 숫자 검증은 FakeLLMClient로 테스트.

### 4. 검증
`ruff check app/briefing.py app/config.py app/db.py`. run_briefing은 FakeLLMClient + 인메모리 conn으로 1건 생성 → disclaimer 포함·raw 숫자 0 단언.
