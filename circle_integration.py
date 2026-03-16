import httpx
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone
import os
from dotenv import load_dotenv
import aiohttp
import re
from typing import List   
from pathlib import Path
import jwt
import requests
import asyncio

load_dotenv()

logging.basicConfig(
    filename=f"circle_api_debug_{datetime.now().strftime('%Y%m%d')}.txt",
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Instance-specific data directory
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
Path(DATA_DIR).mkdir(parents=True, exist_ok=True)

CHAT_MEMBERS_FILE = os.path.join(DATA_DIR, "chat_members.json")
CHAT_MEMBERS_SGID_FILE = os.path.join(DATA_DIR, "chat_members_SGID.json")


logger = logging.getLogger(__name__)

class CircleClient:
    def __init__(self):
        self.auth_url = "https://app.circle.so/api/v1/headless/auth_token"
        self.member_api_base = "https://app.circle.so/api/headless/v1"
        self.admin_v2_api_base = "https://app.circle.so/api/admin/v2"
        self.headless_auth_token = os.getenv("CIRCLE_HEADLESS_AUTH_TOKEN")
        self.admin_v2_token = os.getenv("CIRCLE_ADMIN_V2_TOKEN")
        self.community_id = os.getenv("CIRCLE_COMMUNITY_ID")
        self.token_cache = {}  # Cache: {email: {token, expires_at, refresh_token}}
    

    def _is_token_expired(self, email: str) -> bool:
        """Check if cached token is expired or will expire soon"""
        if email not in self.token_cache:
            return True
        
        expires_at = self.token_cache[email].get("expires_at")
        if not expires_at:
            return True
        
        # Refresh if expires in less than 5 minutes
        return datetime.fromisoformat(expires_at.replace('Z', '+00:00')) < datetime.now(timezone.utc) + timedelta(minutes=5)
    
    async def get_member_token(self, email: str) -> str:
        """Get or refresh JWT token for a member"""
        if not self._is_token_expired(email):
            return self.token_cache[email]["access_token"]
        
        # If we have a refresh token, try to use it
        if email in self.token_cache and self.token_cache[email].get("refresh_token"):
            try:
                return await self.refresh_token(email)
            except Exception as e:
                logger.warning(f"Token refresh failed for {email}, getting new token: {e}")
        
        # Get new token
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    self.auth_url,
                    headers={
                        "Authorization": f"Bearer {self.headless_auth_token}",
                        "Content-Type": "application/json"
                    },
                    json={"email": email}
                )
                response.raise_for_status()
                data = response.json()
                
                # Cache the token
                self.token_cache[email] = {
                    "access_token": data["access_token"],
                    "refresh_token": data.get("refresh_token"),
                    "expires_at": data.get("access_token_expires_at"),
                    "community_member_id": data.get("community_member_id")
                }
                logger.debug(f"✅ Cached token for {email}, member_id: {data.get('community_member_id')}")

                return data["access_token"]
            except httpx.HTTPError as e:
                logger.error(f"Failed to get token for {email}: {e}")
                raise
    
    async def refresh_token(self, email: str) -> str:
        """Refresh an expired token"""
        if email not in self.token_cache or not self.token_cache[email].get("refresh_token"):
            raise ValueError("No refresh token available")
        
        refresh_token = self.token_cache[email]["refresh_token"]
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    f"{self.auth_url}/refresh",
                    headers={
                        "Authorization": f"Bearer {self.headless_auth_token}",
                        "Content-Type": "application/json"
                    },
                    json={"refresh_token": refresh_token}
                )
                response.raise_for_status()
                data = response.json()
                
                # Update cache
                self.token_cache[email].update({
                    "access_token": data["access_token"],
                    "refresh_token": data.get("refresh_token"),
                    "expires_at": data.get("access_token_expires_at")
                })
                
                return data["access_token"]
            except httpx.HTTPError as e:
                logger.error(f"Failed to refresh token for {email}: {e}")
                raise

    
    
    # ---------------- Chat Room Integration ----------------

    async def get_unread_chat_threads(self, member_email: str) -> List[int]:
        """
        Fetch unread chat thread IDs for the given member.
        Uses the authenticated headless member token.
        """
        token = await self.get_member_token(member_email)
        url = f"{self.member_api_base}/chat_threads/unread_chat_threads"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.get(
                    url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                )
                r.raise_for_status()
                data = r.json()
                thread_ids = data.get("chat_thread_ids", [])
                logger.info(f"📬 Found {len(thread_ids)} unread chat threads.")
                return thread_ids
        except httpx.HTTPError as e:
            logger.error(f"❌ Failed to fetch unread chat threads: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ Unexpected error fetching unread chat threads: {e}")
            return []

    async def get_chat_thread_details(self, member_email: str, thread_id: int) -> Optional[Dict]:
        """
        Fetch the parent message and all replies in a specific chat thread.
        Returns full thread data.
        """
        token = await self.get_member_token(member_email)
        url = f"{self.member_api_base}/chat_threads/{thread_id}"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.get(
                    url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                )
                r.raise_for_status()
                thread_data = r.json()
                logger.info(f"💬 Retrieved thread {thread_id} with {len(thread_data.get('replies', []))} replies.")
                return thread_data
        except httpx.HTTPError as e:
            logger.error(f"❌ Failed to fetch thread {thread_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Unexpected error fetching thread {thread_id}: {e}")
            return None

    
    async def get_chat_room_participants(self, member_email: str, chat_room_uuid: str,
                                         page: int = 1, per_page: int = 50) -> Dict:
        """Fetch all participants in a Circle chat room and save them locally."""
        token = await self.get_member_token(member_email)
        url = f"{self.member_api_base}/messages/{chat_room_uuid}/chat_room_participants"
        all_records = []
        has_next = True
        while has_next:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.get(
                    url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    params={"page": page, "per_page": per_page},
                )
                r.raise_for_status()
                data = r.json()
                all_records.extend(data.get("records", []))
                has_next = data.get("has_next_page", False)
                page += 1

        with open(CHAT_MEMBERS_FILE, "w") as f:
            json.dump(all_records, f, indent=2)
        logger.info(f"✅ Saved {len(all_records)} chat room participants.")
        return {"records": all_records}

    
    async def get_chat_room_messages(self, member_email: str, chat_room_uuid: str,
                                     last_message_id: Optional[int] = None,
                                     next_per_page: int = 20) -> Dict:
        """Fetch chat messages newer than a given ID."""
        token = await self.get_member_token(member_email)
        url = f"{self.member_api_base}/messages/{chat_room_uuid}/chat_room_messages"
        params = {"next_per_page": next_per_page}
        if last_message_id:
            params["id"] = last_message_id
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                params=params,
            )
            r.raise_for_status()
            return r.json()
    
    async def get_member_attachable_sgid(self, email: str):
        """
        Retrieves and caches the SGID (Signed Global ID) for a Circle member
        so it can be reused for mentions in chat messages.
        """
        cache_file = CHAT_MEMBERS_SGID_FILE
        cache = {}

        # ✅ Load cache from disk (if exists)
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cache = json.load(f)
            except json.JSONDecodeError:
                logging.warning("⚠️ Corrupted chat_members_SGID.json — resetting cache.")
                cache = {}

        # ✅ Return cached SGID if already available
        if email in cache and "sgid" in cache[email]:
            logging.info(f"🔁 Using cached SGID for {email}: {cache[email]['sgid']}")
            return cache[email]["sgid"]

        # ✅ Otherwise, fetch via Admin API
        url = f"{self.admin_v2_api_base}/advanced_search?query={email}&search_type=members"
        headers = {"Authorization": f"Bearer {self.admin_v2_token}"}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    text = await response.text()
                    logging.error(f"❌ Failed to fetch SGID for {email}: {response.status} - {text}")
                    return None

                data = await response.json()

        if data.get("records"):
            member = data["records"][0]
            sgid = member.get("sgid")
            logging.info(f"🔍 Found member record for {email}: {member}")

            if sgid:
                # ✅ Save to cache
                cache[email] = member
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(cache, f, indent=2)

                logging.info(f"✅ Saved SGID for {email}: {sgid}")
                return sgid
            else:
                logging.warning(f"⚠️ No SGID found for member {email}")
                return None
        else:
            logging.warning(f"⚠️ Member not found in search for {email}")
            return None

        
    async def post_chat_message(
    self,
    member_email: str,
    chat_room_uuid: str,
    text: str,
    mention_sgid: Optional[str] = None,
    parent_message_id: Optional[int] = None,
    ) -> Dict:
        """
        Post a message in the Circle chat room, optionally mentioning a user using the mention_sgid (to get the SGID use the get_member_attachable_sgid method first).
        The mention_sgid should be the full attachable_sgid (long base64 string).
        """
        token = await self.get_member_token(member_email)
        url = f"{self.member_api_base}/messages/{chat_room_uuid}/chat_room_messages"
         # --- Markdown to Circle TipTap converter ---
       
        def markdown_to_tiptap(text: str):
            """Convert Markdown (bold, links, lists, line breaks) to TipTap JSON content."""
            content_blocks = []
            lines = text.split("\n")

            for line in lines:
                line = line.strip()
                if not line:
                    content_blocks.append({"type": "paragraph"})
                    continue

                # Match list items like '1. text' or '- text'
                list_match = re.match(r"^(\d+\.|-)\s+(.*)", line)
                if list_match:
                    text_part = list_match.group(2)
                else:
                    text_part = line

                # Convert links [**Label**](URL) or [Label](URL)
                link_pattern = r"\[([^\]]+)\]\(([^)]+)\)"
                matches = list(re.finditer(link_pattern, text_part))
                
                if matches:
                    segments = []
                    last_idx = 0
                    for m in matches:
                        if m.start() > last_idx:
                            segments.append({
                            "type": "text",
                            "text": text_part[last_idx:m.start()]
                        })
                        label = m.group(1).replace("**", "")
                        url = m.group(2)
                        segments.append({
                            "type": "text",
                            "text": label,
                            "marks": [{"type": "link", "attrs": {"href": url, "target": "_blank"}}]
                        })
                        last_idx = m.end()
                    if last_idx < len(text_part):
                        segments.append({"type": "text", "text": text_part[last_idx:]})
                    content_blocks.append({"type": "paragraph", "content": segments})
                    continue

                # Convert **bold**
                bold_segments = []
                while "**" in text_part:
                    parts = text_part.split("**", 2)
                    if len(parts) == 3:
                        before, bold, rest = parts
                        if before:
                            bold_segments.append({"type": "text", "text": before})
                        bold_segments.append({"type": "text", "text": bold, "marks": [{"type": "bold"}]})
                        text_part = rest
                    else:
                        break
                if text_part:
                    bold_segments.append({"type": "text", "text": text_part})

                content_blocks.append({"type": "paragraph", "content": bold_segments})

            return content_blocks

        # --- Build mention block if SGID provided ---
        mention_block = []
        sgids_to_object_map = {}

        if mention_sgid:
            mention_block = [
                {
                    "type": "mention",
                    "attrs": {"sgid": mention_sgid},
                    "circle_ios_fallback_text": "@user"
                },
                {"type": "text", "text": " "}
            ]
            sgids_to_object_map[mention_sgid] = {"type": "CommunityMember"}

        formatted_blocks = markdown_to_tiptap(text)
        
        # --- Build full message body ---
        body = {
            "rich_text_body": {
                "body": {
                    "type": "doc",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": mention_block + [{"type": "text", "text": " "}]
                        }
                    ]
                    + formatted_blocks 
                },
                "circle_ios_fallback_text": text,
                "attachments": [],
                "inline_attachments": [],
                "sgids_to_object_map": sgids_to_object_map,
                "format": "chat",
            },
            "parent_message_id": parent_message_id
        }

        if parent_message_id is None:
            del body["parent_message_id"]

        # --- Send request ---
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=body,
            )

            # logger.info(f"💬 POST Body Sent:\n{json.dumps(body, indent=2)}")
            logger.info(f"💬 Circle Response [{r.status_code}]: {r.text}")
            r.raise_for_status()
            logger.info(f"✅ Sent message to chat room {chat_room_uuid}")
            return r.json()


