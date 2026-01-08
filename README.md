# AI Receptionist

## Project Overview

This project is a real-time AI Voice Receptionist capable of answering phone calls, processing speech, and responding intelligently. It serves as a bridge between traditional telephony (Twilio) and modern AI audio streaming (Deepgram).

The system is built using **FastAPI** for high-performance asynchronous handling of WebSocket connections and HTTP requests.

## Architecture

The application is designed with a modular architecture to separate infrastructure from logic:

- **Telephony Layer (Twilio):** Handles the physical phone line, voice capture, and audio playback.
- **Server Layer (FastAPI):** Acts as the central switchboard, managing Webhook events and WebSocket streams.
- **Intelligence Layer (Deepgram):** Processes live audio streams to transcribe speech to text in real-time.

## Tech Stack

- **Language:** Python 3.9+
- **Framework:** FastAPI
- **Server:** Uvicorn
- **Telephony:** Twilio (Programmable Voice)
- **Speech-to-Text:** Deepgram SDK
- **Tunneling:** Ngrok (for local development)

---

## Installation Guide

Follow these steps to set up the project locally.

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/ai-receptionist.git
cd ai-receptionist

```

### 2. Set Up Virtual Environment

It is recommended to use a virtual environment to manage dependencies.

**Windows:**

```bash
python -m venv venv
.\venv\Scripts\activate

```

**Mac/Linux:**

```bash
python3 -m venv venv
source venv/bin/activate

```

### 3. Install Dependencies

```bash
pip install -r requirements.txt

```

---

## Configuration

This project requires sensitive API keys. These keys must be stored in a `.env` file, which is excluded from version control for security.

1. Create a file named `.env` in the root directory.
2. Add the following variables:

```ini
# Deepgram API Key (Required for transcription)
DEEPGRAM_API_KEY=your_deepgram_key_here

# Twilio Credentials (Optional: Only required if using Twilio SDK features later)
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token

```

---

## Usage Instructions

To make the AI Receptionist operational, you must run the local server and expose it to the internet so Twilio can access it.

### Step 1: Start the Local Server

Run the application using Uvicorn. This starts the FastAPI server on port 8000.

```bash
uvicorn main:app --reload

```

### Step 2: Expose Server via Ngrok

Open a new terminal window and run Ngrok to create a secure tunnel to your localhost.

```bash
ngrok http 8000

```

_Copy the HTTPS URL provided by Ngrok (e.g., `https://example.ngrok-free.app`)._

### Step 3: Configure Twilio Webhook

1. Log in to the **Twilio Console**.
2. Navigate to **Phone Numbers** > **Manage** > **Active Numbers**.
3. Select your number.
4. Under the **Voice & Fax** section, locate **"A Call Comes In"**.
5. Set the type to **Webhook**.
6. Paste your Ngrok URL and append `/incoming-call`.

- _Example:_ `https://example.ngrok-free.app/incoming-call`

7. Ensure the HTTP method is set to **POST**.
8. Save changes.

---

## Project Structure

The codebase is organized into modular routers to prevent conflicts between infrastructure logic and AI logic.

```text
ai-receptionist/
├── main.py                 # Entry point. Initializes FastAPI and connects routers.
├── requirements.txt        # List of Python dependencies.
├── .env                    # Environment variables (API Keys).
├── .gitignore              # Specifies files to exclude from Git (e.g., .env, venv).
└── routers/
    ├── twilio.py           # Handles incoming calls and TwiML XML responses.
    └── deepgram.py         # Manages WebSocket connections for real-time audio.

```

## API Endpoints

### `POST /incoming-call`

- **Description:** The entry point for all phone calls. Twilio hits this endpoint when a user dials the number.
- **Response:** Returns TwiML (XML) instructions telling Twilio to connect the call to the media stream.

### `WebSocket /media-stream`

- **Description:** A bidirectional WebSocket connection.
- **Function:** Receives raw audio data from Twilio and forwards it to the Deepgram AI service for processing.

---

## Troubleshooting

**Issue: "404 Not Found" when calling**

- **Cause:** The Webhook URL in Twilio is incorrect.
- **Fix:** Ensure you added `/incoming-call` to the end of your Ngrok URL.

**Issue: "Method Not Allowed"**

- **Cause:** The Twilio Webhook is set to GET.
- **Fix:** Change the Webhook method to POST in the Twilio Console.

**Issue: Server crashes on startup**

- **Cause:** Missing environment variables or dependencies.
- **Fix:** Ensure `.env` exists and `pip install -r requirements.txt` was run successfully.
