Architecture Overview

Supabase (feedback table)
        ↓
FastAPI Background Worker
        ↓
Check: min_rating < 0 AND processed = false
        ↓
Generate follow-up (OpenAI)
        ↓
Insert into followups table
Insert into tickets table
Update feedback.processed = true

Project Structure

FeedbackAgent/
│
├── app/
│   ├── main.py
│   └── __pycache__/
│
├── db_test.py
├── .env
├── .venv/
├── README.md

Agent trigger condition: min_rating < 0 AND processed = false

Create a .env file in the project root:

DATABASE_URL=postgresql://postgres.ksolcmbvogpzqzoklupc:ZhkhYP2EOE4Q1MR8@aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres
SUPABASE_URL=https://ksolcmbvogpzqzoklupc.supabase.co
SUPABASE_SERVICE_ROLE_KEY=sb_publishable_Tu917rlIR9qdw53y8G23dg_UhPT5dKN
OPENAI_API_KEY=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

Installation:
1- python -m venv .venv
2- .\.venv\Scripts\Activate.ps1
3- python -m pip install --upgrade pip
python -m pip install fastapi uvicorn supabase openai python-dotenv pandas "psycopg[binary]"

4- from project root: python -m uvicorn app.main:app --reload

5- Health Check: http://127.0.0.1:8000/health
