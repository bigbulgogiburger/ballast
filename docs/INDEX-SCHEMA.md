# INDEX-SCHEMA.md — Ballast(BAL) wiki 정책

> jira-ingest + wiki-lint 공통 SSoT의 **프로젝트별 schema**. 카테고리·cross-ref·bounded_writes 정의.
> SSoT 절차: `~/.claude/skills/_wiki-schema.md`. 본 파일은 BAL 프로젝트 적응판.

```yaml
version: 1
project: ballast
issue_prefix: BAL

categories:
  - id: foundational
    label: 기반 스펙 (제품/설계/백엔드/DB/AI)
    match:
      pattern: "^[0-9]{2}-.*\\.md$"
    columns: [num, file, summary, updated]

  - id: decisions
    label: 의사결정 (ADR · m1a/w2 decisions)
    match:
      pattern: "^(adr/.*|BAL-\\d+-.*-decisions)\\.md$"
    columns: [file, scope, updated]

  - id: issue_guides
    label: 이슈 dev-guide
    # BAL 슬라이스 구분자는 '-BAL-' (예: BAL-3-BAL-18-dev-guide.md). default의 +/: 아님.
    match:
      pattern: "^BAL-\\d+(?:-BAL-\\d+)?-dev-guide\\.md$"
    columns: [issue, status, title, week, parent, owns, persona, updated]

  - id: process
    label: 오케스트레이션 기록 (wave 실행)
    match:
      pattern: "^BAL-\\d+-.*-orchestration\\.md$"
    columns: [file, scope, updated]

cross_refs:
  adr_pattern: "\\bADR-\\d+\\b"
  adr_dir: "docs/adr/"          # 이 프로젝트 ADR은 docs/adr/NNNN-*.md (08-decision-log.md 없음)
  issue_pattern: "\\bBAL-\\d+\\b"

closure_signals:
  jira_done_transition: true     # 이 프로젝트는 QA 상태 없음 — 완료(Done)가 종결
  archive_dir_exists: ".claude/runtime/archive/<ISSUE>"

bounded_writes:
  always:
    - "docs/INDEX.md"
    - "docs/LOG.md"
  conditional:
    - path: "docs/adr/*.md"
      write_when:
        - mode: "closure"
        - dev_guide.related_adrs: not_empty
      action: "upsert ingest-managed block per ADR file (Referenced-by)"
  forbidden:
    - "docs/0[0-9]-*.md"          # 기반 스펙 정본 — ingest 편집 금지
    - "CLAUDE.md"                  # auto-patch는 onboarding 1회만, 이후 forbidden
    - "CHANGELOG.md"
    - "**/*.py"
    - "**/*.html"
    - "**/*.css"

stale_thresholds:
  planned_days: 7
  last_activity_days: 14

claude_md_integration:
  mode: auto-patch
  target_section: "Reference Docs"
```

## 비고 — BAL 적응점 (default 대비)
- **ADR 위치**: `docs/adr/NNNN-*.md` (default의 `08-decision-log.md` 미사용).
- **슬라이스 구분자**: `BAL-3-BAL-18-dev-guide.md` 형태(`-BAL-`). INDEX key는 `BAL-3::BAL-18`로 표기.
- **QA 상태 없음**: 완료(Done) 전이가 closure 신호.
- **sprint/setup 디렉토리 없음**: 대신 `process`(orchestration) 카테고리.
- **forbidden 확장**: Python/HTML/CSS 코드 + 기반 스펙 `0X-*.md` 보호.
