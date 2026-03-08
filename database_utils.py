import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

def get_supabase():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    return create_client(url, key)

def fetch_week_from_db(course_id, week_num):
    """
    Fetches data using exact matches for course_id (int) and week_number (string).
    """
    supabase = get_supabase()
    try:
        # Based on your image: course_id is int4 and week_number is text
        query_course = int(course_id)
        query_week = str(week_num).strip()

        response = (
            supabase.table("schedule")
            .select("*")
            .eq("course_id", query_course) 
            .eq("week_number", query_week)
            .execute()
        )
        return response.data
    except Exception as e:
        print(f"Fetch Error: {e}")
        return []

def save_to_supabase(items):
    """Utility to sync PDF data. Note: Manually verify course_id in Supabase."""
    supabase = get_supabase()
    if not items or isinstance(items, str):
        return "No valid data to save."
    try:
        formatted = [{
            "week_number": str(i.get("Week")), 
            "topic": i.get("Topics"), 
            "course_id": 1, # Default placeholder
            "session_date": "N/A", 
            "session_time": "N/A",   
            "expert_name": "N/A", 
            "zoom_link": "N/A"       
        } for i in items]
        
        supabase.table("schedule").insert(formatted).execute()
        return f"Successfully saved {len(formatted)} rows!"
    except Exception as e:
        return f"Database Error: {e}"
