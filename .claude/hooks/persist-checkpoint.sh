#!/usr/bin/env bash
# Stop — 세션 종료 시 체크포인트 저장
HARNESS_MODE="${HARNESS_MODE:-suggest}"
[[ "$HARNESS_MODE" == "off" ]] && exit 0
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
BRANCH=$(git branch --show-current 2>/dev/null || echo "")
ISSUE_KEY=$(echo "$BRANCH" | grep -oE "[A-Z]+-[0-9]+" || echo "")
[[ -z "$ISSUE_KEY" ]] && exit 0
mkdir -p .claude/runtime
cat > ".claude/runtime/checkpoint.md" << EOF
# Harness Checkpoint
- **Issue**: $ISSUE_KEY
- **Branch**: $BRANCH
- **Timestamp**: $(date -Iseconds)
- **Last Commit**: $(git log --oneline -1 2>/dev/null || echo "none")
## 복원: /harness-resume
EOF
echo "[Harness] 체크포인트 저장됨" >&2
exit 0
