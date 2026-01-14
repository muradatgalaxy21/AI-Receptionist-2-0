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
from dotenv import load_dotenv

# Import your modules
from routers import twilio
from routers.brain import process_audio_stream

# Load environment variables
load_dotenv()

app = FastAPI()

# 1. Register the Twilio HTTP Route (The "Doorbell")
# This handles the initial ringing of the phone.
app.include_router(twilio.router)

# 2. Register the Health Check
@app.get("/")
async def health_check():
    return {"status": "AI Receptionist is Fully Operational"}

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