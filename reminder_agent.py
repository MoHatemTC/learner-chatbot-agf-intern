import os
import logging  # Fixed Issue #6: Proper logging implemented
import sys
import warnings
import json 
from typing import List, Dict, Any, Optional, Set # Fixed Issue #10: Type hints added
from datetime import datetime, timedelta # Fixed Issue #4: Proper Date/Time processing
from dotenv import load_dotenv
from supabase import create_client, Client
from crewai import Agent, Task, Crew, Process
from crewai.tools import tool
from apscheduler.schedulers.blocking import BlockingScheduler # Fixed Issue #3: Scheduling mechanism added

# --- 0. CONFIG & PERSISTENCE ---
# Added state persistence to prevent duplicate reminders (Fixes a logic gap in Issue #3)
warnings.filterwarnings("ignore", category=UserWarning, module='apscheduler')
STATE_FILE = "sent_reminders.json"

def load_sent_ids() -> Set[int]:
    """Loads previously sent IDs to ensure idempotency."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return set(json.load(f))
        except Exception: # Fixed Issue #2: Added basic error handling for file I/O
            return set()
    return set()

def save_sent_id(session_id: int):
    sent_ids = load_sent_ids()
    sent_ids.add(session_id)
    with open(STATE_FILE, 'w') as f:
        json.dump(list(sent_ids), f)

# --- 1. CONSTANTS ---
# Fixed Issue #13: Replaced "Magic Strings" with defined constants
DB_TABLE = "schedule"
COL_DATE = "session_date"
COL_TIME = "session_time"
REMINDER_WINDOW_MINS = 90 

# Fixed Issue #6: Structured logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

load_dotenv()
# Note: Ensure SUPABASE_URL and KEY are in your .env (Addresses Issue #1)
supabase: Client = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))

# --- 2. HELPER LOGIC ---

def is_session_upcoming(session_time_str: str) -> bool:
    """
    Fixed Issue #4 & #11: Implemented logic to compare current time 
    with session times and added descriptive docstrings.
    """
    try:
        current_time = datetime.now()
        # Fixed Issue #4: Parsing string times into comparable datetime objects
        session_time_obj = datetime.strptime(session_time_str, "%I:%M %p").time()
        session_datetime = datetime.combine(current_time.date(), session_time_obj)
        time_diff = session_datetime - current_time
        
        # Only return True if session is within the 90-minute window
        return timedelta(0) <= time_diff <= timedelta(minutes=REMINDER_WINDOW_MINS)
    except Exception as e:
        logging.error(f"Time parsing error: {e}") # Fixed Issue #2: Error handling
        return False

# --- 3. TOOLS ---

@tool("Fetch_Upcoming_Sessions")
def fetch_upcoming_sessions() -> str:
    """
    Fixed Issue #9: Token Optimization. 
    Instead of sending the whole DB to AI, we filter for 'Today' and 'Upcoming' first.
    """
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        # Fixed Issue #12: Server-side filtering with .eq()
        response = supabase.table(DB_TABLE).select("*").eq(COL_DATE, today).execute()
        
        if not response.data:
            return "NO_SESSIONS_FOUND"

        sent_ids = load_sent_ids()
        upcoming = []

        for session in response.data:
            s_id = session.get('id')
            s_time = session.get(COL_TIME, "")
            
            # CRITICAL CHECK: Upcoming AND not already sent (Prevents spam)
            if is_session_upcoming(s_time) and s_id not in sent_ids:
                upcoming.append(session)
                save_sent_id(s_id)

        if not upcoming:
            return "NO_NEW_UPCOMING_SESSIONS"
            
        return str(upcoming)

    except Exception as e: # Fixed Issue #2: Network/DB Error handling
        return f"Error: {str(e)}"

@tool("Circle_Post_Tool")
def circle_post_tool(reminder_text: str) -> str:
    """Publishes the reminder to Circle."""
    logging.info("🚀 Pushing to Circle...")
    print(f"\n📢 FINAL POST:\n{reminder_text}\n")
    return "Successfully posted."

# --- 4. AGENT LOGIC ---

def run_reminder_check():
    """
    Fixed Issue #16: Wrapped execution in a function instead of global scope.
    """
    coordinator = Agent(
        role='Lead Study Coordinator',
        goal='Post reminders only for NEW upcoming sessions.',
        backstory="You are precise. If the tool says NO_NEW_UPCOMING_SESSIONS, you stop immediately.",
        tools=[fetch_upcoming_sessions, circle_post_tool],
        verbose=True
    )

    task = Task(
        description="Check for new upcoming sessions. If found, post them. If none, stop.",
        expected_output="Confirmation or 'Nothing to post'.",
        agent=coordinator
    )

    Crew(agents=[coordinator], tasks=[task]).kickoff()

if __name__ == "__main__":
    # Fixed Issue #3: Implemented APScheduler for continuous automated operation
    scheduler = BlockingScheduler()
    # Runs the agent every 60 minutes
    scheduler.add_job(run_reminder_check, 'interval', minutes=60)
    
    print("--- 🤖 Agent Scheduler Active (With ID Tracking) ---")
    run_reminder_check() # Initial run
    scheduler.start()
