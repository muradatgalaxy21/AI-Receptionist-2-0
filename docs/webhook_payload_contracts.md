# Outbound Webhook Payload Contracts

Phase 0 deliverable (Engineer A / Track 0A). These are the JSON contracts the
Python backend will POST to `MAKE_WEBHOOK_URL` once `services/webhook_dispatcher.py`
is built in Track A. Engineer B's Make.com scenario + GHL field mapping is
built against this shape.

Both events share an envelope:

```json
{
  "event": "booking.created | call.completed",
  "timestamp": "2026-09-05T14:32:00Z",
  "call_sid": "string | null",
  "data": { ... event-specific fields below ... }
}
```

## `booking.created`

Fired once `try_book_from_json_payload`-equivalent hotel logic confirms a
reservation.

```json
{
  "event": "booking.created",
  "timestamp": "2026-09-05T14:32:00Z",
  "call_sid": "CA1234567890abcdef",
  "data": {
    "booking_id": "HTL-8492X",
    "guest_name": "Jane Doe",
    "phone_number": "+15551234567",
    "room_type": "Deluxe King",
    "check_in_date": "2026-09-10",
    "check_out_date": "2026-09-12",
    "number_of_guests": 2,
    "nights": 2,
    "total_cost": 398.00,
    "special_requests": "Late check-in, high floor"
  }
}
```

## `call.completed`

Fired when the call/chat session ends (farewell detected or socket closes),
regardless of whether a booking resulted.

```json
{
  "event": "call.completed",
  "timestamp": "2026-09-05T14:35:00Z",
  "call_sid": "CA1234567890abcdef",
  "data": {
    "caller_id": "+15551234567",
    "to_number": "+15559876543",
    "duration_seconds": 187,
    "booking_confirmed": true,
    "booking_id": "HTL-8492X"
  }
}
```

## Field notes

- `call_sid` is `null` for web/text-chat sessions (no Twilio call).
- `timestamp` is UTC ISO-8601.
- `total_cost` is a plain number (no currency symbol); currency is USD unless
  the hotel config says otherwise.
- Delivery is fire-and-forget (async, non-blocking) — a failed POST must not
  interrupt the live call. Dispatcher retries/logging are a Track A concern,
  not part of this contract.
