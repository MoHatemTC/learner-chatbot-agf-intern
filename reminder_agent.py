import os
from dotenv import load_dotenv
from supabase import create_client  
from crewai import Agent, Task, Crew

# Load environment variables (Make sure SUPABASE_URL and SUPABASE_KEY are in your .env)
load_dotenv()

# --- 1. THE NEW TOOL: Fetch data from Supabase ---
def fetch_schedule_from_db():
    """Reads the schedule table from Supabase and returns the list of sessions."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    
    # Initialize the Supabase client
    supabase = create_client(url, key)
    
    # Fetch all rows from the 'schedule' table you just created
    response = supabase.table("schedule").select("*").execute()
    
    # response.data contains the list of sessions
    return response.data

# --- 2. THE AGENT: The Punctual Coordinator ---
reminder_bot = Agent(
    role='Punctual Study Coordinator',
    goal='Analyze the class schedule from the database and send reminders.',
    backstory='You are an organized assistant. You check the LIVE database and alert students about their sessions.',
    allow_delegation=False,
    verbose=True
)

# --- 3. GET DATA & CREATE TASK ---
# Instead of opening a file, we call the database function
session_data = fetch_schedule_from_db()

reminder_task = Task(
    description=f"""
    1. Analyze the following live database data: {session_data}
    2. Identify the Program Name, Expert Name, and Time for each session.
    3. Write a friendly reminder message for the students. 
    4. Mention that this information comes from the 'US Embassy Weekly Schedule'.
    """,
    expected_output="A list of formatted reminder messages for WhatsApp/Slack.",
    agent=reminder_bot
)

# --- 4. EXECUTION ---
if __name__ == "__main__":
    crew = Crew(agents=[reminder_bot], tasks=[reminder_task])
    result = crew.kickoff()
    
    print("\n\n########################")
    print("## LIVE DATABASE REMINDERS ##")
    print("########################\n")
    print(result)