# services/calender.py
# Google Calendar synchronization bridge for hotel reservations.
#
# This is a *fallback* sync: the source of truth for a booking is the
# booking.created webhook -> Make.com -> GoHighLevel. When Google Calendar is
# configured, each confirmed reservation is also mirrored onto a calendar so
# front-desk staff have a visual room-nights view.
#
# It is optional and self-disabling. If the google client libraries or
# credentials are not present, every call logs a "(mock)" line and returns
# ok=True so a reservation is never blocked by calendar problems.
#
# To enable real sync:
#   pip install google-api-python-client google-auth
#   set GOOGLE_CALENDAR_CREDENTIALS=/path/to/service_account.json  (default: credentials.json)
#   set GOOGLE_CALENDAR_ID=<calendar id>                           (default: primary)
#   share the target calendar with the service account's email.

import os

_SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def _credentials_path() -> str:
    return os.getenv("GOOGLE_CALENDAR_CREDENTIALS", "credentials.json")


def _calendar_id() -> str:
    return os.getenv("GOOGLE_CALENDAR_ID", "primary")


def _get_service():
    """Return an authorized Google Calendar service, or None if sync is not
    available (libraries missing, no credentials file, or auth failure)."""
    creds_path = _credentials_path()
    if not os.path.exists(creds_path):
        return None
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        return None
    try:
        creds = Credentials.from_service_account_file(creds_path, scopes=_SCOPES)
        return build("calendar", "v3", credentials=creds, cache_discovery=False)
    except Exception as e:
        print(f"[CALENDAR] Auth failed, falling back to mock: {e}")
        return None


def add_reservation_to_calendar(booking: dict) -> dict:
    """Mirror a confirmed reservation onto Google Calendar as an all-day event
    spanning check-in to check-out.

    `booking` is the booking.created `data` payload. Returns:
      {"ok": bool, "mode": "google"|"mock", "event_id": str|None, "error": str|None}
    """
    summary = (
        f"{booking.get('guest_name', 'Guest')} - {booking.get('room_type', 'Room')} "
        f"({booking.get('booking_id', 'no-id')})"
    )
    description = (
        f"Booking ID: {booking.get('booking_id')}\n"
        f"Phone: {booking.get('phone_number')}\n"
        f"Guests: {booking.get('number_of_guests')}\n"
        f"Nights: {booking.get('nights')}\n"
        f"Total: {booking.get('total_cost')}\n"
        f"Special requests: {booking.get('special_requests') or 'none'}"
    )
    check_in = booking.get("check_in_date")
    check_out = booking.get("check_out_date")

    service = _get_service()
    if service is None:
        print(f"[CALENDAR] (mock) would add event: {summary} | {check_in} -> {check_out}")
        return {"ok": True, "mode": "mock", "event_id": None, "error": None}

    event = {
        "summary": summary,
        "description": description,
        # All-day event: Google treats the end date as exclusive, which matches
        # hotel checkout (guest is gone on the checkout date).
        "start": {"date": check_in},
        "end": {"date": check_out},
    }
    try:
        created = service.events().insert(calendarId=_calendar_id(), body=event).execute()
        print(f"[CALENDAR] Reservation synced: {created.get('id')} ({summary})")
        return {"ok": True, "mode": "google", "event_id": created.get("id"), "error": None}
    except Exception as e:
        print(f"[CALENDAR] Sync failed (booking still confirmed): {e}")
        return {"ok": False, "mode": "google", "event_id": None, "error": str(e)}


# --- Backwards-compatible shims (old dental helpers) -------------------------
def check_google_calendar(time_str):
    """Deprecated. Availability is not calendar-gated in the hotel flow."""
    print(f"[CALENDAR] (mock) check for {time_str} -> available")
    return True


def add_google_event(name, time_str):
    """Deprecated thin wrapper kept for old callers."""
    return add_reservation_to_calendar({"guest_name": name, "check_in_date": time_str})["ok"]


if __name__ == "__main__":
    res = add_reservation_to_calendar({
        "booking_id": "HTL-0001A", "guest_name": "Jane Doe", "room_type": "Deluxe King",
        "phone_number": "+15551234567", "number_of_guests": 2, "nights": 2,
        "total_cost": 398.0, "special_requests": "high floor",
        "check_in_date": "2026-09-10", "check_out_date": "2026-09-12",
    })
    assert res["ok"] and res["mode"] == "mock", res
    print("OK - calendar bridge:", res)
