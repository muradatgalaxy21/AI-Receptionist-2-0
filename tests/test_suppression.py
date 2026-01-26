
import asyncio
import json
import time

# Mocking parts of the system for standalone testing
class MockWebSocket:
    def __init__(self):
        self.sent_messages = []

    async def send_text(self, message):
        self.sent_messages.append(message)
        # print(f"[WebSocket] Sent: {message[:50]}...")

class MockDeepgramSocket:
    def __init__(self, scenario_data):
        self.scenario_data = scenario_data
        self.index = 0

    async def recv(self):
        if self.index < len(self.scenario_data):
            item = self.scenario_data[self.index]
            self.index += 1
            # Simulate network delay slightly
            await asyncio.sleep(0.1)
            return item
        else:
            # Keep stream open but no more data
            await asyncio.sleep(10)
            return None
            
    async def send(self, data):
        pass

# ==================================================================================
# PROPOSED REFACTORED LOGIC FROM brain.py
# ==================================================================================

async def test_logic_flow(scenario_data):
    websocket = MockWebSocket()
    dg_agent = MockDeepgramSocket(scenario_data)
    
    # Shared State
    should_speak = True
    audio_queue = asyncio.Queue()
    conversation_state = {}

    print("\n--- STARTING SIMULATION ---\n")

    # 1. Socket Listener Task
    async def socket_listener():
        nonlocal should_speak
        try:
            while True:
                response = await dg_agent.recv()
                if response is None: 
                    break # End of test data

                if isinstance(response, bytes):
                    # Audio Handling
                    if should_speak:
                        # Put into queue with timestamp
                        await audio_queue.put((time.time(), response))
                        print(f"[Listener] Queued Audio Chunk ({len(response)} bytes)")
                    else:
                        print(f"[Listener] DROPPED Audio Chunk ({len(response)} bytes) - Muted")
                else:
                    # Text Handling
                    msg = json.loads(response)
                    msg_type = msg.get("type")

                    if msg_type == "UserStartedSpeaking":
                        print("[Listener] User Started Speaking -> UNMUTE & RESET")
                        should_speak = True
                        # Clear queue ideally, but strict decoupling might just reset the gate
                        # For now, let's just reset the gate. 
                    
                    elif msg_type == "ConversationText":
                        content = msg.get("content")
                        print(f"[Listener] Received Text: {content}")

                        # Check if it is JSON
                        try:
                            payload = json.loads(content)
                            if isinstance(payload, dict) and payload.get("type") in ["field_update", "ready_to_book"]:
                                print("[Listener] DETECTED JSON CONTROL MESSAGE -> MUTING")
                                should_speak = False
                            else:
                                # Normal JSON that we want to speak? Rare, but assume text is speech
                                should_speak = True
                        except json.JSONDecodeError:
                            # It's normal text
                            print("[Listener] Normal Speech Text -> UNMUTING")
                            should_speak = True
        except Exception as e:
            print(f"[Listener] Error: {e}")

    # 2. Audio Sender Task
    async def audio_sender():
        # Delay logic state
        last_user_start_time = time.time() # Mock
        first_byte_received = False
        
        while True:
            # Get from queue
            timestamp, audio_chunk = await audio_queue.get()
            
            # Simple sending simulation
            print(f"[Sender] Sending Audio Chunk to WebSocket")
            audio_queue.task_done()

    # Run tasks
    listener_task = asyncio.create_task(socket_listener())
    sender_task = asyncio.create_task(audio_sender())

    # Wait for listener to finish consuming data
    await asyncio.sleep(2)  # Give enough time for the mock data to process
    
    listener_task.cancel()
    sender_task.cancel()
    print("\n--- SIMULATION ENDED ---\n")


# ==================================================================================
# TEST SCENARIO
# ==================================================================================

if __name__ == "__main__":
    # Simulate a stream of meesages from Deepgram
    
    # 1. Normal Greeting Audio
    # 2. JSON Update (Text) -> Should Mute
    # 3. Audio for JSON (Bytes) -> Should be Dropped
    # 4. Normal Question (Text) -> Should Unmute
    # 5. Audio for Question (Bytes) -> Should be Queued
    
    scenario = [
        # 1. Initial Greeting Audio
        b'\x01\x02\x03', 
        
        # 2. JSON Update
        json.dumps({
            "type": "ConversationText",
            "content": json.dumps({
                "type": "field_update",
                "field": "first_name",
                "value": "Murat"
            })
        }),
        
        # 3. Audio corresponding to the JSON read-out (should be dropped)
        b'\x04\x05\x06',
        b'\x07\x08\x09',

        # 4. Next Question Text
        json.dumps({
            "type": "ConversationText",
            "content": "What is your last name?"
        }),

        # 5. Audio for the question (should be sent)
        b'\x0A\x0B\x0C'
    ]

    asyncio.run(test_logic_flow(scenario))
