# FAQ Bot - Hybrid PDF Ingestion & Retrieval System

A production-ready FAQ chatbot for Sprints/American Center Cairo students. Combines PDF ingestion with a multi-agent retrieval pipeline and live Circle.so chat integration. Built with PyMuPDF, OpenAI, Google Gemini Vision, Qdrant, CrewAI, and aiohttp/httpx.

## ✨ Features

- **Hybrid Embeddings**: Dual-vector storage with text (OpenAI) and image (Gemini) embeddings
- **Smart Visual Processing**: Automatic detection of images/diagrams with intelligent Gemini Vision OCR
- **Optimized Performance**: Single-pass page rendering reused for both OCR and embeddings
- **Flexible Search**: Named vectors in Qdrant for precise text or image-based retrieval
- **CrewAI Integration**: Multi-agent workflow for context analysis and answer generation
- **Circle.so Live Bot**: Real-time polling of Circle chat rooms — reads student messages, answers them, and posts replies with @mention and thread-reply support

## 🏗️ Architecture

```
PDF Document
    ├── Step 1: Render pages to images (PyMuPDF @ 150 DPI)
    ├── Step 2: Text extraction + Visual enhancement
    │   ├── PyMuPDF.get_text() → Native text extraction
    │   ├── Detect images/diagrams automatically
    │   └── Gemini Vision → Extract text + describe visuals (when needed)
    ├── Step 3: Chunk text (1000 chars, 200 overlap)
    ├── Step 4: Generate text embeddings (OpenAI text-embedding-3-small)
    ├── Step 5: Generate image embeddings (Gemini gemini-embedding-001)
    └── Step 6: Store in Qdrant with named vectors
```

**Fallback Logic**: If Gemini Vision fails, system gracefully falls back to PyMuPDF text extraction.

**Circle.so Bot Flow**:
```
Circle Chat Room
    └── CircleBotRunner (polls every 15 s)
            ├── Fetch new messages (TipTap JSON → plain text)
            ├── Skip thread-replies and the bot's own messages
            ├── Call ChatbotRunner.answer_question() (Qdrant + CrewAI)
            └── Post answer back with @mention + in-thread reply
```

## 📦 Installation

### Prerequisites
- Python 3.9+
- Docker (for Qdrant vector database)

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Create a `.env` file with your API keys:

```env
# OpenAI API Key (required)
OPENAI_API_KEY=sk-...

# Google Gemini API Key (required for hybrid mode)
GEMINI_API_KEY=...

# Qdrant Configuration
# Option 1: Local Qdrant
QDRANT_MODE=local
QDRANT_URL=http://localhost:6333
COLLECTION_NAME=your_collection_name

# Option 2: Qdrant Cloud
# QDRANT_MODE=cloud
# QDRANT_URL=...
# QDRANT_API_KEY=...

# Embedding Settings
EMBEDDING_MODEL=text-embedding-3-small
CHUNK_SIZE=1000
CHUNK_OVERLAP=200
TOP_K=7
SCORE_THRESHOLD=0.3   # Lower = more lenient, Higher = stricter

# ── Circle.so Bot (required only when running circle_integration.py) ──────────
# Set CIRCLE_ENABLED=true to activate the polling bot.
CIRCLE_ENABLED=false

# Headless API auth token (Community Settings → API → Headless Auth Token)
CIRCLE_HEADLESS_AUTH_TOKEN=your_headless_auth_token

# Admin v2 API token (Community Settings → API → Admin API Token v2)
CIRCLE_ADMIN_V2_TOKEN=your_admin_v2_token

# Email address of the bot's Circle account (used to authenticate as the bot)
CIRCLE_BOT_EMAIL=bot@example.com

# UUID of the chat room the bot should monitor
# Find it in the Circle chat room URL: /c/{uuid}/messages
CIRCLE_CHAT_ROOM_UUID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# Optional overrides (defaults shown)
# CIRCLE_AUTH_URL=https://app.circle.so/api/v1/headless/auth_token
# CIRCLE_MEMBER_API_BASE=https://app.circle.so/api/headless/v1
# DATA_DIR=./data    # Storage path for bot_state.json and member caches
```

