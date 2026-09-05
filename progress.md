# Hotel AI Receptionist - Development Progress Tracker

Spec source: `implementation_plan.md`. Owner of this file's Track A / Track 0A
rows: Engineer A (Python core). Track 0B / Track B rows belong to Engineer B
(Make.com, GHL, Twilio, telephony).

## Phase 0: Pre-Flight Configuration (Track 0A - Engineer A)
- [x] [DONE] Set up Python virtual environment and verify dependencies — used `.venv` (not literally `AI-Receptionist-2-0`, since that name is already the repo folder itself; nesting a same-named venv inside it would be confusing). All packages in `requirements.txt` install clean and import clean.
- [ ] [BLOCKED - needs Engineer A's own Deepgram account] Generate fresh Deepgram API key and configure in `.env`. `.env` is created locally (gitignored) with a placeholder `DEEPGRAM_API_KEY`; whoever has the Deepgram account must drop the real key in.
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

## Track A: Python Codebase & AI Core (Engineer A)
- [ ] [TODO] Define hotel metadata, room tiers, rates, and policies in `data/data.json`
- [ ] [TODO] Rewrite system prompt for Hotel Sarah in `data/config.json`
- [ ] [TODO] Implement hotel booking state machine in `services/agent_logic.py`
- [ ] [TODO] Implement unique booking ID generator in `services/booking_id.py`
- [ ] [TODO] Implement stay duration and pricing calculation helper in `services/tools.py`
- [ ] [TODO] Create asynchronous webhook dispatcher in `services/webhook_dispatcher.py`
- [ ] [TODO] Hook `booking.created` and `call.completed` into `routers/brain.py` and `routers/text_test.py`
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

### Session 1 — 2026-09-05 (Engineer A)

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

**Left for next session:**
- All of Track A (hotel data/prompt/state-machine/booking-id/pricing/
  webhook-dispatcher/router-wiring/test-UI/calendar). Current codebase is
  still the dental-clinic domain (`services/agent_logic.py`, `data/config.json`,
  `data/data.json` all reference "Bright Smile Dental Care", patient
  name/date/time/reason fields).

**Issues / blockers:**
- `DEEPGRAM_API_KEY` in `.env` is a placeholder — needs a real key from
  whoever owns the Deepgram account before the server can actually run a
  live voice/text session.
- `MAKE_WEBHOOK_URL`, `GHL_LOCATION_ID`, `GHL_API_KEY` are also placeholders
  — depend on Engineer B's Track 0B setup.
- No blockers on the Track A code work itself; can start immediately next
  session.

---

## Next Session Kickoff Prompt

Paste this to start the next session:

> Read `progress.md` and `implementation_plan.md` in this repo. I'm Engineer A,
> continuing on branch `engineer-a`. Pick up Track A from where progress.md
> says it's left off, work through the unchecked Track A items in order,
> update progress.md's checklist and Session Log as you go, and commit +
> push to the `engineer-a` branch after each completed feature.
