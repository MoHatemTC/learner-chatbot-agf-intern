import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from pydantic import BaseModel
from crewai import Agent, Task, Crew

load_dotenv()


class SessionReminder(BaseModel):
    session_name: str
    start_time: str
    link: str


def fetch_upcoming_sessions():

    now = datetime.now()
    return [
        {"name": "GenAI Workshop", "time": (now + timedelta(minutes=15)).strftime("%H:%M"), "link": "https://zoom.us/j/123"}
    ]

# 3. Create Agent (The Personality)
reminder_bot = Agent(
    role='Punctual Study Coordinator',
    goal='Ensure learners never miss a live session by sending friendly reminders.',
    backstory='You are a helpful assistant that monitors schedules and provides clear, encouraging alerts.',
    allow_delegation=False,
    verbose=True
)

# 4. Define the Task
reminder_task = Task(
    description=f"Check the schedule: {fetch_upcoming_sessions()}. If a session starts soon, draft a WhatsApp/Slack reminder.",
    expected_output="A friendly reminder message containing the session name, time, and link.",
    agent=reminder_bot
)


if __name__ == "__main__":
    crew = Crew(agents=[reminder_bot], tasks=[reminder_task])
    result = crew.kickoff()
    print(result)