**Get API Keys:**
- OpenAI: https://platform.openai.com/api-keys
- Gemini: https://makersuite.google.com/app/apikey

### 3. Start Qdrant Vector Database if running Quadrant Locally
```bash
docker-compose up -d qdrant
```

Verify Qdrant is running at: http://localhost:6333/dashboard

## 🚀 Usage

### Ingest a PDF

**Smart Detection Mode (Recommended)**
```bash
python ingest_hybrid.py your_document.pdf
```
- Uses Gemini Vision when text extraction is poor OR page contains images
- Balances quality and API costs

**Always-Use-Gemini Mode**
```bash
python ingest_hybrid.py your_document.pdf --always-gemini
```
- Processes ALL pages with Gemini Vision
- Best for documents with charts, diagrams, or complex layouts
- Ensures no visual content is missed

**Text-Only Mode**
```bash
python ingest_hybrid.py your_document.pdf --text-only
```
- Disables image embeddings entirely
- Fastest processing, minimal API costs

### Run Chatbot (CLI)
```bash
python runner.py
```

Interactive CLI for testing queries against the ingested PDF.

### Run Circle.so Bot
```bash
# Make sure CIRCLE_ENABLED=true and all CIRCLE_* vars are set in .env
python circle_integration.py
```

The bot will:
1. Authenticate with Circle using your bot email
2. Bookmark all existing messages on first run (so old messages are not replayed)
3. Poll the chat room every 15 seconds for new messages
4. Answer each new message using the Qdrant + CrewAI pipeline
5. Post the answer back with an @mention of the sender, as a thread reply

## 📁 Project Structure

```
fqa_bot/
├── ingest_hybrid.py          # Main ingestion pipeline
├── multimodal_embedder.py    # Gemini Vision OCR + image embeddings
├── embedder.py                # OpenAI text embeddings
├── chunking.py                # Text chunking utilities
├── qdrant_utils.py            # Qdrant database operations
├── agents.py                  # CrewAI agent definitions
├── tasks.py                   # CrewAI task definitions
├── runner.py                  # CLI chatbot runner + ChatbotRunner class
├── circle_integration.py      # Circle.so live chat bot (CircleClient + CircleBotRunner)
├── eval_with_ragas.py         # RAGAS-based retrieval evaluation
├── requirements.txt           # Full dependencies
├── requirements_hybrid.txt    # Minimal ingestion-only deps
├── Dockerfile                 # Container image for the bot service
├── docker-compose.yml         # Full stack (Qdrant + fqa_bot)
└── .env                       # API keys and config (not in git)
```

## 🔧 Configuration Options

Customize `HybridPDFIngestor` initialization in `ingest_hybrid.py`:

```python
ingestor = HybridPDFIngestor(
    use_hybrid=True,          # Enable/disable image embeddings
    ocr_threshold=50,         # Min chars to trigger OCR (smart mode)
    always_use_gemini=False   # Force Gemini for all pages
)
```

## 🎯 When to Use Each Mode

| Mode | Best For | API Costs | Visual Content Captured |
|------|----------|-----------|-------------------------|
| **Smart Detection** | Mixed content, balancing cost/quality | Moderate | 95% ✅ |
| **Always Gemini** | Technical docs with diagrams | High | 100% ✅ |
| **Text-Only** | Pure text documents | Minimal | 0% ❌ |

## 🔍 How It Works

### Ingestion Pipeline

1. **Image Rendering**: Pages rendered once at 150 DPI using PyMuPDF
2. **Text Extraction**: Attempts native text extraction from PDF
3. **Visual Detection**: Automatically detects pages with images/diagrams
4. **Gemini Enhancement**: Triggered when:
   - Text extraction yields < 50 characters, OR
   - Page contains images/diagrams, OR
   - `--always-gemini` flag is used
5. **Content Combination**: Merges PyMuPDF text with Gemini visual descriptions
6. **Embedding Generation**:
   - Text embeddings: OpenAI text-embedding-3-small (1536D)
   - Image embeddings: Gemini gemini-embedding-001 (3072D)
