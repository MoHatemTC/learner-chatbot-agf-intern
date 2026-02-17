# FAQ Bot - Hybrid PDF Ingestion & Retrieval System

A production-ready PDF ingestion and retrieval system that combines text and visual understanding for comprehensive document processing. Built with PyMuPDF, OpenAI, Google Gemini Vision, and Qdrant vector database.

## ✨ Features

- **Hybrid Embeddings**: Dual-vector storage with text (OpenAI) and image (Gemini) embeddings
- **Smart Visual Processing**: Automatic detection of images/diagrams with intelligent Gemini Vision OCR
- **Optimized Performance**: Single-pass page rendering reused for both OCR and embeddings
- **Flexible Search**: Named vectors in Qdrant for precise text or image-based retrieval
- **CrewAI Integration**: Multi-agent workflow for context analysis and answer generation

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
```

**Get API Keys:**
- OpenAI: https://platform.openai.com/api-keys
- Gemini: https://makersuite.google.com/app/apikey

### 3. Start Qdrant Vector Database if running Quadrant Locally
```bash
docker-compose up -d
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
├── runner.py                  # CLI chatbot runner
├── requirements.txt           # Full dependencies
├── requirements_hybrid.txt    # Minimal ingestion-only deps
├── docker-compose.yml         # Qdrant setup
└── .env                       # API keys (not in git)
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

## 🛠️ Troubleshooting

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

See `requirements.txt` for complete dependency list with versions.

---
