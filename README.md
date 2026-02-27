## 🤖 Academic Coordinator Agent

This repository automates the extraction and summarization of student curricula using an AI-driven pipeline. It transforms raw, unstructured PDF data into structured database entries and professional student announcements.

---

### 📋 Agent Task Overview

The system performs a two-stage operation to bridge the gap between static documents and student engagement:

1. **Data Extraction & Sync:** The script parses a 30-page academic PDF, identifying rows for programs, modules, topics, and tasks. It then synchronizes this data (approx. 177 rows) into a **Supabase** database.
2. **Intelligent Summarization:** A **Senior Academic Coordinator Agent** (built with CrewAI) queries the database for a specific week. It is tasked with:
* Extracting hidden topics from merged text fields.
* Identifying specific Live Session requirements.
* Formatting a friendly, actionable "Next Steps" announcement for Slack or Discord.



---

### 🚀 How to Run the Agent

Follow these steps to execute the pipeline:

1. **Install Dependencies:**
```bash
pip install crewai supabase pymupdf python-dotenv

```


2. **Execute the Agent:**
```bash
python agent.py

```


3. **Provide Input:**
When the terminal prompts `Enter the week to summarize`, type the week number (e.g., `4`) and press Enter.

---

### ✨ Importance of the Agent

* **Data Accuracy:** Automatically handles noisy PDF data and font errors that usually break standard parsers.
* **Time Efficiency:** Replaces the manual work of searching through large PDFs to create weekly updates for multiple programs.
* **Clarity:** It acts as a "logic filter," ensuring that even if the database contains "N/A" or messy strings, the final output to students is clean, professional, and encouraging.
* **Scalability:** Allows a single coordinator to manage dozens of different programs by simply changing the query parameters.

---