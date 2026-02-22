import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

if not url or not key:
    raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY in .env file!")

supabase: Client = create_client(url, key)

def save_to_supabase(items):
    """Saves the list of extracted schedule items to the database in bulk"""
    if not items or isinstance(items, str):
        return "No items to save or error in extraction."
        
    try:
        formatted_items = [
            {
                "week": item.get("Week"),
                "program": item.get("Program"),
                "module": item.get("Module"),
                "topics": item.get("Topics"),
                "tasks": item.get("Tasks")
            } for item in items
        ]
        
        supabase.table("schedule_data").insert(formatted_items).execute()
        return "Data successfully synced to Supabase!"
    except Exception as e:
        return f"Error saving to Supabase: {e}"