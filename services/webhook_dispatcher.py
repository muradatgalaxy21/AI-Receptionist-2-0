# services/webhook_dispatcher.py
# Fire-and-forget outbound webhook delivery to the Make.com scenario.
#
# Contract: docs/webhook_payload_contracts.md
#   { "event", "timestamp", "call_sid", "data": {...} }
#
# Delivery is non-blocking: callers use dispatch_booking_created /
# dispatch_call_completed, which schedule the POST as a background task and
# return immediately. A failed POST is logged and swallowed so it can never
# interrupt a live call.

import os
import json
import asyncio
import datetime as _dt

import httpx
from dotenv import load_dotenv

load_dotenv()

_TIMEOUT_SECONDS = 10.0

# Values shipped in .env.example — treat as "not configured yet".
_PLACEHOLDER_MARKERS = ("your_webhook_id", "your_make_webhook", "your_make_webhook_id")


def _webhook_url() -> str | None:
    url = (os.getenv("MAKE_WEBHOOK_URL") or "").strip()
    if not url.startswith("http"):
        return None
    if any(marker in url for marker in _PLACEHOLDER_MARKERS):
        return None
    return url


def _utc_now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_envelope(event: str, data: dict, call_sid: str | None = None) -> dict:
    return {
        "event": event,
        "timestamp": _utc_now_iso(),
        "call_sid": call_sid,
        "data": data,
    }


async def dispatch(event: str, data: dict, call_sid: str | None = None) -> bool:
    """POST one event to the Make.com webhook. Returns True on 2xx, False
    otherwise (including when no webhook URL is configured). Never raises."""
    url = _webhook_url()
    payload = build_envelope(event, data, call_sid)

    if not url:
        print(f"[WEBHOOK] {event}: skipped - MAKE_WEBHOOK_URL not configured. "
              f"Payload: {json.dumps(payload)}")
        return False

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            resp = await client.post(url, json=payload)
        ok = 200 <= resp.status_code < 300
        level = "ok" if ok else f"HTTP {resp.status_code}"
        print(f"[WEBHOOK] {event}: {level} -> {url}")
        return ok
    except Exception as e:
        print(f"[WEBHOOK] {event}: delivery failed ({type(e).__name__}: {e})")
        return False


def _fire(event: str, data: dict, call_sid: str | None) -> None:
    """Schedule dispatch() without blocking the caller."""
    try:
        asyncio.get_running_loop().create_task(dispatch(event, data, call_sid))
    except RuntimeError:
        # No running loop (sync context / test) — run it inline.
        asyncio.run(dispatch(event, data, call_sid))


def dispatch_booking_created(data: dict, call_sid: str | None = None) -> None:
    _fire("booking.created", data, call_sid)


def dispatch_call_completed(data: dict, call_sid: str | None = None) -> None:
    _fire("call.completed", data, call_sid)


if __name__ == "__main__":
    # Self-check: envelope shape + graceful no-URL path (no network needed).
    os.environ.pop("MAKE_WEBHOOK_URL", None)
    env = build_envelope("booking.created", {"booking_id": "HTL-0001A"}, "CA123")
    assert env["event"] == "booking.created"
    assert env["call_sid"] == "CA123"
    assert env["data"]["booking_id"] == "HTL-0001A"
    assert env["timestamp"].endswith("Z") and "T" in env["timestamp"]
    assert asyncio.run(dispatch("call.completed", {"duration_seconds": 12})) is False
    print("OK - webhook_dispatcher:", json.dumps(env))
