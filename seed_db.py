# seed_db.py
from services.database import init_db, book_appointment
import sqlite3
import os

# 1. Initialize the table (in case it doesn't exist yet)
init_db()

print("\n--- 📝 INSERTING TEST DATA ---")

# 2. Command 1: Add Alice
book_appointment(
    first_name="Alice",
    last_name="Wonderland",
    appointment_date="2025-10-27",
    appointment_time="10:00",
    reason="Dental Checkup"
)

# 3. Command 2: Add Bob
book_appointment(
    first_name="Bob",
    last_name="Builder",
    appointment_date="2025-10-27",
    appointment_time="11:00",
    reason="Site Consultation"
)

# 4. Command 3: Add Charlie
book_appointment(
    first_name="Charlie",
    last_name="Chocolate",
    appointment_date="2025-10-28",
    appointment_time="14:00",
    reason="Factory Tour"
)

print("--- ✅ DONE ---")

# --- OPTIONAL: READ BACK DATA TO VERIFY ---
print("\n--- 🔍 CURRENT DATABASE CONTENTS ---")
# We connect manually here just to read and print the data for you
# (Make sure the path matches where your database.py thinks it is)
BASE_DIR = os.path.dirname(os.path.abspath("services/database.py"))
DB_PATH = r"E:\AI_and_Beyond\AI-Receptionist\ai-receptionist\services\appointments.db"

print("Base Dir:", os.path.abspath(BASE_DIR))
print("DB PATH:", os.path.abspath(DB_PATH))

try:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM appointments")
    rows = cursor.fetchall()
    
    if not rows:
        print("Database is empty.")
    else:
        print(f"{'ID':<5} {'Name':<20} {'Date':<12} {'Time':<8} {'Reason'}")
        print("-" * 60)
        for row in rows:
            # row structure: (id, first, last, reason, date, time, status)
            full_name = f"{row[1]} {row[2]}"
            print(f"{row[0]:<5} {full_name:<20} {row[4]:<12} {row[5]:<8} {row[3]}")

    conn.close()
except Exception as e:
    print(f"Could not read database: {e}")