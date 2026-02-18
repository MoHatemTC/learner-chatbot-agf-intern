import os
import logging
import sys
import warnings
import json # Added for state persistence
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timedelta
from dotenv import load_dotenv
from supabase import create_client, Client
from crewai import Agent, Task, Crew, Process
from crewai.tools import tool
from apscheduler.schedulers.blocking import BlockingScheduler

# --- 0. CONFIG & PERSISTENCE ---
warnings.filterwarnings("ignore", category=UserWarning, module='apscheduler')
STATE_FILE = "sent_reminders.json"

# Load previously sent IDs so we don't post them again if the script restarts
def load_sent_ids() -> Set[int]:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return set(json.load(f))
        except:
            return set()
    return set()

def save_sent_id(session_id: int):
    sent_ids = load_sent_ids()
    sent_ids.add(session_id)
    with open(STATE_FILE, 'w') as f:
        json.dump(list(sent_ids), f)

# --- 1. CONSTANTS ---
DB_TABLE = "schedule"
COL_DATE = "session_date"
COL_TIME = "session_time"
REMINDER_WINDOW_MINS = 90 

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

load_dotenv()
supabase: Client = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))

# --- 2. HELPER LOGIC ---

def is_session_upcoming(session_time_str: str) -> bool:
    try:
        current_time = datetime.now()
        session_time_obj = datetime.strptime(session_time_str, "%I:%M %p").time()
        session_datetime = datetime.combine(current_time.date(), session_time_obj)
        time_diff = session_datetime - current_time
        return timedelta(0) <= time_diff <= timedelta(minutes=REMINDER_WINDOW_MINS)
    except Exception as e:
        logging.error(f"Time parsing error: {e}")
        return False

# --- 3. TOOLS ---

@tool("Fetch_Upcoming_Sessions")
def fetch_upcoming_sessions() -> str:
    """
    Fetches sessions today that are starting soon AND haven't been posted yet.
    """
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        response = supabase.table(DB_TABLE).select("*").eq(COL_DATE, today).execute()
        
        if not response.data:
            return "NO_SESSIONS_FOUND"

        sent_ids = load_sent_ids()
        upcoming = []

        for session in response.data:
            s_id = session.get('id')
            s_time = session.get(COL_TIME, "")
            
            # CRITICAL CHECK: Upcoming AND not already sent
            if is_session_upcoming(s_time) and s_id not in sent_ids:
                upcoming.append(session)
                # Mark as sent immediately to prevent race conditions
                save_sent_id(s_id)

        if not upcoming:
            return "NO_NEW_UPCOMING_SESSIONS"
            
        return str(upcoming)

    except Exception as e:
        return f"Error: {str(e)}"

@tool("Circle_Post_Tool")
def circle_post_tool(reminder_text: str) -> str:
    """Publishes the reminder to Circle."""
    logging.info("🚀 Pushing to Circle...")
    print(f"\n📢 FINAL POST:\n{reminder_text}\n")
    return "Successfully posted."

# --- 4. AGENT LOGIC ---

def run_reminder_check():
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
    scheduler = BlockingScheduler()
    scheduler.add_job(run_reminder_check, 'interval', minutes=60)
    
    print("--- 🤖 Agent Scheduler Active (With ID Tracking) ---")
    run_reminder_check()
    scheduler.start()