# Helper Functions
def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# --- CREWAI AGENTS & TASKS ---
from crewai import Agent, Task, Crew, Process

def get_course_coordinator_crew():
    """Defines the AI agent responsible for curriculum and schedule lookups."""
    coordinator = Agent(
        role="Course Coordinator",
        goal="Provide accurate schedule details, topics, and session links for {course} on week {week}",
        backstory="""You are the lead coordinator for Sprints. You have the full curriculum 
        for AI/ML and Mobile Development. You provide clear, friendly responses with Zoom links 
        and session times.""",
        allow_delegation=False,
        verbose=True
    )
    
    lookup_task = Task(
        description="""Find the session details for the {course} program during Week {week}. 
        Include the topic name, date, time (GMT+2), and the Zoom link if available.""",
        expected_output="A structured summary of the week's sessions formatted for a chat message.",
        agent=coordinator
    )
    
    return Crew(
        agents=[coordinator],
        tasks=[lookup_task],
        process=Process.sequential,
        verbose=True
    )

# --- BOT RUNNER CLASS ---
class CircleBot:
    def __init__(self, client: CircleClient):
        self.api = client
        self.crew = get_course_coordinator_crew()
        self.chat_room_uuid = os.getenv("CIRCLE_CHAT_ROOM_UUID")
        self.bot_email = os.getenv("CIRCLE_BOT_EMAIL")
        self.state_file = os.path.join(DATA_DIR, "processed_messages.json")
        self.processed_ids = self._load_state()

    def _load_state(self) -> set:
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    return set(json.load(f))
            except Exception:
                return set()
        return set()

    def _save_state(self):
        with open(self.state_file, 'w') as f:
            json.dump(list(self.processed_ids), f)

    async def process_message(self, msg: Dict[str, Any]):
        msg_id = msg.get('id')
        
        # --- IMPROVED TEXT EXTRACTION ---
        # Some Circle messages use 'body_text', others use 'rich_text_body'
        body_text = msg.get('body_text') or ""
        
        # If body_text is empty, try to extract from rich_text_body (basic extraction)
        if not body_text and msg.get('rich_text_body'):
            try:
                # This is a fallback to try and find strings in the TipTap JSON
                rich_body = str(msg.get('rich_text_body'))
                body_text = rich_body.lower() 
            except:
                body_text = ""

        body_text = body_text.lower()
        
        # Get author info safely
        user_data = msg.get('user') or {}
        author_email = user_data.get('email', 'unknown_email')
        author_name = user_data.get('name', 'Student')

        # 1. Skip if already processed
        if msg_id in self.processed_ids:
            return

        # 2. Skip if it's the bot's own message
        if author_email == self.bot_email:
            self.processed_ids.add(msg_id)
            return

        print(f"📩 Processing message from {author_name} ({author_email}): '{body_text}'")

        # --- RECOGNITION LOGIC ---
        is_ai = any(word in body_text for word in ['ai', 'ml', 'artificial', 'intelligence', 'machine'])
        is_mobile = any(word in body_text for word in ['mobile', 'ios', 'android', 'flutter', 'react native'])
        week_match = re.search(r'week\s*(\d+)', body_text)

        if (is_ai or is_mobile) and week_match:
            week_num = week_match.group(1)
            course_name = "AI/ML" if is_ai else "Mobile Development"
            
            print(f"🎯 MATCH FOUND: {course_name} Week {week_num}. Kicking off CrewAI...")

            try:
                # Get the user's SGID for the @mention
                user_sgid = await self.api.get_member_attachable_sgid(author_email)
                
                print(f"🤖 CrewAI is researching the schedule for {course_name} Week {week_num}...")
                result = self.crew.kickoff(inputs={"course": course_name, "week": week_num})
                
                print(f"📤 Posting reply to Circle...")
                await self.api.post_chat_message(
                    member_email=self.bot_email,
                    chat_room_uuid=self.chat_room_uuid,
                    text=str(result),
                    mention_sgid=user_sgid,
                    parent_message_id=msg_id 
                )
                print(f"✅ Successfully replied to {author_name}!")
            except Exception as e:
                print(f"❌ Error during processing: {e}")
        else:
            print(f"⏭️ Message ignored (Does not match 'AI/Mobile' + 'Week #').")

        # Mark as processed
        self.processed_ids.add(msg_id)
        self._save_state()

    async def run_forever(self):
        print("🚀 BOT IS LIVE - Monitoring Chat Room...")
        
        if not self.chat_room_uuid or not self.bot_email:
            print("❌ ERROR: Check your .env for CIRCLE_CHAT_ROOM_UUID and CIRCLE_BOT_EMAIL")
            return

        while True:
            try:
                now = datetime.now().strftime("%H:%M:%S")
                data = await self.api.get_chat_room_messages(
                    member_email=self.bot_email,
                    chat_room_uuid=self.chat_room_uuid
                )
                
                messages = data.get("records", [])
                # Only look at messages not in our processed list
                new_messages = [m for m in messages if m.get('id') not in self.processed_ids]
                
                if new_messages:
                    print(f"🕒 [{now}] Found {len(new_messages)} new messages!")
                    for msg in reversed(new_messages):
                        await self.process_message(msg)
                
                await asyncio.sleep(10)
                
            except Exception as e:
                print(f"❌ LOOP ERROR: {e}")
                await asyncio.sleep(10)

# --- EXECUTION BLOCK ---
async def main():
    try:
        client = CircleClient()
        bot = CircleBot(client)
        await bot.run_forever()
    except Exception as e:
        print(f"❌ CRITICAL STARTUP ERROR: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user (Ctrl+C).")
    except Exception as e:
        print(f"❌ System Error: {e}")