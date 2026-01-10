import asyncio
import json
from brain import process_audio_stream

# A Mock WebSocket that pretends to be Twilio
class MockWebSocket:
    def __init__(self):
        self.queue = [
            json.dumps({"event": "start", "start": {"streamSid": "TEST_ID"}}),
            # Simulated audio packet
            json.dumps({"event": "media", "media": {"payload": "UklGRi4AAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA="}}), 
            json.dumps({"event": "stop"})
        ]
        self.index = 0

    async def accept(self):
        pass

    async def receive_text(self):
        if self.index < len(self.queue):
            msg = self.queue[self.index]
            self.index += 1
            await asyncio.sleep(0.5)
            return msg
        else:
            await asyncio.sleep(1)
            return json.dumps({"event": "stop"})

    async def send_text(self, text):
        print(f"[Success] Brain sent response: {text[:30]}...")

async def run_test():
    print("--- STARTING TEST ---")
    fake_socket = MockWebSocket()
    await process_audio_stream(fake_socket)
    print("--- TEST FINISHED ---")

if __name__ == "__main__":
    asyncio.run(run_test())