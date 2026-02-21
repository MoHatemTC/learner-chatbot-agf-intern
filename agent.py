import os
from dotenv import load_dotenv
from extractPDF import extract_schedule_data
from crewai import Agent, Task, Crew
from database_utils import save_to_supabase

load_dotenv()

openAI_Key = os.getenv("OPENAI_API_KEY")

if not os.getenv("OPENAI_API_KEY"):
    raise ValueError("OPENAI_API_KEY not found in .env file!")

import os
print(f"Current Directory: {os.getcwd()}")
print(f"Files in folder: {os.listdir('.')}")

target_file = 'US Embassy - Weekly Schedule.pdf'
if os.path.exists(target_file):
    print(f"SUCCESS: {target_file} was found!")
else:
    print(f"ERROR: {target_file} is NOT in this folder.")

schedule_data = extract_schedule_data._run("US Embassy - Weekly Schedule.pdf")
result = save_to_supabase(schedule_data)
print(result)

share_schedule_agent = Agent (
    role = 'Academic Success & Schedule Coordinator',
    goal = 'Deliver upcoming session times and deadlines from the Program Plan accurately.',
    backstory = '''You are a supportive assistant for Sprints AI learners. 
    You excel at turning complex PDF schedules into friendly, actionable reminders. 
    Your mission is to ensure no learner ever misses a live session or a deadline.''',
    tools=[extract_schedule_data],
    verbose = True,
    allow_delegation = False
)

share_schedule_task = Task(
    description="""
        1. Use the 'extract_schedule_data' tool.
        2. For the pdf_path argument, use EXACTLY: {pdf_path}
        3. Identify the upcoming Week's sessions, topics, and deadlines.
        4. Distinguish between 'Recorded Videos' and 'Live Sessions'.
    """,
    expected_output="""
        A friendly summary of the week's schedule including:
        - Topic name
        - Live session date/time
        - Task deadline
        - Expert name
    """,
    agent=share_schedule_agent, 
)

crew = Crew(
    agents=[share_schedule_agent],
    tasks= [share_schedule_task],
    verbose = True
)

result = crew.kickoff(inputs={'pdf_path': 'US Embassy - Weekly Schedule.pdf'})
print("CHATBOT RESPONSE")
print(result)

