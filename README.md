Feedback Recovery Agent

An automated system that monitors student feedback stored in Supabase, detects negative ratings, generates AI-powered follow-up messages, and posts alerts to a Circle community chat room.

The system uses FastAPI, Supabase, OpenAI, and the Circle Headless API.

Architecture Overview
Student Feedback → Supabase (feedback table)
                         │
                         │ polling worker
                         ▼
             Feedback Recovery Agent (FastAPI)
                         │
             ├── Detect negative ratings
             │
             ├── Generate follow-up message (OpenAI)
             │
             ├── Create support ticket (Supabase)
             │
             ├── Log follow-up (Supabase)
             │
             └── Send alert message to Circle chat
Features

Detects negative feedback automatically

Generates follow-up messages using OpenAI

Creates support tickets in Supabase

Logs follow-up messages

Sends alerts to Circle community chat

Provides API endpoints for testing and debugging

Background worker automatically processes feedback

Tech Stack
Component	Technology
Backend	FastAPI
Database	Supabase (PostgreSQL)
AI	OpenAI API
Community Integration	Circle Headless API
Language	Python
Project Structure
FeedbackAgent
│
├── app
│   ├── main.py                 # FastAPI application
│   ├── config.py               # Environment validation
│   └── circle_integration.py   # Circle API client
│
├── .env                        # Environment variables
├── .env.example                # Environment template
├── requirements.txt            # Python dependencies
└── README.md
Environment Configuration

Create a .env file in the project root.

Example configuration:

# Supabase
SUPABASE_URL=your_supabase_url
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key

# OpenAI
OPENAI_API_KEY=your_openai_api_key

# Circle Integration
CIRCLE_ENABLED=true
CIRCLE_HEADLESS_AUTH_TOKEN=your_circle_headless_token
CIRCLE_ADMIN_V2_TOKEN=your_circle_admin_token
CIRCLE_COMMUNITY_ID=your_circle_community_id
CIRCLE_BOT_EMAIL=bot_email_in_circle

# Chat room configuration
CIRCLE_CHAT_ROOM_UUID=chat_room_uuid
Installation

Clone the repository and install dependencies.

git clone <repository_url>
cd FeedbackAgent

Create a virtual environment:

python -m venv .venv

Activate environment:

Windows
.venv\Scripts\activate
Mac/Linux
source .venv/bin/activate

Install dependencies:

pip install -r requirements.txt
Running the Application

Start the FastAPI server:

uvicorn app.main:app --reload

Server will run at:

http://127.0.0.1:8000

API documentation is available at:

http://127.0.0.1:8000/docs
API Endpoints
Health Check
GET /health

Returns:

{
  "status": "running"
}
Circle Configuration Check
GET /health/circle-config

Verifies Circle environment configuration.

Example response:

{
  "status": "ok",
  "message": "Circle configuration loaded"
}
Test Circle Chat Integration
POST /test/circle-chat

Sends a test message to the configured Circle chat room.

Expected result:

{
 "status": "ok",
 "circle_response": {
   "creation_uuid": "...",
   "sent_at": "..."
 }
}
Test Feedback Processing
POST /test/process-feedback/{feedback_id}

Processes a single feedback entry manually.

Example:

POST /test/process-feedback/2

This will:

Read feedback from Supabase

Detect negative ratings

Generate AI follow-up message

Send alert to Circle chat

Return the generated message

Example response:

{
 "status": "ok",
 "feedback_id": 2,
 "student_id": "...",
 "subject": "...",
 "body": "...",
 "circle_response": {...}
}
Automatic Processing Worker

The agent includes a background worker that runs every 20 seconds.

POLL_INTERVAL = 20

Worker actions:

Query Supabase feedback table

Detect rows where:

min_rating < 0
processed = false

Generate follow-up message

Send notification to Circle chat

Create ticket in Supabase

Log follow-up message

Mark feedback as processed

Supabase Database Tables
feedback

Stores raw student feedback.

Important fields:

id
student_id
min_rating
processed
processed_at
teaching
coursecontent
examination
labwork
library_facilities
extracurricular
followups

Stores AI generated follow-up messages.

feedback_id
student_id
message
created_at
tickets

Stores support tickets created from negative feedback.

student_id
subject
description
status
created_at
Circle Integration

The project integrates with Circle Headless API to send messages to a community chat room.

Workflow:

Authenticate using Headless Auth Token

Generate member access token

Send formatted chat message

Optionally mention community members

Circle client implementation is located in:

app/circle_integration.py
Testing the System

Recommended testing order:

1. Start the server
uvicorn app.main:app --reload
2. Verify health endpoint
GET /health
3. Verify Circle configuration
GET /health/circle-config
4. Send test Circle message
POST /test/circle-chat

Confirm message appears in Circle chat.

5. Process a feedback row
POST /test/process-feedback/{feedback_id}

Example:

POST /test/process-feedback/2

Confirm message appears in Circle.

6. Test automatic processing

Insert a feedback row in Supabase with:

min_rating = -1
processed = false

Within ~20 seconds the worker will:

generate follow-up

send Circle alert

create ticket

mark row processed

Logging

Circle API logs are stored in:

circle_api_debug_YYYYMMDD.txt

These logs help debug API responses.