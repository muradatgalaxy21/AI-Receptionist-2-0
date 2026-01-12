import requests

# 🚨 WE ARE TESTING YOUR SPECIFIC KEY 🚨
KEY_TO_TEST = "9d50360b68c8ac3cdefa81dbf0d91eb7421d4d76"

def check_key_status():
    print(f"🕵️ CHECKING KEY: {KEY_TO_TEST[:5]}...")
    
    headers = {
        "Authorization": f"Token {KEY_TO_TEST}",
        "Content-Type": "application/json"
    }
    
    try:
        # Ask Deepgram for Project Details
        response = requests.get("https://api.deepgram.com/v1/projects", headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            print("\n✅ SUCCESS! The key is VALID.")
            print("------------------------------------------------")
            # Loop through projects (usually just one)
            for project in data.get('projects', []):
                p_id = project['project_id']
                p_name = project['name']
                print(f"📂 Linked Project Name: '{p_name}'")
                print(f"🆔 Linked Project ID:   {p_id}")
            print("------------------------------------------------")
            print("👉 ACTION: Go to Deepgram Console > Billing.")
            print("   Does the project ID in your Browser URL match the ID above?")
            
        elif response.status_code == 401:
            print("\n❌ FAILURE (401): Unauthorized.")
            print("   This key is completely invalid or deleted.")
            
        else:
            print(f"\n⚠️ ERROR: Status Code {response.status_code}")
            print(response.text)

    except Exception as e:
        print(f"Error: {e}")

check_key_status()