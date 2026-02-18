# US Embassy Sprints: Session Reminders Agent

An automated, AI-driven reminder system built with **CrewAI**, **Supabase**, and **APScheduler**. This agent monitors study schedules and posts community reminders only when a session is about to begin.

## 🚀 Overview
The system runs as a background service that checks the database every hour. It uses a "Lead Study Coordinator" agent to determine if a session is starting within a specific window (90 minutes) and drafts a professional announcement for the students.



## 🛠️ Tech Stack
- **Orchestration:** CrewAI (Agentic logic)
- **Database:** Supabase (PostgreSQL)
- **Scheduling:** APScheduler
- **Environment:** Python 3.11+

## 📋 Features
- **Smart Filtering:** Prevents spam by only posting reminders within a 90-minute window of the session start time.
- **Error Resilience:** Robust error handling for database connection failures and API timeouts.
- **Automated Scheduling:** Runs 24/7 with a 1-hour heartbeat check.
- **Professional Tone:** Uses OpenAI's LLM to generate warm, engaging community posts.

## ⚙️ Setup Instructions
1. **Clone the repository:**
   ```bash
   git clone 
   cd learner-chatbot-agf-intern

2. Install dependencies:
   pip install -r requirements.txt

3. Configure Environment:
Create a .env file with the following keys:
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_service_role_key
OPENAI_API_KEY=your_openai_key

4. Run the Agent:
python reminder_agent.py

🗄️ Database Schema Requirement
The Supabase table (defined as schedule) must contain:

session_date (Format: YYYY-MM-DD)

session_time (Format: HH:MM AM/PM, e.g., "10:00 PM")

topic (String)

expert_name (String)
