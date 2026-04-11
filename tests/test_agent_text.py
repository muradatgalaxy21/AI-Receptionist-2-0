# tests/test_agent_text.py
# Standalone CLI script for testing the Deepgram agent via text input.
# Connects directly to the Deepgram Agent API, sends config, and lets you
# type messages that are injected as InjectUserMessage.
#
# Usage:
#   cd ai-receptionist
#   python tests/test_agent_text.py
#
# Type your messages and press Enter. The agent (Sarah) will respond.
# Type 'quit' or 'exit' to end the session.

import json
import asyncio
import threading
import websockets
import os
import sys
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Add the project root to the Python path so we can import services
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from services.agent_logic import process_agent_text_response
from services.conversation_logger import ConversationLogger

load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

DEEPGRAM_API_KEY: str = os.getenv("DEEPGRAM_API_KEY", "")
AGENT_URL: str = "wss://agent.deepgram.com/v1/agent/converse"

# How often (seconds) to send Deepgram's KeepAlive JSON message.
# In text-only mode there is no audio stream to keep the connection alive,
# so we must send { "type": "KeepAlive" } periodically.
# Deepgram recommends sending this whenever no other data is being transmitted.
KEEPALIVE_INTERVAL: int = 8


def load_agent_config() -> dict:
    """
    Load config from data/config.json and inject current datetime.
    1. Reads the JSON file from the project data directory.
    2. Appends the current date/time to the agent prompt.

    Returns:
        The augmented agent configuration dict.
    """
    config_path: Path = PROJECT_ROOT / "data" / "config.json"
    with open(config_path, "r") as f:
        agent_config: dict = json.load(f)

    current_time: str = datetime.now().strftime("%A, %d %B %Y, %I:%M %p")
    agent_config["agent"]["think"]["prompt"] += f"\n\nCONTEXT: Today is {current_time}."
    return agent_config


