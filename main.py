import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from openai import OpenAI
from supabase import create_client

from app.config import validate_circle_config
from app.circle_integration import CircleClient


env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# ===== ENV CONFIG =====
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not SUPABASE_URL or not SUPABASE_KEY or not OPENAI_API_KEY:
    raise RuntimeError(
        "Missing env vars. Check .env file: "
        "SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, OPENAI_API_KEY"
    )

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
openai_client = OpenAI(api_key=OPENAI_API_KEY)

POLL_INTERVAL = 20  # seconds

# ===== CATEGORY MAPPING (EXACTLY YOUR COLUMN NAMES) =====
RATING_FIELDS = [
    ("teaching", "teaching_comment", "Teaching"),
    ("coursecontent", "coursecontent_comment", "Course Content"),
    ("examination", "examination_comment", "Examination"),
    ("labwork", "labwork_comment", "Lab Work"),
    ("library_facilities", "library_facilities_comment", "Library Facilities"),
    ("extracurricular", "extracurricular_comment", "Extracurricular"),
]


def get_negative_categories(row):
    negatives = []

    for rating_col, comment_col, label in RATING_FIELDS:
        rating = row.get(rating_col)

        if rating is not None and int(rating) < 0:
            negatives.append(
                {
                    "category": label,
                    "rating": int(rating),
                    "comment": (row.get(comment_col) or "").strip(),
                }
            )

    return negatives


def draft_followup(student_id, negatives):
    category_summary = "\n".join(
        f"- {n['category']}: rating {n['rating']} | comment: {n['comment'] or '(no comment)'}"
        for n in negatives
    )

    prompt = f"""
A student has submitted feedback with negative rating (-1).

Student ID: {student_id}

Negative categories:
{category_summary}

Write a professional and polite follow-up message asking:
- What specifically caused dissatisfaction
- What improvements they would suggest
- Whether they prefer email or phone follow-up

Return EXACTLY in this format:

SUBJECT: ...
BODY:
...
"""

    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )

    text = response.choices[0].message.content or ""

    subject = "We’d Like to Understand Your Feedback"
    body = text

    if "SUBJECT:" in text and "BODY:" in text:
        try:
            subject = text.split("SUBJECT:", 1)[1].split("BODY:", 1)[0].strip()
            body = text.split("BODY:", 1)[1].strip()
        except Exception:
            pass

    return subject, body


