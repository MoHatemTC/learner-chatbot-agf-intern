import asyncio
import os
import json
import logging
from dotenv import load_dotenv

from circle_integration import CircleClient       # your Circle client wrapper
from Weekly_Progress_Agent import run_progress_check  # your agent
from intent_parser import parse_intent            # your intent parser

# ── Environment ────────────────────────────────────────────────────────────── #
load_dotenv()
BOT_EMAIL   = os.getenv("CIRCLE_BOT_EMAIL")         # bot's email
ROOM_UUID   = os.getenv("CIRCLE_CHAT_ROOM_UUID")    # chatroom UUID

# ── Logging ────────────────────────────────────────────────────────────────── #
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ── Retry / polling config ─────────────────────────────────────────────────── #
POLL_INTERVAL_SEC        = 2      # normal polling cadence
ERROR_BACKOFF_SEC        = 5      # wait after a fetch error
MAX_BACKOFF_SEC          = 60     # ceiling for exponential backoff
POST_RETRY_ATTEMPTS      = 3      # how many times to retry a failed post
POST_RETRY_DELAY_SEC     = 3      # delay between post retries

# ── Helpers ────────────────────────────────────────────────────────────────── #

def normalize_id(id_val: int | str) -> int:
    """Convert any message-id representation to a plain int (0 on failure)."""
    try:
        return int(id_val)
    except (TypeError, ValueError):
        try:
            return int(str(id_val).split("-")[-1])
        except (TypeError, ValueError):
            return 0


def get_message_text(msg: dict) -> str:
    return (
        msg.get("plain_text_body")
        or msg.get("body")
        or msg.get("text")
        or ""
    ).strip()


def get_sender_email(msg: dict) -> str:
    return (
        msg.get("creator", {}).get("email")
        or msg.get("sender", {}).get("email")
        or msg.get("author", {}).get("email")
        or ""
    )


def get_sender_name(msg: dict) -> str:
    return (
        msg.get("creator", {}).get("name")
        or msg.get("sender", {}).get("name")
        or msg.get("author", {}).get("name")
        or ""
    )


async def safe_parse_intent(text: str) -> dict:
    """Parse intent from text; return {'intent': None} on any failure."""
    try:
        intent = parse_intent(text)
        if isinstance(intent, str):
            try:
                intent = json.loads(intent)
            except json.JSONDecodeError:
                return {"intent": None}
        return intent if isinstance(intent, dict) else {"intent": None}
    except Exception as e:
        logger.warning(f"Intent parsing failed: {e}")
        return {"intent": None}


def extract_agent_message(result) -> str:
    """Safely extract a user-friendly message from the agent result."""
    try:
        if hasattr(result, "raw"):
            data = json.loads(result.raw)
        elif isinstance(result, str):
            data = json.loads(result)
        elif isinstance(result, dict):
            data = result
        else:
            return "Progress check completed, but the result format was unexpected."

        status  = data.get("status", "")
        message = data.get("message", "")
        if not message:
            return "Progress check completed."
        return f"Status: {status}\n\n{message}" if status else message
    except (json.JSONDecodeError, AttributeError):
        # Avoid exposing raw Python object repr to users
        return "Progress check completed."


async def resolve_sgid(circle: "CircleClient", sender_email: str) -> str | None:
    """
    Look up the attachable SGID for a member by email.
    Returns None (no mention) if:
      - the lookup fails
      - the result is empty
      - the resolved email doesn't match sender_email (wrong-person guard)
    """
    if not sender_email:
        return None
    try:
        result = await circle.get_member_attachable_sgid(sender_email)
        if not result:
            logger.debug(f"SGID lookup returned empty for {sender_email}.")
            return None

        # If the API returns a dict, validate the email matches
        if isinstance(result, dict):
            resolved_email = (
                result.get("email")
                or result.get("member", {}).get("email")
                or ""
            )
            if resolved_email and resolved_email.lower() != sender_email.lower():
                logger.warning(
                    f"SGID mismatch: requested '{sender_email}' "
                    f"but resolved to '{resolved_email}'. Skipping mention."
                )
                return None
            sgid = result.get("sgid") or result.get("attachable_sgid")
            logger.debug(f"Resolved SGID for {sender_email}: {sgid}")
            return sgid

        # If it's a plain string SGID, trust it
        logger.debug(f"Resolved SGID for {sender_email}: {result}")
        return result

    except Exception as e:
        logger.warning(f"SGID lookup failed for {sender_email}: {e}")
        return None



async def post_with_retry(
    circle: "CircleClient",
    reply_text: str,
    sgid: str | None,
    message_id: int,
) -> bool:
    """
    Attempt to post a reply up to POST_RETRY_ATTEMPTS times.
    Returns True on success, False if all attempts fail.
    """
    for attempt in range(1, POST_RETRY_ATTEMPTS + 1):
        try:
            await circle.post_chat_message(
                BOT_EMAIL,
                ROOM_UUID,
                reply_text,
                mention_sgid=sgid,
                parent_message_id=message_id,
            )
            logger.info(f"Replied to message {message_id} (attempt {attempt}).")
            return True
        except Exception as e:
            logger.error(
                f"Post attempt {attempt}/{POST_RETRY_ATTEMPTS} failed "
                f"for message {message_id}: {e}"
            )
            if attempt < POST_RETRY_ATTEMPTS:
                await asyncio.sleep(POST_RETRY_DELAY_SEC)
    return False


