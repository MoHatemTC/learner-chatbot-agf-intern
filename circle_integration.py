"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Stage 2 — Circle Integration
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This module is the Stage 2 addition to the project.
Stage 1 (core pipeline) built the PDF ingestion and CrewAI
retrieval system (ingest_hybrid.py, runner.py, agents.py, tasks.py,
embedder.py, chunking.py, qdrant_utils.py).

Stage 2 connects that pipeline to a live Circle.so community
chat room so students can ask questions directly in Circle and
receive automated answers from the bot.

Circle.so Chat Integration for the Sprints FAQ Bot
====================================================
- CircleClient  : low-level headless + admin API client with token caching.
- CircleBotRunner: polling loop that reads new chat-room messages and replies
                   using ChatbotRunner (CrewAI / Qdrant pipeline).

Run standalone:
    python circle_integration.py

Or import CircleBotRunner and call await bot.run() from your app.
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
import httpx
from dotenv import load_dotenv

load_dotenv()

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    filename=f"circle_api_debug_{datetime.now().strftime('%Y%m%d')}.txt",
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ── Data directory (platform-safe, relative to this script) ────────────────────
# FIX #1: original used "/app/data" (Linux/Docker path) — breaks on Windows.
DATA_DIR = os.getenv("DATA_DIR", str(Path(__file__).parent / "data"))
Path(DATA_DIR).mkdir(parents=True, exist_ok=True)

CHAT_MEMBERS_FILE = os.path.join(DATA_DIR, "chat_members.json")
CHAT_MEMBERS_SGID_FILE = os.path.join(DATA_DIR, "chat_members_SGID.json")
BOT_STATE_FILE = os.path.join(DATA_DIR, "bot_state.json")

# ── TipTap plain-text extractor (for parsing incoming Circle messages) ─────────
def tiptap_to_text(node: Dict) -> str:
    """Recursively extract plain text from a TipTap document node."""
    if not node or not isinstance(node, dict):
        return ""
    node_type = node.get("type", "")
    if node_type == "text":
        return node.get("text", "")
    if node_type == "mention":
        return node.get("circle_ios_fallback_text", "@user")
    if node_type == "hardBreak":
        return "\n"
    parts: List[str] = []
    for child in node.get("content", []):
        parts.append(tiptap_to_text(child))
    separator = "\n" if node_type in ("paragraph", "listItem", "bulletList", "orderedList") else ""
    return separator.join(p for p in parts if p).strip()


# ── Markdown → TipTap converter ───────────────────────────────────────────────
_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_BOLD_PATTERN = re.compile(r"\*\*(.+?)\*\*")


def _append_bold_segments(segments: List[Dict], text: str) -> None:
    last = 0
    for m in _BOLD_PATTERN.finditer(text):
        if m.start() > last:
            segments.append({"type": "text", "text": text[last: m.start()]})
        segments.append({"type": "text", "text": m.group(1), "marks": [{"type": "bold"}]})
        last = m.end()
    if last < len(text):
        segments.append({"type": "text", "text": text[last:]})


def _markdown_to_tiptap(markdown: str) -> List[Dict]:
    """Convert Markdown (bold, links, line-breaks) to TipTap paragraph blocks."""
    blocks: List[Dict] = []
    for line in markdown.split("\n"):
        line = line.strip()
        if not line:
            blocks.append({"type": "paragraph"})
            continue
        segments: List[Dict] = []
        last_idx = 0
        for m in _LINK_PATTERN.finditer(line):
            if m.start() > last_idx:
                _append_bold_segments(segments, line[last_idx: m.start()])
            label = m.group(1).replace("**", "")
            href = m.group(2)
            segments.append({
                "type": "text",
                "text": label,
                "marks": [{"type": "link", "attrs": {"href": href, "target": "_blank"}}],
            })
            last_idx = m.end()
        if last_idx < len(line):
            _append_bold_segments(segments, line[last_idx:])
        if segments:
            blocks.append({"type": "paragraph", "content": segments})
    return blocks


# ── Bot state persistence ──────────────────────────────────────────────────────

