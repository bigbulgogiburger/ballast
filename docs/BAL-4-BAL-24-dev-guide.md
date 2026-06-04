# [BAL-24] ClaudeCLIClient subprocess — slice dev-guide

> 부모: `docs/BAL-4-dev-guide.md` · Wave1 (병렬) · 소유: `app/llm.py` (신규)

### 0. Touched Files
- **신규**: `app/llm.py`
- 읽기: `app/models.py`(LLMClient Protocol, BAL-3 완료), 06 §5.1
- ⚠️ `briefing.py` 만지지 말 것 (BAL-27/28). 스펙의 `# app/briefing.py` 주석은 무시 — 본 슬라이스는 분리 모듈.

### 1. 작업 범위 (06 §5.1 — 스펙 코드 정본)
```python
import json, subprocess
from pathlib import Path

class LLMError(Exception): ...

class ClaudeCLIClient:               # implements models.LLMClient Protocol
    SYSTEM_PROMPT_FILE = "app/prompts/briefing.md"
    def __init__(self, model: str = "claude-sonnet-4-5"):
        self.model = model
        self._system_prompt = Path(self.SYSTEM_PROMPT_FILE).read_text(encoding="utf-8")
    def generate(self, prompt: str, schema: dict) -> dict:
        cmd = ["claude","-p","--bare","--model",self.model,
               "--append-system-prompt",self._system_prompt,
               "--output-format","json","--json-schema",json.dumps(schema),
               "--allowedTools",""]
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            raise LLMError(f"claude -p exit {proc.returncode}: {proc.stderr[:200]}")
        envelope = json.loads(proc.stdout)
        if envelope.get("is_error"):
            raise LLMError(f"claude error: {envelope.get('result')}")
        return envelope["structured_output"]
```
- `total_cost_usd`는 envelope에 있음 → 호출측(run_briefing)이 로깅하도록 envelope 전체 접근이 필요하면 별도 메서드 고려. 최소: generate는 structured_output 반환(스펙대로). 비용 로깅 훅은 BAL-28에서.

### 2. 인수조건
- [ ] subprocess 호출 + structured_output 파싱
- [ ] exit≠0 / is_error envelope → LLMError
- [ ] **API 키·시스템프롬프트를 로그/예외 메시지에 노출 금지** (stderr 200자 절단 — 키 미포함 확인)

### 3. 위험
- 테스트에서 실제 subprocess 호출 금지 — 본 슬라이스는 import + 시그니처만 검증. 실제 generate는 BAL-27/28 테스트에서 FakeLLMClient로 대체.
- `app/prompts/briefing.md`(BAL-25)가 아직 없으면 `__init__`이 FileNotFoundError → 테스트는 prompt 파일 존재 후 또는 SYSTEM_PROMPT_FILE monkeypatch.

### 4. 검증
`python -c "from app.llm import ClaudeCLIClient, LLMError"` + `ruff check app/llm.py`.
