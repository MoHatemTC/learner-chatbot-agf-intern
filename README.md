# Session Reminder Agent
An autonomous AI Agent that monitors a Supabase schedule and posts professional reminders to Circle.so.

## Setup
1. Clone the repo.
2. Install dependencies: `pip install -r requirements.txt`
3. Add `SUPABASE_URL` and `SUPABASE_KEY` to your `.env` file.
4. Run: `python reminder_agent.py`

## Architecture
- **Database:** Supabase (PostgreSQL)
- **Framework:** CrewAI
- **Engine:** GPT-4o (OpenAI)
