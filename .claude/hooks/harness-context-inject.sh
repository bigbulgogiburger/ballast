#!/usr/bin/env bash
# Harness Context Injection — Forced Eval Pattern
HARNESS_MODE="${HARNESS_MODE:-suggest}"
[[ "$HARNESS_MODE" == "off" ]] && exit 0
PROMPT=$(cat)

if echo "$PROMPT" | grep -qi "/jira-plan\|jira-plan"; then
  if [[ "$HARNESS_MODE" == "auto" ]]; then
    cat <<'EOF'
INSTRUCTION: MANDATORY HARNESS SKILL ACTIVATION
/jira-plan이 감지되었습니다.
1. EVALUATE: /jira-plan을 먼저 실행하여 dev-guide.md를 생성합니다.
2. ACTIVATE: 완료 후 Skill tool로 /harness-plan을 반드시 실행합니다.
3. IMPLEMENT: 두 산출물이 모두 준비된 후에만 다음 단계를 진행합니다.
CRITICAL: /harness-plan을 실행하지 않고 넘어가는 것은 WORTHLESS.
EOF
  else
    echo "RECOMMENDATION: /jira-plan 완료 후 /harness-plan 실행을 권장합니다."
  fi
fi

if echo "$PROMPT" | grep -qi "/jira-execute\|jira-execute"; then
  if [[ "$HARNESS_MODE" == "auto" ]]; then
    cat <<'EOF'
INSTRUCTION: MANDATORY HARNESS REVIEW ACTIVATION
/jira-execute가 감지되었습니다.
1. EVALUATE: Phase 구현을 완료합니다.
2. ACTIVATE: 완료 후 Skill tool로 /harness-review를 반드시 실행합니다.
3. IMPLEMENT: verdict=PASS일 때만 다음 Phase로 진행합니다.
CRITICAL: /harness-review 없이 넘어가는 것은 WORTHLESS.
EOF
  else
    echo "RECOMMENDATION: Phase 완료 후 /harness-review 실행을 권장합니다."
  fi
fi
exit 0
