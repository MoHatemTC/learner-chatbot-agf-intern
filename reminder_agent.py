import os
import logging
import json
import sys
import pytz
import requests
from typing import Set, List, Dict, Optional
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client, Client
from crewai import Agent, Task, Crew, LLM
from crewai.tools import tool

# ---------------------------------------------------
# 0. LOAD ENVIRONMENT VARIABLES
# ---------------------------------------------------
load_dotenv()

# ---------------------------------------------------
# 1. CONFIG
# ---------------------------------------------------

CAIRO_TZ = pytz.timezone("Africa/Cairo")
UAE_TZ = pytz.timezone("Asia/Dubai")

# Pulling values from .env file
STATE_FILE = os.getenv("STATE_FILE", "sent_reminders.json")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Set the environment variable for CrewAI and OpenAI internal use
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# ---------------------------------------------------
# 2. PERSISTENCE
# ---------------------------------------------------

def load_sent_ids() -> Set[int]:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_sent_id(session_id: int):
    ids = load_sent_ids()
    ids.add(session_id)

    with open(STATE_FILE, "w") as f:
        json.dump(list(ids), f)


# ---------------------------------------------------
# 3. CIRCLE HELPER
# ---------------------------------------------------

def get_circle_member_token(email: str) -> Optional[str]:
    """Get a dynamic JWT token for a member using the Headless Auth Token."""
    auth_url = "https://app.circle.so/api/v1/headless/auth_token"
    headless_auth_token = os.getenv("CIRCLE_HEADLESS_AUTH_TOKEN")
    
    if not headless_auth_token:
        logging.error("CIRCLE_HEADLESS_AUTH_TOKEN not found in environment.")
        return None

    try:
        response = requests.post(
            auth_url,
            headers={
                "Authorization": f"Bearer {headless_auth_token}",
                "Content-Type": "application/json"
            },
            json={"email": email}
        )
        if response.status_code == 200:
            return response.json().get("access_token")
        else:
            logging.error(f"Circle Auth Error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        logging.error(f"Circle Auth Exception: {e}")
        return None

# ---------------------------------------------------
# 4. TOOL
# ---------------------------------------------------

@tool("Circle_Post_Tool")
def circle_post_tool(reminder_text: str, session_id: int) -> str:
    """Publishes formatted reminders to the Circle community platform."""

    logging.info(f"🚀 Pushing Reminder to Circle for ID: {session_id}")

    # Circle Configuration from .env
    room_uuid = os.getenv("CIRCLE_CHAT_ROOM_UUID")
    bot_email = os.getenv("CIRCLE_BOT_EMAIL")
    enabled = os.getenv("CIRCLE_ENABLED", "true").lower() == "true"

    if not enabled:
        logging.info("Circle posting is disabled.")
        return "Circle posting is disabled."

    if not room_uuid or not bot_email:
        logging.error("Missing Circle configuration (room_uuid or bot_email).")
        return "Missing Circle configuration."

    # Get dynamic token
    token = get_circle_member_token(bot_email)
    if not token:
        return "Failed to authenticate with Circle."

    url = f"https://app.circle.so/api/headless/v1/messages/{room_uuid}/chat_room_messages"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # Using the rich_text_body structure required by the Headless V1 API
    payload = {
        "rich_text_body": {
            "body": {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": reminder_text
                            }
                        ]
                    }
                ]
            },
            "circle_ios_fallback_text": reminder_text,
            "attachments": [],
            "inline_attachments": [],
            "sgids_to_object_map": {},
            "format": "chat",
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        # Status 201 or 202 are considered successful for message creation
        if response.status_code in [201, 202]:
            logging.info(f"✅ Successfully posted to Circle for session {session_id}")
            save_sent_id(session_id)
            return "Successfully posted to Circle."
        else:
            logging.error(f"❌ Failed to post to Circle: {response.status_code} - {response.text}")
            return f"Failed to post to Circle: {response.status_code}"
    except Exception as e:
        logging.error(f"❌ Error posting to Circle: {e}")
        return f"Error posting to Circle: {str(e)}"


# ---------------------------------------------------
# 5. CORE LOGIC
# ---------------------------------------------------

def run_reminder_pipeline():
    """Main function to fetch schedule and post reminders."""
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    now_cairo = datetime.now(CAIRO_TZ)
    today_cairo = now_cairo.strftime("%Y-%m-%d")

    logging.info(f"Checking Supabase for sessions on: {today_cairo}")

    try:
        res = supabase.table("schedule").select("*").eq("session_date", today_cairo).execute()
    except Exception as e:
        logging.error(f"DB Error: {e}")
        return

    sent_ids = load_sent_ids()
    upcoming = [s for s in res.data if s["id"] not in sent_ids]

    if not upcoming:
        logging.info("⏭️ No new sessions to process.")
        return

    crew_llm = LLM(model="gpt-4o-mini")

    coordinator = Agent(
        role="Strict Data Formatter",
        goal="Convert database rows to factual reminders. No filler.",
        backstory="Automated reminder pipeline for the Sprints internship program.",
        tools=[circle_post_tool],
        verbose=True,
        llm=crew_llm
    )

    for session in upcoming:
        session_id = session["id"]
        time_str = session["session_time"].strip()
        date_str = str(session["session_date"])

        # Convert to datetime for timezone adjustment
        naive_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %I:%M %p")
        session_cairo = CAIRO_TZ.localize(naive_dt)
        session_uae = session_cairo.astimezone(UAE_TZ)
        uae_time_str = session_uae.strftime("%I:%M %p")

        factual_data = (
            f"Topic: {session.get('topic')}\n"
            f"Expert: {session.get('expert_name')}\n"
            f"Cairo Time: {time_str}\n"
            f"UAE Time: {uae_time_str}\n"
            f"Zoom Link: {session.get('zoom_link')}"
        )

        task = Task(
            description=f"Draft and post a reminder using ONLY these facts for session {session_id}:\n{factual_data}",
            expected_output="Confirmation of the reminder being successfully sent to Circle.",
            agent=coordinator
        )

        crew = Crew(
            agents=[coordinator],
            tasks=[task]
        )

        # Kickoff the crew to process the session and use the tool
        crew.kickoff()

# ---------------------------------------------------
# 6. MAIN
# ---------------------------------------------------

if __name__ == "__main__":


    run_reminder_pipeline()
