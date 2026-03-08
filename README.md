US Embassy Sprints: Session Reminders Agent
An automated, AI-driven reminder system built with CrewAI, Supabase, and Ragas. This agent monitors study schedules, converts timezones, and ensures students receive factual, timely reminders via the Circle platform.

🚀 Overview
The system acts as a background coordinator that:

Fetches upcoming sessions from a Supabase PostgreSQL database.

Calculates localized times (Cairo to UAE) for international students.

Drafts reminders using a specialized CrewAI Agent.

Audits the output using the Ragas framework to ensure faithfulness and accuracy.

🛠️ Tech Stack
Orchestration: CrewAI (Agentic logic)

Database: Supabase (PostgreSQL)

Evaluation: Ragas (Automated RAG metrics)

Environment: Python 3.11+

LLM: GPT-4o-mini

📋 Features
Smart Timezone Handling: Automatically converts session times from Cairo Time (EET) to UAE Time (GST).

Agentic Formatting: Uses a "Strict Data Formatter" agent to ensure posts are factual and free of hallucinated "filler" text.

Automated Auditing: Every reminder generated is evaluated against the source database data using Faithfulness, Answer Relevancy, Context Precision, and Context Recall.

Persistence: Uses a local state file (sent_reminders.json) to prevent duplicate posts.

📊 Evaluation Logic
To maintain high data integrity, this project implements a Ragas evaluation pipeline. After generating reminders, the system creates a report (evaluation_report.csv) that scores the agent's output:

Metric	Purpose
Faithfulness	Ensures the agent didn't invent session details.
Answer Relevancy	Checks if the reminder actually addresses the session topic.
Context Recall	Verifies that all database facts (Zoom link, Expert name) were included.
⚙️ Setup Instructions
1. Clone the repository

Bash
git clone [https://github.com/your-username/learner-chatbot-agf-intern.git](https://github.com/MoHatemTC/learner-chatbot-agf-intern/edit/feature-session-reminders/README.md)
cd learner-chatbot-agf-intern
2. Install dependencies

Bash
pip install -r requirements.txt
3. Configure Environment

Create a .env file in the root directory (refer to .env.example):

Plaintext
OPENAI_API_KEY=your_openai_key
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_service_role_key
STATE_FILE=sent_reminders.json
4. Run the Agent

python main.py
🗄️ Database Schema Requirement
The Supabase table (defined as schedule) must contain the following columns:

id: Primary Key (Integer)

session_date: Date (Format: YYYY-MM-DD)

session_time: Text (Format: HH:MM AM/PM, e.g., "10:00 PM")

topic: Text

expert_name: Text

zoom_link: Text
