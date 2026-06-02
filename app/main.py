# 바인딩은 반드시 127.0.0.1 (SSoT §12 로컬전용).
# uvicorn app.main:app --host 127.0.0.1 --port 8000. 0.0.0.0 금지.
from fastapi import FastAPI

app = FastAPI(title="ballast")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """W0 빈 200 DoD 충족용 헬스 라우트."""
    return {"status": "ok"}
