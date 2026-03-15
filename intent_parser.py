# intent_parser.py

import re

UUID_PATTERN = r"[0-9a-fA-F-]{36}"
WEEK_PATTERN = r"week\s*(\d+)|(\d+)$"

def parse_intent(message):

    message_lower = message.lower()

    # Detect student id
    student_match = re.search(UUID_PATTERN, message)

    # Detect week number
    week_match = re.search(r"week\s*(\d+)", message_lower)

    if student_match and week_match:

        student_id = student_match.group()
        week = int(week_match.group(1))

        return {
            "intent": "progress_check",
            "student_id": student_id,
            "week": week
        }

    return {
        "intent": "unknown"
    }