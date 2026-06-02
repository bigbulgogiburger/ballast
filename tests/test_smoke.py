"""스모크 테스트: /healthz 엔드포인트 검증."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.unit
def test_healthz() -> None:
    # GET /healthz가 200 + {"status": "ok"} 반환
    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
