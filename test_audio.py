# 🚨 PASTE YOUR KEY HERE
API_KEY = "9c81094c8b7be49dfab223260f70dd865c4cffe0"

print("\n--- 🔍 KEY INSPECTION ---")
print(f"RAW STRING: {repr(API_KEY)}")
print(f"LENGTH:     {len(API_KEY)}")

if " " in API_KEY:
    print("❌ CRITICAL ERROR: Found a SPACE in your key!")
    print("   Fix: Delete the space inside the quotes.")
elif len(API_KEY) != 40:
    print(f"⚠️ WARNING: Standard keys are usually 40 chars. Yours is {len(API_KEY)}.")
else:
    print("✅ FORMAT CHECK: No spaces found. Length looks good.")

print("--------------------------")