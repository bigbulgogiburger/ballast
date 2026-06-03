"""소스 어댑터 공통 가드 (W-2a). 04 §7.1 + orchestration §2.7 + decisions §3.7.

kr.py(BAL-11) 등 어댑터가 import. retry는 지수 백오프 재시도, validate_response는
rows==0을 EmptyResponseError로 승격(데이터 실재 보증). W1 본체는 rows==0만 검사하고
latest/expected는 시그니처에 보존(날짜 일치 검사는 W2 collect로 확장).
"""
import functools
import time
from collections.abc import Callable
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


class EmptyResponseError(Exception):
    """소스가 빈 응답(rows==0)을 반환했을 때. '조용한 실패'를 예외로 승격."""


def retry(times: int = 3, backoff: float = 1.5) -> Callable[[F], F]:
    """지수 백오프 재시도 데코레이터. 마지막 시도 실패는 그대로 raise."""

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Exception | None = None
            for attempt in range(times):
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001 — 어댑터 재시도 경계
                    last_exc = exc
                    if attempt < times - 1:
                        time.sleep(backoff ** attempt)
            assert last_exc is not None
            raise last_exc

        return wrapper  # type: ignore[return-value]

    return decorator


def validate_response(rows: int, latest: str, expected: str) -> None:
    """행수 검증. rows==0 → EmptyResponseError. 날짜 일치 검사는 W2(시그니처만 보존)."""
    if rows == 0:
        raise EmptyResponseError(f"empty response (latest={latest!r}, expected={expected!r})")
