# services/db_client.py
"""
Unified database client that connects to either local SQLite or remote Turso.
If TURSO_DATABASE_URL and TURSO_AUTH_TOKEN are set in environment variables,
it uses Turso (libsql-client). Otherwise, it falls back to a local SQLite database.
"""

import os
import sqlite3
from typing import List, Tuple, Any

class DatabaseClient:
    def __init__(self) -> None:
        self.db_url = os.getenv("TURSO_DATABASE_URL")
        self.auth_token = os.getenv("TURSO_AUTH_TOKEN")
        self.client = None

        # Clean whitespaces and strip quotes if any
        if self.db_url:
            self.db_url = self.db_url.strip().strip('"').strip("'")
            
            # Auto-convert regional Turso URLs to global URLs to bypass the WSServerHandshakeError / 400
            # handshake bug in the libsql-client Python library.
            if "turso.io" in self.db_url:
                proto = ""
                host = self.db_url
                if "://" in self.db_url:
                    proto, host = self.db_url.split("://", 1)
                    proto = proto + "://"
                
                if ".turso.io" in host:
                    parts = host.split(".")
                    if len(parts) > 2:
                        global_host = parts[0] + ".turso.io"
                        self.db_url = proto + global_host
                
        if self.auth_token:
            self.auth_token = self.auth_token.strip().strip('"').strip("'")

        self.use_turso = bool(self.db_url and self.auth_token)

        if self.use_turso:
            try:
                import libsql_client
                self.client = libsql_client.create_client_sync(
                    url=self.db_url,
                    auth_token=self.auth_token
                )
                print(f"[DB] Connected to Turso cloud database using URL: {self.db_url}")
            except ImportError:
                print("[DB] WARNING: TURSO_DATABASE_URL is set but 'libsql-client' is not installed. Falling back to local SQLite.")
                self.use_turso = False
                self._init_local_db()
        else:
            self._init_local_db()

        # Automatically initialize tables
        self.init_db()

    def _init_local_db(self) -> None:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(base_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        self.local_db_path = os.path.join(data_dir, "receptionist.db")
        print(f"[DB] Using local SQLite database at {self.local_db_path}")

    def _get_local_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.local_db_path)

    def init_db(self) -> None:
        """Initialize tables for calls and appointments."""
        # Create appointments table
        self.execute_write('''
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                reason TEXT NOT NULL,
                appointment_date TEXT NOT NULL,
                appointment_time TEXT NOT NULL,
                status TEXT DEFAULT 'confirmed',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Create calls table
        self.execute_write('''
            CREATE TABLE IF NOT EXISTS calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                caller_id TEXT NOT NULL,
                to_number TEXT,
                patient_name TEXT,
                call_duration REAL NOT NULL,
                intent TEXT NOT NULL,
                summary TEXT,
                transcript TEXT,
                status TEXT NOT NULL,
                estimated_value REAL DEFAULT 0.0,
                recording_url TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Alter table failsafes to add columns if database already existed
        try:
            self.execute_write("ALTER TABLE calls ADD COLUMN to_number TEXT")
        except Exception:
            pass
        try:
            self.execute_write("ALTER TABLE calls ADD COLUMN transcript TEXT")
        except Exception:
            pass

        print("[DB] Tables verified/initialized.")

    def execute(self, query: str, params: Tuple[Any, ...] = ()) -> List[Tuple[Any, ...]]:
        """Executes a SELECT query and returns a list of rows as tuples."""
        if self.use_turso and self.client:
            try:
                # libsql-client supports '?' placeholders and returns ResultSet
                result = self.client.execute(query, params)
                return [tuple(row) for row in result.rows]
            except Exception as e:
                print(f"[DB] Turso read error: {e}")
                # Fallback to local if Turso fails or behaves unexpectedly
                return []
        else:
            conn = self._get_local_connection()
            cursor = conn.cursor()
            try:
                cursor.execute(query, params)
                return cursor.fetchall()
            except Exception as e:
                print(f"[DB] Local SQLite read error: {e}")
                return []
            finally:
                conn.close()

    def execute_write(self, query: str, params: Tuple[Any, ...] = ()) -> bool:
        """Executes an INSERT, UPDATE, or DELETE query and commits it."""
        if self.use_turso and self.client:
            try:
                self.client.execute(query, params)
                return True
            except Exception as e:
                print(f"[DB] Turso write error: {e}")
                return False
        else:
            conn = self._get_local_connection()
            try:
                # Acquire an immediate lock to avoid concurrent write lock contention
                conn.execute("BEGIN IMMEDIATE")
                cursor = conn.cursor()
                cursor.execute(query, params)
                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                print(f"[DB] Local SQLite write error: {e}")
                return False
            finally:
                conn.close()

    def get_dashboard_stats(self) -> dict:
        """Fetch unified metrics and data for the web dashboard."""
        # 1. Total Calls
        res_total = self.execute("SELECT COUNT(*) FROM calls")
        total_calls = res_total[0][0] if res_total else 0

        # 2. Confirmed appointments
        res_conf = self.execute("SELECT COUNT(*) FROM calls WHERE status = 'Confirmed'")
        confirmed = res_conf[0][0] if res_conf else 0

        # 3. Revenue recovered
        res_rev = self.execute("SELECT SUM(estimated_value) FROM calls")
        revenue = res_rev[0][0] if res_rev and res_rev[0][0] is not None else 0.0

        # 4. Conversion rate
        conv_rate = (confirmed / total_calls * 100) if total_calls > 0 else 0.0

        # 5. Fetch call logs (limit to latest 100)
        res_calls = self.execute("""
            SELECT id, timestamp, caller_id, to_number, patient_name, call_duration, intent, summary, transcript, status, estimated_value, recording_url
            FROM calls
            ORDER BY timestamp DESC
            LIMIT 100
        """)
        calls_list = []
        for r in res_calls:
            calls_list.append({
                "id": r[0],
                "timestamp": r[1],
                "caller_id": r[2],
                "to_number": r[3],
                "patient_name": r[4],
                "call_duration": r[5],
                "intent": r[6],
                "summary": r[7],
                "transcript": r[8],
                "status": r[9],
                "estimated_value": r[10],
                "recording_url": r[11],
            })

        # 6. Chart: Daily Revenue (last 30 active dates)
        res_daily_rev = self.execute("""
            SELECT SUBSTR(timestamp, 1, 10) as call_date, SUM(estimated_value)
            FROM calls
            GROUP BY call_date
            ORDER BY call_date ASC
            LIMIT 30
        """)
        rev_labels = [r[0] for r in res_daily_rev]
        rev_values = [r[1] for r in res_daily_rev]

        # 7. Chart: Intent Distribution
        res_intent = self.execute("""
            SELECT intent, COUNT(*)
            FROM calls
            GROUP BY intent
            ORDER BY COUNT(*) DESC
        """)
        intent_labels = [r[0] for r in res_intent]
        intent_values = [r[1] for r in res_intent]

        return {
            "total_calls": total_calls,
            "appointments_confirmed": confirmed,
            "conversion_rate": conv_rate,
            "revenue_recovered": revenue,
            "calls": calls_list,
            "charts": {
                "revenue": {
                    "labels": rev_labels,
                    "values": rev_values,
                },
                "intent": {
                    "labels": intent_labels,
                    "values": intent_values,
                }
            }
        }

# Singleton instance for the application
db = DatabaseClient()
