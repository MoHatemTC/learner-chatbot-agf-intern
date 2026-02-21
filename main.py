import asyncio
from datetime import datetime, timezone
from fastapi import FastAPI
from supabase import create_client
from openai import OpenAI
import os
from dotenv import load_dotenv
from pathlib import Path

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

app = FastAPI(title="Feedback Recovery Agent")

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
            negatives.append({
                "category": label,
                "rating": int(rating),
                "comment": (row.get(comment_col) or "").strip()
            })

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
        temperature=0.3
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
                feedback_id = row["id"]
                student_id = row["student_id"]

                negatives = get_negative_categories(row)

                if not negatives:
                    # Safety fallback
                    supabase.table("feedback").update({
                        "processed": True,
                        "processed_at": datetime.now(timezone.utc).isoformat()
                    }).eq("id", feedback_id).execute()
                    continue

                subject, body = draft_followup(student_id, negatives)

                # ===== INSERT FOLLOWUP LOG =====
                supabase.table("followups").insert({
                    "feedback_id": feedback_id,
                    "student_id": student_id,
                    "message": f"SUBJECT: {subject}\n\n{body}",
                    "created_at": datetime.now(timezone.utc).isoformat()
                }).execute()

                # ===== CREATE TICKET =====
                neg_summary = "\n".join(
                    f"{n['category']} (rating {n['rating']}): {n['comment'] or '(no comment)'}"
                    for n in negatives
                )

                supabase.table("tickets").insert({
                    "student_id": student_id,
                    "subject": f"Negative Feedback Alert - {subject}",
                    "description": f"""
Feedback ID: {feedback_id}

Negative Categories:
{neg_summary}

Follow-up Message:
{body}
""",
                    "status": "open",
                    "created_at": datetime.now(timezone.utc).isoformat()
                }).execute()

                # ===== MARK AS PROCESSED =====
                supabase.table("feedback").update({
                    "processed": True,
                    "processed_at": datetime.now(timezone.utc).isoformat()
                }).eq("id", feedback_id).execute()

                print(f"Processed feedback {feedback_id}")

        except Exception as e:
            print("Worker Error:", e)

        await asyncio.sleep(POLL_INTERVAL)


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(process_negative_feedback())


@app.get("/health")
def health():
    return {"status": "running"}