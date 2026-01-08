# main.py
import os
from fastapi import FastAPI
from dotenv import load_dotenv
from routers import twilio
# from routers import deepgram  <-- IGNORE AHAD'S FILE FOR NOW

# Load environment variables
load_dotenv()

app = FastAPI()

# Only include YOUR router
app.include_router(twilio.router)
# app.include_router(deepgram.router) <-- IGNORE AHAD'S ROUTER

@app.get("/")
async def health_check():
    return {"status": "AI Receptionist is Live (Engineer A Mode)"}