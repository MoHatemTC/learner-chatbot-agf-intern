import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

def save_to_supabase(items):
    """Saves the list of extracted schedule items to the database"""
    if not items:
        return "No items to save."
        
    try:
        for item in items:
            supabase.table("schedule_data").insert({
                "week": item.get("Week"),
                "program": item.get("Program"),
                "module": item.get("Module"),
                "topics": item.get("Topics"),
                "tasks": item.get("Tasks")
            }).execute()
        return "Data successfully synced to Supabase!"
    except Exception as e:
        return f"Error saving to Supabase: {e}"