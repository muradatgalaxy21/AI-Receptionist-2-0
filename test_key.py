import requests

# 🚨 PASTE YOUR KEY HERE
API_KEY = "4ca1fdbf693e32c4194bdcb0679dcf6d8b21910c"

def test_key_http():
    print("Testing Key with HTTP (Standard Web Request)...")
    
    url = "https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true"
    headers = {
        "Authorization": f"Token {API_KEY}",
        "Content-Type": "application/json"
    }
    
    # We will send a tiny bit of silence just to check auth
    try:
        # Using a public sample audio file from Deepgram
        response = requests.post(
            url, 
            headers=headers, 
            json={"url": "https://static.deepgram.com/examples/interview_speech-analytics.wav"}
        )
        
        if response.status_code == 200:
            print("✅ SUCCESS! Your API Key is VALID.")
            print("   (The issue is your Internet/Network blocking WebSockets)")
        else:
            print(f"❌ FAILURE. Status Code: {response.status_code}")
            print(f"   Message: {response.text}")
            
    except Exception as e:
        print(f"❌ Network Error: {e}")

if __name__ == "__main__":
    test_key_http()