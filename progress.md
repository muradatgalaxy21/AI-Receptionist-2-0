# Hotel AI Receptionist - Development Progress Tracker

Spec source: `implementation_plan.md`. Owner of this file's Track A / Track 0A
rows: Engineer A (Python core). Track 0B / Track B rows belong to Engineer B
(Make.com, GHL, Twilio, telephony).

## Phase 0: Pre-Flight Configuration (Track 0A - Engineer A)
- [x] [DONE] Set up Python virtual environment and verify dependencies — used `.venv` (not literally `AI-Receptionist-2-0`, since that name is already the repo folder itself; nesting a same-named venv inside it would be confusing). All packages in `requirements.txt` install clean and import clean.
- [x] [DONE] Generate fresh Deepgram API key and configure in `.env` — real key set locally in `.env` (gitignored, never pushed).
- [x] [DONE] Document outbound JSON webhook payload contracts (`booking.created`, `call.completed`) — see `docs/webhook_payload_contracts.md`.
- [x] [DONE] Configure local server settings (`PORT=8000`, `HOST=0.0.0.0`) in `.env` — also wired `main.py` to actually read `HOST`/`PORT` from env instead of hardcoding.

## Phase 0: Pre-Flight Configuration (Track 0B - Engineer B)
- [ ] [TODO] Set up Ngrok / Cloudflared public tunnel and configure `PUBLIC_BASE_URL`
- [ ] [TODO] Provision Twilio voice phone number and configure webhook to `<PUBLIC_BASE_URL>/incoming-call`
- [ ] [TODO] Create Make.com scenario webhook listener and share `MAKE_WEBHOOK_URL`
- [ ] [TODO] Generate GHL API key / private token and retrieve `GHL_LOCATION_ID`
- [ ] [TODO] Create GHL custom contact fields (Booking ID, Room Type, Check-in, Check-out, Total Cost)
- [ ] [TODO] Build GHL "Hotel Reservations" Pipeline and stages
- [ ] [TODO] Configure GHL automated SMS reservation confirmation workflow