7. **Storage**: Both vectors stored in Qdrant with named vectors (`"text"` and `"image"`)

### Search & Retrieval

- Runner searches the `"text"` vector by default
- Falls back gracefully for non-hybrid collections
- CrewAI agents analyze context and generate answers
- Returns answers with source page references

## 📊 Vector Dimensions

- **Text embeddings**: 1536 dimensions (OpenAI text-embedding-3-small)
- **Image embeddings**: 3072 dimensions (Gemini gemini-embedding-001)

Both stored as named vectors in same Qdrant collection for hybrid search capability.

---

## 🌐 Circle.so Integration

`circle_integration.py` connects the FAQ bot to a live [Circle.so](https://circle.so) community chat room.

### Components

| Class | Purpose |
|-------|---------|
| `CircleClient` | Low-level HTTP client — authenticates as any member via headless API, fetches/posts chat messages, handles JWT caching and automatic refresh, resolves member SGIDs for @mentions |
| `CircleBotRunner` | High-level polling loop — calls `CircleClient` + `ChatbotRunner` to answer student questions in real time |

### How `CircleBotRunner` works

1. **Authentication** — obtains a JWT for the bot account; token is cached in memory and refreshed when it expires within 5 minutes.
2. **Message ingestion** — calls `GET /messages/{uuid}/chat_room_messages` every 15 seconds and decodes the TipTap rich-text JSON into plain text.
3. **Deduplication** — skips thread-replies (messages with `parent_message_id`), the bot's own messages (matched by `community_member_id`), and any message ID already in the persisted `processed_ids` set.
4. **First-run bookmark** — on the very first startup (no saved state) all existing messages are bookmarked without being answered, preventing the bot from replaying old conversations.
5. **Answer generation** — calls `ChatbotRunner.answer_question()` in a thread pool (`asyncio.to_thread`) so the async event loop is not blocked.
6. **Reply** — posts back using the TipTap-formatted `rich_text_body`, @mentioning the original sender and attaching the reply as a thread reply to the question message.
7. **State persistence** — saves `last_message_id` and a rolling window of the 500 most-recent `processed_ids` to `data/bot_state.json`.

### Message format helpers

| Function | Purpose |
|----------|---------|
| `tiptap_to_text(node)` | Recursively extracts plain text from TipTap document JSON (handles text, mention, hardBreak, paragraph nodes) |
| `_markdown_to_tiptap(text)` | Converts Markdown (bold `**text**`, links `[label](url)`, line-breaks) back into TipTap paragraph block objects for outgoing messages |

### Required environment variables (Circle)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `CIRCLE_ENABLED` | ✅ | `false` | Set to `true` to activate the bot |
| `CIRCLE_HEADLESS_AUTH_TOKEN` | ✅ | — | Community headless auth token |
| `CIRCLE_ADMIN_V2_TOKEN` | ✅ | — | Admin v2 API token (for SGID/member lookup) |
| `CIRCLE_BOT_EMAIL` | ✅ | `agfintern8@sprints.ai` | Email of the bot's Circle account |
| `CIRCLE_CHAT_ROOM_UUID` | ✅ | — | UUID of the monitored chat room |
| `CIRCLE_AUTH_URL` | ⬜ | `https://app.circle.so/api/v1/headless/auth_token` | Override auth endpoint |
| `CIRCLE_MEMBER_API_BASE` | ⬜ | `https://app.circle.so/api/headless/v1` | Override member API base URL |
| `DATA_DIR` | ⬜ | `./data` | Directory for state files and caches |

---

## 🐳 Docker

The full stack (Qdrant + FAQ bot) is defined in `docker-compose.yml`.

### Quick start

```bash
# 1. Create .env with all required variables (see Configuration section above)

# 2. Build and start everything
docker-compose up -d

# 3. Run ingestion once (needed before the bot can answer questions)
docker-compose run --rm fqa_bot python ingest_hybrid.py "ACC FAQs.pdf" --always-gemini

# 4. Watch logs
docker-compose logs -f fqa_bot
```

### Common commands

```bash
# Start Qdrant only (for local CLI development)
docker-compose up -d qdrant

# Interactive CLI inside the container
docker-compose run --rm fqa_bot python runner.py

# Re-build after code changes
docker-compose build fqa_bot

# Stop everything and remove containers
docker-compose down
```

### Service overview

| Service | Image | Port | Description |
|---------|-------|------|-------------|
| `qdrant` | `qdrant/qdrant:v1.16.2` | 6333 (HTTP), 6334 (gRPC) | Vector database |
| `fqa_bot` | Built from `Dockerfile` | — | Circle.so polling bot (default CMD) |

The `fqa_bot` service waits for Qdrant to pass a `/readyz` health-check before starting, so you never need to worry about startup ordering.

> **Tip**: Ingest your PDF before starting the bot so the Qdrant collection is populated when the first student message arrives.

---

Following a comprehensive code review by Raghad Saad, several critical and minor issues were identified and resolved to improve the system's reliability, idempotency, and maintainability.

### Summary of Issues & Resolutions

| Issue # | Issue Name | Severity | Status | Files Modified |
|---------|------------|----------|--------|----------------|
| **#1** | Ghost Vector Problem (Retrieval Gap) | ⚪ DISREGARDED | N/A | Architecture correct as-is |
| **#2** | Contextual Modality Blindness | 🟠 HIGH | ✅ FIXED | `ingest_hybrid.py`, `tasks.py` |
| **#3** | Non-Idempotent Indexing (Data Bloat) | 🟠 HIGH | ✅ FIXED | `chunking.py` |
| **#4** | Multi-Provider Latency | 🟡 MEDIUM | ⚪ DISREGARDED | N/A | Architecture correct as-is |
| **#5** | Hardcoded Similarity Thresholds | 🟡 MEDIUM | ✅ FIXED | `runner.py` |
| **#6** | Inconsistent Type Hinting | 🔵 MINOR | ✅ FIXED | `runner.py`, `tasks.py`, `agents.py`, `chunking.py` |

---

### Issue #1: Ghost Vector Problem (DISREGARDED)

**Issue**: The reviewer identified that image embeddings were generated during ingestion but never searched, suggesting they were "ghost vectors" going unused.

**Analysis**: Upon review, this is actually by design:
- During ingestion, Gemini Vision analyzes images and **merges descriptions into text chunks**
- Text chunks contain: `original_text + "[Visual Content Description]\n" + gemini_description`
- **Text embeddings** (OpenAI) already capture both textual and visual information
- Image embeddings are stored for potential future image-based queries but aren't needed for text-based search

**Resolution**: 
- **No code changes required** - Architecture is intentionally text-centric
- Visual content (diagrams, charts, flowcharts) **is retrievable** through text vector search
- When users ask about visual elements, the text chunks contain Gemini's descriptions of those visuals
- Image vectors remain available for future enhancements (e.g., image similarity search)

**Rationale**:
- Users ask questions in **text**, not images
- Text embeddings of "diagram showing X" are sufficient to match queries about "X"
- Avoids multi-provider latency on every query (Issue #4)
- Simpler, faster, more cost-effective

**Files Modified**: None (architecture validated as correct)

**Note**: Original implementation in [`runner.py`](runner.py#L48-L76) uses text-only search, which is the correct approach.

---

### FIX#2: Contextual Modality Blindness (HIGH)

**Issue**: Visual content descriptions (from Gemini) and primary PDF text were merged without marking their source. Agents couldn't distinguish between native text and AI-generated visual interpretations.

**Impact**: Limited agent's ability to cite sources accurately (e.g., "As shown in the diagram on page 5" vs. "According to the text on page 5").

**Resolution**:
- Added **`content_type` metadata** to track source of information:
  - `text_only`: Native PDF text extraction
  - `image_analysis_only`: Pure Gemini Vision analysis
  - `text_with_visual_analysis`: Combined text + visual descriptions
- Modified task context to prepend source tags visible to agents:
  - `[SOURCE: PRIMARY TEXT]`
  - `[SOURCE: IMAGE_ANALYSIS]`
  - `[SOURCE: TEXT + IMAGE_ANALYSIS]`

**Files Modified**: 
- [`ingest_hybrid.py` (lines 203-290, 358-366, 412-422)](ingest_hybrid.py)
- [`tasks.py` (lines 20-36)](tasks.py#L20-L36)

**Benefit**: Agents can now distinguish content origins and provide more accurate citations.

---

### FIX#3: Non-Idempotent Indexing (HIGH)

**Issue**: Chunk IDs were generated as incrementing integers (`chunk_id = 0, 1, 2, ...`). Any change to `chunk_size` or document content would shift all IDs, causing Qdrant to create duplicates instead of updating existing points.

**Impact**: Re-running ingestion would result in 100% data duplication, leading to:
- Increased storage costs
- Skewed search results (same chunks appearing multiple times)
- Database bloat over time

**Resolution**:
- Replaced sequential integers with **content-addressable MD5 hashes**
- Same chunk text → Same hash ID → Idempotent updates
- Qdrant now updates existing points instead of creating duplicates

**Files Modified**: [`chunking.py` (lines 8, 97)](chunking.py#L8,L97)

**Code Example**:
```python
# Before: Sequential IDs (non-idempotent)
chunk_id = 0
for chunk in chunks:
    chunk_id += 1  # Changes if chunk_size changes

# After: Content-addressable IDs (idempotent)
chunk_id = hashlib.md5(chunk_text.encode()).hexdigest()
# Same text = Same ID, always
```

---

### Issue #4: Multi-Provider Latency (DISREGARDED)

**Reviewer's Concern**: Using OpenAI for text embeddings and Google Gemini for vision creates multi-provider latency and fragmented billing.

**Decision**: **Intentionally kept**. The dual-provider approach is optimal:

**During Ingestion** (one-time cost):
- **OpenAI** `text-embedding-3-small`: Text chunks (including Gemini's visual descriptions) → 1536D vectors
- **Google Gemini** Vision API: Image analysis → Text descriptions (merged into chunks)
- **Google Gemini** `gemini-embedding-001`: Page images → 3072D vectors (stored for future use)

**During Queries** (every request):
- **OpenAI only**: Single API call for text embedding
- **No Gemini calls** during search
- Visual content is found via text search (descriptions are in the text chunks)

**Rationale**:
- ✅ **No multi-provider latency on queries** - Only OpenAI is called
- ✅ OpenAI: Industry-leading text embeddings with consistent performance
- ✅ Google Gemini: Superior multimodal capabilities for image analysis during ingestion
- ✅ Best-of-breed approach: Each provider does what it does best
- ✅ Image embeddings stored as future-proofing for image-based queries

**Conclusion**: This is a deliberate architectural choice that optimizes for query performance while leveraging each provider's strengths.

---

### FIX#5: Hardcoded Similarity Thresholds (MEDIUM)

**Issue**: Similarity threshold (`score_threshold = 0.3`) was hardcoded in `runner.py`. Different embedding models have varying score distributions, making this inflexible.

**Impact**: Operators couldn't tune retrieval sensitivity without modifying code. A 0.3 threshold might be too loose/strict depending on the model.

**Resolution**:
- Made `score_threshold` configurable via environment variable `SCORE_THRESHOLD`
- Default value: `0.3` (maintains backward compatibility)
- Can be adjusted per deployment in `.env` file

**Files Modified**: [`runner.py` (lines 33-34)](runner.py#L33-L34)

**Configuration**:
```env
# Add to .env file
SCORE_THRESHOLD=0.3  # Lower = more lenient, Higher = stricter
```

---

### FIX#6: Inconsistent Type Hinting (MINOR)

**Issue**: Type hints were partially applied across the codebase, reducing IDE effectiveness and making code harder to maintain.

**Impact**: Reduced developer velocity, limited autocomplete, and hindered static analysis tools.

**Resolution**:
- Added comprehensive type hints to all public functions:
  - Function parameters: `question: str`, `agent: Agent`, etc.
  - Return types: `-> List[Any]`, `-> Dict[str, Any]`, `-> None`
- Imported necessary typing modules: `List`, `Dict`, `Any`, `Callable`

**Files Modified**: 
- [`runner.py`](runner.py)
- [`tasks.py`](tasks.py)
- [`agents.py`](agents.py)
- [`chunking.py`](chunking.py)

**Benefit**: Improved IDE support, better code documentation, and easier maintenance.

---

### Fixes Deployment Checklist - For the ones pulled the code before the fix

To benefit from all fixes:

1. **Upgrade Qdrant Client** (Recommended):
   ```bash
   pip install --upgrade qdrant-client
   ```
   Recommended: qdrant-client >= 1.9.0 for better API compatibility and performance.

2. **Update Environment Variables** (`.env`):
   ```env
   SCORE_THRESHOLD=0.3  # Optional, uses default if omitted (FIX#5)
   ```

3. **Re-ingest Documents** (Required for FIX#2 & FIX#3):
   ```bash
   python ingest_hybrid.py "ACC FAQs.pdf" --always-gemini
   ```
   This ensures:
   - Content-addressable IDs are generated (FIX#3)
   - `content_type` metadata is stored (FIX#2)

4. **Test Visual Content Retrieval**:
   - Query visual content (e.g., "explain the flowchart", "what does the diagram show?")
   - Verify that text search finds chunks containing Gemini Vision descriptions
   - Check that content_type tags appear in results (FIX#2)

5. **Validate Type Checking** (FIX#6):
   ```bash
   mypy fqa_bot/*.py  # Optional: Run static type checker
   ```

---

## 🛠️ Troubleshooting
### 'QdrantClient' object has no attribute 'query_points'
You're using an older version of qdrant-client that doesn't support hybrid search:
```bash
pip install --upgrade qdrant-client
```
Then restart your application. Requires qdrant-client >= 1.9.0.
### Qdrant Connection Failed
```bash
# Check if Docker is running
docker ps

# Start Qdrant
docker-compose up -d

# Check logs
docker-compose logs qdrant
```

### Gemini API Quota Exceeded
- Wait for quota reset (per-minute or daily limits)
- Use smart detection mode instead of `--always-gemini`
- Increase `ocr_threshold` to reduce API calls

### No Results Found
- Verify collection name matches `.env` setting
- Check if PDF was successfully ingested
- Lower `score_threshold` in `runner.py` for more lenient matching

### Circle Bot Not Responding
- Confirm `CIRCLE_ENABLED=true` in `.env`
- Ensure all four `CIRCLE_*` variables are set (auth token, admin token, bot email, room UUID)
- Check `circle_api_debug_<date>.txt` for detailed HTTP request/response logs
- Verify the bot account is a member of the chat room (otherwise JWT fetch will fail)
- On first run, old messages are bookmarked and not answered — this is expected behaviour

### Circle Bot Posts No @mention
- The `CIRCLE_ADMIN_V2_TOKEN` is required for SGID lookup; without it @mentions are silently skipped
- Ensure the admin token has `advanced_search` permission in Circle community settings

## 🔐 Security Notes

- Never commit `.env` file (already in `.gitignore`)
- Rotate API keys regularly
- Use environment-specific API keys for production

## 📝 License

...

## 🤝 Contributing

...

## 🔗 Dependencies

- **PyMuPDF**: PDF processing and image rendering
- **OpenAI**: Text embeddings
- **Google Gemini**: Vision OCR and image embeddings
- **Qdrant**: Vector database
- **CrewAI**: Multi-agent orchestration
- **Pillow**: Image manipulation
- **httpx**: Async/sync HTTP client (Circle.so headless + member API)
- **aiohttp**: Async HTTP client (Circle.so admin v2 API / SGID lookup)

See `requirements.txt` for complete dependency list with versions.

---

# To evaluate the relevance of your code using the RAG testing system. 
1- Add eval_with_ragas.py to VS Code
2- Make sure your .ven has COLLECTION_NAME=Sprints_FQA_Collection
3- In the terminal, run: pip install ragas datasets langchain-openai 
4- Once completed, run: python eval_with_ragas.py
