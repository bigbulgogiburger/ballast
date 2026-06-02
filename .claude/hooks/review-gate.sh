#!/usr/bin/env bash
# PreToolUse — git commit 전 품질 게이트
HARNESS_MODE="${HARNESS_MODE:-suggest}"
[[ "$HARNESS_MODE" == "off" ]] && exit 0
INPUT=$(cat)
CMD=$(echo "$INPUT" | grep -oE '"command"\s*:\s*"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)".*/\1/' 2>/dev/null || echo "")
if echo "$CMD" | grep -qi "git commit"; then
  VERDICT_FILE=".claude/runtime/aggregate-verdict.md"
  if [[ ! -f "$VERDICT_FILE" ]]; then
    echo "[Harness] ⚠️ /harness-review가 실행되지 않았습니다." >&2
    exit 0
  fi
  VERDICT=$(grep -oiE "(PASS|ITERATE|ESCALATE)" "$VERDICT_FILE" | head -1 || echo "UNKNOWN")
  if echo "$VERDICT" | grep -qi "ITERATE\|ESCALATE"; then
    echo "[Harness] 🔴 품질 게이트 미통과 (verdict=$VERDICT)." >&2
    [[ "$HARNESS_MODE" == "auto" ]] && exit 1
  elif echo "$VERDICT" | grep -qi "PASS"; then
    echo "[Harness] ✅ 품질 게이트 통과." >&2
  fi
fi
exit 0
