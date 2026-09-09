# Hotel AI Receptionist - Development Progress Tracker

> **Plan change (2026-09-07):** GoHighLevel dropped (not working / phone verification blocked). Replaced with **Airtable** as CRM + **Twilio SMS via Make.com** for confirmation texts. All "GHL" tasks below are superseded by Airtable equivalents.
>
> **Plan change (2026-09-09):** Twilio dropped (out of free credits) → replaced with **SignalWire** for voice. GoHighLevel phone-verification blocker resolved (US number bought + verified via Tello, $7.5 spent) → **GHL back in scope**, config not started, needs setup from scratch. Airtable + Make.com pipeline stays as-is alongside GHL for now.

## Phase 0: Pre-Flight Configuration (Track 0A - Engineer 1)
- [ ] [TODO] Set up Python virtual environment `AI-Receptionist-2-0` and verify dependencies
- [ ] [TODO] Generate fresh Deepgram API key and configure in `.env`
- [ ] [TODO] Document outbound JSON webhook payload contracts (`booking.created`, `call.completed`)
- [ ] [TODO] Configure local server settings (`PORT=8000`, `HOST=0.0.0.0`) in `.env`

## Phase 0: Pre-Flight Configuration (Track 0B - Engineer 2 / Murad)
- [x] [DONE] Set up Ngrok static domain (`unpromotive-anthropomorphously-dreama.ngrok-free.dev`) and configure `PUBLIC_BASE_URL`
- [ ] [TODO] ~~Provision Twilio voice phone number (`+15134363387`)~~ (dropped - out of free credits)
- [x] [DONE] Buy + verify US number via Tello ($7.5 spent) for GHL
- [ ] [TODO] Provision SignalWire voice number (trial) and configure Voice webhook to `<PUBLIC_BASE_URL>/incoming-call`
- [ ] [TODO] Verify Tello number under SignalWire "Verified Caller IDs" so trial account can call it (avoids further spend)
- [x] [DONE] Create Make.com scenario webhook listener and share `MAKE_WEBHOOK_URL` (`https://hook.eu1.make.com/hlmg8hst5sb0vew28wfyj6hiibgyg9e1`)
- [x] [DONE] Create Airtable base `Hotel Reservations` with `Reservations` table + fields (Booking ID, Guest Name, Phone, Room Type, Check-in/out Date, Number of Guests, Total Cost, Special Requests, Status)
- [x] [DONE] Generate Airtable Personal Access Token (scopes: `data.records:read`, `data.records:write`, `schema.bases:read`) and retrieve Base ID (`appjup9acxjGIokKZ`)
- [x] [DONE] Connect Airtable to Make.com scenario (PAT auth, fixed initial 403 by adding `schema.bases:read` scope)
- [x] [DONE] Fire test curl payload to `MAKE_WEBHOOK_URL` to capture sample bundle for field mapping
- [x] [DONE] Map Airtable "Create a Record" module fields to webhook bubbles (booking_id, guest_name, phone_number, room_type, check_in_date, check_out_date, number_of_guests, total_cost, special_requests)
- [ ] [TODO] Rename Airtable table from default "Table 1" to "Reservations" if not already applied in scenario
- [ ] [TODO] Add SignalWire "Send SMS" module in Make.com after Airtable record creation, using dynamic booking fields
- [ ] [TODO] Sign up / log into GHL, create sub-account ("Location") for hotel
- [ ] [TODO] Add + verify Tello US number as GHL's calling/SMS number (LC Phone or number import)
- [ ] [TODO] Generate GHL API key / private integration token and retrieve `GHL_LOCATION_ID`
- [ ] [TODO] Create GHL custom contact fields (booking_id, room_type, check_in_date, check_out_date, number_of_guests, total_cost, special_requests)
- [ ] [TODO] Build GHL "Hotel Reservations" Pipeline and stages
- [ ] [TODO] Configure GHL automated SMS workflow (booking confirmation trigger)
- [ ] [TODO] Decide: GHL replaces Airtable+Make SMS leg, or runs in parallel for pitch comparison

## Track A: Python Codebase & AI Core (Engineer 1)
- [ ] [TODO] Define hotel metadata, room tiers, rates, and policies in `data/data.json`
- [ ] [TODO] Rewrite system prompt for Hotel Sarah in `data/config.json`
- [ ] [TODO] Implement hotel booking state machine in `services/agent_logic.py`
- [ ] [TODO] Implement unique booking ID generator in `services/booking_id.py`
- [ ] [TODO] Implement stay duration and pricing calculation helper in `services/tools.py`
- [ ] [TODO] Create asynchronous webhook dispatcher in `services/webhook_dispatcher.py`
- [ ] [TODO] Hook `booking.created` and `call.completed` into `routers/brain.py` and `routers/text_test.py`
- [ ] [TODO] Update web chat testing interface in `static/test_chat.html`
- [ ] [TODO] Google Calendar API synchronization bridge in `services/calender.py`

## Track B: Cloud Automations, Airtable & Presentation (Engineer 2 / Murad)
- [x] [DONE] Build Make.com scenario routing (`booking.created` and `call.completed`) - webhook + Airtable module wired, field mapping complete
- [x] [DONE] Map Make.com data to Airtable `Reservations` table records
- [ ] [TODO] Build and test SignalWire SMS confirmation module in Make.com with dynamic Booking ID
- [ ] [TODO] Set up GoHighLevel from scratch (sub-account, number, pipeline, workflow) - see Track 0B
- [ ] [TODO] Build 4-6 slide STARR presentation deck for client pitch
- [ ] [TODO] Lead live demo walkthrough test

## Track C: Joint Verification
- [ ] [TODO] End-to-end web chat reservation -> Make.com -> Airtable record -> SMS verification received
- [ ] [TODO] End-to-end phone call reservation -> Voice booking -> Airtable record -> SMS verification received

## Environment (`.env`) Status
- [x] `PUBLIC_BASE_URL`, `PORT`, `HOST` set
- [ ] ~~`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`~~ (dropped - out of credits)
- [ ] `SIGNALWIRE_PROJECT_ID`, `SIGNALWIRE_TOKEN`, `SIGNALWIRE_SPACE_URL`, `SIGNALWIRE_PHONE_NUMBER` pending
- [x] `MAKE_WEBHOOK_URL` set
- [x] `AIRTABLE_BASE_ID`, `AIRTABLE_API_KEY` set
- [ ] `GHL_LOCATION_ID`, `GHL_API_KEY` pending (GHL back in scope, not yet configured)
- [ ] `DEEPGRAM_API_KEY` pending from Engineer 1
- [ ] `TURSO_DATABASE_URL` / `TURSO_AUTH_TOKEN` optional, not yet needed

## Resume Point for Next Session
Pick up at: (1) verify Tello number under SignalWire "Verified Caller IDs" (trial account, avoid further spend) and provision SignalWire voice number; (2) start GHL setup from scratch - sub-account, add/verify Tello number, API key, custom fields, pipeline, SMS workflow.
