import httpx
import json
import logging
import os
import re
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dotenv import load_dotenv
import aiohttp

load_dotenv()

logger = logging.getLogger(__name__)

# Instance-specific data directory
DATA_DIR = os.getenv("DATA_DIR", "/home/ubuntu/data")
Path(DATA_DIR).mkdir(parents=True, exist_ok=True)

CHAT_MEMBERS_FILE = os.path.join(DATA_DIR, "chat_members.json")
CHAT_MEMBERS_SGID_FILE = os.path.join(DATA_DIR, "chat_members_SGID.json")

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

    async def get_unread_chat_threads(self, member_email: str) -> List[int]:
        """Fetch unread chat thread IDs for the given member."""
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
        """Fetch the parent message and all replies in a specific chat thread."""
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

    async def get_message_comments(
        self,
        member_email: str,
        message_id: int,
        last_comment_id: Optional[int] = None,
        next_per_page: int = 20,
    ) -> Dict:
        """Fetch comments for a given message newer than a given comment ID."""
        token = await self.get_member_token(member_email)
        url = f"{self.member_api_base}/messages/{message_id}/comments"
        params: Dict[str, Any] = {"next_per_page": next_per_page}
        if last_comment_id:
            params["id"] = last_comment_id
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
        """Retrieves and caches the SGID for a Circle member."""
        cache_file = CHAT_MEMBERS_SGID_FILE
        cache = {}

        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cache = json.load(f)
            except json.JSONDecodeError:
                logging.warning("⚠️ Corrupted chat_members_SGID.json — resetting cache.")
                cache = {}

        if email in cache and "sgid" in cache[email]:
            logging.info(f"🔁 Using cached SGID for {email}: {cache[email]['sgid']}")
            return cache[email]["sgid"]

        url = f"{self.admin_v2_api_base}/advanced_search?query={email}&search_type=members"
        headers = {"Authorization": f"Token {self.admin_v2_token}"}

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
                    if sgid:
                        cache[email] = member
                        with open(cache_file, "w", encoding="utf-8") as f:
                            json.dump(cache, f, indent=2)
                        return sgid
        return None

    async def post_chat_message(
        self,
        member_email: str,
        chat_room_uuid: str,
        text: str,
        mention_sgid: Optional[str] = None,
        parent_message_id: Optional[int] = None,
        creation_uuid: Optional[str] = None,
    ) -> Dict:
        """Post a message in the Circle chat room.

        If `creation_uuid` is provided, Circle uses it for idempotency (prevents duplicate posts).
        """
        token = await self.get_member_token(member_email)
        url = f"{self.member_api_base}/messages/{chat_room_uuid}/chat_room_messages"

        def markdown_to_tiptap(text: str):
            content_blocks = []
            lines = text.split("\n")
            for line in lines:
                line = line.strip()
                if not line:
                    content_blocks.append({"type": "paragraph"})
                    continue
                list_match = re.match(r"^(\d+\.|-)\s+(.*)", line)
                text_part = list_match.group(2) if list_match else line
                link_pattern = r"\[([^\]]+)\]\(([^)]+)\)"
                matches = list(re.finditer(link_pattern, text_part))
                if matches:
                    segments = []
                    last_idx = 0
                    for m in matches:
                        if m.start() > last_idx:
                            segments.append(
                                {"type": "text", "text": text_part[last_idx : m.start()]}
                            )
                        label = m.group(1).replace("**", "")
                        url = m.group(2)
                        segments.append(
                            {
                                "type": "text",
                                "text": label,
                                "marks": [
                                    {
                                        "type": "link",
                                        "attrs": {"href": url, "target": "_blank"},
                                    }
                                ],
                            }
                        )
                        last_idx = m.end()
                    if last_idx < len(text_part):
                        segments.append({"type": "text", "text": text_part[last_idx:]})
                    content_blocks.append({"type": "paragraph", "content": segments})
                    continue
                bold_segments = []
                while "**" in text_part:
                    parts = text_part.split("**", 2)
                    if len(parts) == 3:
                        before, bold, rest = parts
                        if before:
                            bold_segments.append({"type": "text", "text": before})
                        bold_segments.append(
                            {
                                "type": "text",
                                "text": bold,
                                "marks": [{"type": "bold"}],
                            }
                        )
                        text_part = rest
                    else:
                        break
                if text_part:
                    bold_segments.append({"type": "text", "text": text_part})
                content_blocks.append({"type": "paragraph", "content": bold_segments})
            return content_blocks

        mention_block = []
        sgids_to_object_map = {}
        if mention_sgid:
            mention_block = [
                {
                    "type": "mention",
                    "attrs": {"sgid": mention_sgid},
                    "circle_ios_fallback_text": "@user",
                },
                {"type": "text", "text": " "},
            ]
            sgids_to_object_map[mention_sgid] = {"type": "CommunityMember"}

        formatted_blocks = markdown_to_tiptap(text)

        body: Dict[str, Any] = {
            "rich_text_body": {
                "body": {
                    "type": "doc",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": mention_block + [{"type": "text", "text": " "}],
                        }
                    ]
                    + formatted_blocks,
                },
                "circle_ios_fallback_text": text,
                "attachments": [],
                "inline_attachments": [],
                "sgids_to_object_map": sgids_to_object_map,
                "format": "chat",
            },
        }

        if parent_message_id is not None:
            body["parent_message_id"] = parent_message_id
        if creation_uuid is not None:
            body["creation_uuid"] = creation_uuid

        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            r.raise_for_status()
            return r.json()