async def process_negative_feedback():
    circle_client = CircleClient()

    while True:
        try:
            result = (
                supabase.table("feedback")
                .select("*")
                .lt("min_rating", 0)
                .eq("processed", False)
                .limit(50)
                .execute()
            )

            rows = result.data or []

            for row in rows:
                feedback_id = row.get("id")
                student_id = row.get("student_id")

                if feedback_id is None:
                    print(f"Skipping row with missing id: {row}")
                    continue

                if student_id is None:
                    print(f"Skipping feedback {feedback_id} because student_id is missing")
                    continue

                negatives = get_negative_categories(row)

                if not negatives:
                    supabase.table("feedback").update(
                        {
                            "processed": True,
                            "processed_at": datetime.now(timezone.utc).isoformat(),
                        }
                    ).eq("id", feedback_id).execute()
                    continue

                subject, body = draft_followup(student_id, negatives)

                neg_summary = "\n".join(
                    f"- {n['category']} (rating {n['rating']}): {n['comment'] or '(no comment)'}"
                    for n in negatives
                )

                circle_message = f"""New negative feedback detected.

Feedback ID: {feedback_id}
Student ID: {student_id}

Negative Categories:
{neg_summary}

Suggested Follow-up Subject:
{subject}

Suggested Follow-up Body:
{body}
"""

                circle_result = await circle_client.post_chat_message(
                    member_email=os.getenv("CIRCLE_BOT_EMAIL"),
                    chat_room_uuid=os.getenv("CIRCLE_CHAT_ROOM_UUID"),
                    text=circle_message,
                )

                # ===== INSERT FOLLOWUP LOG =====
                supabase.table("followups").insert(
                    {
                        "feedback_id": feedback_id,
                        "student_id": student_id,
                        "channel": "circle",
                        "message": f"SUBJECT: {subject}\n\n{body}",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        }
                ).execute()

                # ===== CREATE TICKET =====
                supabase.table("tickets").insert(
                    {
                        "feedback_id": feedback_id,
                        "student_id": student_id,
                        "subject": f"Negative Feedback Alert - {subject}",
                        "description": f"""
                Feedback ID: {feedback_id}

                Negative Categories:
                {neg_summary}
                        
                Follow-up Message:
                {body}
                        
                Circle Response:
                {circle_result}
                """,
                        "status": "open",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                ).execute()

                
                # ===== MARK AS PROCESSED =====
                supabase.table("feedback").update(
                    {
                        "processed": True,
                        "processed_at": datetime.now(timezone.utc).isoformat(),
                    }
                ).eq("id", feedback_id).execute()

                print(f"Processed feedback {feedback_id}")

        except Exception as e:
            print("Worker Error:", e)

        await asyncio.sleep(POLL_INTERVAL)


_worker_task: Optional[asyncio.Task] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _worker_task
    _worker_task = asyncio.create_task(process_negative_feedback())
    try:
        yield
    finally:
        if _worker_task is not None:
            _worker_task.cancel()
            try:
                await _worker_task
            except asyncio.CancelledError:
                pass


app = FastAPI(title="Feedback Recovery Agent", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "running"}


@app.get("/health/circle-config")
def health_circle_config():
    missing = validate_circle_config()

    if missing:
        return {
            "status": "error",
            "missing": missing,
        }

    return {
        "status": "ok",
        "message": "Circle configuration loaded",
    }


@app.post("/test/circle-chat")
async def test_circle_chat():
    missing = validate_circle_config()
    if missing:
        return {
            "status": "error",
            "missing": missing,
        }

    client = CircleClient()

    try:
        result = await client.post_chat_message(
            member_email=os.getenv("CIRCLE_BOT_EMAIL"),
            chat_room_uuid=os.getenv("CIRCLE_CHAT_ROOM_UUID"),
            text="Test message from Feedback Recovery Agent integration.",
        )

        return {
            "status": "ok",
            "circle_response": result,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
        }


@app.post("/test/process-feedback/{feedback_id}")
async def test_process_feedback(feedback_id: int):
    try:
        result = (
            supabase.table("feedback")
            .select("*")
            .eq("id", feedback_id)
            .limit(1)
            .execute()
        )

        rows = result.data or []

        if not rows:
            return {
                "status": "error",
                "message": f"Feedback {feedback_id} not found",
            }

        row = rows[0]
        student_id = row.get("student_id")

        if student_id is None:
            return {
                "status": "error",
                "message": "student_id is missing",
            }

        negatives = get_negative_categories(row)

        if not negatives:
            return {
                "status": "error",
                "message": "No negative categories found for this feedback row",
            }

        subject, body = draft_followup(student_id, negatives)

        neg_summary = "\n".join(
            f"- {n['category']} (rating {n['rating']}): {n['comment'] or '(no comment)'}"
            for n in negatives
        )

        circle_message = f"""New negative feedback detected.

Feedback ID: {feedback_id}
Student ID: {student_id}

Negative Categories:
{neg_summary}

Suggested Follow-up Subject:
{subject}

Suggested Follow-up Body:
{body}
"""

        circle_client = CircleClient()
        circle_result = await circle_client.post_chat_message(
            member_email=os.getenv("CIRCLE_BOT_EMAIL"),
            chat_room_uuid=os.getenv("CIRCLE_CHAT_ROOM_UUID"),
            text=circle_message,
        )

        return {
            "status": "ok",
            "feedback_id": feedback_id,
            "student_id": student_id,
            "subject": subject,
            "body": body,
            "circle_response": circle_result,
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
        }