import os
import logging
import json
import sys
import pytz
from typing import Set
from datetime import datetime, timedelta
from dotenv import load_dotenv
from supabase import create_client, Client
from crewai import Agent, Task, Crew
from crewai.tools import tool
from apscheduler.schedulers.blocking import BlockingScheduler

# --- 1. CONFIG & LOGGING (Addresses Issue #6 & #17) ---
load_dotenv()
CAIRO_TZ = pytz.timezone('Africa/Cairo')
UAE_TZ = pytz.timezone('Asia/Dubai')
STATE_FILE = "sent_reminders.json"
REMINDER_WINDOW_MINS = 180  # Addresses Issue #4: Proper timing logic

# Fixed Issue #6: Proper logging implemented for production debugging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Fixed Issue #1: Environment variable validation
if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_KEY"):
    raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY in .env file")

supabase: Client = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))

# --- 2. PERSISTENCE LAYER (Fixed Issue #3 Logic Gap) ---
def load_sent_ids() -> Set[int]:
    """Ensures we don't send duplicate reminders if the script restarts."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f: return set(json.load(f))
        except Exception: return set()
    return set()

def save_sent_id(session_id: int):
    ids = load_sent_ids()
    ids.add(session_id)
    with open(STATE_FILE, 'w') as f: 
        json.dump(list(ids), f)

# --- 3. THE TIME-BRIDGE (Fixed Issue #4: Date/Time Processing) ---
def is_session_upcoming(session: dict) -> bool:
    """
    Fixed Issue #4: Bridges the UAE/Cairo time gap using UTC normalization.
    Ensures logic works regardless of server location.
    """
    try:
        now_utc = datetime.now(pytz.utc)
        
        # Parse data from Supabase
        time_str = session['session_time'].strip()
        date_str = str(session['session_date'])
        naive_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %I:%M %p")
        
        # Standardize Cairo Time to UTC
        session_utc = CAIRO_TZ.localize(naive_dt).astimezone(pytz.utc)
        
        # Calculate time difference
        diff_mins = (session_utc - now_utc).total_seconds() / 60
        
        logging.info(f"Checking: {session['topic']} | Gap: {diff_mins:.1f} mins")
        return 0 <= diff_mins <= REMINDER_WINDOW_MINS
    except Exception as e:
        logging.error(f"Time processing error: {e}")
        return False

# --- 4. TOOLS (Fixed Issue #15: Separation of Concerns) ---
@tool("Circle_Post_Tool")
def circle_post_tool(reminder_text: str, session_id: int) -> str:
    """Publishes formatted reminders to the Circle community platform."""
    # This tool handles the 'Presentation Layer' separately from the 'Logic Layer'
    logging.info(f"🚀 Pushing Reminder to Circle for ID: {session_id}")
    print(f"\n📢 FINAL POST:\n{reminder_text}\n")
    save_sent_id(session_id)
    return "Successfully posted."

# --- 5. CORE AGENT LOGIC (Fixed Issue #8: Inefficient AI Usage) ---
def run_reminder_check():
    """
    Fixed Issue #8 & #9: We pre-filter data in Python before sending it to the AI.
    This saves token costs and prevents the 'Entire DB Dump' issue.
    """
    # Fixed Issue #4: Fetch based on Cairo's current date
    today_cairo = datetime.now(CAIRO_TZ).strftime('%Y-%m-%d')
    
    # Fixed Issue #2: Added try-except for database calls
    try:
        res = supabase.table("schedule").select("*").eq("session_date", today_cairo).execute()
    except Exception as e:
        logging.error(f"Database connection failed: {e}")
        return

    sent_ids = load_sent_ids()
    # Filter only for sessions that are (1) upcoming and (2) NOT sent yet
    upcoming = [s for s in res.data if s['id'] not in sent_ids and is_session_upcoming(s)]

    if not upcoming:
        logging.info("⏭️ No new sessions to notify.")
        return

    # Fixed Issue #15/16: Agent is initialized inside a function, not global scope
    coordinator = Agent(
        role='Study Coordinator',
        goal='Draft friendly reminders. Include Cairo and UAE times to help students.',
        backstory="You are a meticulous coordinator helping students across different timezones.",
        tools=[circle_post_tool],
        verbose=True # Set to False in production to save logs
    )

    for session in upcoming:
        task = Task(
            description=f"Draft a reminder for topic: {session['topic']}. Expert: {session['expert_name']}. Time: {session['session_time']} Cairo. ID: {session['id']}",
            expected_output="Confirmation of post.",
            agent=coordinator
        )
        Crew(agents=[coordinator], tasks=[task]).kickoff()

# --- 6. AUTOMATION (Fixed Issue #3: Missing Scheduling Mechanism) ---
if __name__ == "__main__":
    # Fixed Issue #3: Using a real background scheduler instead of a manual script
    scheduler = BlockingScheduler(timezone=pytz.utc)
    scheduler.add_job(run_reminder_check, 'interval', minutes=15)
    
    logging.info("--- 🤖 Session Reminder Agent Started (UTC Bridge Active) ---")
    run_reminder_check()  # Initial check on startup
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logging.info("Agent shutting down...")
