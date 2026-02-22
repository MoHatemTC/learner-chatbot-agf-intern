import os
from dotenv import load_dotenv
from extractPDF import extract_logic, extract_schedule_data
from crewai import Agent, Task, Crew
from database_utils import save_to_supabase

def main():
    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY not found in .env file!")

    print(f"Current Directory: {os.getcwd()}")
    print(f"Files in folder: {os.listdir('.')}")

    target_file = 'US Embassy - Weekly Schedule.pdf'
    if not os.path.exists(target_file):
        print(f" ERROR: {target_file} not found.")
        return
    
    print("--- Starting Extraction & Sync ---")
    
    raw_data = extract_logic(target_file) 
    
    db_result = save_to_supabase(raw_data)
    print(db_result)

    share_schedule_agent = Agent(
        role='Academic Success & Schedule Coordinator',
        goal='Deliver upcoming session times and deadlines from the Program Plan accurately.',
        backstory='''You are a supportive assistant for Sprints AI learners. 
        You excel at turning complex PDF schedules into friendly, actionable reminders. 
        Your mission is to ensure no learner ever misses a live session or a deadline.''',
        verbose=True,
        allow_delegation=False
    )

    share_schedule_task = Task(
        description=f"""
            Review the following schedule data extracted from the PDF:
            {raw_data}

            1. Identify the upcoming Week's sessions, topics, and deadlines.
            2. Distinguish clearly between 'Recorded Videos' and 'Live Sessions'.
            3. Create a clean, easy-to-read summary.
        """,
        expected_output="""
            A friendly summary of the week's schedule including:
            - Topic name
            - Live session date/time
            - Task deadline
            - Expert name (if available)
        """,
        agent=share_schedule_agent, 
    )

    crew = Crew(
        agents=[share_schedule_agent],
        tasks=[share_schedule_task],
        verbose=True
    )

    print("\n--- Starting AI Summary ---")
    result = crew.kickoff()
    print("\nCHATBOT RESPONSE:\n", result)

if __name__ == "__main__":
    main()