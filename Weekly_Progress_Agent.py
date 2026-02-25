from crewai import Agent, Task, Crew, Process
from dotenv import load_dotenv
from compute_status import compute_status
from fetch_student_data import fetch_student_data
import os

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    raise ValueError("OPENAI_API_KEY not found in environment variables.")

progress_agent = Agent(
    role="Learner Success Communication Specialist",
    goal="""
    Generate supportive weekly progress messages for learners
    based on ONLY their sprint performance status.
    """,
    backstory="""
    You are a learner success AI assistant.
    You receive structured learner performance data.
    You never calculate numbers.
    You never fetch data.
    You only generate motivating and actionable messages.
    """,
    verbose=True
)


progress_task = Task(
    description="""
    You are given structured learner progress data.
    ONLY use the provided data to generate a personalized message.

    If status = "behind":
    
        - Mention missing_items clearly.
        - Mention performance_issues if any.
        - Provide motivating and actionable guidance.
        - Keep message under 150 words.
        - Tone must be supportive and constructive.

    If status = "on_track":
        - Provide short congratulatory message.
        - Encourage continued consistency.

    Do not calculate anything.
    Do not change status.
    """,
    expected_output="""
    {
        "status": "on_track" | "behind",
        "message": "Personalized message"
    }
    """,
    agent=progress_agent
)
def run_progress_check(student_id, week_number):

    # 1️⃣ Fetch
    raw_data = fetch_student_data(student_id, week_number) 

    # 2️⃣ Compute
    structured_data = compute_status(raw_data)

    # 3️⃣ Run Crew
    crew = Crew(
        agents=[progress_agent],
        tasks=[progress_task],
        process=Process.sequential
    )

    result = crew.kickoff(inputs=structured_data)

    return result

print(run_progress_check("002",1))


