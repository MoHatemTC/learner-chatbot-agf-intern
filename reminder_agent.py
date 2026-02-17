import os
import logging
import sys
import time
from typing import List, Dict, Any
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client, Client
from crewai import Agent, Task, Crew, Process
from crewai.tools import tool
from apscheduler.schedulers.blocking import BlockingScheduler

# --- 1. SETUP LOGGING & CONFIG ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# --- 2. CRITICAL VALIDATION ---
if not SUPABASE_URL or not SUPABASE_KEY:
    logging.critical("❌ Missing SUPABASE_URL or SUPABASE_KEY. Exiting.")
    sys.exit(1)

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    logging.critical(f"❌ Failed to initialize Supabase client: {e}")
    sys.exit(1)


# --- 3. TOOLS WITH ERROR HANDLING ---

@tool("Fetch_Todays_Schedule")
def fetch_todays_schedule() -> str:
    """
    Fetches ONLY sessions scheduled for the current date from Supabase.
    """
    try:
        # Get today's date (YYYY-MM-DD) to filter the database
        today = datetime.now().strftime('%Y-%m-%d')
        logging.info(f"📅 Checking schedule for: {today}")

        # OPTIMIZED: Use .eq() to fetch only today's rows
        response = supabase.table("schedule").select("*").eq("live_session_date", today).execute()
        
        if not response.data:
            return "NO_SESSIONS_FOUND"
            
        return str(response.data)

    except Exception as e:
        logging.error(f"Database error: {e}")
        return f"Error fetching schedule: {str(e)}"

@tool("Circle_Post_Tool")
def circle_post_tool(reminder_text: str) -> str:
    """
    Posts the reminder to Circle.
    """
    try:
        # detailed logging instead of print
        logging.info("🚀 TRIGGERING CIRCLE POST...")
        print(f"\n📢 FINAL POST:\n{reminder_text}\n")
        return "Successfully posted to Circle."
    except Exception as e:
        logging.error(f"Post failed: {e}")
        return f"Error posting: {e}"


# --- 4. THE AGENT LOGIC ---

def run_reminder_check():
    """
    The function that the Scheduler runs automatically.
    """
    logging.info("⏰ Starting scheduled check...")

    reminder_bot = Agent(
        role='Lead Study Coordinator',
        goal='Analyze the daily schedule and post professional reminders ONLY if sessions exist.',
        backstory=(
            "You are the Voice of the US Embassy Sprints program. "
            "You are precise. If the tool returns 'NO_SESSIONS_FOUND', you do nothing and report 'No sessions today'. "
            "If sessions exist, you write a warm, professional reminder including the time and topic."
        ),
        tools=[fetch_todays_schedule, circle_post_tool],
        allow_delegation=False,
        verbose=True
    )

    reminder_task = Task(
        description=(
            f"Current Time: {datetime.now().strftime('%H:%M')}\n"
            "1. Call 'Fetch_Todays_Schedule'.\n"
            "2. IF the result is 'NO_SESSIONS_FOUND': STOP. Do not post anything.\n"
            "3. IF sessions are found: Draft a friendly reminder.\n"
            "4. Use 'Circle_Post_Tool' to publish it."
        ),
        expected_output="Confirmation that a post was sent OR that no sessions were found.",
        agent=reminder_bot
    )

    crew = Crew(
        agents=[reminder_bot],
        tasks=[reminder_task],
        process=Process.sequential
    )

    result = crew.kickoff()
    logging.info(f"✅ Check Complete. Result: {result}")


# --- 5. THE SCHEDULER (EXECUTION) ---

if __name__ == "__main__":
    scheduler = BlockingScheduler()
    
    # Run the check every 60 minutes
    scheduler.add_job(run_reminder_check, 'interval', minutes=60)
    
    print("--- 🤖 Agent Scheduler Started ---")
    print("Waiting for next scheduled run... (Press Ctrl+C to stop)")

    try:
        # Run once immediately for testing
        run_reminder_check()
        
        # Keep running forever
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n--- Scheduler Stopped ---")
