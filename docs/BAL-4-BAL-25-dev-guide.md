# [BAL-25] prompts/briefing.md — slice dev-guide

> 부모: `docs/BAL-4-dev-guide.md` · Wave1 (병렬) · 소유: `app/prompts/briefing.md` (신규)

### 0. Touched Files
- **신규**: `app/prompts/briefing.md` (마크다운, 코드 아님)
- 읽기: 06 §6

### 1. 작업 범위 (06 §6 — 시스템 프롬프트, 어댑터가 `--append-system-prompt`로 전달)
구성:
1. **역할·톤**: "정보 제공·교육 목적의 맥락형 코멘트. 단정·권유 금지."
2. **하드 규칙**:
   - 입력에 없는 수치·사실 생성 금지.
   - **숫자는 직접 쓰지 말고 placeholder `{key}`로만** 표기 (코드가 치환).
   - `canonical_ticker`는 입력 그대로 echo (번역·종목명 변환 금지 — G2).
   - 금지어("매수/매도하세요·지금 기회·반드시·보장") 사용 금지.
3. **양면 라벨 규칙(SSoT §6 ③)**: "저평가" 단정 대신 "5년 하위 {pctile} (저평가 또는 디레이팅 — 펀더멘털 확인)".
4. **few-shot good/bad 페어**:
```
[BAD]  "삼성전자는 12.4배로 저평가, 지금 매수 기회입니다."
[GOOD] "삼성전자 PER {per}배는 5년 {valuation_band}입니다. 저평가일 수도,
        업황 디레이팅일 수도 있어 EPS 추세 확인이 필요합니다."
```

### 2. 인수조건
- [ ] 숫자 생성 금지·placeholder 규칙·금지어 규칙 명시
- [ ] ct echo(G2) 규칙 명시
- [ ] good/bad 예시 포함
- [ ] 면책 문구는 **여기 넣지 않음** (코드가 disclaimer 상수로 박음 — 06 §6 말미)

### 3. 검증
파일 존재 + 위 4구성 포함. `ClaudeCLIClient`가 `Path(...).read_text()` 가능해야 함(UTF-8).
