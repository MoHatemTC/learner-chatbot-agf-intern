# ══════════════════════════════════════════════════════════════
# Stage 3 — Dockerization
# ══════════════════════════════════════════════════════════════
# This Dockerfile is the Stage 3 addition to the project.
# Stage 1 built the core PDF ingestion + CrewAI retrieval pipeline.
# Stage 2 added the Circle.so live chat integration (circle_integration.py).
#
# Stage 3 packages the full application into a container image so
# the Circle bot and Qdrant can be deployed as a reproducible stack
# using docker-compose.yml.
# ══════════════════════════════════════════════════════════════

# ── Build stage ────────────────────────────────────────────────────────────────
# Python 3.11-slim keeps the image small while providing a recent runtime.
# PyMuPDF ships pre-compiled manylinux wheels, so no extra C libraries are needed.
FROM python:3.11-slim AS builder

WORKDIR /app

# Install pip build tools and any OS-level headers required to compile any
# package that does not ship a binary wheel (rare, but defensive).
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first so Docker can cache the pip layer independently of
# source-code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt


# ── Runtime stage ──────────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages and binaries from builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source
COPY . .

# Persistent volume for bot state (bot_state.json, SGID cache, member lists)
# and for Circle debug logs written at runtime.
RUN mkdir -p /app/data /app/logs

# DATA_DIR is read by circle_integration.py and can be overridden at runtime.
ENV DATA_DIR=/app/data

# ── Default command: run the Circle.so polling bot ─────────────────────────────
# Override with `docker run ... python runner.py` for the interactive CLI, or
# `python ingest_hybrid.py <file.pdf>` to run ingestion.
CMD ["python", "circle_integration.py"]
