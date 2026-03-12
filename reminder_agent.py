import uuid
import os
import logging
import json
import sys
import pytz
import asyncio
from pathlib import Path
from typing import Set, List, Dict, Optional, Deque, Tuple, Any
from datetime import datetime, timezone
from dotenv import load_dotenv
from supabase import create_client, Client
from crewai import Agent, Task, Crew, LLM
from crewai.tools import tool
from collections import deque


from circle_integration import CircleClient 

# ---------------------------------------------------
# 0. CONFIG & ENVIRONMENT
# ---------------------------------------------------

env_path = os.getenv("ENV_FILE_PATH", ".env.circle")
load_dotenv(env_path)

CAIRO_TZ = pytz.timezone("Africa/Cairo")
UAE_TZ = pytz.timezone("Asia/Dubai")

# Setup data directory for persistence
DEFAULT_DATA_DIR = os.path.join(os.getcwd(), "data")
DATA_DIR = os.getenv("DATA_DIR", DEFAULT_DATA_DIR)
Path(DATA_DIR).mkdir(parents=True, exist_ok=True)

STATE_FILE = os.path.join(DATA_DIR, "sent_reminders.json")
LAST_MESSAGE_ID_FILE = os.path.join(DATA_DIR, "last_message_id.json")
PROCESSED_IDS_FILE = os.path.join(DATA_DIR, "processed_ids.json")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# ---------------------------------------------------
# 1. PERSISTENCE HELPERS
# ---------------------------------------------------

def load_sent_ids() -> Set[int]:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return set(json.load(f))
        except Exception: return set()
    return set()

def save_sent_id(session_id: int):
    ids = load_sent_ids()
    ids.add(session_id)
    with open(STATE_FILE, "w") as f:
        json.dump(list(ids), f)

