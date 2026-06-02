#!/usr/bin/env bash
# Python compile-check — 변경 파일 추적 + .py 문법 검사 (py_compile)
HARNESS_MODE="${HARNESS_MODE:-suggest}"
[[ "$HARNESS_MODE" == "off" ]] && exit 0
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | grep -oE '"file_path"\s*:\s*"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)".*/\1/' 2>/dev/null || echo "")
[[ -z "$FILE_PATH" ]] && exit 0

mkdir -p .claude/runtime
echo "$FILE_PATH" >> .claude/runtime/changed-files.txt
sort -u .claude/runtime/changed-files.txt -o .claude/runtime/changed-files.txt

# .py 파일이면 가벼운 문법 검사 (의존성 import 없이 컴파일만)
if [[ "$FILE_PATH" == *.py && -f "$FILE_PATH" ]] && command -v python3 >/dev/null 2>&1; then
  if ! python3 -m py_compile "$FILE_PATH" 2>/tmp/harness-pycompile.err; then
    echo "[Harness] 🔴 문법 오류: $FILE_PATH" >&2
    cat /tmp/harness-pycompile.err >&2
  fi
fi
exit 0
