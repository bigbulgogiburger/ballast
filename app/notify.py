"""수집 실패 알림 (BAL-37). ntfy.sh / Telegram push — 외부 라이브러리 없이 urllib만.

환경변수는 함수 내부에서 os.environ.get으로 직접 읽어 자기 캡슐화(테스트 monkeypatch 용이).
알림 실패가 수집을 중단시키면 안 되므로 HTTP 예외는 모두 삼키고 log.warning만 남긴다.
Telegram bot token은 URL path(/bot{token}/sendMessage)에만 쓰고 로그에 찍지 않는다.
"""
import logging
import os
import urllib.parse
import urllib.request

log = logging.getLogger(__name__)

_TIMEOUT = 5


def send_fail_alert(market: str, reason: str) -> None:
    """수집 FAIL 시 설정된 채널로 1회 알림. 미설정이면 조용히 반환.

    reason은 호출측에서 시크릿(예외 원문·API 키 포함 URL)을 넣지 않는 고정 문자열이어야 한다.
    방어적으로 200자 절단(알림 본문 비대·렌더링 깨짐 방지).
    """
    if not _broadcast(f"[Ballast] {market} 수집 실패: {reason[:200]}"):
        log.warning("notify: no channel configured, skipping alert for %s", market)


def send_briefing_alert(headline: str, flag_count: int) -> None:
    """브리핑 생성 성공 시 1회 알림 — 헤드라인 1줄 + 리밸런싱 플래그 개수 + 대시보드 링크.

    headline은 코드가 고른 문자열(banner 또는 regime_label)만 — LLM 자유텍스트 금지.
    링크는 로컬 전용이라 기본 127.0.0.1, 외부 접근 환경(Tailscale 등)은 env로 교체.
    """
    url = os.environ.get("BALLAST_DASHBOARD_URL", "http://127.0.0.1:8000/")
    text = (
        f"[Ballast] 오늘의 브리핑 도착 — {headline[:100]} · "
        f"리밸런싱 플래그 {flag_count}건 · {url}"
    )
    if not _broadcast(text):
        log.warning("notify: no channel configured, skipping briefing alert")


def _broadcast(text: str) -> bool:
    """설정된 전 채널로 발송. 하나라도 시도했으면 True(미설정 False)."""
    sent = False
    ntfy_url = os.environ.get("NTFY_URL")
    if ntfy_url:
        _post(ntfy_url, text.encode("utf-8"), "ntfy", None)
        sent = True
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        body = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
        _post(url, body, "telegram", "application/x-www-form-urlencoded")
        sent = True
    return sent


def _post(url: str, data: bytes, channel: str, content_type: str | None) -> None:
    """POST 1회. 예외는 삼키고 예외 '타입'만 로그(token/URL 절대 로그 금지 — 06 §5.1)."""
    # 스킴 화이트리스트 — file:// 등 비-HTTP 스킴 차단(SSRF/로컬파일 접근 방지).
    if urllib.parse.urlparse(url).scheme not in ("http", "https"):
        log.warning("notify %s: unsupported URL scheme, skipping", channel)
        return
    try:
        req = urllib.request.Request(url, data=data, method="POST")
        if content_type:
            req.add_header("Content-Type", content_type)
        urllib.request.urlopen(req, timeout=_TIMEOUT)  # noqa: S310 — 스킴 검증 후 신뢰 엔드포인트
    except Exception as exc:  # noqa: BLE001 — 알림 실패가 수집 중단 금지
        # str(exc)에 토큰 포함 URL이 섞일 수 있어 예외 타입명만 기록.
        log.warning("notify %s send failed: %s", channel, type(exc).__name__)
