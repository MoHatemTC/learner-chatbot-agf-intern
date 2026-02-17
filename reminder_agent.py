import os
import logging
import sys
from datetime import datetime
from typing import List, Dict, Any
from dotenv import load_dotenv
from supabase import create_client, Client
from crewai import Agent, Task, Crew, Process
from crewai.tools import tool
from apscheduler.schedulers.blocking import BlockingScheduler

# --- 1. SETUP LOGGING ---
# Using professional logging with timestamps for monitoring
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

load_dotenv()

# --- 2. ENVIRONMENT VALIDATION ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    logging.critical("❌ Missing SUPABASE_URL or SUPABASE_KEY in .env file.")
    sys.exit(1)

# Initialize Supabase Client
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    logging.critical(f"❌ Failed to connect to Supabase: {e}")
    sys.exit(1)


# --- 3. UPDATED TOOLS ---

@tool("Fetch_Todays_Schedule")
def fetch_todays_schedule() -> str:
    """
    Queries Supabase for sessions occurring on the current calendar date.
    Uses 'session_date' column to match the SQL schema.
    """
    try:
        # Format today's date to match PostgreSQL DATE type (YYYY-MM-DD)
        today = datetime.now().strftime('%Y-%m-%d')
        logging.info(f"📅 Querying database for date: {today}")

        # Execute filtered query to minimize token usage and data transfer
        response = supabase.table("schedule").select("*").eq("session_date", today).execute()
        
        if not response.data:
            return "NO_SESSIONS_FOUND"
            
        return str(response.data)

    except Exception as e:
        logging.error(f"Database error: {e}")
        return f"Error: {str(e)}"

@tool("Circle_Post_Tool")
def circle_post_tool(reminder_text: str) -> str:
    """
    Simulates posting the finalized announcement to the Circle.so community.
    """
    try:
        logging.info("🚀 TRIGGERING CIRCLE POST...")
        print(f"\n📢 --- FINAL CIRCLE POST CONTENT ---\n{reminder_text}\n")
        return "Successfully posted to Circle."
    except Exception as e:
        logging.error(f"Post failed: {e}")
        return f"Error posting to platform: {e}"


# --- 4. AGENT & TASK DEFINITIONS ---

def run_reminder_check():
    """
    The core logic executed by the scheduler. 
    Encapsulated to allow for recurring execution.
    """
    logging.info("⏰ Starting scheduled reminder check...")

    # Agent: Lead Study Coordinator
    reminder_bot = Agent(
        role='Lead Study Coordinator',
        goal='Analyze the daily schedule and post professional reminders ONLY if sessions exist today.',
        backstory=(
            "You represent the US Embassy Sprints program. You are professional, warm, and precise. "
            "If the tool returns 'NO_SESSIONS_FOUND', you acknowledge it and stop. "
            "If data is returned, you draft a clear announcement with the topic, expert, and time."
        ),
        tools=[fetch_todays_schedule, circle_post_tool],
        allow_delegation=False,
        verbose=True
    )

    # Task: Processing and Delivery
    reminder_task = Task(
        description=(
            f"Current Date: {datetime.now().strftime('%Y-%m-%d')}\n"
            "1. Call 'Fetch_Todays_Schedule'.\n"
            "2. IF the result is 'NO_SESSIONS_FOUND', do not post anything.\n"
            "3. IF sessions exist, draft a friendly community reminder.\n"
            "4. Use 'Circle_Post_Tool' to finalize the announcement."
        ),
        expected_output="A confirmation of the post or a report that no sessions were found.",
        agent=reminder_bot
    )

    # Crew Execution
    crew = Crew(
        agents=[reminder_bot],
        tasks=[reminder_task],
        process=Process.sequential
    )

    result = crew.kickoff()
    logging.info(f"✅ Cycle Complete. Result: {result}")


# --- 5. BLOCKING SCHEDULER (AUTOMATION) ---

if __name__ == "__main__":
    scheduler = BlockingScheduler()
    
    # Schedule to run every hour (Adjust 'minutes' as needed)
    scheduler.add_job(run_reminder_check, 'interval', minutes=60)
    
    print("--- 🤖 Agent Scheduler Active ---")
    print("Monitoring database... (Press Ctrl+C to stop)")

    try:
        # Immediate first run for testing
        run_reminder_check()
        # Start the recurring loop
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n--- Scheduler Stopped Safely ---")
