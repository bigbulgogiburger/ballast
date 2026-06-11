"""LLM --json-schema 페이로드 (06 §2 — 스펙 정본).

LLM은 문장·라벨만 생성하고 canonical_ticker는 echo만 한다.
숫자형 필드는 0개 — 수치는 코드가 슬롯주입한다(1차 방어선).
모든 스키마는 `json.dumps`로 `--json-schema`에 전달 가능하도록 직렬화 안전.
"""

from typing import Any

SECURITY_SCHEMA: dict[str, Any] = {
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
                    "investment_points": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "why_note": {"type": "string"},
                },
                "required": [
                    "canonical_ticker",
                    "comment",
                    "trend_note",
                    "investment_points",
                    "why_note",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["securities"],
    "additionalProperties": False,
}

PORTFOLIO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "rebalance_note": {"type": "string"},
        "dca_note": {"type": "string"},
        "weight_note": {"type": "string"},
    },
    "required": ["rebalance_note", "dca_note", "weight_note"],
    "additionalProperties": False,
}
