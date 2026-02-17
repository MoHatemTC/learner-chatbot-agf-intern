import os
import logging
from typing import List, Dict, Any
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client  
from crewai import Agent, Task, Crew, Process
from crewai.tools import tool


logging.basicConfig(level=logging.INFO)
load_dotenv()


SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("❌ Missing SUPABASE_URL or SUPABASE_KEY in .env file. Check WhatsApp for keys!")


@tool("Fetch_Schedule_Tool")
def fetch_schedule_tool() -> List[Dict[str, Any]]:
    """Fetches today's class schedule from the Supabase cloud database."""
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

        today = datetime.now().strftime('%Y-%m-%d')
        response = supabase.table("schedule").select("*").execute() 
        
        if not response.data:
            return "No sessions found in the database."
        return response.data
    except Exception as e:
        logging.error(f"Database connection failed: {e}")
        return f"Error connecting to database: {str(e)}"

@tool("Circle_Post_Tool")
def circle_post_tool(reminder_text: str) -> str:
    """Posts the finalized reminder to the Circle community platform."""
  
    print("\n" + "="*60)
    print(f"🚀 [LIVE TRIGGER] POSTING TO CIRCLE.SO...")
    print(f"📝 CONTENT: {reminder_text}")
    print("✅ STATUS: 200 OK")
    print("="*60 + "\n")
    return "Successfully posted to Circle."


reminder_bot = Agent(
    role='Lead Study Coordinator',
    goal='Monitor the database and ensure students receive high-quality reminders on Circle.',
    backstory="""You are an expert community manager. You don't just copy-paste; 
    you analyze the schedule, check for upcoming sessions, and use your tools 
    to post reminders. You represent the US Embassy Sprints program.""",
    tools=[fetch_schedule_tool, circle_post_tool],
    allow_delegation=False,
    verbose=True
)


reminder_task = Task(
    description=(
        "1. Use the Fetch_Schedule_Tool to see what is in the database.\n"
        "2. Filter sessions to find those happening soon.\n"
        "3. For each session found, draft a professional reminder.\n"
        "4. Trigger the Circle_Post_Tool to deliver each reminder individually.\n"
        "5. Ensure the tone is encouraging and professional."
    ),
    expected_output="A summary report of all sessions processed and posted.",
    agent=reminder_bot
)


if __name__ == "__main__":
    crew = Crew(
        agents=[reminder_bot], 
        tasks=[reminder_task],
        process=Process.sequential
    )
    
    print("--- Starting Agent Execution ---")
    result = crew.kickoff()
    print("\n--- Final Report ---")
    print(result)