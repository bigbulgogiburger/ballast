# 06 · AI 에이전트 명세 — `claude -p` 브리핑 생성

> SSoT: `TECH-DESIGN.md` v3.2 (**DTO·색·키·런타임 정본 = §15 Contract SoT, 충돌 시 §15 우선**) · E2E: `docs/00-e2e-flow.md`
> 범위: `briefing.py` 의 LLM 호출 계층. 지표 계산(`metrics/`)·수집(`collect.py`)·렌더(`templates/`)는 본 문서 밖.
> 핵심 결정(SSoT §1·§7): **코드가 숫자를 계산·주입하고 LLM은 문장·라벨만 생성한다.** LLM은 어떤 수치도 쓰지 않는다.
> 작성일: 2026-06-01

---

## 0. SSoT 정정 — G1 확정: AI 호출 메커니즘 = `claude -p` CLI

E2E G1(BLOCKER)은 "SSoT §2/§7 = Anthropic SDK" vs "프로젝트 의도 = `claude -p` CLI" 모순을 지적했다.
프로젝트 지시에 따라 **(B) `claude -p` 채택**으로 확정한다. SSoT §2/§7의 SDK 전제 항목을 CLI 제약에 맞춰 아래처럼 매핑한다(의미는 동일, 메커니즘만 교체).

| SSoT §2/§7 (SDK 전제) | `claude -p` CLI 대응 | 비고 |
|---|---|---|
| structured JSON 스키마 강제 | `--output-format json --json-schema '<schema>'` → 응답의 `structured_output` 필드 | CLI가 스키마 준수 출력 보장(공식). 추가로 코드측 Pydantic 재검증 |
| `temperature=0` (결정성) | **CLI는 temperature 직접 제어 불가** → 대체 결정성 장치: `--json-schema` 스키마 고정 + 슬롯주입(숫자는 코드) + 금지어 린터 + 재호출 | 숫자가 코드 주입이라 온도 변동의 실질 위험은 "문장 표현 흔들림"뿐 → 허용 |
| `cache_control: ephemeral` 명시 프롬프트 캐싱 | `--append-system-prompt`(고정·동일 문자열) + 배치 내 `--continue`(세션 캐시) | CLI는 명시 cache_control 미노출 → 시스템 프롬프트 고정 + 세션 재사용으로 캐시-퍼스트(§6 비용). 플래그 정본 = §15.1 |
| Claude Sonnet 4.5 고정 | `--model claude-sonnet-4-5` | 비용 통제 핵심(SSoT §13). Opus 금지 |
| 재현성(CI/cron) | `--bare`(hooks·MCP·CLAUDE.md 미로딩) + 인증(구독 로그인 또는 `ANTHROPIC_API_KEY`) | 머신 무관 동일 결과. 인증 정본 = §15.1 |

> 결론: §7 "구조화 JSON으로 문장만, 수치 코드주입" 계약은 `--json-schema` + Pydantic 파싱 + 슬롯주입으로 **인터페이스 레벨에서 연결됨**. temperature=0의 "결정성" 의도는 숫자 코드주입이 이미 달성하므로 CLI 미지원이 설계를 깨지 않는다.

---

## 1. 인터페이스 계약 (`briefing.py`)

### 1.1 LLMClient Protocol (E2E G1 fix — 전환비용 0 어댑터)

```python
# app/models.py
from typing import Protocol

class LLMClient(Protocol):
    def generate(self, prompt: str, schema: dict) -> dict:
        """프롬프트+스키마 → 스키마 준수 dict. 실패 시 LLMError. 숫자 슬롯은 비움."""
        ...
```

구현체는 `ClaudeCLIClient`(아래 §5) 하나. 추후 SDK로 바꿔도 `briefing.py`는 무수정.
**시스템 프롬프트는 시그니처에서 뺀다** — 브리핑 용도라 고정이므로 어댑터 내부 상수(`prompts/briefing.md` 경로)로 흡수한다. 04-backend 호출부(`llm.generate(prompt, schema)`)와 동일 시그니처(§15 단일 계약).

### 1.2 입력 DTO — 지표 엔진(S5) → 브리핑(S6)

