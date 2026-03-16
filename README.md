## 🤖 Sprints Academic Coordinator Bot (Circle.so Integrated)

This repository hosts an automated AI-driven pipeline that bridges the gap between structured academic curricula and student engagement. It features an intelligent **CrewAI** agent that monitors a **Circle.so** chat room, identifies student queries, and provides real-time schedule updates.

---

### 📋 System Architecture

The system operates in a real-time loop to serve students directly where they communicate:

1. **Circle Integration:** The bot polls the Circle Headless API to monitor specific chat rooms for student mentions of program weeks (e.g., "AI Week 3").
2. **Contextual Processing:** The system identifies the student, extracts the relevant program (AI/ML or Mobile), and detects the specific week requested.
3. **CrewAI Intelligence:** A **Senior Academic Coordinator Agent** is triggered to:
    * Research session details, topics, and GMT+2 timings.
    * Format a professional, friendly response including Zoom links.
4. **Automated Response:** The bot replies directly to the student's message in Circle, using **TipTap JSON** formatting for @mentions and rich text.

---

### 🚀 Deployment & Usage

#### 1. Environment Configuration
Create a `.env` file in the root directory with the keys

for running the code type this in your terminal after running Docker Desktop:
# Build the image
docker build -t circle-bot .

# Run the container with persistent memory
docker run -d \
  --name sprints-bot \
  --env-file .env \
  -v ${PWD}/data:/app/data \
  circle-bot