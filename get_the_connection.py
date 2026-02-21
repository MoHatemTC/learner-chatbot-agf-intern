from dotenv import load_dotenv
import os
from supabase import create_client, Client


# load environment variables from a .env file in the project root
load_dotenv()

url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_KEY")

# debug output to verify that variables were loaded
print("SUPABASE_URL", url)
print("SUPABASE_KEY", key)

if not url or not key:
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_KEY environment variables")

supabase: Client = create_client(url, key)



# query the table afterwards
result = supabase.table("StudentsInfo").select("*").execute()
print("select response:", result)