"""build_freshness_badge 신선도 등급 — 경계 + 결측 degrade (BAL-33).

worst_level 경계: 0/1=fresh, 2/4=stale, 5+=warn (03 §4.2).
등급 산출(_level)은 결정적 경계라 직접 단위 테스트하고,
build_freshness_badge는 DB 결측 시 안전 degrade('warn'·큰 age)를 검증한다.
expected_trade_date가 달력 의존이라 build_freshness_badge의 age 절대값은
단언하지 않고, 결측 안전성과 worst_level 집계 경로만 확인한다.
"""
import pytest

from app.briefing import _level, build_freshness_badge


@pytest.mark.unit
@pytest.mark.parametrize(
    "age, expected",
    [
        (0, "fresh"),
        (1, "fresh"),
        (2, "stale"),
        (4, "stale"),
        (5, "warn"),
        (10, "warn"),
    ],
)
def test_level_boundaries(age: int, expected: str) -> None:
    """_level 경계: 0~1=fresh, 2~4=stale, 5+=warn."""
    assert _level(age) == expected


@pytest.mark.unit
def test_empty_db_degrades_to_warn(conn) -> None:
    """결측 안전 degrade — 빈 DB(보유·스냅샷 0)면 worst_level='warn', age는 큰 값."""
    badge = build_freshness_badge(conn)
    assert badge.worst_level == "warn"
    # 스냅샷 결측 → _age_days가 999로 degrade(>= warn 임계 5).
    assert badge.price_age_days >= 5
    assert badge.fx_age_days >= 5
    # 펀더 결측 라벨.
    assert badge.funda_label == "미확보(워밍업)"
    # collect_run 없음 → fallback False.
    assert badge.consecutive_fallback is False


@pytest.mark.unit
def test_badge_shape(conn) -> None:
    """FreshnessBadge 필드 형태 — 회귀 방지(타입 계약)."""
    badge = build_freshness_badge(conn)
    assert isinstance(badge.price_age_days, int)
    assert isinstance(badge.fx_age_days, int)
    assert isinstance(badge.funda_label, str)
    assert badge.worst_level in ("fresh", "stale", "warn")
    assert isinstance(badge.consecutive_fallback, bool)
