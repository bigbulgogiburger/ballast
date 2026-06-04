# pytest 공통 설정.
import pytest

from app import db
from app.models import HoldingRow


@pytest.fixture
def conn():
    """in-memory DB + 스키마 초기화 (BAL-8 §6). 실 DB(data/ballast.db) 오염 방지."""
    c = db.connect(":memory:")
    db.init_schema(c)
    yield c
    c.close()


@pytest.fixture
def make_holding():
    """HoldingRow 빌더 (BAL-23 test_metrics). 필요한 필드만 override."""

    def _build(
        *,
        id: int | None = 1,
        user_id: int = 1,
        asset_class: str = "equity",
        instrument: str = "stock",
        tracking: str = "auto",
        market: str | None = "KR",
        canonical_ticker: str | None = "005930",
        name: str = "삼성전자",
        quantity: float | None = 10.0,
        value_manual: float | None = None,
        ccy: str | None = "KRW",
        avg_price: float | None = None,
        category: str | None = "core",
        target_pct: float | None = None,
    ) -> HoldingRow:
        return HoldingRow(
            id=id,
            user_id=user_id,
            asset_class=asset_class,
            instrument=instrument,
            tracking=tracking,
            market=market,
            canonical_ticker=canonical_ticker,
            name=name,
            quantity=quantity,
            value_manual=value_manual,
            ccy=ccy,
            avg_price=avg_price,
            category=category,
            target_pct=target_pct,
        )

    return _build
