"""LLM 어댑터 — Claude CLI subprocess 구현 (BAL-24).

`models.LLMClient` Protocol 구현체. `briefing.py`는 본 모듈의 `generate`만
호출하므로 추후 SDK 등으로 교체해도 호출측 무수정 (06 §1.1).

NEVER: API 키·시스템 프롬프트를 로그/예외 메시지/URL에 노출 금지.
  stderr는 200자 절단(키 미포함 보장 — 06 §5.1).
"""
import json
import subprocess
from pathlib import Path


class LLMError(Exception):
    """claude CLI 실패(exit≠0) 또는 is_error envelope를 래핑."""


def make_llm_client() -> "ClaudeCLIClient":
    """기본 LLM 클라이언트 팩토리 — ClaudeCLIClient 반환(스크립트 진입점용)."""
    return ClaudeCLIClient()


class ClaudeCLIClient:
    """`claude -p` subprocess 어댑터. models.LLMClient Protocol 구현 (06 §5.1)."""

    # 파일 위치 기준 절대경로 — cwd 비의존(cron/다른 디렉토리 import 안전).
    SYSTEM_PROMPT_FILE = Path(__file__).resolve().parent / "prompts" / "briefing.md"

    def __init__(self, model: str = "claude-sonnet-4-5") -> None:
        self.model = model
        self._system_prompt = Path(self.SYSTEM_PROMPT_FILE).read_text(encoding="utf-8")

    def generate(self, prompt: str, schema: dict) -> dict:
        """프롬프트+스키마로 구조화 출력(structured_output) dict 반환.

        Raises:
            LLMError: exit code≠0 또는 envelope.is_error.
        """
        cmd = [
            "claude",
            "-p",
            "--bare",  # CI 재현성: hooks/MCP/CLAUDE.md 미로딩
            "--model",
            self.model,
            "--append-system-prompt",
            self._system_prompt,
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(schema),
            "--allowedTools",
            "",  # 도구 0개 (순수 텍스트 생성)
        ]
        proc = subprocess.run(
            cmd, input=prompt, capture_output=True, text=True, timeout=120
        )
        if proc.returncode != 0:
            # stderr 200자 절단 — API 키 등 시크릿 로그/예외 노출 차단.
            raise LLMError(f"claude -p exit {proc.returncode}: {proc.stderr[:200]}")
        envelope = json.loads(proc.stdout)
        if envelope.get("is_error"):
            # result 300자 절단 — 시스템 프롬프트 echo·오류 상세의 로그 노출 차단.
            raise LLMError(f"claude error: {str(envelope.get('result', ''))[:300]}")
        return envelope["structured_output"]
