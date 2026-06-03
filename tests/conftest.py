# pytest 공통 설정.
import pytest

from app import db


@pytest.fixture
def conn():
    """in-memory DB + 스키마 초기화 (BAL-8 §6). 실 DB(data/ballast.db) 오염 방지."""
    c = db.connect(":memory:")
    db.init_schema(c)
    yield c
    c.close()