LLM에 넘기는 dict는 **숫자를 포함**하되(맥락 판단용), LLM은 그 숫자를 **출력에 echo하지 않고 라벨·문장만** 생성한다.
배치 분할 join 안전성을 위해 `canonical_ticker`가 모든 항목의 1차 키다(E2E G2).

```python
# app/models.py — frozen DTO (입력)
from dataclasses import dataclass

@dataclass(frozen=True)
class SecurityInput:
    canonical_ticker: str          # join 키 (LLM이 echo, 식별자일 뿐 수치 아님)
    name: str
    market: str                    # 'KR' | 'US'
    # --- 지표 엔진 산출 (LLM은 참고만, 출력 echo 금지) ---
    valuation_band: str | None     # 예 '5년 하위 18%ile' / None=워밍업중(G3)
    valuation_warmup: bool         # per_pctile_5y NULL → 절대 PER만(G3 degrade)
    per: float | None              # 음수/NaN → None (적자, §6 음수PER 제외)
    trend_pos_52w: str             # 예 '52주 고점 대비 -8%' (맥락용·신호 아님)
    eps_trend: str                 # 'rising'|'flat'|'falling' (value trap 식별)
    headlines: list[dict]          # [{title,url,source}] 본문없음 (E2E G7)
    hold_status: str               # §15.4 status enum. 'ok'만 LLM 호출, 'data_pending'|'fx_held'|'warmup'은 보류(G3/G6), 'failed'는 LLM 머지 후 부여

@dataclass(frozen=True)
class PortfolioInput:
    drift_summary: list[dict]      # [{group,current_pct,target_pct,drift,flag_525,is_auto_target}]
    core_sat: dict                 # {core_pct,sat_pct,sat_limit_pct,over_limit:bool} — LLM 입력 컨텍스트.
                                    #   출력 asset_allocation 2층 키(satellite_pct/satellite_over_limit, §15.2)와 동일 개념(코드가 매핑)
    dca_candidates: list[dict]     # [{canonical_ticker,reason}] 드리프트 우선
    regime: str                    # CAPE/KOSPI PBR 한 줄
    one_layer_held: bool           # USD fx FAIL → 1층 배분 산출보류(G6)
```

> `valuation_band`·`per`·`trend_pos_52w` 등의 **수치 문자열은 LLM 판단용 컨텍스트일 뿐, 최종 화면 숫자는 §3 슬롯주입에서 코드가 다시 박는다.** LLM 출력에 숫자가 섞이면 §4 린터가 reject.

### 1.3 출력 DTO — LLM이 반환하는 **텍스트 전용** DTO (§15.2 정본)

> **DTO 분리(§15.2):** LLM은 `SecurityLLMOut`(문장만)을 반환하고, 코드가 여기에 수치를 슬롯주입해 최종 `SecurityCard`(수치 포함)·`BriefingDoc`로 조립한다. 최종형 정본 정의·직렬화는 **§15.2 / 04-backend §4.4**. 06은 LLM 텍스트 출력만 책임진다.

```python
# app/models.py — LLM 반환 텍스트 전용 (숫자 없음). canonical_ticker가 join 키(§15.2)
@dataclass(frozen=True)
class SecurityLLMOut:
    canonical_ticker: str          # echo 검증 통과한 join 키 (G2)
    comment: str                   # 맥락형 코멘트 (숫자 슬롯 {pos_52w} 등은 §3에서 코드 치환)
    trend_note: str                # 추세·밸류에이션 양면 라벨 문장
    investment_points: list[str]   # 투자 포인트 항목들
```

**[호출 2] 포트폴리오 LLM 출력**은 `{rebalance_note, dca_note, weight_note}` dict로 반환되어, 코드가 `BriefingDoc.portfolio_comment`(§15.2 dict)에 슬롯주입 후 담는다.

