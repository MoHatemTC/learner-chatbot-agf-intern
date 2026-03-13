import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

CIRCLE_ENABLED = os.getenv("CIRCLE_ENABLED", "false").lower() == "true"
CIRCLE_HEADLESS_AUTH_TOKEN = os.getenv("CIRCLE_HEADLESS_AUTH_TOKEN")
CIRCLE_ADMIN_V2_TOKEN = os.getenv("CIRCLE_ADMIN_V2_TOKEN")
CIRCLE_AUTH_URL = os.getenv(
    "CIRCLE_AUTH_URL",
    "https://app.circle.so/api/v1/headless/auth_token"
)
CIRCLE_MEMBER_API_BASE = os.getenv(
    "CIRCLE_MEMBER_API_BASE",
    "https://app.circle.so/api/headless/v1"
)
CIRCLE_BOT_EMAIL = os.getenv("CIRCLE_BOT_EMAIL")
CIRCLE_CHAT_SPACE_ID = os.getenv("CIRCLE_CHAT_SPACE_ID")
CIRCLE_CHAT_ROOM_UUID = os.getenv("CIRCLE_CHAT_ROOM_UUID")


def validate_circle_config():
    missing = []

    if not CIRCLE_HEADLESS_AUTH_TOKEN:
        missing.append("CIRCLE_HEADLESS_AUTH_TOKEN")

    if not CIRCLE_ADMIN_V2_TOKEN:
        missing.append("CIRCLE_ADMIN_V2_TOKEN")

    if not CIRCLE_BOT_EMAIL:
        missing.append("CIRCLE_BOT_EMAIL")

    if not CIRCLE_CHAT_SPACE_ID:
        missing.append("CIRCLE_CHAT_SPACE_ID")

    if not CIRCLE_CHAT_ROOM_UUID:
        missing.append("CIRCLE_CHAT_ROOM_UUID")

    return missing