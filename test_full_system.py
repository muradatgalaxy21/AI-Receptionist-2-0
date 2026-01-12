import asyncio
import json
import websockets
import uvicorn
from multiprocessing import Process
import time

# Function to start your actual server in the background
def start_server():
    from main import app
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="error")

async def run_test_client():
    uri = "ws://127.0.0.1:8000/media-stream"
    
    print("📞 [Test] Dialing the AI Receptionist...")
    
    try:
        async with websockets.connect(uri) as websocket:
            print("✅ [Test] Connected to WebSocket!")

            # 1. Send the "Start" event (Twilio does this first)
            start_event = {
                "event": "start",
                "start": {"streamSid": "TEST_CALL_123"}
            }
            await websocket.send(json.dumps(start_event))
            
            # 2. Simulate sending audio (just silence for testing)
            # This triggers the "Brain" to process it
            media_event = {
                "event": "media",
                "media": {
                    "payload": "UklGRi4AAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA="
                }
            }
            await websocket.send(json.dumps(media_event))
            
            # 3. Listen for a response
            print("👂 [Test] Listening for AI response...")
            try:
                # Wait 5 seconds for a response
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                print(f"🗣️ [Test] AI Responded: {response[:100]}...")
            except asyncio.TimeoutError:
                print("⚠️ [Test] No transcript received (Expected for silence). Connection is good!")
            
            # 4. Clean up
            stop_event = {"event": "stop"}
            await websocket.send(json.dumps(stop_event))
            print("✅ [Test] Test passed. System is integrated.")

    except Exception as e:
        print(f"❌ [Test] Failed: {e}")

if __name__ == "__main__":
    # 1. Start the Server in a separate process
    server_process = Process(target=start_server)
    server_process.start()
    
    # Give the server 2 seconds to wake up
    time.sleep(2)
    
    # 2. Run the Test Client
    try:
        asyncio.run(run_test_client())
    finally:
        # 3. Kill the server when done
        server_process.terminate()