async def seed_last_message_id(circle: "CircleClient") -> int:
    """
    On startup, fetch the latest message ID so we don't replay history.
    Falls back to 0 if the room is empty or the fetch fails.
    """
    try:
        data = await circle.get_chat_room_messages(BOT_EMAIL, ROOM_UUID, 0)
        records = data.get("records", [])
        if records:
            latest = max(normalize_id(m.get("id", 0)) for m in records)
            logger.info(f"Seeded last_message_id={latest} from startup fetch.")
            return latest
    except Exception as e:
        logger.warning(f"Could not seed last_message_id: {e}")
    return 0


# ── Main listener loop ─────────────────────────────────────────────────────── #

async def listen():
    circle = CircleClient()
    last_message_id = await seed_last_message_id(circle)
    consecutive_errors = 0

    while True:
        # ── Fetch new messages ─────────────────────────────────────────────── #
        try:
            data = await circle.get_chat_room_messages(
                BOT_EMAIL, ROOM_UUID, last_message_id
            )
            consecutive_errors = 0  # reset backoff on success
        except Exception as e:
            consecutive_errors += 1
            backoff = min(ERROR_BACKOFF_SEC * consecutive_errors, MAX_BACKOFF_SEC)
            logger.error(
                f"Failed fetching messages (error #{consecutive_errors}): {e}. "
                f"Retrying in {backoff}s."
            )
            await asyncio.sleep(backoff)
            continue

        messages = data.get("records", [])
        if not messages:
            await asyncio.sleep(POLL_INTERVAL_SEC)
            continue

        # Sort oldest → newest so we process in order
        messages.sort(key=lambda m: normalize_id(m.get("id", 0)))

        for msg in messages:
            message_id   = normalize_id(msg.get("id", 0))
            sender_email = get_sender_email(msg)
            sender_name  = get_sender_name(msg)

            # ── Skip already-seen messages ─────────────────────────────────── #
            if message_id <= last_message_id:
                continue

            # ── Skip bot's own messages (by email only, not by name) ──────── #
            if sender_email == BOT_EMAIL:
                last_message_id = max(last_message_id, message_id)
                continue

            # ── Only respond to @mentions ──────────────────────────────────── #
            text = get_message_text(msg)
            if f"@{BOT_EMAIL}" not in text and "@Bot 1" not in text:
                last_message_id = max(last_message_id, message_id)
                continue

            clean_text = (
                text.replace(f"@{BOT_EMAIL}", "")
                    .replace("@Bot 1", "")
                    .strip()
            )
            logger.info(
                f"New message (id={message_id}) from {sender_email}: {clean_text}"
            )

            # ── Parse intent ───────────────────────────────────────────────── #
            intent = await safe_parse_intent(clean_text)

            if intent.get("intent") != "progress_check":
                logger.info(f"Unrecognized intent '{intent.get('intent')}' – notifying user.")
                unknown_reply = (
                    "Sorry, I didn't understand that request. "
                    "Try: *@Bot 1 check progress for student <ID> week <N>*"
                )
                # Best-effort – don't block on failure
                sgid = await resolve_sgid(circle, sender_email)
                await post_with_retry(circle, unknown_reply, sgid, message_id)
                last_message_id = max(last_message_id, message_id)
                continue

            # ── Extract & validate parameters ─────────────────────────────── #
            student_id = (
                intent.get("student_id")
                or intent.get("student")
                or intent.get("studentId")
            )
            week_raw = (
                intent.get("week")
                or intent.get("week_number")
                or intent.get("weekNumber")
            )

            try:
                week = int(week_raw)
            except (TypeError, ValueError):
                logger.warning(f"Invalid week value: {week_raw!r}")
                bad_param_reply = (
                    "I couldn't find a valid week number in your request. "
                    "Please include a week number, e.g. *week 3*."
                )
                try:
                    sgid = await resolve_sgid(circle, sender_email)
                except Exception:
                    sgid = None
                await post_with_retry(circle, bad_param_reply, sgid, message_id)
                last_message_id = max(last_message_id, message_id)
                continue

            if not student_id:
                logger.warning("No student_id found in intent.")
                bad_param_reply = (
                    "I couldn't identify the student in your request. "
                    "Please include a student ID or name."
                )
                try:
                    sgid = await resolve_sgid(circle, sender_email)
                except Exception:
                    sgid = None
                await post_with_retry(circle, bad_param_reply, sgid, message_id)
                last_message_id = max(last_message_id, message_id)
                continue

            # ── Run the progress-check agent ───────────────────────────────── #
            try:
                result      = run_progress_check(student_id, week)
                reply_text  = extract_agent_message(result)
            except Exception as e:
                logger.error(f"Agent failed for student={student_id} week={week}: {e}")
                reply_text = (
                    "Sorry, I ran into an error while checking progress. "
                    "Please try again or contact support."
                )

            # ── Resolve sender SGID for mention ───────────────────────────── #
            sgid = await resolve_sgid(circle, sender_email)

            # ── Post reply (with retry) & advance pointer ──────────────────── #
            success = await post_with_retry(circle, reply_text, sgid, message_id)
            if not success:
                logger.error(
                    f"All post attempts failed for message {message_id}. "
                    "Advancing pointer to avoid infinite retry."
                )
            # Always advance – even on post failure – to prevent infinite loops
            last_message_id = max(last_message_id, message_id)

            await asyncio.sleep(0.5)   # small courtesy delay between messages

        await asyncio.sleep(POLL_INTERVAL_SEC)


# ── Entry point ────────────────────────────────────────────────────────────── #

if __name__ == "__main__":
    asyncio.run(listen())