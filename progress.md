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
- [ ] [TODO] Update web chat testing interface in `static/test_chat.html`
- [ ] [TODO] Google Calendar API synchronization bridge in `services/calender.py`

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

### Session 2 — 2026-09-05 (Engineer A) — IN PROGRESS

Phase 1 / Track A implementation. Hotel = **Grand Horizon Hotel**, receptionist
persona stays **Sarah**. Commit + push to `engineer-a` after each feature.

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
- Built the leaf modules ahead of the state machine (the plan's listed order)
  because `agent_logic.py` depends on all three.

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

## Next Session Kickoff Prompt (Phase 1)

Paste this to start the next session:

> Read `progress.md` and `implementation_plan.md` in this repo
> (`AI-Receptionist-2-0`). I'm Engineer A, continuing on branch `engineer-a`.
> Phase 0 is done. Start Phase 1 / Track A — work through the unchecked
> Phase 1 / Track A items in `progress.md` in order (hotel data, Hotel Sarah
> prompt, booking state machine, booking-id generator, pricing helper,
> webhook dispatcher, router wiring, test UI, calendar bridge). Update
> `progress.md`'s checklist and Session Log as you go, and commit + push to
> the `engineer-a` branch after each completed feature.
