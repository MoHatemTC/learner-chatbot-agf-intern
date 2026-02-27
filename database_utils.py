import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

# IMPROVEMENT: Reusable client (Singleton-style)
def get_supabase():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    return create_client(url, key)

def save_to_supabase(items):
    supabase = get_supabase()

    if not items or isinstance(items, str):
        return "No valid data to save."

    try:
        formatted = [{
            "week": i.get("Week"), 
            "program": i.get("Program"),
            "module": i.get("Module"), 
            "topics": i.get("Topics"), 
            "tasks": i.get("Tasks")
        } for i in items]
        
        supabase.table("schedule_data").insert(formatted).execute()
        return f"Successfully saved {len(formatted)} rows!"
    except Exception as e:
        return f"Database Error: {e}"

# NEW: Fetching logic to satisfy 'filtering' requirements
def fetch_week_from_db(week_identifier):
    """Fetches specific context so the agent isn't overwhelmed."""
    supabase = get_supabase()
    try:
        response = supabase.table("schedule_data").select("*").ilike("week", f"%{week_identifier}%").execute()
        return response.data
    except Exception as e:
        print(f"Fetch Error: {e}")
        return []