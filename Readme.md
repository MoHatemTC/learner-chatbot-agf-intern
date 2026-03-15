#  Circle Learner Progress Bot

An AI-powered bot for the Circle.so community that automatically checks student weekly progress and delivers personalized feedback messages using CrewAI agents.

---

##  Overview

The bot listens for @mentions in a Circle chat room. When a mentor or admin asks for a student's weekly progress, it:

1. Fetches the student's progress data from Supabase
2. Compares it against weekly targets
3. Uses a CrewAI agent (powered by OpenAI) to generate a personalized, motivating message
4. Posts the reply back in the Circle chat room, mentioning the requester

---

##  Project Structure

```
learner-chatbot-agf-intern/
├── circle_bot.py              # Main bot listener — polls Circle for messages
├── circle_integration.py      # Circle.so API client wrapper
├── Weekly_Progress_Agent.py   # CrewAI agent that generates progress messages
├── fetch_student_data.py      # Fetches student data from Supabase
├── compute_status.py          # Compares progress against targets
├── intent_parser.py           # Parses @mention messages to extract intent
├── Dockerfile                 # Docker container definition
├── .dockerignore              # Files excluded from Docker image
├── requirements.txt           # Python dependencies
└── .env                       # Environment variables (never commit this)
```

---

## ⚙️ How It Works

```
User @mentions bot in Circle
        ↓
intent_parser.py extracts student_id + week
        ↓
fetch_student_data.py fetches from Supabase
        ↓
compute_status.py computes on_track / behind
        ↓
Weekly_Progress_Agent.py generates message via CrewAI
        ↓
Bot posts reply in Circle chat
```

### Trigger Format
To trigger the bot, send a message in the Circle chat room:
```
@Bot 1 check progress for student <UUID> week <N>
```

Example:
```
@Bot 1 check progress for student 57fddfdd-bf6d-4cc9-a533-362c09424ab7 week 3
```

---

##  Tech Stack

| Component | Technology |
|-----------|------------|
| Bot runtime | Python + asyncio |
| AI agent | CrewAI + OpenAI GPT |
| Database | Supabase (PostgreSQL) |
| Community platform | Circle.so |
| Containerization | Docker |

---

##  Setup & Installation

### Prerequisites
- Python 3.11+
- Docker Desktop
- A Circle.so community with bot account
- Supabase project with `student progress` and `weekly targets` tables
- OpenAI API key

### 1. Clone the repository
```bash
git clone <your-repo-url>
cd learner-chatbot-agf-intern
```

### 2. Create your `.env` file
```bash
cp .env.example .env
```
Fill in your credentials (see Environment Variables section below).

### 3. Run with Docker (recommended)
```bash
# Build the image
docker build -t circle-bot .

# Run the bot
docker run --env-file .env circle-bot
```

### 4. Run locally (without Docker)
```bash
pip install -r requirements.txt
python circle_bot.py
```

---

##  Environment Variables

Create a `.env` file in the project root with the following variables:

```env
# Supabase
SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_supabase_anon_key

# OpenAI
OPENAI_API_KEY=your_openai_api_key

# Circle.so
CIRCLE_ENABLED=true
CIRCLE_HEADLESS_AUTH_TOKEN=your_circle_headless_token
CIRCLE_ADMIN_V2_TOKEN=your_circle_admin_token
CIRCLE_AUTH_URL=https://app.circle.so/api/v1/headless/auth_token
CIRCLE_MEMBER_API_BASE=https://app.circle.so/api/headless/v1
CIRCLE_BOT_EMAIL=your_bot_email@example.com
CIRCLE_CHAT_SPACE_ID=your_space_id
CIRCLE_CHAT_ROOM_UUID=your_chat_room_uuid
```

>  **Never commit your `.env` file.** It contains sensitive API keys and tokens.

---

##  Database Schema

The bot expects two tables in Supabase:

### `student progress`
| Column | Type | Description |
|--------|------|-------------|
| Student_Id | UUID | Student identifier |
| Week_Nu | Integer | Week number |
| Vedios_Nu | Integer | Videos watched |
| Quiz_Nu | Integer | Quizzes completed |
| Quize_Average_Grade | Float | Average quiz grade (0–1) |
| Task_Nu | Integer | Tasks completed |
| Task_Average_Grade | Float | Average task grade (0–1) |
| Project_Nu | Integer | Projects completed |
| Project_Average_Grade | Float | Average project grade (0–1) |

### `weekly targets`
| Column | Type | Description |
|--------|------|-------------|
| Week_Nu | Integer | Week number |
| Vedios_Target | Integer | Target videos to watch |
| Quiz_Target | Integer | Target quizzes to complete |
| Task_Target | Integer | Target tasks to complete |
| Project_Target | Integer | Target projects to complete |

---

## Progress Status Logic

| Condition | Status |
|-----------|--------|
| All completion rates ≥ 70% AND all grades ≥ 80% | `on_track` ✅ |
| Any completion rate < 70% OR any grade < 80% | `behind` ⚠️ |

Grades are only evaluated when the student has completed enough work (≥ 70% completion). A student who completed 0 quizzes won't be flagged for poor quiz grades.

---

##  Docker

The bot is fully containerized. The image is based on `python:3.11-slim` for a lightweight footprint.

```bash
# Build
docker build -t circle-bot .

# Run
docker run --env-file .env circle-bot

# Check running containers
docker ps

# View live logs
docker logs -f <container_id>

# Stop the bot
docker stop <container_id>
```

---

##  Dependencies

```
crewai
supabase
python-dotenv
openai
```

---

##  Security Notes

- Never commit `.env` to version control
- Rotate your API keys immediately if they are ever exposed
- The Docker image does not bake in any secrets — they are passed at runtime via `--env-file`

---

## 👤 Author

Built as part of the AGF Internship Program.