코드가 조립하는 최종 `SecurityCard`는 §15.2 필드 전체(canonical_ticker·name·instrument·…·valuation_label·week52_pos·sma200_gap·**status**·comment·trend_note·investment_points)를 가지며, `comment/trend_note/investment_points`만 `SecurityLLMOut`에서 머지하고 나머지 수치는 S5 계산값이다. `briefing.content_json` = `BriefingDoc`(§15.2: regime_label top-level, as_of 3키, asset_allocation 1·2층, holds_excluded=list[HoldExcluded], portfolio_comment dict) JSON 직렬화. Jinja2는 이 DTO만 신뢰.

---

## 2. LLM 출력 JSON 스키마 (`--json-schema`)

LLM은 **문장·라벨만, canonical_ticker는 식별자 echo만** 한다. 숫자 필드 없음.

### 2.1 [호출 1] 종목별 — `SECURITY_SCHEMA`

```python
SECURITY_SCHEMA = {
    "type": "object",
    "properties": {
        "securities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "canonical_ticker": {"type": "string"},   # echo 필수 (G2 join 키)
                    "comment": {"type": "string"},
                    "trend_note": {"type": "string"},
                    "investment_points": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["canonical_ticker", "comment",
                             "trend_note", "investment_points"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["securities"],
    "additionalProperties": False,
}
```

### 2.2 [호출 2] 포트폴리오 — `PORTFOLIO_SCHEMA`

```python
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

> 수치 슬롯이 필요한 문장은 LLM이 **placeholder 토큰**(`{pos_52w}`, `{drift}`, `{core_pct}` 등)으로 쓰고, §3에서 코드가 치환. 스키마에 숫자형 필드를 두지 않는 것이 1차 방어선.

---

## 3. 수치 슬롯 주입 (SSoT §7 — "숫자는 코드가 박는다")

LLM은 문장에 **명명된 placeholder**만 남기고, 코드가 S5 계산값으로 치환한다.
echo 대조-reject 루프는 SSoT가 폐기(표기차 무한재생성) → **단방향 치환**만 한다.

```python
# app/briefing.py
import re

SLOT = re.compile(r"\{([a-z0-9_]+)\}")

def inject(text: str, slots: dict[str, str]) -> str:
    """LLM 문장의 {key}를 코드 계산값으로 치환. 미정의 키 발견 시 LLMError(누락 방지)."""
    def repl(m: re.Match) -> str:
        key = m.group(1)
        if key not in slots:
            raise LLMError(f"unknown slot {{{key}}}")
        return slots[key]
    return SLOT.sub(repl, text)
```

종목별 `slots`는 S5 `SecurityInput`에서 코드가 포맷(예 `{"pos_52w": "-8%", "per": "12.4"}`).
포트폴리오 `slots`는 `PortfolioInput`에서. **placeholder가 안 박힌 raw 숫자가 문장에 있으면 §4 린터가 reject.**

> day-0/보류(G3·G6): `hold_status != 'ok'` 종목은 LLM 호출 자체에서 제외하고 placeholder 카드("데이터 준비중"/"환율 보류")만 렌더. `valuation_warmup=True`면 `trend_note`에 "5년 percentile 워밍업 중(절대 PER만)" 고정문 주입(LLM 생성 아님).

---

## 4. 금지어 린터 + 종목수·숫자 검증 게이트 (SSoT §7 (a)(b))

슬롯 주입 **후** 최종 문자열에 대해 검증. 하나라도 실패 → 해당 배치 1회 재호출, 재실패 시 그 종목 "처리 실패" 카드.

```python
# app/briefing.py
BANNED = re.compile(
    r"(매수하세요|매도하세요|사세요|파세요|지금이?\s*기회|반드시|"
    r"무조건|급등|급락 예상|확실|보장|추천합니다)"
)
RAW_NUMBER = re.compile(r"(?<![{\w])\d+(\.\d+)?\s*(%|원|달러|\$|배)")  # 슬롯 밖 raw 숫자

def lint(card_text: str) -> None:
    if BANNED.search(card_text):
        raise LintError("banned phrase")
    if RAW_NUMBER.search(card_text):
        raise LintError("raw number outside slot")  # LLM이 숫자 직접 씀 → reject
