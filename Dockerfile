FROM python:3.11-slim

# Ensure real-time logging
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/app/data

# Root of the repo inside the container
WORKDIR /app

# System deps (if needed later, can extend)
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first for better caching
COPY learner-chatbot-agf-intern/requirements.txt /app/learner-chatbot-agf-intern/requirements.txt
RUN pip install --no-cache-dir -r /app/learner-chatbot-agf-intern/requirements.txt

# Copy the whole repo (including learner-chatbot-agf-intern)
COPY . /app

# Ensure data directory exists and is writable
RUN mkdir -p /app/data \
    && chmod -R 777 /app/data

# Work inside the learner-chatbot-agf-intern project
WORKDIR /app/learner-chatbot-agf-intern

# Default command: run the reminder agent
CMD ["python", "reminder_agent.py"]
