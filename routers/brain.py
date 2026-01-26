import json
import base64
import asyncio
import websockets
import os
from fastapi import WebSocket
from dotenv import load_dotenv
from services import tools

load_dotenv()

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
AGENT_URL = "wss://agent.deepgram.com/v1/agent/converse"

async def process_audio_stream(websocket: WebSocket):
    headers = { "Authorization": f"Token {DEEPGRAM_API_KEY}" }

    try:
        with open("data/config.json", "r") as f:
            agent_config = json.load(f)
    except Exception as e:
        print(f"Config Error: {e}")
        return

    stream_sid = None
    print(f"Connecting to: {AGENT_URL}")

    try:
        async with websockets.connect(AGENT_URL, extra_headers=headers, ping_interval=None) as dg_agent:
            await dg_agent.send(json.dumps(agent_config))
            print("CONNECTION SUCCESS! Sarah is listening...")

            async def send_mic_audio():
                nonlocal stream_sid
                try:
                    while True:
                        message = await websocket.receive_text()
                        data = json.loads(message)
                        if data['event'] == 'start':
                            stream_sid = data['start']['streamSid']
                        elif data['event'] == 'media':
                            audio_bytes = base64.b64decode(data['media']['payload'])
                            if dg_agent.open:
                                await dg_agent.send(audio_bytes)
                        elif data['event'] == 'stop':
                            break
                except Exception:
                    pass

            async def receive_agent_audio():
                try:
                    while True:
                        response = await dg_agent.recv()
                        
                        if isinstance(response, bytes):
                            if stream_sid:
                                media_message = {
                                    "event": "media",
                                    "streamSid": stream_sid,
                                    "media": { "payload": base64.b64encode(response).decode("utf-8") }
                                }
                                await websocket.send_text(json.dumps(media_message))
                        else:
                            msg = json.loads(response)
                            
                            if msg.get("type") == "ConversationText":
                                role = msg.get("role")
                                if role == "assistant":
                                    print(f"🗣️ Sarah: {msg.get('content')}")
                                elif role == "user":
                                    print(f"👤 YOU: {msg.get('content')}")

                            elif msg.get("type") == "UserStartedSpeaking":
                                print("⬇️ BARGE-IN: Clearing audio...")
                                if stream_sid:
                                    await websocket.send_text(json.dumps({ "event": "clear", "streamSid": stream_sid }))

                            elif msg.get("type") == "FunctionCallRequest":
                                function_name = msg.get("function_name")
                                arguments = msg.get("parameters")
                                call_id = msg.get("function_call_id")

                                print(f"⚡ AI Requesting: {function_name} | Args: {arguments}")

                                # --- THE FIX: HANDLE GHOST CALLS ---
                                if not call_id:
                                    # If we ignore it, the AI waits forever.
                                    # We cannot reply without an ID.
                                    # So we do nothing, BUT we rely on Config Rule #2 to prevent this.
                                    print("⚠️ Ghost Call (No ID). Skipping.")
                                    continue
                                
                                # Safety Net: If AI sends ID but no Name (Partial Ghost)
                                if not function_name:
                                    result = "System Error: Missing function name. Please ask the user to repeat."
                                else:
                                    result = "Error: Unknown function"
                                    try:
                                        if function_name == "check_availability":
                                            result = tools.check_availability(arguments.get("date"), arguments.get("time"))
                                        elif function_name == "book_appointment_tool":
                                            result = tools.book_appointment_tool(
                                                arguments.get("name"), arguments.get("reason"),
                                                arguments.get("date"), arguments.get("time")
                                            )
                                    except Exception as e:
                                        result = f"System Error: {str(e)}"
                                        print(f"❌ TOOL ERROR: {e}")

                                # Always send a response back!
                                response_payload = {
                                    "type": "FunctionCallResponse",
                                    "function_call_id": call_id,
                                    "output": str(result)
                                }
                                await dg_agent.send(json.dumps(response_payload))
                                print(f"✅ Sent Result: {result}")
                            
                except Exception as e:
                    print(f"Receiver Error: {e}")

            await asyncio.gather(send_mic_audio(), receive_agent_audio())

    except Exception as e:
        print(f"Connection Error: {e}")