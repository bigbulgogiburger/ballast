"""main.py 라우트 스모크 — fastapi TestClient (BAL-32).

대시보드/holdings/settings GET 200, POST /holdings 실패(400 상태보존)·
성공(303 PRG), POST /api/regenerate 외부 host 차단(403 — TestClient는
client.host='testclient'이므로 127.0.0.1 아님).

라우트는 config.DB_PATH로 자체 연결(요청 단위)하므로 임시 파일 DB로
monkeypatch하여 실 DB(data/ballast.db) 오염을 방지한다.
"""
import pytest
from fastapi.testclient import TestClient

from app import config, main


@pytest.fixture
def client(tmp_path, monkeypatch):
    """임시 파일 DB를 바라보는 TestClient. _conn()이 config.DB_PATH를 읽음."""
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(config, "DB_PATH", str(db_file))
    monkeypatch.setattr(main.config, "DB_PATH", str(db_file))
    return TestClient(main.app)


@pytest.mark.integration
def test_dashboard_get_empty_state(client) -> None:
    """GET / — 200, doc None(빈 DB)이어도 빈 상태로 렌더(e2e G3)."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    # doc None → 빈 상태 안내(BAL-30 §5). 면책 전문은 doc 푸터에서만 렌더.
    assert "초기 데이터 적재중" in resp.text


@pytest.mark.integration
def test_holdings_get(client) -> None:
    """GET /holdings — 200 렌더."""
    resp = client.get("/holdings")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


@pytest.mark.integration
def test_holdings_post_invalid_preserves_state_400(client) -> None:
    """POST /holdings 검증 실패 — 400 + 동일 폼 재렌더(상태보존, F5)."""
    resp = client.post(
        "/holdings",
        data={
            "rows[0][instrument]": "stock",
            "rows[0][canonical_ticker]": "005930",
            "rows[0][market]": "KR",
            "rows[0][quantity]": "",  # 수량 누락 → 검증 실패
            "rows[0][ccy]": "KRW",
            "rows[0][category]": "",
        },
    )
    assert resp.status_code == 400
    assert "text/html" in resp.headers["content-type"]


@pytest.mark.integration
def test_holdings_post_valid_redirects_303(client) -> None:
    """POST /holdings 성공 — 303 PRG redirect(?saved=1), 저장 반영."""
    resp = client.post(
        "/holdings",
        data={
            "rows[0][instrument]": "stock",
            "rows[0][canonical_ticker]": "005930",
            "rows[0][market]": "KR",
            "rows[0][quantity]": "10",
            "rows[0][ccy]": "KRW",
            "rows[0][category]": "satellite",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "saved=1" in resp.headers["location"]


@pytest.mark.integration
def test_settings_get(client) -> None:
    """GET /settings — 200 렌더."""
    resp = client.get("/settings")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


@pytest.mark.integration
def test_regenerate_external_host_forbidden_403(client) -> None:
    """POST /api/regenerate — TestClient host(127.0.0.1 아님)는 403."""
    resp = client.post("/api/regenerate", follow_redirects=False)
    assert resp.status_code == 403


@pytest.mark.integration
def test_healthz(client) -> None:
    """GET /healthz — 200 {status: ok} (W0 회귀 방지)."""
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
