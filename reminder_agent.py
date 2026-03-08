import os
import logging
import json
import sys
import pytz
from typing import Set, List, Dict
from datetime import datetime, timedelta
from dotenv import load_dotenv
from supabase import create_client, Client
from crewai import Agent, Task, Crew
from crewai.tools import tool

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

# Use the provided keys
SUPABASE_URL = "https://dycbxblpynlleliludfx.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImR5Y2J4YmxweW5sbGVsaWx1ZGZ4Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MTE0MTM0OSwiZXhwIjoyMDg2NzE3MzQ5fQ.-bHnISZTqd7e_xox5ycUIhhBywZ5jODnZkm1Sll8upE"
# API key is already in environment
pass

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

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
        # Current time in UTC
        now_utc = datetime.now(pytz.utc)
        
        # Parse data from Supabase
        time_str = session['session_time'].strip()
        date_str = str(session['session_date'])
        
        # Handle format "2026-03-07 07:00 PM"
        naive_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %I:%M %p")
        
        # The session time in the DB is in Cairo time
        session_cairo = CAIRO_TZ.localize(naive_dt)
        session_utc = session_cairo.astimezone(pytz.utc)
        
        diff_mins = (session_utc - now_utc).total_seconds() / 60
        
        logging.info(f"Checking: {session['topic']} | Cairo Time: {time_str} | Gap: {diff_mins:.1f} mins")
        
        # Return true if session is within the next REMINDER_WINDOW_MINS
        return 0 <= diff_mins <= REMINDER_WINDOW_MINS
    except Exception as e:
        logging.error(f"Time processing error for session {session.get('id')}: {e}")
        return False

# --- 4. TOOLS ---
@tool("Circle_Post_Tool")
def circle_post_tool(reminder_text: str, session_id: int) -> str:
    """Publishes formatted reminders to the Circle community platform."""
    logging.info(f"🚀 Pushing Reminder to Circle for ID: {session_id}")
    # In a real scenario, this would call an API. Here we just print.
    print(f"\n📢 FINAL POST:\n{reminder_text}\n")
    save_sent_id(session_id)
    return "Successfully posted."

# --- 5. CORE AGENT LOGIC ---
def run_reminder_check() -> List[Dict]:
    """
    Checks for upcoming sessions and runs the agent.
    Returns a list of (input_data, agent_output) for RAGAS evaluation.
    """
    # Fix: Query based on Cairo's current date
    now_cairo = datetime.now(CAIRO_TZ)
    today_cairo = now_cairo.strftime('%Y-%m-%d')
    
    logging.info(f"Running check for Cairo Date: {today_cairo}")
    
    try:
        res = supabase.table("schedule").select("*").eq("session_date", today_cairo).execute()
    except Exception as e:
        logging.error(f"Database connection failed: {e}")
        return []

    sent_ids = load_sent_ids()
    upcoming = [s for s in res.data if s['id'] not in sent_ids and is_session_upcoming(s)]

    if not upcoming:
        logging.info("⏭️ No new sessions to notify.")
        return []

    evaluation_data = []

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
        memory=False
    )

    for session in upcoming:
        # Calculate UAE time for the prompt
        time_str = session['session_time'].strip()
        date_str = str(session['session_date'])
        naive_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %I:%M %p")
        session_cairo = CAIRO_TZ.localize(naive_dt)
        session_uae = session_cairo.astimezone(UAE_TZ)
        uae_time_str = session_uae.strftime("%I:%M %p")

        factual_data = (
            f"- Topic: {session.get('topic', 'N/A')}\n"
            f"- Expert: {session.get('expert_name', 'TBA')}\n"
            f"- Cairo Time: {time_str}\n"
            f"- UAE Time: {uae_time_str}\n"
            f"- Zoom Link: {session.get('zoom_link', 'Available in dashboard')}\n"
            f"- Session ID: {session['id']}"
        )

        task = Task(
            description=(
                f"FACTUAL DATA SET:\n{factual_data}\n\n"
                f"INSTRUCTIONS:\n"
                f"1. Draft a friendly reminder for the Circle community.\n"
                f"2. Explicitly state both Cairo and UAE times.\n"
                f"3. Use the Circle_Post_Tool to publish the final message.\n"
                f"4. DO NOT add any information or links not found in the FACTUAL DATA SET."
            ),
            expected_output="A confirmation message that the post was successfully published via the tool.",
            agent=coordinator
        )
        
        crew = Crew(agents=[coordinator], tasks=[task])
        result = crew.kickoff()
        
        evaluation_data.append({
            "session_id": session['id'],
            "context": factual_data,
            "question": "Draft a reminder for this session.",
            "answer": str(result)
        })
    
    return evaluation_data

if __name__ == "__main__":
    # For testing, we might want to clear the state file
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
    run_reminder_check()