def _load_bot_state() -> Dict:
    if os.path.exists(BOT_STATE_FILE):
        try:
            with open(BOT_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"last_message_id": None, "processed_ids": []}


def _save_bot_state(state: Dict) -> None:
    with open(BOT_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


# ── CircleClient ───────────────────────────────────────────────────────────────

class CircleClient:
    """Low-level Circle.so headless + admin API client with JWT token caching."""

    def __init__(self) -> None:
        self.auth_url = os.getenv("CIRCLE_AUTH_URL", "https://app.circle.so/api/v1/headless/auth_token")
        self.member_api_base = os.getenv("CIRCLE_MEMBER_API_BASE", "https://app.circle.so/api/headless/v1")
        self.admin_v2_api_base = "https://app.circle.so/api/admin/v2"
        self.headless_auth_token = os.getenv("CIRCLE_HEADLESS_AUTH_TOKEN")
        self.admin_v2_token = os.getenv("CIRCLE_ADMIN_V2_TOKEN")
        self._token_cache: Dict[str, Dict] = {}  # private; keyed by email
    

    def _is_token_expired(self, email: str) -> bool:
        """Return True if the cached token is missing or expires within 5 minutes."""
        if email not in self._token_cache:
            return True
        expires_at = self._token_cache[email].get("expires_at")
        if not expires_at:
            return True
        return (
            datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            < datetime.now(timezone.utc) + timedelta(minutes=5)
        )

    async def get_member_token(self, email: str) -> str:
        """Return a valid JWT access token for *email*, refreshing if needed."""
        if not self._is_token_expired(email):
            return self._token_cache[email]["access_token"]

        if email in self._token_cache and self._token_cache[email].get("refresh_token"):
            try:
                return await self._refresh_token(email)
            except Exception as exc:
                logger.warning(f"Token refresh failed for {email}, fetching new: {exc}")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.auth_url,
                headers={
                    "Authorization": f"Token {self.headless_auth_token}",
                    "Content-Type": "application/json",
                },
                json={"email": email},
            )
            response.raise_for_status()
            data = response.json()
            self._token_cache[email] = {
                "access_token": data["access_token"],
                "refresh_token": data.get("refresh_token"),
                "expires_at": data.get("access_token_expires_at"),
                "community_member_id": data.get("community_member_id"),
            }
            logger.debug(f"✅ Cached token for {email} (member_id={data.get('community_member_id')})")
            return data["access_token"]

    async def _refresh_token(self, email: str) -> str:
        """Use the stored refresh_token to get a new access_token."""
        refresh_token = self._token_cache[email]["refresh_token"]
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.auth_url}/refresh",
                headers={
                    "Authorization": f"Token {self.headless_auth_token}",
                    "Content-Type": "application/json",
                },
                json={"refresh_token": refresh_token},
            )
            response.raise_for_status()
            data = response.json()
            self._token_cache[email].update({
                "access_token": data["access_token"],
                "refresh_token": data.get("refresh_token"),
                "expires_at": data.get("access_token_expires_at"),
            })
            return data["access_token"]

    def get_cached_member_id(self, email: str) -> Optional[int]:
        """Return the cached community_member_id for *email* (requires prior token fetch)."""
        return self._token_cache.get(email, {}).get("community_member_id")

    # ── Chat room messages ─────────────────────────────────────────────────────

    async def get_chat_room_messages(
        self,
        member_email: str,
        chat_room_uuid: str,
        after_message_id: Optional[int] = None,
        per_page: int = 50,
    ) -> Any:
        """
        Fetch chat messages.  Pass *after_message_id* to get only newer messages.
        Returns the raw JSON (list or {records: [...]} dict depending on Circle version).
        """
        token = await self.get_member_token(member_email)
        endpoint = f"{self.member_api_base}/messages/{chat_room_uuid}/chat_room_messages"
        params: Dict[str, Any] = {"next_per_page": per_page}
        if after_message_id:
            params["id"] = after_message_id
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                endpoint,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                params=params,
            )
            r.raise_for_status()
            return r.json()

    async def post_chat_message(
        self,
        member_email: str,
        chat_room_uuid: str,
        text: str,
        mention_sgid: Optional[str] = None,
        parent_message_id: Optional[int] = None,
    ) -> Dict:
        """
        Post a message to the Circle chat room.

        Args:
            member_email:      Email of the sender (bot account).
            chat_room_uuid:    UUID of the target chat room.
            text:              Markdown-formatted message body.
            mention_sgid:      Attachable SGID of the user to @mention (optional).
            parent_message_id: Message ID to reply to in a thread (optional).
        """
        token = await self.get_member_token(member_email)
        endpoint = f"{self.member_api_base}/messages/{chat_room_uuid}/chat_room_messages"

        doc_content: List[Dict] = []
        sgids_map: Dict[str, Dict] = {}

        if mention_sgid:
            doc_content.append({
                "type": "paragraph",
                "content": [
                    {"type": "mention", "attrs": {"sgid": mention_sgid}, "circle_ios_fallback_text": "@user"},
                    {"type": "text", "text": " "},
                ],
            })
            sgids_map[mention_sgid] = {"type": "CommunityMember"}

        doc_content.extend(_markdown_to_tiptap(text))

        body: Dict[str, Any] = {
            "rich_text_body": {
                "body": {"type": "doc", "content": doc_content},
                "circle_ios_fallback_text": text,
                "attachments": [],
                "inline_attachments": [],
                "sgids_to_object_map": sgids_map,
                "format": "chat",
            }
        }
        if parent_message_id is not None:
            body["parent_message_id"] = parent_message_id

        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=body,
            )
            logger.info(f"💬 Circle POST [{r.status_code}]: {r.text[:500]}")
            r.raise_for_status()
            logger.info(f"✅ Message posted to room {chat_room_uuid}")
            return r.json()

    # ── Chat room participants ─────────────────────────────────────────────────

    async def get_chat_room_participants(
        self, member_email: str, chat_room_uuid: str, per_page: int = 50
    ) -> Dict:
        """Fetch all chat room participants (paginated) and save them to disk."""
        token = await self.get_member_token(member_email)
        url = f"{self.member_api_base}/messages/{chat_room_uuid}/chat_room_participants"
        all_records: List[Dict] = []
        page, has_next = 1, True
        while has_next:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    params={"page": page, "per_page": per_page},
                )
                r.raise_for_status()
                data = r.json()
                all_records.extend(data.get("records", []))
                has_next = data.get("has_next_page", False)
                page += 1
        with open(CHAT_MEMBERS_FILE, "w", encoding="utf-8") as f:
            json.dump(all_records, f, indent=2)
        logger.info(f"✅ Saved {len(all_records)} chat room participants.")
        return {"records": all_records}

    # ── Unread chat threads ────────────────────────────────────────────────────

    async def get_unread_chat_threads(self, member_email: str) -> List[int]:
        """Return a list of unread chat thread IDs for *member_email*."""
        token = await self.get_member_token(member_email)
        url = f"{self.member_api_base}/chat_threads/unread_chat_threads"
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                r = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                )
                r.raise_for_status()
                thread_ids = r.json().get("chat_thread_ids", [])
                logger.info(f"📬 {len(thread_ids)} unread chat threads.")
                return thread_ids
            except httpx.HTTPError as exc:
                logger.error(f"❌ Unread threads fetch failed: {exc}")
                return []

    async def get_chat_thread_details(self, member_email: str, thread_id: int) -> Optional[Dict]:
        """Return full thread data including replies for *thread_id*."""
        token = await self.get_member_token(member_email)
        url = f"{self.member_api_base}/chat_threads/{thread_id}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                r = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                )
                r.raise_for_status()
                td = r.json()
                logger.info(f"💬 Thread {thread_id}: {len(td.get('replies', []))} replies.")
                return td
            except httpx.HTTPError as exc:
                logger.error(f"❌ Thread {thread_id} fetch failed: {exc}")
                return None

    # ── Member SGID lookup (for @mentions) ────────────────────────────────────

    async def get_member_attachable_sgid(self, email: str) -> Optional[str]:
        """
        Look up and cache the attachable_sgid for a member (used for @mentions).
        Checks a local disk cache first to avoid repeated API calls.
        """
        cache: Dict = {}
        if os.path.exists(CHAT_MEMBERS_SGID_FILE):
            try:
                with open(CHAT_MEMBERS_SGID_FILE, "r", encoding="utf-8") as f:
                    cache = json.load(f)
            except (json.JSONDecodeError, OSError):
                logger.warning("⚠️ Corrupted SGID cache — resetting.")

        if email in cache and cache[email].get("sgid"):
            logger.info(f"🔁 Cached SGID for {email}: {cache[email]['sgid']}")
            return cache[email]["sgid"]

        search_url = (
            f"{self.admin_v2_api_base}/advanced_search?query={email}&search_type=members"
        )
        async with aiohttp.ClientSession() as session:
            async with session.get(
                search_url, headers={"Authorization": f"Bearer {self.admin_v2_token}"}
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error(f"❌ SGID fetch failed ({resp.status}): {body}")
                    return None
                data = await resp.json()

        records = data.get("records", [])
        if not records:
            logger.warning(f"⚠️ No member found for {email}")
            return None

        member = records[0]
        # check both key names used by different Circle API endpoints
        sgid = member.get("sgid") or member.get("attachable_sgid")
        if sgid:
            cache[email] = {**member, "sgid": sgid}
            with open(CHAT_MEMBERS_SGID_FILE, "w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2)
            logger.info(f"✅ Cached SGID for {email}: {sgid}")
        return sgid


# ── CircleBotRunner ────────────────────────────────────────────────────────────

class CircleBotRunner:
    """
    Polls a Circle chat room for new messages and replies using ChatbotRunner.

    Flow per poll cycle:
      1. Fetch messages newer than last_message_id.
      2. Skip thread-replies (parent_message_id set) and the bot's own messages.
      3. Extract plain text → call ChatbotRunner.answer_question() in a thread pool.
      4. Post the answer back, @mentioning the sender and replying in-thread.
      5. Persist the highest seen message ID to disk.

    On first run (no saved state) all existing messages are bookmarked without
    being answered, so the bot does not replay old messages.
    """

    def __init__(self, poll_interval: int = 15) -> None:
        from runner import ChatbotRunner  # local import keeps module lightweight

        self.bot_email: str = os.getenv("CIRCLE_BOT_EMAIL", "agfintern8@sprints.ai")
        self.chat_room_uuid: str = os.getenv("CIRCLE_CHAT_ROOM_UUID", "")
        self.poll_interval = poll_interval
        self.circle = CircleClient()
        self.chatbot = ChatbotRunner()
        self._state = _load_bot_state()
        self._first_run: bool = self._state.get("last_message_id") is None

        if not self.chat_room_uuid:
            raise ValueError("CIRCLE_CHAT_ROOM_UUID is not set in .env")

        logger.info(
            f"🤖 CircleBotRunner ready — room={self.chat_room_uuid} "
            f"bot={self.bot_email} interval={self.poll_interval}s"
        )

    async def _get_bot_member_id(self) -> Optional[int]:
        await self.circle.get_member_token(self.bot_email)
        return self.circle.get_cached_member_id(self.bot_email)

    @staticmethod
    def _extract_text(msg: Dict) -> str:
        """Pull plain text out of a Circle chat message object."""
        rtb = msg.get("rich_text_body") or {}
        tiptap_body = rtb.get("body") or msg.get("body")
        if isinstance(tiptap_body, dict):
            return tiptap_to_text(tiptap_body)
        if isinstance(tiptap_body, str):
            return tiptap_body
        return rtb.get("circle_ios_fallback_text", "")

    @staticmethod
    def _sender_member_id(msg: Dict) -> Optional[int]:
        sender = msg.get("sender") or msg.get("community_member") or msg.get("author") or {}
        return sender.get("community_member_id") or sender.get("id")

    @staticmethod
    def _sender_email(msg: Dict) -> Optional[str]:
        sender = msg.get("sender") or msg.get("community_member") or msg.get("author") or {}
        return sender.get("email")

    async def _handle_message(self, msg: Dict, bot_member_id: Optional[int]) -> None:
        msg_id: int = msg.get("id", 0)

        if msg.get("parent_message_id"):
            logger.debug(f"⏭️  Skipping thread reply {msg_id}")
            return
        if bot_member_id and self._sender_member_id(msg) == bot_member_id:
            logger.debug(f"⏭️  Skipping own message {msg_id}")
            return

        text = self._extract_text(msg).strip()
        if not text:
            return

        logger.info(f"💬 [{msg_id}] {text[:120]}")
        print(f"\n💬 Question [{msg_id}]: {text[:200]}")

        mention_sgid: Optional[str] = None
        sender_email = self._sender_email(msg)
        if sender_email:
            try:
                mention_sgid = await self.circle.get_member_attachable_sgid(sender_email)
            except Exception as exc:
                logger.warning(f"Could not get SGID for {sender_email}: {exc}")

        try:
            result: Dict = await asyncio.to_thread(self.chatbot.answer_question, text)
            answer: str = result.get(
                "answer",
                "I was unable to process your question. Please contact the administration.",
            )
        except Exception as exc:
            logger.error(f"❌ ChatbotRunner error for message {msg_id}: {exc}", exc_info=True)
            answer = (
                "Sorry, I encountered an error while processing your question. "
                "Please contact the administration."
            )

        print(f"🤖 Answer [{msg_id}]: {answer[:200]}")

        try:
            await self.circle.post_chat_message(
                member_email=self.bot_email,
                chat_room_uuid=self.chat_room_uuid,
                text=answer,
                mention_sgid=mention_sgid,
                parent_message_id=msg_id,
            )
            logger.info(f"✅ Replied to message {msg_id}")
        except Exception as exc:
            logger.error(f"❌ Failed to post reply for message {msg_id}: {exc}")

    async def poll_once(self) -> None:
        """Fetch and process one batch of new messages."""
        try:
            bot_member_id = await self._get_bot_member_id()
            last_id: Optional[int] = self._state.get("last_message_id")
            processed: set = set(self._state.get("processed_ids", []))

            raw = await self.circle.get_chat_room_messages(
                member_email=self.bot_email,
                chat_room_uuid=self.chat_room_uuid,
                after_message_id=last_id,
            )
            messages: List[Dict] = raw if isinstance(raw, list) else raw.get("records", [])

            if self._first_run:
                self._first_run = False
                if messages:
                    max_id = max(m.get("id", 0) for m in messages)
                    self._state["last_message_id"] = max_id
                    self._state["processed_ids"] = [m["id"] for m in messages if m.get("id")]
                    _save_bot_state(self._state)
                    print(f"🔖 First run: bookmarked up to message {max_id} — won't replay old messages.")
                return

            new_messages = [m for m in messages if m.get("id") not in processed]
            if not new_messages:
                return

            new_messages.sort(key=lambda m: m.get("id", 0))
            for msg in new_messages:
                await self._handle_message(msg, bot_member_id)
                mid = msg.get("id")
                if mid:
                    processed.add(mid)
                    if not last_id or mid > last_id:
                        last_id = mid

            self._state["last_message_id"] = last_id
            self._state["processed_ids"] = sorted(processed)[-500:]
            _save_bot_state(self._state)

        except Exception as exc:
            logger.error(f"❌ Poll error: {exc}", exc_info=True)
            print(f"❌ Polling error: {exc}")

    async def run(self) -> None:
        """Start the polling loop. Runs indefinitely until interrupted."""
        print(f"\n🚀 Circle Bot started (polling every {self.poll_interval}s)")
        print(f"   Room UUID : {self.chat_room_uuid}")
        print(f"   Bot email : {self.bot_email}")
        print("   Press Ctrl+C to stop.\n")
        while True:
            await self.poll_once()
            await asyncio.sleep(self.poll_interval)


# ── Utility ────────────────────────────────────────────────────────────────────

def save_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ── Entry point ────────────────────────────────────────────────────────────────

async def _main() -> None:
    enabled = os.getenv("CIRCLE_ENABLED", "false").lower() == "true"
    if not enabled:
        print("⚠️  CIRCLE_ENABLED is not 'true' in .env — set it to start the bot.")
        return
    bot = CircleBotRunner()
    await bot.run()


if __name__ == "__main__":
    asyncio.run(_main())