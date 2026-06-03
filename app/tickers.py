"""티커 정규화·분류 (BAL-9). canonical 04 §5.1/§5.2/§5.3 + decisions §3.1~§3.3.

캐시 PK는 항상 canonical 기준. to_source는 canonical → 소스별 표기로 변환.
W1=KOSDAQ 미구분(무조건 .KS), KOSDAQ frozenset 빌드는 W2 (decisions §3.1).
"""
from typing import Literal

from app.models import HoldingInput

# 그룹 매핑(decisions §3.3): source별 if문 대신 집합 멤버십으로 분기.
_KR_BARE = frozenset({"pykrx", "fdr", "dart"})   # KR → 6자리 그대로
_US_PLAIN = frozenset({"yf", "finnhub", "fmp"})  # US → 점→하이픈 + 대문자


def to_source(
    source: Literal["yf", "finnhub", "stooq", "pykrx", "fdr", "fmp", "dart"],
    ct: str,
    market: str,
) -> str:
    """canonical 티커를 소스별 표기로 변환. 미지원 조합은 fail-fast ValueError(decisions Q2).

    예: to_source('yf','005930','KR')->'005930.KS' / ('stooq','VOO','US')->'voo.us'
        to_source('finnhub','BRK.B','US')->'BRK-B' / ('pykrx','005930','KR')->'005930'
    """
    if market == "KR":
        if source in _KR_BARE:
            return ct
        if source in {"yf", "finnhub", "stooq"}:
            return f"{ct}.KS"  # W1=무조건 .KS (KOSDAQ .KQ는 W2)
        raise ValueError(f"source {source!r} not supported for KR market")
    if market == "US":
        if source in _US_PLAIN:
            return ct.replace(".", "-").upper()
        if source == "stooq":
            return f"{ct.replace('.', '-').lower()}.us"
        raise ValueError(f"source {source!r} not supported for US market")
    raise ValueError(f"unknown market {market!r} (expected 'KR' or 'US')")


# 코어 ETF 화이트리스트 (G4, 04 §5.2). 섹터·테마·레버리지·액티브 ETF 포함 금지.
CORE_ETF_WHITELIST: frozenset[str] = frozenset({
    "069500",   # KODEX 200
    "360750",   # TIGER 미국S&P500
    "379800",   # KODEX 미국S&P500TR
    "VOO", "SPY", "VTI", "IVV", "ITOT", "VT",
})


def classify_category(h: HoldingInput) -> Literal["core", "satellite"] | None:
    """category 자동판정(G4, 04 §5.3). enum 밖 instrument는 방어적 None(decisions Q3)."""
    if h.category is not None:          # 1) 사용자 명시 우선
        return h.category
    if h.instrument == "stock":         # 2) 개별주 → satellite
        return "satellite"
    if h.instrument == "etf":           # 3) ETF: 화이트리스트 매칭만 core
        return "core" if h.canonical_ticker in CORE_ETF_WHITELIST else None
    return None                          # 4) cash 등 → 확인 필요
