# # main.py
# import os
# from fastapi import FastAPI
# from dotenv import load_dotenv
# from routers import twilio
# # from routers import deepgram  <-- IGNORE AHAD'S FILE FOR NOW

# # Load environment variables
# load_dotenv()

# app = FastAPI()

# # Only include YOUR router
# app.include_router(twilio.router)
# # app.include_router(deepgram.router) <-- IGNORE AHAD'S ROUTER

# @app.get("/")
# async def health_check():
#     return {"status": "AI Receptionist is Live (Engineer A Mode)"}



# ===========================================================

import os
import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

# Import your modules
from routers import twilio
from routers import text_test
from routers import voice_browser
from routers.brain import process_audio_stream

# Load environment variables
load_dotenv()

app = FastAPI()

# 1. Register the Twilio HTTP Route (The "Doorbell")
# This handles the initial ringing of the phone.
app.include_router(twilio.router)

# 1b. Register the Text Test Route (for testing without Twilio)
# Provides a /test-chat WebSocket endpoint for text-based testing.
app.include_router(text_test.router)
app.include_router(voice_browser.router)

# 1c. Serve static files (browser test chat page)
app.mount("/static", StaticFiles(directory="static"), name="static")

# 2. Register the Health Check
@app.get("/")
async def health_check():
    return {"status": "AI Receptionist is Fully Operational"}

# 2b. Serve the Chat Page at a clean URL
@app.get("/chat")
async def chat_page():
    """Serves the text-based chat interface."""
    return FileResponse("static/test_chat.html")

# 3. THE MISSING LINK: The WebSocket Route (The "Conversation")
# When Twilio connects the audio, it looks for "/media-stream".
@app.websocket("/media-stream")
async def media_stream(websocket: WebSocket):
    # Accept the connection
    await websocket.accept()
    
    # Hand over control to your "Brain"
    # This will automatically load your config.json and data.json
    await process_audio_stream(websocket)

if __name__ == "__main__":
    # This allows you to run "python main.py" to start the server
    uvicorn.run(app, host="0.0.0.0", port=8000)