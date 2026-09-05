# tests/test_booking_flow.py
# Offline checks for the Grand Horizon Hotel booking state machine in
# services/agent_logic.py. No network is touched: the webhook dispatcher
# no-ops (and just logs) while MAKE_WEBHOOK_URL is unset, and the Google
# Calendar mirror self-disables without google-api-python-client / creds.
#
# Run either way:
#   python tests/test_booking_flow.py
#   python -m pytest tests/test_booking_flow.py

import re
import sys
import json
import asyncio
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from services.agent_logic import (
    finalize_booking,
    handle_booking_function_call,
    try_book_from_json_payload,
)

# A complete, valid set of gathered fields. 2026-09-10 -> 2026-09-12 is
# 2 nights; Deluxe King is $199/night -> $398.00 total.
BASE = {
    "first_name": "Jane",
    "last_name": "Doe",
    "phone_number": "+15551234567",
    "room_type": "deluxe king",
    "check_in_date": "2026-09-10",
    "check_out_date": "2026-09-12",
    "number_of_guests": "2 guests",
    "special_requests": "high floor",
}


def test_happy_path():
    r = finalize_booking(dict(BASE))
    assert r["ok"], r
    assert r["nights"] == 2, r
    assert r["total_cost"] == 398.0, r
    assert r["room_type"] == "Deluxe King", r
    assert re.fullmatch(r"HTL-\d{4}[A-Z]", r["booking_id"]), r


def test_state_updated_on_confirm():
    s = dict(BASE)
    finalize_booking(s)
    assert s["booking_confirmed"] is True, s
    assert s["room_type"] == "Deluxe King", s
    assert s["total_cost"] == 398.0, s


def test_idempotent_replays_result():
    s = dict(BASE)
    first = finalize_booking(s)
    second = finalize_booking(s)
    assert second.get("already") is True, second
    assert second["booking_id"] == first["booking_id"], (first, second)


def test_missing_required_field():
    r = finalize_booking({"first_name": "A"})
    assert not r["ok"], r
    assert "missing" in r["error"].lower(), r


def test_over_occupancy_rejected():
    s = dict(BASE)
    s["room_type"] = "Standard Queen"   # max_occupancy 2
    s["number_of_guests"] = 5
    r = finalize_booking(s)
    assert not r["ok"], r
    assert "holds up to" in r["error"], r


def test_checkout_before_checkin_rejected():
    s = dict(BASE)
    s["check_in_date"] = "2026-09-12"
    s["check_out_date"] = "2026-09-10"
    r = finalize_booking(s)
    assert not r["ok"], r


def test_same_day_checkout_rejected():
    s = dict(BASE)
    s["check_out_date"] = s["check_in_date"]
    r = finalize_booking(s)
    assert not r["ok"], r


def test_iso_dates_not_misparsed():
    # Regression: parse_date(dayfirst=True) used to read "2026-09-10" as Oct 9,
    # which every book_room ISO date would hit. 10th -> 12th must stay 2 nights.
    r = finalize_booking(dict(BASE))
    assert r["nights"] == 2, r


def test_unknown_room_type_rejected():
    s = dict(BASE)
    s["room_type"] = "Presidential Bungalow"
    r = finalize_booking(s)
    assert not r["ok"], r


def test_function_call_path():
    async def go():
        class FakeAgent:
            async def send(self, _m):
                pass

        state = {}
        out = await handle_booking_function_call(
            {
                "first_name": "Sam",
                "last_name": "Lee",
                "phone_number": "+15550001111",
                "room_type": "Penthouse",
                "check_in_date": "2026-12-01",
                "check_out_date": "2026-12-04",
                "number_of_guests": 3,
            },
            state,
            FakeAgent(),
        )
        assert "Booking ID" in out, out
        assert state["booking_confirmed"] is True, state

    asyncio.run(go())


def test_ready_to_book_json_fallback_path():
    async def go():
        class FakeAgent:
            def __init__(self):
                self.sent = []

            async def send(self, m):
                self.sent.append(m)

        state = {}
        payload = dict(BASE)
        payload["type"] = "ready_to_book"
        agent = FakeAgent()
        await try_book_from_json_payload(json.dumps(payload), state, agent)
        assert state.get("booking_confirmed") is True, state
        # confirmation was injected back to the agent
        assert any("InjectAgentMessage" in m for m in agent.sent), agent.sent

    asyncio.run(go())


def test_ready_to_book_ignores_non_signal_content():
    async def go():
        state = {}
        await try_book_from_json_payload("just a normal sentence", state, None)
        assert "booking_confirmed" not in state, state

    asyncio.run(go())


if __name__ == "__main__":
    tests = sorted(
        (name, fn)
        for name, fn in list(globals().items())
        if name.startswith("test_") and callable(fn)
    )
    for name, fn in tests:
        fn()
        print("ok  ", name)
    print(f"ALL PASS ({len(tests)} checks)")
