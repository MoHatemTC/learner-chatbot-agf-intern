import os
from dotenv import load_dotenv
from extractPDF import extract_logic
from database_utils import save_to_supabase, fetch_week_from_db
from crewai import Agent, Task, Crew

def main():
    load_dotenv()
    target_file = os.getenv('PDF_PATH')

    print("--- 1. Data Pipeline: Extracting & Syncing ---")
    data = extract_logic(target_file)
    db_status = save_to_supabase(data)
    print(db_status)

    # 2. Filtering Logic (Raghad's Requirement: Focus & Clarity)
    print("\n" + "="*40)
    selected_week = input("Enter the week to summarize (e.g., Week 1): ")
    context_data = fetch_week_from_db(selected_week)
    
    if not context_data:
        print(f"Warning: No data found in Supabase for {selected_week}.")
        return

    student_helper = Agent(
        role='Senior Academic Coordinator',
        goal=f'Summarize {selected_week} into a clear, student-friendly announcement.',
        backstory=(
            'You are an expert at extracting the most important details from '
            'complex schedules. You ensure students know exactly what to watch and what to submit.'
        ),
        verbose=True,
        memory=True 
    )

    summary_task = Task(
        description=(
            f"Review the following data for {selected_week}: {context_data}. "
            "Note: Some topics might be merged into the 'program' or 'module' text. "
            "1. Create a bulleted list of topics for each program (extract them carefully). "
            "2. List the specific Live Session dates and times clearly. "
            "3. Identify any tasks or 'Calculate/Check' exercises mentioned. "
            "Format this as a friendly 'Next Steps' announcement for a student Slack/Discord channel."
        ),
        expected_output="A professional Markdown announcement with bold headings, emojis, and clear bullet points.",
        agent=student_helper
    )

    crew = Crew(agents=[student_helper],
                 tasks=[summary_task])
    result = crew.kickoff()
    
    print("\n" + "*"*50)
    print(f"FINAL OUTPUT FOR {selected_week}")
    print("*"*50 + "\n")
    print(result)

if __name__ == "__main__":
    main()