## Phase 1 / Track A: Python Codebase & AI Core (Engineer A)
- [x] [DONE] Define hotel metadata, room tiers, rates, and policies in `data/data.json` — Grand Horizon Hotel, San Diego. 4 room types (Standard Queen $149, Deluxe King $199, Executive Suite $329, Penthouse $599) with rates/occupancy/descriptions, plus amenities, policies (check-in/out, cancellation, pets, smoking, parking, resort fee, extra guests), and FAQs.
- [x] [DONE] Rewrite system prompt for Hotel Sarah in `data/config.json` — Sarah is now the Grand Horizon Hotel front desk. Prompt collects the 8 reservation fields one by one, confirms, then calls the new `book_room` function (replaces `book_appointment`). Greeting + FAQ handling reworked for hotel domain; voice/silence rules kept.
- [x] [DONE] Implement hotel booking state machine in `services/agent_logic.py` — rewritten for hotel fields (`first_name`, `last_name`, `phone_number`, `room_type`, `check_in_date`, `check_out_date`, `number_of_guests`, `special_requests`). `finalize_booking()` validates required fields, prices the stay, enforces room max-occupancy, mints a Booking ID, fires `booking.created`, and is idempotent. Two entry points converge on it: `handle_booking_function_call()` (the `book_room` function call) and `try_book_from_json_payload()` (legacy `ready_to_book` fallback). Dental slot-injection / early-availability code removed; `handle_user_slot_query` / `handle_date_selection_in_booking` kept as no-ops for callers still importing them. `python -m services.agent_logic` self-check covers the happy path, idempotency, missing fields, and over-occupancy.
- [x] [DONE] Implement unique booking ID generator in `services/booking_id.py` — `generate_booking_id()` returns `HTL-####X` (4 digits + capital letter). In-process dedupe set; `python services/booking_id.py` self-check asserts format + uniqueness over 5000 draws.
- [x] [DONE] Implement stay duration and pricing calculation helper in `services/tools.py` — `calculate_nights()`, `match_room_type()`, `get_nightly_rate()`, `price_reservation()` (reads rates from `data/data.json`; `total_cost = nights * nightly_rate` per the webhook contract). Also fixed a latent `parse_date()` bug: `dayfirst=True` mis-read `YYYY-MM-DD` strings (`2026-09-10` -> Oct 9), which `book_room`'s ISO dates would hit every time. `python services/tools.py` self-check covers both.
- [x] [DONE] Create asynchronous webhook dispatcher in `services/webhook_dispatcher.py` — `dispatch_booking_created()` / `dispatch_call_completed()` schedule a background `httpx` POST (10s timeout) and return immediately; all errors logged + swallowed. Builds the `{event, timestamp, call_sid, data}` envelope from `docs/webhook_payload_contracts.md`. When `MAKE_WEBHOOK_URL` is unset/placeholder it logs the payload and no-ops (Engineer B hasn't delivered the URL yet). `python services/webhook_dispatcher.py` self-check covers envelope + no-URL path.
- [x] [DONE] Hook `booking.created` and `call.completed` into `routers/brain.py` and `routers/text_test.py` — both routers now dispatch the `book_room` function call to `handle_booking_function_call` (which fires `booking.created` from inside `finalize_booking`), init the hotel `conversation_state`, and fire `call.completed` on session end (brain.py also captures Twilio `callSid` and logs `total_cost` as the call's estimated value). Dental slot-injection wiring removed. `routers/voice_browser.py` got the same treatment (not in the checklist, but it imports the same shared logic and would otherwise still book dental appointments / crash the app import). Prompt context label `CLINIC DATA:` -> `HOTEL DATA:` in all three. `python -c "import main"` loads the full app clean.
- [x] [DONE] Update web chat testing interface in `static/test_chat.html` — retitled/rethemed for the Grand Horizon Hotel (Sarah "AI Concierge", gold + navy palette swapped in for the blue/purple), added a row of quick-action chips (Book a room, Room rates, Check-in times, Pet policy, Airport shuttle) that prefill and send a test prompt; chips enable/disable with the connection. WebSocket logic untouched. (Pre-existing glow-shadow styling left as-is — cosmetic, outside Track A scope.)
- [x] [DONE] Google Calendar API synchronization bridge in `services/calender.py` — `add_reservation_to_calendar(booking)` mirrors a confirmed reservation onto a calendar as an all-day check-in→check-out event. Self-disabling: with no `google-api-python-client` / `credentials.json` / `GOOGLE_CALENDAR_ID` it logs a `(mock)` line and returns ok, so a booking is never blocked by calendar issues. Called from `finalize_booking` right after the webhook dispatch (wrapped in try/except). Google libs deliberately NOT added to `requirements.txt` (optional per the plan); enable steps are in the module docstring. `python -m services.calender` self-check covers mock mode.

## Track B: Cloud Automations, GHL & Presentation (Engineer B)
- [ ] [TODO] Build Make.com scenario routing (`booking.created` and `call.completed`)
- [ ] [TODO] Map Make.com data to GoHighLevel Contact and Opportunity records
- [ ] [TODO] Test automated GoHighLevel SMS workflow with dynamic Booking ID
- [ ] [TODO] Configure GoHighLevel Calendar and staff availability rules
- [ ] [TODO] Build 4-6 slide STARR presentation deck for client pitch
- [ ] [TODO] Lead live demo walkthrough test

## Track C: Joint Verification
- [ ] [TODO] End-to-end web chat reservation -> Make.com -> GHL Contact -> SMS verification received
- [ ] [TODO] End-to-end phone call reservation -> Voice booking -> GHL Opportunity -> SMS verification received

---

## Session Log

### Session 3 — 2026-09-05 (Engineer A) — CLOSED

Live verification of Track A + fixed every bug the live run surfaced. Track C
still blocked on Engineer B's `MAKE_WEBHOOK_URL`.

**Verified live (was self-checks only before):**
- Server boots; `/`, `/chat`, `/static/test_chat.html` all 200.
- Full web-chat reservation against Deepgram end to end: greeting -> 8 fields
  gathered one by one -> `book_room` function call -> `finalize_booking` prices
  the stay (3 nights x $199 = $597) -> Booking ID minted -> `booking.created`
  envelope built (no-op, `MAKE_WEBHOOK_URL` still placeholder) -> Google
  Calendar mock mirror -> `call.completed` fires on session end -> **Sarah
  speaks the Booking ID back to the guest**. Ran clean start to finish.

**Bugs found and fixed this session:**
- `routers/text_test.py` — `websockets.connect(additional_headers=...)` is the
  websockets 13+ kwarg; pinned version is 12.0 which needs `extra_headers=`.
  Web chat could never open the Deepgram socket. Now matches brain.py /
  voice_browser.py. Also added `Error` / `Warning` / unhandled-type logging to
  the agent receiver (brain.py already had it) — that is what surfaced the
  FunctionCallResponse bug below.
- `services/agent_logic.py` — `FAREWELL_PHRASES` contained
  `"thank you for calling"`, which is the *opening* of the Grand Horizon
  greeting ("Thank you for calling the Grand Horizon Hotel..."). `is_farewell()`
  returned True on Sarah's first line, so every session (voice and text) ended
  on the greeting. Removed that phrase; real farewells still caught by
  `"goodbye"` / `"have a great day"`. Added a regression assert to the
  `__main__` self-check.
- `routers/brain.py`, `routers/text_test.py`, `routers/voice_browser.py` —
  the `FunctionCallResponse` sent back to Deepgram used `{"id", "output"}`.
  The Voice Agent API expects `{"id", "name", "content"}`. Deepgram rejected
  it with `UNPARSABLE_CLIENT_MESSAGE` and closed the socket right after
  `book_room`, so the booking completed server-side but Sarah never voiced the
  confirmation. Fixed the field names in all three routers.
- `services/db_client.py` — the `ALTER TABLE calls ADD COLUMN` failsafes ran
  unconditionally every boot; `execute_write` logs the "duplicate column name"
  error before the outer `try/except` can swallow it, so two red `[DB]` lines
  printed on every startup. Now checks `PRAGMA table_info(calls)` and only
  ALTERs columns that are actually missing.
- `services/log_capture.py` — `LogCapture` replaces `sys.stdout` but only
  implemented `write` / `flush`. `uvicorn.run()` (i.e. `python main.py`) calls
  `sys.stdout.isatty()` at startup and crashed with `AttributeError`. Added
  `__getattr__` delegating any other attribute (`isatty`, `fileno`, `encoding`,
  ...) to the real stdout. `python main.py` now boots clean.

**Test housekeeping:**
- Deleted `tests/test_agent_text.py` and `tests/test_suppression.py` — stale
  dental-era manual CLI scripts, no asserts, unreferenced.
- Added `tests/test_booking_flow.py` — 12 offline asserts over `finalize_booking`
  and both booking entry points (happy path, state mutation, idempotency,
  missing field, over-occupancy, checkout-before-checkin, same-day checkout,
  ISO-date regression, unknown room type, `book_room` function-call path,
  `ready_to_book` JSON fallback path). Runs standalone
  (`python tests/test_booking_flow.py`) or under pytest.

**Verified this session:**
- `tests/test_booking_flow.py` — 12/12.
- `python -m services.<mod>` self-checks still pass; `python -c "import main"`
  clean; `python main.py` boots.
- Live Deepgram web-chat reservation completes with the Booking ID spoken back.

**Left for next session:**
- Track C joint verification, still blocked on Engineer B's `MAKE_WEBHOOK_URL` +
  GHL. Once live: run a web-chat reservation, confirm `booking.created` reaches
  Make.com and lands on a GHL contact/opportunity, confirm the SMS.
- The three router `FunctionCallResponse` fixes and the farewell fix also touch
  the Twilio voice path (`brain.py`) — worth a live phone-call check when
  Engineer B has the Twilio number wired.

### Session 2 — 2026-09-05 (Engineer A) — CLOSED

Phase 1 / Track A implementation — **all 9 items done**. Hotel = **Grand
Horizon Hotel**, receptionist persona stays **Sarah**. One commit + push to
`engineer-a` per feature.

**Done:**
- `data/data.json` rewritten from dental clinic to Grand Horizon Hotel: room
  tiers + nightly rates + occupancy, amenities, full policy set, FAQs.
- `data/config.json` prompt rewritten for Sarah at the Grand Horizon Hotel;
  `book_appointment` function replaced with `book_room` (8 reservation
  fields, dates in YYYY-MM-DD). New greeting.
- `services/booking_id.py` — `generate_booking_id()` -> `HTL-####X`.
- `services/tools.py` — hotel pricing helpers (`calculate_nights`,
  `match_room_type`, `get_nightly_rate`, `price_reservation`); fixed
  `parse_date()` ISO-date (`dayfirst`) bug.
- `services/webhook_dispatcher.py` — non-blocking `httpx` POST to
  `MAKE_WEBHOOK_URL`; no-ops with a logged payload until the URL is set.
- `services/agent_logic.py` — rewritten hotel booking state machine
  (`finalize_booking` + `book_room` / `ready_to_book` entry points);
  dental slot code dropped.
- `routers/brain.py`, `routers/text_test.py`, `routers/voice_browser.py` —
  wired `book_room` -> `handle_booking_function_call`, hotel
  `conversation_state`, `call.completed` on session end, `HOTEL DATA:`
  label. brain.py captures Twilio `callSid`.
- `static/test_chat.html` — hotel retheme + quick-action chips.
- `services/calender.py` — optional, self-disabling Google Calendar mirror
  called from `finalize_booking`.
- Built the leaf modules ahead of the state machine (the plan's listed order)
  because `agent_logic.py` depends on all three.

**Verified this session:**
- `python -m services.<mod>` self-checks pass for `booking_id`, `tools`,
  `webhook_dispatcher`, `agent_logic`, `calender`.
- `python -c "import main"` loads the full FastAPI app clean; every tracked
  `.py` compiles.
- NOT run: a live end-to-end call/chat against Deepgram (needs the running
  server + a real conversation), and the real Make.com / Google Calendar
  round-trips — those depend on Engineer B's `MAKE_WEBHOOK_URL` and optional
  Google creds, both still placeholders, so the dispatcher logs the payload
  instead of POSTing.

**Left for next session:**
- Track A code is complete. Next is Track C joint verification once
  `MAKE_WEBHOOK_URL` is live: run the server, do a web-chat reservation,
  confirm the `booking.created` payload reaches Make.com.
- `tests/` still holds the old dental CLI helpers (`test_agent_text.py`,
  `test_suppression.py`). A small hotel booking test module is worth adding.

### Session 1 — 2026-09-05 (Engineer A) — CLOSED

**Done:**
- Cloned repo (`AI-Receptionist-2-0`, branch `main`) locally.
- Created `.venv`, installed `requirements.txt`, verified every import works.
- Created local `.env` from `.env.example` (gitignored, not pushed).
- Wired `main.py` to read `HOST`/`PORT` from env (was hardcoded).
- Wrote `docs/webhook_payload_contracts.md` defining `booking.created` /
  `call.completed` JSON shape for Engineer B's Make.com scenario.
- Created this `progress.md`.
- Created branch `engineer-a` off `main` for all of Engineer A's future
  commits; pushed to origin.

**Left for next session (Phase 1 / Track A):**
- All of Track A (hotel data/prompt/state-machine/booking-id/pricing/
  webhook-dispatcher/router-wiring/test-UI/calendar). Current codebase is
  still the dental-clinic domain (`services/agent_logic.py`, `data/config.json`,
  `data/data.json` all reference "Bright Smile Dental Care", patient
  name/date/time/reason fields).

**Issues / blockers:**
- `DEEPGRAM_API_KEY` real key now set in local `.env` (Track 0A fully done).
- `MAKE_WEBHOOK_URL`, `GHL_LOCATION_ID`, `GHL_API_KEY` are still placeholders
  — depend on Engineer B's Track 0B setup.
- No blockers on the Track A code work itself; can start immediately next
  session.

---

## Status Summary (as of end of Session 3)

Engineer A owned scope is **100% done and now verified live**:
- Phase 0 / Track 0A — 4/4
- Phase 1 / Track A — 9/9
- Session 3: live Deepgram web-chat reservation runs end to end; 5 bugs the
  live run surfaced are fixed (websockets kwarg, farewell-on-greeting,
  `FunctionCallResponse` field names x3 routers, DB duplicate-column spam,
  `python main.py` stdout crash). Added `tests/test_booking_flow.py` (12
  checks), removed the two stale dental test scripts.

Pushed to `origin/engineer-a`. Nothing left that is Engineer A only.

**Still open (not Engineer A solo):**
- Phase 0 / Track 0B and Phase 1 / Track B — all Engineer B.
- Track C joint verification (2 items) — needs Engineer B's `MAKE_WEBHOOK_URL`
  + GHL live first.

**Waiting on from Engineer B before Track C:**
- Real `MAKE_WEBHOOK_URL` (drop into local `.env`; dispatcher currently logs
  the payload instead of POSTing).
- GHL custom fields + "Hotel Reservations" pipeline + SMS workflow deployed.

---

## Next Session Kickoff Prompt (Track C — joint verification)

Paste this to start the next session:

> Read `progress.md` and `implementation_plan.md` in this repo
> (`AI-Receptionist-2-0`). I'm Engineer A on branch `engineer-a`. Phase 0
> Track 0A and Phase 1 Track A are 100% done and pushed. Now do Track C
> verification for the web-chat path:
> 1. Confirm Engineer B has delivered `MAKE_WEBHOOK_URL`; put it in local
>    `.env` (gitignored). If not delivered yet, stop and say so.
> 2. Start the server (`python main.py`), open `/chat`, and run a full
>    reservation with Sarah end to end.
> 3. Verify the `booking.created` payload actually reaches Make.com and lands
>    on a GHL contact/opportunity, and that the confirmation SMS is received.
> 4. Verify `call.completed` fires on session end.
> 5. Log results in `progress.md` Session Log, tick the Track C web-chat row
>    if it passes, and commit + push. File any code bugs found as follow-up
>    commits on `engineer-a`.
>
> If Track C is blocked (no `MAKE_WEBHOOK_URL`), instead add a small hotel
> booking test module under `tests/` (`test_booking_flow.py`) covering
> `finalize_booking` happy path, missing fields, over-occupancy, bad dates,
> and idempotency — then commit + push.
