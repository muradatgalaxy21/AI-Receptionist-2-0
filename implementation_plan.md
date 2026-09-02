# Implementation Plan: Hotel AI Receptionist Transformation & Make.com / GoHighLevel Integration

This plan outlines the end-to-end transformation of the current AI Receptionist from a dental clinic assistant into a **Hotel AI Receptionist** powered by an event-driven Webhook architecture (Model A) connected to **Make.com** and **GoHighLevel (GHL)**. It includes a balanced 50/50 workload division for two engineers, progress tracking specification, and a 4-6 slide STARR pitch presentation outline.

---

## Balanced 50/50 Work Division Strategy

To prevent overloading and completely eliminate Git merge conflicts, the responsibilities are split between **Python Codebase & AI Backend (Engineer 1)** and **Cloud Automations, CRM Architecture & Client Pitch (Engineer 2)**.

```mermaid
graph TD
    subgraph Engineer 1: Python Codebase & AI Core
        E1_A[data/data.json - Hotel Data & Pricing]
        E1_B[data/config.json - Hotel Sarah Prompt]
        E1_C[services/agent_logic.py - Hotel State Machine]
        E1_D[services/booking_id.py - Unique ID Engine]
        E1_E[services/tools.py - Stay Duration & Pricing Engine]
        E1_F[services/webhook_dispatcher.py - Async Webhook Service]
        E1_G[routers/brain.py & text_test.py - Event Wiring]
        E1_H[services/calender.py - Google Calendar Bridge]
        E1_I[static/test_chat.html - Hotel Test Web UI]
    end

    subgraph Engineer 2: Make.com, GoHighLevel & Pitch Deck
        E2_A[Make.com - Scenario, Webhook Listener & Routing]
        E2_B[GoHighLevel - Custom Fields: Room Type, Booking ID, Dates]
        E2_C[GoHighLevel - Hotel Reservation Pipeline & Stages]
        E2_D[GoHighLevel - Automated SMS & Confirmation Workflows]
        E2_E[GoHighLevel - Calendar Setup & Availability Rules]
        E2_F[Twilio Console - Webhook Configuration & Numbers]
        E2_G[STARR Presentation Deck - 4-6 Slide Client Pitch]
        E2_H[End-to-End Client Demo Lead]
    end

    E1_F -->|Live Webhook JSON Stream| E2_A
    E2_A --> E2_B & E2_C & E2_D & E2_E
```

---

### Detailed Task Breakdown

#### Engineer 1: Python Codebase & AI Backend Engineer
*Owns 100% of the Python code and Git repository.*

1. **Hotel Domain Knowledge & Prompting**:
   - Refactor `data/data.json` with hotel details (room categories, pricing, amenities, check-in/out policies, FAQs).
   - Update `data/config.json` with Hotel Sarah prompt and structured JSON booking trigger.
2. **Hotel Conversation State & Booking Logic**:
   - Refactor `services/agent_logic.py` for hotel fields: `guest_name`, `phone_number`, `room_type`, `check_in_date`, `check_out_date`, `number_of_guests`, `special_requests`.
   - Create `services/booking_id.py` to generate unique confirmation IDs (e.g. `HTL-8492X`).
   - Implement stay duration (number of nights) and total cost calculation in `services/tools.py`.
3. **Webhook Dispatcher & Pipeline Integration**:
   - Create `services/webhook_dispatcher.py` for non-blocking asynchronous HTTP POST delivery to Make.com.
   - Wire event triggers for `booking.created` and `call.completed` in `routers/brain.py` and `routers/text_test.py`.
4. **Calendar Bridge & Web UI**:
   - Refactor `services/calender.py` for Google Calendar synchronization fallback.
   - Update `static/test_chat.html` theme and quick-action prompt buttons for hotel testing.

---

#### Engineer 2: Cloud Automations, GoHighLevel CRM Architect & Pitch Lead
*Owns Make.com, GoHighLevel sub-account setup, SMS automations, and Client Presentation.*

