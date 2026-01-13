import asyncio
import websockets

# PASTE YOUR KEY HERE
API_KEY = "4ca1fdbf693e32c4194bdcb0679dcf6d8b21910c"

async def test_header_auth():
    clean_key = API_KEY.strip()
    
    print(f"Testing with Header Auth...")

    # 1. URL has NO key in it (Safe from stripping)
    url = "wss://api.deepgram.com/v1/listen?encoding=mulaw&sample_rate=8000&model=nova-2&smart_format=true"

    # 2. Key is inside the Headers (Secure Envelope)
    headers = {
        "Authorization": f"Token {clean_key}"
    }

    print("Attempting connection...")

    try:
        # 3. Connect using extra_headers
        async with websockets.connect(url, extra_headers=headers) as ws:
            print("SUCCESS! Connected to Deepgram using Headers.")
            print("(The URL-stripping issue is bypassed!)")
            await ws.close()
    except Exception as e:
        print("FAILED.")
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_header_auth())