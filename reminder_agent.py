import os
import logging
import json
import sys
import pytz
from typing import Set
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client, Client
from crewai import Agent, Task, Crew
from crewai.tools import tool
from apscheduler.schedulers.blocking import BlockingScheduler

# --- 1. CONFIG & LOGGING ---
load_dotenv()
CAIRO_TZ = pytz.timezone('Africa/Cairo')
UAE_TZ = pytz.timezone('Asia/Dubai')
STATE_FILE = "sent_reminders.json"
REMINDER_WINDOW_MINS = 180 

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_KEY"):
    raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY in .env file")

supabase: Client = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))

# --- 2. PERSISTENCE LAYER ---
def load_sent_ids() -> Set[int]:
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

# --- 3. THE TIME-BRIDGE ---
def is_session_upcoming(session: dict) -> bool:
    try:
        now_utc = datetime.now(pytz.utc)
        
        # Parse data from Supabase
        time_str = session['session_time'].strip()
        date_str = str(session['session_date'])
        # Handle format "2026-03-07 07:00 PM"
        naive_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %I:%M %p")
        
        # Standardize Cairo Time to UTC for comparison
        session_utc = CAIRO_TZ.localize(naive_dt).astimezone(pytz.utc)
        
        diff_mins = (session_utc - now_utc).total_seconds() / 60
        
        logging.info(f"Checking: {session['topic']} | Gap: {diff_mins:.1f} mins")
        return 0 <= diff_mins <= REMINDER_WINDOW_MINS
    except Exception as e:
        logging.error(f"Time processing error: {e}")
        return False

# --- 4. TOOLS ---
@tool("Circle_Post_Tool")
def circle_post_tool(reminder_text: str, session_id: int) -> str:
    """Publishes formatted reminders to the Circle community platform."""
    logging.info(f"🚀 Pushing Reminder to Circle for ID: {session_id}")
    print(f"\n📢 FINAL POST:\n{reminder_text}\n")
    save_sent_id(session_id)
    return "Successfully posted."

# --- 5. CORE AGENT LOGIC (Refined for Faithfulness) ---
def run_reminder_check():
    today_cairo = datetime.now(CAIRO_TZ).strftime('%Y-%m-%d')
    
    try:
        res = supabase.table("schedule").select("*").eq("session_date", today_cairo).execute()
    except Exception as e:
        logging.error(f"Database connection failed: {e}")
        return

    sent_ids = load_sent_ids()
    upcoming = [s for s in res.data if s['id'] not in sent_ids and is_session_upcoming(s)]

    if not upcoming:
        logging.info("⏭️ No new sessions to notify.")
        return

    # IMPROVED: Strict persona to minimize hallucinations
    coordinator = Agent(
        role='Study Coordinator',
        goal='Draft accurate reminders using ONLY provided data.',
        backstory=(
            "You are a meticulous coordinator for an Egyptian university program. "
            "Your primary directive is accuracy. You NEVER invent links, names, or "
            "session details. If a piece of data is missing, you do not guess. "
            "You are an expert at converting Cairo time to UAE time (+2 hours)."
        ),
        tools=[circle_post_tool],
        verbose=True,
        allow_delegation=False,
        memory=False # Keep it stateless for higher reliability
    )

    for session in upcoming:
        # IMPROVED: Structured data input to separate facts from instructions
        task = Task(
            description=(
                f"FACTUAL DATA SET:\n"
                f"- Topic: {session.get('topic', 'N/A')}\n"
                f"- Expert: {session.get('expert_name', 'TBA')}\n"
                f"- Cairo Time: {session.get('session_time', 'N/A')}\n"
                f"- Zoom Link: {session.get('zoom_link', 'Available in dashboard')}\n"
                f"- Session ID: {session['id']}\n\n"
                f"INSTRUCTIONS:\n"
                f"1. Draft a friendly reminder for the Circle community.\n"
                f"2. Explicitly state both Cairo and UAE times.\n"
                f"3. Use the Circle_Post_Tool to publish the final message.\n"
                f"4. DO NOT add any information or links not found in the FACTUAL DATA SET."
            ),
            expected_output="A confirmation message that the post was successfully published via the tool.",
            agent=coordinator
        )
        
        Crew(agents=[coordinator], tasks=[task]).kickoff()

# --- 6. AUTOMATION ---
if __name__ == "__main__":
    scheduler = BlockingScheduler(timezone=pytz.utc)
    scheduler.add_job(run_reminder_check, 'interval', minutes=15)
    
    logging.info("--- 🤖 Session Reminder Agent Started (UTC Bridge Active) ---")
    run_reminder_check() 
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logging.info("Agent shutting down...")
