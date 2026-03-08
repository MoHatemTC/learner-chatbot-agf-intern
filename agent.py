import os
from dotenv import load_dotenv
from extractPDF import extract_logic
from database_utils import save_to_supabase, fetch_week_from_db
from crewai import Agent, Task, Crew

def main():
    load_dotenv()

    print("\n" + "="*45)
    print("🚀 ACADEMIC COORDINATOR SYSTEM")
    print("="*45)

    # --- PART 1: OPTIONAL EXTRACTION ---
    refresh_db = input("Do you want to extract and update Supabase from the PDF? (y/n): ").lower()
    if refresh_db == 'y':
        target_file = os.getenv('PDF_PATH')
        print(f"--- Extraction: Reading {target_file} ---")
        data = extract_logic(target_file)
        db_status = save_to_supabase(data)
        print(db_status)
    else:
        print("--- Skipping Extraction: Using existing Supabase data ---")

    # --- PART 2: COURSE & WEEK SELECTION ---
    print("\nSelect the Course:")
    print("1. Mobile Development")
    print("2. AI/ML")
    course_choice = input("Enter number (1 or 2): ")
    
    course_name = "Mobile Development" if course_choice == "1" else "AI/ML"

    print("-" * 30)
    # Based on your table, enter just the number (e.g., 3)
    selected_week = input(f"Enter week number for {course_name} (e.g., 3): ")
    
    print(f"🔍 Querying: course_id={course_choice} AND week_number='{selected_week}'")
    context_data = fetch_week_from_db(course_choice, selected_week)
    
    if not context_data:
        print(f"❌ Error: No data found for {course_name} Week {selected_week}.")
        return

    # --- PART 3: AGENT EXECUTION ---
    student_helper = Agent(
        role='Senior Academic Coordinator',
        goal=f'Summarize {selected_week} of {course_name} into a clear announcement.',
        backstory=(
            f'You are an expert at managing the {course_name} curriculum. '
            'You turn complex schedule rows into friendly student updates.'
        ),
        verbose=True
    )

    summary_task = Task(
        description=(
            f"Review the following data for {course_name}, Week {selected_week}: {context_data}. "
            "Use the fields: 'topic', 'session_date', 'session_time', 'expert_name', and 'zoom_link'. "
            "1. List the specific topics for this course clearly. "
            "2. Identify Live Session dates and times. "
            "3. Include the expert name and zoom link if they are available. "
            "Format this as a friendly Slack/Discord announcement with emojis."
        ),
        expected_output="A professional Markdown announcement with bold headings.",
        agent=student_helper
    )

    crew = Crew(agents=[student_helper], tasks=[summary_task])
    result = crew.kickoff()
    
    print("\n" + "*"*50)
    print(f"📢 FINAL OUTPUT FOR {course_name} - Week {selected_week}")
    print("*"*50 + "\n")
    print(result)

if __name__ == "__main__":
    main()
    