1. **Make.com Scenario Engineering**:
   - Set up Webhook Listener module to ingest payloads from the Python server.
   - Create Router branches for `booking.created` vs `call.completed`.
   - Configure data mapping, formatting, and error handling.
2. **GoHighLevel CRM & Pipeline Architecture**:
   - Create Custom Contact Fields: `Booking ID`, `Room Type`, `Check-in Date`, `Check-out Date`, `Total Cost`, `Number of Guests`.
   - Build a "Hotel Reservations" Pipeline (Stages: *Inquiry*, *Reserved*, *Checked In*, *Checked Out*, *Cancelled*).
   - Configure GoHighLevel Calendar for room/staff schedules.
3. **Automated SMS Confirmation Workflow**:
   - Build automated GoHighLevel Workflow triggered upon reservation creation.
   - Format instant SMS template:
     `"Hello {{contact.first_name}}, your reservation at Grand Horizon Hotel is confirmed! Booking ID: {{contact.booking_id}}. Room: {{contact.room_type}}. Check-in: {{contact.check_in_date}} at 3:00 PM. Please present your Booking ID upon arrival."`
4. **Client Pitch Deck & Presentation (STARR)**:
   - Build the 4-6 slide STARR presentation deck.
   - Document client ROI metrics (direct bookings, zero missed calls, automated check-in).
   - Lead the live client demo walkthrough.

---

## `progress.md` Specification

```markdown
# Hotel AI Receptionist - Development Progress Tracker

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

## Track B: Cloud Automations, GHL & Presentation (Engineer 2)
- [ ] [TODO] Create Make.com webhook receiver scenario and route data
- [ ] [TODO] Set up GoHighLevel custom contact fields (Booking ID, Room Type, Dates)
- [ ] [TODO] Build GoHighLevel "Hotel Reservations" Opportunity Pipeline
- [ ] [TODO] Configure GoHighLevel Calendar and availability rules
- [ ] [TODO] Build automated GoHighLevel SMS workflow with Booking ID confirmation template
- [ ] [TODO] Configure Twilio phone number webhook routing to Ngrok / Server
- [ ] [TODO] Build 4-6 slide STARR presentation deck for client pitch
- [ ] [TODO] Lead live demo walkthrough test

## Track C: Joint Verification
- [ ] [TODO] End-to-end web chat reservation -> Make.com -> GHL Contact -> SMS verification received
- [ ] [TODO] End-to-end phone call reservation -> Voice booking -> GHL Opportunity -> SMS verification received
```

---

## STARR Presentation Outline (4-6 Slides for Client Showcase)

### Slide 1: Situation (The Front Desk Bottleneck in Hospitality)
- **Problem**: 30-35% of hotel inquiry and reservation calls go unanswered during peak check-in rushes and night shifts.
- **Impact**: Lost direct bookings and heavy reliance on 15-25% OTA commissions.

### Slide 2: Task (The 24/7 Autonomous Concierge Objective)
- **Objective**: Deploy an intelligent voice AI capable of answering instantly, checking room availability, answering hotel policy questions, and confirming reservations 24/7/365.

### Slide 3: Action (The AI & CRM Architecture)
- **Technology**: Sub-second Deepgram Voice AI + GPT-4o-mini reasoning connected via real-time Webhooks to Make.com and GoHighLevel CRM with instant SMS verification ID dispatch.

### Slide 4: Result (Operational Impact & ROI)
- **Metrics**: 100% call answer rate, 70%+ front desk workload reduction, increased direct booking revenue, and friction-free check-in.

### Slide 5: Reflection & Future Expansion
- **Growth**: In-stay WhatsApp concierge for room service/housekeeping, multi-language international guest support, and automated upselling (spa, dining, airport shuttles).

### Slide 6: Visual System Flow Demo
- **Diagram**: Guest Call $\rightarrow$ Voice AI Receptionist $\rightarrow$ Make.com Webhook $\rightarrow$ GoHighLevel Pipeline $\rightarrow$ Instant SMS Confirmation with Booking ID.