```

**종목수·join 검증 (E2E G2):** LLM 응답 `securities[].canonical_ticker`를 holdings 기준 **left-join**.
- 미매칭(LLM이 `005930`→`삼성전자`로 변형) → 해당 종목 "처리 실패" 카드.
- 중복 ticker → 첫 건만 채택, 로그 경고.
- `len(응답) != len(입력 배치)` → 누락분 "처리 실패" 카드.
순서 무관(ticker join이라 배치 분할에도 안전).

> M3 검증(SSoT §11): **금지어 0건 assert + 면책 문자열 포함 + LLM 수치 0개**.

---

## 5. `ClaudeCLIClient` 구현 + 호출 예시

### 5.1 CLI 호출 (subprocess)

```python
# app/briefing.py
import json, subprocess
from pathlib import Path

class ClaudeCLIClient:
    SYSTEM_PROMPT_FILE = "app/prompts/briefing.md"     # 고정(면책·톤·few-shot). 어댑터 내부 상수.

    def __init__(self, model: str = "claude-sonnet-4-5"):
        self.model = model
        self._system_prompt = Path(self.SYSTEM_PROMPT_FILE).read_text(encoding="utf-8")

    def generate(self, prompt: str, schema: dict) -> dict:  # §15 단일 시그니처(시스템프롬프트 비노출)
        cmd = [
            "claude", "-p",
            "--bare",                                  # CI 재현성: hooks/MCP/CLAUDE.md 미로딩
            "--model", self.model,                     # Sonnet 고정 (비용)
            "--append-system-prompt", self._system_prompt,  # §15.1 정본 플래그(고정 문자열)
            "--output-format", "json",
            "--json-schema", json.dumps(schema),       # content 스키마 강제
            "--allowedTools", "",                      # 도구 0개 (순수 텍스트 생성)
        ]
        proc = subprocess.run(
            cmd, input=prompt, capture_output=True, text=True, timeout=120
        )
        if proc.returncode != 0:                       # exit code != 0 → 실패
            raise LLMError(f"claude -p exit {proc.returncode}: {proc.stderr[:200]}")
        envelope = json.loads(proc.stdout)             # {result, structured_output, total_cost_usd, is_error, session_id}
        if envelope.get("is_error"):
            raise LLMError(f"claude error: {envelope.get('result')}")
        return envelope["structured_output"]           # 스키마 준수 dict
```

> `ANTHROPIC_API_KEY`는 `.env`(SSoT §10)에서 환경변수로. `--bare`라 keychain/OAuth 미사용 → cron 적합.
> `total_cost_usd`를 로깅해 일/월 비용 추적(SSoT §13).

### 5.2 배치 분할 호출 (SSoT §7 — 8~10개씩)

```python
BATCH = 10

def run_securities(client: LLMClient,
                   items: list[SecurityInput]) -> tuple[list[SecurityLLMOut], list[HoldExcluded]]:
    """06 소유 경계: LLM 호출 + ct 조인(G2) + 금지어 린트 + 텍스트 슬롯주입까지.
       **텍스트 전용** SecurityLLMOut와, LLM이 누락/중복한 ct(=failed) HoldExcluded를 반환.
       수치는 절대 안 건드림 — 최종 SecurityCard 조립(수치 주입)은 04 assemble_briefing 소유."""
    live = [s for s in items if s.hold_status == "ok"]   # 보류 종목(data_pending/fx_held/warmup) 제외(G3/G6)
    outs: list[SecurityLLMOut] = []
    failed: list[HoldExcluded] = []
    for i in range(0, len(live), BATCH):
        batch = live[i:i + BATCH]
        resp = client.generate(build_security_prompt(batch), SECURITY_SCHEMA)
        batch_outs, batch_failed = assemble_llm_outs(batch, resp["securities"])  # §3 슬롯주입 + §4 린트/join
        outs += batch_outs; failed += batch_failed
    return outs, failed

def run_portfolio(client: LLMClient, port_input: PortfolioInput) -> dict:
    resp = client.generate(port_input.prompt, PORTFOLIO_SCHEMA)   # {rebalance_note,dca_note,weight_note}
    return inject_portfolio_slots(resp, port_input)              # §3 텍스트 슬롯주입 + §4 린트
