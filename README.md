# AI Receptionist - Doctor Farooq's Dental Clinic

## Project Overview

This project is a real-time AI Voice and Text Receptionist capable of answering phone calls, handling text chats, processing speech/text, checking availability, and booking appointments intelligently. It serves as a bridge between traditional telephony (Twilio), a browser-based chat interface, and a modern AI engine (Deepgram/LLMs).

The system is built using **FastAPI** for high-performance asynchronous handling of WebSocket connections and HTTP requests.

## Features

- **Voice Calls:** Answers live phone calls via Twilio and streams audio back and forth with Deepgram's AI Voice Agent.
- **Text Testing UI:** A beautiful, responsive browser-based chat interface to test the agent's logic, prompts, and booking flows without needing to make phone calls.
- **Real-Time Booking:** Checks availability and books appointments directly into a local SQLite database (`appointments.db`).
- **Conversational Intelligence:** The agent asks for names, desired dates/times, and reasons for the visit, confirms the booking, and accurately handles unavailable slots or follow-up questions.
- **Conversation Logging:** Automatically logs all testing conversations to the filesystem for review.

## Tech Stack

- **Language:** Python 3.9+
- **Framework:** FastAPI
- **Server:** Uvicorn
- **Telephony:** Twilio (Programmable Voice)
- **AI Engine:** Deepgram Agent SDK (Voice & Text)
- **Database:** SQLite3
- **Tunneling:** Ngrok (for local development voice testing)
- **Frontend (Testing):** HTML5, Vanilla CSS, JS

---

## Project Structure

The generative AI logic, database interaction, and routing layers are separated for maintainability:

```text
ai-receptionist/
├── main.py                 # Entry point. Initializes FastAPI and connects all routers.
├── requirements.txt        # Python dependencies.
├── .env                    # Environment variables (API Keys).
├── appointments.db         # SQLite database storing the appointments.
├── data/
│   └── config.json         # Deepgram Agent configuration and system prompt.
├── routers/
│   ├── twilio.py           # Handles incoming Twilio calls and XML (TwiML).
│   ├── brain.py            # Manages WebSocket audio streams to Deepgram.
│   └── text_test.py        # Manages WebSocket text streams for the browser UI.
├── services/
│   ├── agent_logic.py      # Core logic, recap extraction, and booking triggers.
│   ├── database.py         # DB connection, schema, and queries.
│   ├── tools.py            # Date parsing, availability checks.
│   └── conversation_logger.py # Utility to save chat transcripts locally.
├── static/
│   └── test_chat.html      # The frontend web UI for text testing.
└── tests/
    └── conversation_logs/  # Saved transcripts from text testing.
```

---

## Installation Guide

Follow these steps to set up the project locally.

### 1. Clone the Repository

```bash
git clone <repository-url>
cd ai-receptionist
```

### 2. Set Up Virtual Environment

It is required to use a virtual environment named `ai-recep-venv` or similar to manage dependencies.

**Windows:**
```bash
python -m venv ai-recep-venv
.\ai-recep-venv\Scripts\activate
```

**Mac/Linux:**
```bash
python3 -m venv ai-recep-venv
source ai-recep-venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configuration

This project requires sensitive API keys. Create a file named `.env` in the root directory and add the following:

```ini
# Deepgram API Key (Required for AI Agent)
DEEPGRAM_API_KEY=your_deepgram_key_here
```

---

## Usage Instructions

### Starting the Server

Run the application using Python (which invokes Uvicorn via `main.py`). The server runs on port `8000`.

```bash
python main.py
```

### Method A: Testing via Browser Text Chat (No Twilio Required)

The easiest way to test the agent's brain and booking flows:

1. Start the server (`python main.py`).
2. Open your web browser and go to:
   **`http://localhost:8000/static/test_chat.html`**
3. Click "Start Conversation" and chat with Sarah. Your conversation will be logged in the `tests/conversation_logs` directory.

### Method B: Testing via Phone Call (Twilio + Ngrok)

To test the actual voice AI over a real phone call:

1. **Start the local server** (`python main.py`).
2. **Start Ngrok** in a new terminal to expose your local server to the internet:
   ```bash
   ngrok http 8000
   ```
   *Copy the HTTPS URL provided by Ngrok (e.g., `https://1234-abcd.ngrok-free.app`).*
3. **Configure Twilio:**
   - Log in to the Twilio Console.
   - Go to Phone Numbers > Manage > Active Numbers.
   - Under "Voice & Fax", find "A Call Comes In".
   - Set it to Webhook, and paste your Ngrok URL followed by `/incoming-call`.
   - Example: `https://1234-abcd.ngrok-free.app/incoming-call`
   - Set HTTP method to **POST** and save.
4. **Call your Twilio number.**

---

## Database Management

The SQLite database (`appointments.db`) is automatically created and initialized when you start the server. 
It contains a single table `appointments` with columns for `first_name`, `last_name`, `reason`, `appointment_date`, `appointment_time`, and `status`.

Standard operational hours configured are 10:00 AM to 8:00 PM.

---

## Troubleshooting

- **Text Chat stuck on "Connecting..."**
  Ensure the server is running on port 8000 and your `.env` contains a valid `DEEPGRAM_API_KEY`.
- **"404 Not Found" When Calling (Twilio)**
  Ensure you added `/incoming-call` to the end of your Ngrok URL in the Twilio Webhook settings.
- **Server Crashes on Startup**
  Double-check your virtual environment is active and all packages from `requirements.txt` are installed.
