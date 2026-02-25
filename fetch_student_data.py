from dotenv import load_dotenv
from supabase import create_client
import os

def fetch_student_data(student_id, week_number):
    load_dotenv()
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    supabase = create_client(url, key)

    progress = supabase.table("student_progress") \
        .select("*") \
        .eq("Student_Id", student_id) \
        .eq("Week_Nu", week_number) \
        .execute()

    targets = supabase.table("weekly_targets") \
        .select("*") \
        .eq("Week_Nu", week_number) \
        .execute()

    if not progress.data or not targets.data:
        raise ValueError("Missing data")

    return {
        "progress": progress.data[0],
        "targets": targets.data[0]
    }