async def run_text_session() -> None:
    """
    Main async function that runs the interactive text session.
    1. Connects to Deepgram Agent WebSocket with auth headers.
    2. Sends the agent config (Settings message).
    3. Spawns a background keepalive task to send pings every KEEPALIVE_INTERVAL seconds.
    4. Spawns a background task to receive agent responses.
    5. Enters a loop reading user input from stdin and injecting it.
    6. Automatically ends the session if the agent says goodbye.
    7. Logs the full conversation to a file.
    """
    if not DEEPGRAM_API_KEY:
        print("ERROR: DEEPGRAM_API_KEY is missing from .env file")
        print("Set it in your .env file at the project root.")
        return

    logger: ConversationLogger = ConversationLogger(session_label="cli_test")
    print(f"\nConversation log: {logger.file_path}\n")

    # Track conversation state; session_should_end is set by agent_logic when
    # a farewell phrase is detected; last_message_is_payload suppresses JSON display.
    conversation_state: dict = {
        "first_name": None,
        "last_name": None,
        "appointment_date": None,
        "appointment_time": None,
        "reason": None,
        "session_should_end": False,
        "last_message_is_payload": False,
    }

    headers: dict = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}

    try:
        agent_config: dict = load_agent_config()
    except Exception as e:
        print(f"Config Error: {e}")
        return

    print("Connecting to Deepgram Agent...")
    print("=" * 60)

    try:
        # Use default ping_interval (20 s) to maintain the WebSocket transport.
        # The Deepgram-level keepalive is handled by the keepalive_loop below.
        async with websockets.connect(
            AGENT_URL,
            extra_headers=headers,
            ping_interval=20,
            ping_timeout=40,
            close_timeout=5,
        ) as dg_agent:
            # Send the agent configuration
            await dg_agent.send(json.dumps(agent_config))
            logger.log_event("Connected to Deepgram Agent")

            # Shared flag to signal all tasks when the session ends
            session_active: bool = True

            # --- Keepalive task ---
            # In text-only mode there is no audio stream to keep the Deepgram
            # connection alive. We must periodically send the application-level
            # { "type": "KeepAlive" } message as Deepgram's own docs specify.
            async def keepalive_loop() -> None:
                """
                Send Deepgram's KeepAlive JSON every KEEPALIVE_INTERVAL seconds.
                1. Waits for the configured interval.
                2. Sends { "type": "KeepAlive" } as a text frame.
                3. Stops when session ends or socket closes.
                """
                keepalive_msg: str = json.dumps({"type": "KeepAlive"})
                try:
                    while session_active:
                        await asyncio.sleep(KEEPALIVE_INTERVAL)
                        if not session_active:
                            break
                        try:
                            await dg_agent.send(keepalive_msg)
                        except Exception:
                            break
                except asyncio.CancelledError:
                    pass

            # --- Background task: receive and display agent responses ---
            async def receive_responses() -> None:
                nonlocal conversation_state, session_active
                try:
                    while session_active:
                        response = await dg_agent.recv()

                        # Skip binary audio data -- we only want text
                        if isinstance(response, bytes):
                            continue

                        msg: dict = json.loads(response)
                        msg_type: str = msg.get("type", "")

                        if msg_type == "ConversationText":
                            content: str = msg.get("content", "")
                            role: str = msg.get("role", "assistant")

                            # Process through shared logic (recap, availability, booking)
                            # This also sets session_should_end and last_message_is_payload.
                            conversation_state = await process_agent_text_response(
                                content, conversation_state, dg_agent
                            )

                            # Display agent response only if it is visible speech text.
                            # Suppress raw JSON payloads (e.g. ready_to_book) from output.
                            if role == "assistant" and not conversation_state.get("last_message_is_payload"):
                                print(f"\n  SARAH: {content}")
                                print()
                                logger.log("SARAH", content)

                                # If the agent said goodbye, mark for clean shutdown
                                if conversation_state.get("session_should_end"):
                                    print("  [Sarah ended the call. Closing session...]")
                                    session_active = False
                                    return

                                # Show input prompt again
                                print("  YOU > ", end="", flush=True)

                        elif msg_type == "Welcome":
                            print("  [Connected successfully]")

                        elif msg_type == "SettingsApplied":
                            print("  [Agent configured -- Sarah is ready]")
                            print()
                            print("  Type your messages below. Type 'quit' to exit.")
                            print("=" * 60)
                            print()
                            print("  YOU > ", end="", flush=True)

                        elif msg_type == "AgentThinking":
                            print("  [Sarah is thinking...]", end="\r", flush=True)

                        elif msg_type == "InjectionRefused":
                            print("\n  [Message not processed - Sarah was busy. Try again.]")
                            print("  YOU > ", end="", flush=True)

                except websockets.exceptions.ConnectionClosed:
                    if session_active:
                        print("\n  [Connection to Deepgram closed]")
                        session_active = False
                except Exception as e:
                    if session_active:
                        print(f"\n  [Receiver error: {e}]")
                        session_active = False

            # Start keepalive and response receiver as background tasks
            keepalive_task = asyncio.create_task(keepalive_loop())
            receiver_task = asyncio.create_task(receive_responses())

            # --- Main loop: read user input from stdin ---
            # A dedicated daemon thread reads full lines from stdin and posts
            # them to an asyncio.Queue. The main coroutine polls the queue
            # with a 1-second timeout so it can notice session_active=False
            # and exit automatically (without waiting for a keypress).
            loop = asyncio.get_event_loop()
            input_queue: asyncio.Queue = asyncio.Queue()

            def stdin_reader() -> None:
                """
                Blocking stdin reader running in a daemon thread.
                1. Reads one line at a time from sys.stdin.
                2. Puts the line into the asyncio queue in a thread-safe way.
                3. Exits when stdin closes (EOF) or the process ends.
                """
                while True:
                    try:
                        line: str = sys.stdin.readline()
                        if not line:
                            # EOF -- signal the queue so the main loop can exit
                            loop.call_soon_threadsafe(input_queue.put_nowait, None)
                            break
                        loop.call_soon_threadsafe(input_queue.put_nowait, line)
                    except Exception:
                        break

            stdin_thread = threading.Thread(target=stdin_reader, daemon=True)
            stdin_thread.start()

            try:
                while session_active:
                    try:
                        # Poll the queue; 1-second timeout lets us recheck
                        # session_active if the agent said goodbye.
                        raw_line = await asyncio.wait_for(input_queue.get(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue

                    # None signals EOF from the stdin thread
                    if raw_line is None:
                        session_active = False
                        break

                    # If the session ended while we were waiting, discard input
                    if not session_active:
                        break

                    user_input: str = raw_line.strip()

                    if not user_input:
                        continue

                    if user_input.lower() in ("quit", "exit", "q"):
                        print("\n  [Ending session...]")
                        session_active = False
                        break

                    # Log the user input
                    logger.log("USER", user_input)

                    # Inject the text as a user message to the agent
                    inject_message: dict = {
                        "type": "InjectUserMessage",
                        "content": user_input
                    }
                    try:
                        await dg_agent.send(json.dumps(inject_message))
                    except Exception as e:
                        print(f"\n  [Error sending message: {e}]")
                        print("  YOU > ", end="", flush=True)

            except KeyboardInterrupt:
                print("\n\n  [Session interrupted by user]")
                session_active = False

            # Clean up background tasks
            keepalive_task.cancel()
            receiver_task.cancel()
            for task in (keepalive_task, receiver_task):
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    except Exception as e:
        print(f"\nConnection Error: {e}")
    finally:
        logger.log_event("Session ended")
        logger.close()
        print(f"\n  Conversation saved to: {logger.file_path}")
        print("  Session ended.\n")


def main() -> None:
    """
    Entry point for the CLI test script.
    Prints a banner and runs the async session.
    """
    print()
    print("=" * 60)
    print("  AI Receptionist - Text Test Mode")
    print("  Talk to Sarah via text (Deepgram Agent)")
    print("=" * 60)

    asyncio.run(run_text_session())


if __name__ == "__main__":
    main()
