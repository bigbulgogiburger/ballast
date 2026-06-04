# [BAL-27] run_securities/run_portfolio — slice dev-guide (하위 BAL-54/55)

> 부모: `docs/BAL-4-dev-guide.md` · Wave2 · 소유: `app/briefing.py` (BAL-28과 공유 — 한 에이전트가 함께 구현)

### 0. Touched Files
- **수정**: `app/briefing.py` (run_securities/run_portfolio 부분 + lint/inject 헬퍼)
- 읽기: `app/llm.py`(LLMError), `app/schemas.py`, `app/models.py`(SecurityLLMOut/HoldExcluded), 06 §3·§4·§5.2

### 1. 작업 범위 (06 §3 슬롯주입 + §4 린터 + §5.2 배치)
`app/briefing.py`에:
```python
import re
from app.llm import LLMError
from app.schemas import SECURITY_SCHEMA, PORTFOLIO_SCHEMA
from app.models import SecurityLLMOut, HoldExcluded

class LintError(Exception): ...

SLOT = re.compile(r"\{([a-z0-9_]+)\}")
BANNED = re.compile(r"(매수하세요|매도하세요|사세요|파세요|지금이?\s*기회|반드시|무조건|급등|급락 예상|확실|보장|추천합니다)")
RAW_NUMBER = re.compile(r"(?<![{\w])\d+(\.\d+)?\s*(%|원|달러|\$|배)")

def inject(text: str, slots: dict[str, str]) -> str:    # {key} 단방향 치환, 미정의→LLMError
def lint(card_text: str) -> None:                        # BANNED / RAW_NUMBER → LintError
def run_securities(client, items) -> tuple[list[SecurityLLMOut], list[HoldExcluded]]:
    # live = hold_status=='ok'만(보류 LLM 미호출). BATCH=10. assemble_llm_outs로 슬롯주입+린트+join.
def run_portfolio(client, port_input) -> dict:           # {rebalance_note,dca_note,weight_note} 슬롯주입+린트
```

### BAL-54 (하위): 배치 분할 + ct 조인 (G2)
- BATCH=10씩 분할 호출. 응답 `securities[].canonical_ticker`를 입력 배치에 **left-join**.
- 미매칭(변형) → `HoldExcluded(ct, 'llm_unmatched')` + 해당 종목 failed.
- 중복 ticker → 첫 건만, 로그 경고('llm_duplicate').
- `len(응답) != len(배치)` → 누락분 failed. 순서 무관(ticker join).

### BAL-55 (하위): 금지어 린트 + RAW_NUMBER 린터 + 텍스트 슬롯 주입
- 슬롯 주입 **후** 최종 문자열에 lint(). 실패 → 배치 1회 재호출, 재실패 시 그 종목 failed 카드.
- `assemble_llm_outs(batch, resp_securities)` → (list[SecurityLLMOut], list[HoldExcluded]).

### 2. 인수조건 (★ M3 검증)
- [ ] ct join: 누락/중복/변형 시 failed + holds_excluded, 정상 종목 영향 0
- [ ] 금지어 0건 (BANNED) · raw 숫자 0개 (RAW_NUMBER) — 슬롯 밖 숫자 reject
- [ ] 보류 종목(hold_status != 'ok')은 live 필터 제외 → LLM 미호출
- [ ] SecurityLLMOut은 **텍스트 전용** (수치 안 건드림 — 수치는 BAL-28 assemble가 주입)

### 3. 검증
FakeLLMClient(canned resp)로 run_securities 검증. `ruff check app/briefing.py`. **실제 claude CLI 호출 금지.**