def load_processed_ids(max_items: int = 200) -> List[str]:
    """Load the list of already-responded message IDs (as strings), capped to last `max_items`."""
    if os.path.exists(PROCESSED_IDS_FILE):
        try:
            with open(PROCESSED_IDS_FILE, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    cleaned = [str(x) for x in data]
                    return cleaned[-max_items:]
        except Exception:
            return []
    return []

def save_processed_ids(ids: List[str], max_items: int = 200):
    """Persist the list of responded IDs (as strings), keeping only the last `max_items`."""
    trimmed = ids[-max_items:]
    with open(PROCESSED_IDS_FILE, "w") as f:
        json.dump(trimmed, f)

def load_last_processed_message_id() -> Optional[int]:
    if os.path.exists(LAST_MESSAGE_ID_FILE):
        try:
            with open(LAST_MESSAGE_ID_FILE, "r") as f:
                data = json.load(f)
                return data.get("last_processed_id")
        except Exception: return None
    return None

def load_last_processed_comment_id() -> Optional[int]:
    if os.path.exists(LAST_MESSAGE_ID_FILE):
        try:
            with open(LAST_MESSAGE_ID_FILE, "r") as f:
                data = json.load(f)
                return data.get("last_processed_comment_id")
        except Exception:
            return None
    return None

def save_last_processed_message_id(message_id: int):
    # Preserve any other fields in the state file (e.g., last_processed_comment_id)
    state: Dict[str, Any] = {}
    if os.path.exists(LAST_MESSAGE_ID_FILE):
        try:
            with open(LAST_MESSAGE_ID_FILE, "r") as f:
                state = json.load(f) or {}
        except Exception:
            state = {}
    state["last_processed_id"] = message_id
    with open(LAST_MESSAGE_ID_FILE, "w") as f:
        json.dump(state, f)

def save_last_processed_comment_id(comment_id: int):
    state: Dict[str, Any] = {}
    if os.path.exists(LAST_MESSAGE_ID_FILE):
        try:
            with open(LAST_MESSAGE_ID_FILE, "r") as f:
                state = json.load(f) or {}
        except Exception:
            state = {}
    state["last_processed_comment_id"] = comment_id
    with open(LAST_MESSAGE_ID_FILE, "w") as f:
        json.dump(state, f)

# ---------------------------------------------------
# 2. TOOLS
# ---------------------------------------------------

@tool("Circle_Post_Tool")
def circle_post_tool(reminder_text: str, session_id: int) -> str:
    """Publishes formatted reminders to Circle."""
    logging.info(f"🚀 Pushing Reminder to Circle for ID: {session_id}")
    bot_email = os.getenv("CIRCLE_BOT_EMAIL")
    room_uuid = os.getenv("CIRCLE_CHAT_ROOM_UUID")
    
    async def _post():
        client = CircleClient()
        try:
            await client.post_chat_message(member_email=bot_email, chat_room_uuid=room_uuid, text=reminder_text)
            return True
        except Exception as e:
            logging.error(f"❌ Circle API Error: {str(e)}")
            return False

    import nest_asyncio
    nest_asyncio.apply()
    success = asyncio.run(_post())
    
    if success:
        save_sent_id(session_id)
        return "Successfully posted."
    return "Failed to post."

# ---------------------------------------------------
# 3. INTERACTIVE LISTENER (UPGRADED)
# ---------------------------------------------------

async def poll_circle_messages():
    circle_client = CircleClient()
    bot_email = os.getenv("CIRCLE_BOT_EMAIL")
    chat_room_uuid = os.getenv("CIRCLE_CHAT_ROOM_UUID")
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # Local blacklist of messages we've already replied to (top-level + threaded), as strings.
    processed_ids_list: List[str] = load_processed_ids(max_items=200)
    responded_to_ids: Set[str] = set(processed_ids_list)
    recent_bot_message_ids: Deque[int] = deque(maxlen=50)
    
    await circle_client.get_member_token(bot_email)
    my_id = circle_client.token_cache.get(bot_email, {}).get("community_member_id")
    
    last_processed_id = load_last_processed_message_id()
    last_processed_comment_id = load_last_processed_comment_id()
    logging.info(f"🤖 Bot Listening in room {chat_room_uuid}...")

    def extract_text_from_rich_body(record: Dict[str, Any]) -> str:
        blocks = record.get("rich_text_body", {}).get("body", {}).get("content", [])
        return "".join(
            [
                i.get("text", "")
                for b in blocks
                for i in b.get("content", [])
                if i.get("type") == "text"
            ]
        )

    async def maybe_generate_response(clean_text: str) -> Optional[str]:
        response_text = None

        if clean_text == "hi":  # Exact match only
            response_text = (
                "Hello! I'm active and tracking the Sprints schedule. "
                "Type `!next` to see the upcoming session."
            )

        elif "!next" in clean_text:
            now_utc = datetime.now(timezone.utc)
            now_iso = now_utc.isoformat()
            print(f"[!next] now_utc={now_utc.isoformat()} now_iso={now_iso}")
            print("[!next] Querying Supabase: table=schedule filter=session_start >= now_utc order=session_start asc limit=1")
            try:
                res = (
                    supabase.table("schedule")
                    .select("*")
                    .gte("session_start", now_iso)
                    .order("session_start")
                    .limit(1)
                    .execute()
                )
                print(f"DEBUG: Found session: {res.data}")
                print(f"[!next] Supabase raw response data: {res.data}")
                try:
                    print(f"[!next] Supabase raw response count: {len(res.data) if res.data else 0}")
                except Exception:
                    pass
                if res.data:
                    s = res.data[0]
                    session_name = s.get("topic") or s.get("session_name") or s.get("name") or "Upcoming Session"
                    session_start_raw = s.get("session_start")

                    session_start_utc: Optional[datetime] = None
                    if isinstance(session_start_raw, str) and session_start_raw:
                        # Handle ISO strings with 'Z'
                        iso = session_start_raw.replace("Z", "+00:00")
                        try:
                            session_start_utc = datetime.fromisoformat(iso)
                        except ValueError:
                            session_start_utc = None
                    elif isinstance(session_start_raw, datetime):
                        session_start_utc = session_start_raw

                    if session_start_utc is not None and session_start_utc.tzinfo is None:
                        session_start_utc = session_start_utc.replace(tzinfo=timezone.utc)

                    if session_start_utc is None:
                        print(f"[!next] Could not parse session_start: {session_start_raw!r}")
                        response_text = (
                            "I couldn't find any upcoming sessions in the schedule. Please check back later!"
                        )
                    else:
                        cairo_dt = session_start_utc.astimezone(CAIRO_TZ)
                        uae_dt = session_start_utc.astimezone(UAE_TZ)

                        date_str = session_start_utc.strftime("%Y-%m-%d")
                        cairo_time = cairo_dt.strftime("%H:%M")
                        uae_time = uae_dt.strftime("%H:%M")

                        response_text = (
                            f"🗓️ **Next Session:** {session_name}\n"
                            f"📅 **Date (UTC):** {date_str}\n"
                            f"⏰ **Time:** {cairo_time} Cairo / {uae_time} UAE"
                        )
                else:
                    response_text = (
                        "I couldn't find any upcoming sessions in the schedule. Please check back later!"
                    )
            except Exception as e:
                print(f"[!next] Supabase query error: {e}")
                logging.error(f"Supabase error: {e}")
                response_text = "Error fetching the schedule."

        return response_text

    while True:
        try:
            resp = await circle_client.get_chat_room_messages(
                bot_email, chat_room_uuid, last_message_id=last_processed_id
            )
            messages = resp.get("records", [])
            
            for msg in sorted(messages, key=lambda x: x.get('id', 0)):
                msg_id = msg['id']
                msg_key = str(msg_id)

                # Hard guard: skip if we've already responded to this message ID
                if msg_key in responded_to_ids:
                    continue
                if last_processed_id is not None and msg_id <= last_processed_id: continue

                try:
                    sender_email = msg.get("community_member", {}).get("email")
                    sender_id = msg.get("community_member_id")
                    is_from_me = (sender_email == bot_email) or (sender_id == my_id)

                    if is_from_me:
                        recent_bot_message_ids.append(msg_id)
                    else:
                        clean_text = extract_text_from_rich_body(msg).strip().lower()
                        response_text = await maybe_generate_response(clean_text)

                        if response_text:
                            creation_uuid = str(uuid.uuid4())
                            logging.info(f"✨ Replying to '{clean_text}' (ID: {msg_id})")
                            sgid = (
                                await circle_client.get_member_attachable_sgid(sender_email)
                                if sender_email
                                else None
                            )

                            posted = await circle_client.post_chat_message(
                                bot_email,
                                chat_room_uuid,
                                text=response_text,
                                mention_sgid=sgid,
                                parent_message_id=msg_id,
                                creation_uuid=creation_uuid,
                            )
                            posted_id = (
                                posted.get("id")
                                or posted.get("record", {}).get("id")
                                or posted.get("message", {}).get("id")
                            )
                            if isinstance(posted_id, int):
                                recent_bot_message_ids.append(posted_id)
                            # Mark ONLY after successful POST reply
                            if msg_key not in responded_to_ids:
                                processed_ids_list.append(msg_key)
                                responded_to_ids.add(msg_key)
                                save_processed_ids(processed_ids_list)

                except Exception as e:
                    logging.error(f"Error processing message {msg_id}: {e}")

                finally:
                    # Always advance/save state so a single failing message doesn't retry forever
                    last_processed_id = msg_id
                    save_last_processed_message_id(msg_id)

            # Poll unread chat threads (threaded replies)
            try:
                thread_ids = await circle_client.get_unread_chat_threads(bot_email)
            except Exception as e:
                logging.error(f"Thread polling error (unread threads): {e}")
                thread_ids = []

            for thread_id in thread_ids:
                try:
                    thread = await circle_client.get_chat_thread_details(bot_email, thread_id)
                    if not thread:
                        continue

                    replies = thread.get("replies", []) or []
                    for r in sorted(replies, key=lambda x: x.get("id", 0)):
                        reply_id = r.get("id")
                        if not isinstance(reply_id, int):
                            continue
                        reply_key = str(reply_id)
                        # Hard guard for threaded replies
                        if reply_key in responded_to_ids:
                            continue
                        if last_processed_comment_id is not None and reply_id <= last_processed_comment_id:
                            continue

                        try:
                            sender_email = r.get("community_member", {}).get("email")
                            sender_id = r.get("community_member_id")
                            is_from_me = (sender_email == bot_email) or (sender_id == my_id)
                            if is_from_me:
                                continue

                            clean_text = extract_text_from_rich_body(r).strip().lower()
                            response_text = await maybe_generate_response(clean_text)
                            if response_text:
                                creation_uuid = str(uuid.uuid4())
                                logging.info(
                                    f"✨ Replying in thread to '{clean_text}' (Reply ID: {reply_id})"
                                )
                                sgid = (
                                    await circle_client.get_member_attachable_sgid(sender_email)
                                    if sender_email
                                    else None
                                )
                                posted = await circle_client.post_chat_message(
                                    bot_email,
                                    chat_room_uuid,
                                    text=response_text,
                                    mention_sgid=sgid,
                                    parent_message_id=reply_id,
                                    creation_uuid=creation_uuid,
                                )
                                posted_id = (
                                    posted.get("id")
                                    or posted.get("record", {}).get("id")
                                    or posted.get("message", {}).get("id")
                                )
                                if isinstance(posted_id, int):
                                    recent_bot_message_ids.append(posted_id)
                                # Mark ONLY after successful POST reply
                                if reply_key not in responded_to_ids:
                                    processed_ids_list.append(reply_key)
                                    responded_to_ids.add(reply_key)
                                    save_processed_ids(processed_ids_list)

                        except Exception as e:
                            logging.error(f"Error processing thread reply {reply_id}: {e}")

                        finally:
                            last_processed_comment_id = reply_id
                            save_last_processed_comment_id(reply_id)

                except Exception as e:
                    logging.error(f"Thread polling error for thread {thread_id}: {e}")

        except Exception as e:
            logging.error(f"Polling error: {e}")
            
        await asyncio.sleep(10)

# ---------------------------------------------------
# 4. MAIN
# ---------------------------------------------------

async def main_async():
    # Run the scheduled pipeline (reminders) then start the interactive listener
    # Note: run process_reminders() in a thread if it is not async
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, process_reminders)
    await poll_circle_messages()

def process_reminders():
    # (Your existing process_reminders logic goes here)
    pass

if __name__ == "__main__":
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logging.info("👋 Bot shutting down...")
        sys.exit(0)
