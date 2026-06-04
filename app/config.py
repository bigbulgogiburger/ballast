"""앱 설정 로더 (04 §2).

.env를 load_dotenv()로 로드한 뒤 API 키와 설정 기본값을 노출한다.
스캐폴드 단계이므로 환경변수가 없어도 None으로 죽지 않는다.
필수 키는 주석에 표기 — 실제 사용처(config.load 등)에서 os.environ[...]로 강제될 예정.
비밀값 하드코딩 금지.
"""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

# DB 경로 (매니페스트 db_path 기본값)
DB_PATH: str = os.environ.get("DB_PATH", "data/ballast.db")

# API 키 — 스캐폴드에서는 get()으로 읽어 None 허용.
# 필수(누락 시 실사용에서 KeyError로 실패해야 함):
#   FINNHUB_API_KEY, FMP_API_KEY, DART_API_KEY,
#   NAVER_CLIENT_ID, NAVER_CLIENT_SECRET, SEC_USER_AGENT
# 선택: ECOS_API_KEY, ANTHROPIC_API_KEY
FINNHUB_API_KEY: str | None = os.environ.get("FINNHUB_API_KEY")  # 필수
FMP_API_KEY: str | None = os.environ.get("FMP_API_KEY")  # 필수
DART_API_KEY: str | None = os.environ.get("DART_API_KEY")  # 필수
NAVER_CLIENT_ID: str | None = os.environ.get("NAVER_CLIENT_ID")  # 필수
NAVER_CLIENT_SECRET: str | None = os.environ.get("NAVER_CLIENT_SECRET")  # 필수
SEC_USER_AGENT: str | None = os.environ.get("SEC_USER_AGENT")  # 필수
ECOS_API_KEY: str | None = os.environ.get("ECOS_API_KEY")  # 선택
ANTHROPIC_API_KEY: str | None = os.environ.get("ANTHROPIC_API_KEY")  # 선택

# 토큰버킷 rps (config_notes)
FMP_RPS: float = 3.0
FINNHUB_RPS: float = 1.0
NAVER_RPS: float = 5.0

# 고정 면책 문구 — 코드 상수(LLM 생성 금지, 모든 브리핑에 박힌다. 06 §1.3 / 01 AC3).
DISCLAIMER: str = (
    "본 브리핑은 정보 제공·교육 목적이며 투자 권유가 아닙니다. "
    "수치는 무료 데이터 소스 기준의 참고값으로 지연·오류가 있을 수 있으며, "
    "투자 판단과 그 결과의 책임은 이용자 본인에게 있습니다."
)


@dataclass(frozen=True)
class Settings:
    """settings 테이블 기본값 (§15.5). init_schema 직후 seed 대상."""

    base_currency: str = "KRW"
    monthly_contribution: int = 0
    satellite_limit_pct: int = 30
    rebalance_band_abs: int = 5
    rebalance_band_rel: int = 25
    micro_weight_floor: float = 1.0
    usd_cash_gate_threshold: float = 5.0


SETTINGS_DEFAULTS = Settings()
