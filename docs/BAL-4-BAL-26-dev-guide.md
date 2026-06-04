---
issue: BAL-26
title: SECURITY/PORTFOLIO_SCHEMA
type: slice
status: closed
week: W4
parent: BAL-4
persona: Python Expert
created: 2026-06-04
closed: 2026-06-04
---

# [BAL-26] SECURITY_SCHEMA / PORTFOLIO_SCHEMA — slice dev-guide

> 부모: `docs/BAL-4-dev-guide.md` · Wave1 (병렬) · 소유: `app/schemas.py` (신규)

### 0. Touched Files
- **신규**: `app/schemas.py`
- 읽기: 06 §2, `app/models.py`(SecurityLLMOut — §15.2 정합 대조)

### 1. 작업 범위 (06 §2 — 스펙 정본)
LLM은 **문장·라벨만, canonical_ticker는 echo만**. 숫자 필드 없음.
```python
SECURITY_SCHEMA = {
    "type": "object",
    "properties": {
        "securities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "canonical_ticker": {"type": "string"},
                    "comment": {"type": "string"},
                    "trend_note": {"type": "string"},
                    "investment_points": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["canonical_ticker", "comment", "trend_note", "investment_points"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["securities"],
    "additionalProperties": False,
}

PORTFOLIO_SCHEMA = {
    "type": "object",
    "properties": {
        "rebalance_note": {"type": "string"},
        "dca_note": {"type": "string"},
        "weight_note": {"type": "string"},
    },
    "required": ["rebalance_note", "dca_note", "weight_note"],
    "additionalProperties": False,
}
```

### 2. 인수조건
- [ ] SECURITY_SCHEMA 필드 = SecurityLLMOut(canonical_ticker/comment/trend_note/investment_points) 정합
- [ ] PORTFOLIO_SCHEMA = {rebalance_note,dca_note,weight_note}
- [ ] **숫자형 필드 0개** (1차 방어선) · `additionalProperties: False`
- [ ] `json.dumps(SCHEMA)`로 `--json-schema` 전달 가능 (직렬화 안전)

### 3. 검증
`python -c "from app.schemas import SECURITY_SCHEMA, PORTFOLIO_SCHEMA; import json; json.dumps(SECURITY_SCHEMA); json.dumps(PORTFOLIO_SCHEMA)"` + `ruff check app/schemas.py`.