```

`assemble_llm_outs`가 §3 텍스트 슬롯주입 + §4 린트/join 수행 → `SecurityLLMOut`(텍스트만). LLM 미매칭/중복 ct는 `HoldExcluded(ct, reason='llm_unmatched'|'llm_duplicate')`로 분리 반환. 보류(`hold_status != 'ok'`) 종목은 04가 `status` 카드로 별도 렌더(holds_excluded 아님).

---

## 6. 프롬프트 설계 (`prompts/briefing.md`)

시스템 프롬프트는 **고정**(배치마다 동일) → 세션 캐시-퍼스트로 입력비 절감(SSoT §7·§13).
가변 데이터(종목 dict)는 stdin 프롬프트로만 들어가 캐시 경계를 분리한다.

`prompts/briefing.md` 구성(파일을 어댑터가 읽어 `--append-system-prompt`로 전달, §15.1):
1. **역할·톤**: "정보 제공·교육 목적의 맥락형 코멘트. 단정·권유 금지."
2. **하드 규칙**:
   - 입력에 없는 수치·사실 생성 금지.
   - **숫자는 직접 쓰지 말고 placeholder `{key}`로만** 표기(코드가 치환).
   - `canonical_ticker`는 입력 그대로 echo(번역·종목명 변환 금지 — G2).
   - 금지어("매수/매도하세요·지금 기회·반드시·보장") 사용 금지.
3. **양면 라벨 규칙(SSoT §6 ③)**: "저평가" 단정 대신 "5년 하위 X%ile (저평가 또는 디레이팅 — 펀더멘털 확인)".
4. **few-shot good/bad 페어**(SSoT §7):

```
[BAD]  "삼성전자는 12.4배로 저평가, 지금 매수 기회입니다."
[GOOD] "삼성전자 PER {per}배는 5년 {valuation_band}입니다. 저평가일 수도,
        업황 디레이팅일 수도 있어 EPS 추세 확인이 필요합니다."
```

> 면책 문구는 **LLM이 아니라 코드가** `BriefingDoc.disclaimer` 상수로 박는다(§1.3). LLM 환각·누락 차단.

---

## 7. 비용 (Sonnet 고정)

SSoT §13 표 유지(모델 Sonnet 4.5 고정이 통제 핵심):

| 종목 수 | 일 | 월(22거래일) |
|---|---|---|
| 10종목 | ~$0.05 | ~₩1,500 |
| 30종목 | ~$0.16 | ~₩4,700 |

- 시스템 프롬프트 고정 + 배치 내 세션 재사용 → 입력비 추가 절감.
- `--output-format json`의 `total_cost_usd`를 호출마다 로깅해 실측 대조.
- `--bare`로 불필요한 컨텍스트(CLAUDE.md·MCP) 미로딩 → 입력 토큰·startup 절감.
- **인증·과금 정본 = §15.1**: 구독 인증(Claude Code 로그인)이면 **토큰 종량과금 없음**(위 비용표는 `ANTHROPIC_API_KEY` 종량 경로에만 적용). PoC는 둘 중 가용한 인증을 쓰되, API 키 경로면 `total_cost_usd` 로깅으로 비용표 대조. (구독 플랜의 SDK/headless 크레딧 정책이 추후 바뀌면 §15.1을 SSoT에서 먼저 갱신.)

---

## 8. 다른 영역과의 인터페이스 요약

- **입력**(S5 `metrics/`): `SecurityInput`/`PortfolioInput` DTO. `canonical_ticker`가 join 1차키, `hold_status`로 보류 종목 구분.
- **출력**(S7→S8 렌더): `BriefingDoc` → `briefing.content_json`. Jinja2는 이 DTO만 신뢰.
- **수치 경계**: LLM=문장·라벨·placeholder, 코드=슬롯주입. 라인 경계가 §4 린터(RAW_NUMBER).
- **게이트 연동**(S4): `hold_status='fx_held'`(G6 USD fx FAIL)·`'data_pending'`(G3 백필중) 종목은 LLM 미호출, placeholder 카드.

---

> 출처: [Run Claude Code programmatically — Claude Code Docs](https://code.claude.com/docs/en/headless)
