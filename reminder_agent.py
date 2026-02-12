import os
import json
from dotenv import load_dotenv
from datetime import datetime
from crewai import Agent, Task, Crew

# Load environment variables
load_dotenv()

# --- 1. THE TOOL: Fetch data from the JSON file ---
def fetch_schedule_from_file():
    """Reads the schedule.json file and returns the list of sessions."""
    try:
        with open('schedule.json', 'r') as file:
            data = json.load(file)
            return data
    except FileNotFoundError:
        return "Error: schedule.json file not found."

def get_upcoming_sessions():
    """Filters the schedule to find sessions matching a specific criteria."""
    all_sessions = fetch_schedule_from_file()
    
    # In a real app, you would compare this to datetime.now()
    # For this demo, let's pretend we are looking for "Week 1" sessions
    upcoming = [s for s in all_sessions if s['week'] == 1]
    return upcoming

# --- 2. THE AGENT: The Punctual Coordinator ---
reminder_bot = Agent(
    role='Punctual Study Coordinator',
    goal='Analyze the class schedule and send reminders for upcoming sessions.',
    backstory='You are an organized assistant. You check the JSON schedule and alert students exactly when their expert is teaching.',
    allow_delegation=False,
    verbose=True
)

# --- 3. THE TASK: Direct instruction ---
# We inject the data directly into the task description
session_data = get_upcoming_sessions()

reminder_task = Task(
    description=f"""
    1. Analyze the following session data: {session_data}
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
    print("## FINAL REMINDERS ##")
    print("########################\n")
    print(result)