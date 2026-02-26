# Code Review: Weekly Schedule Reminder System

**Reviewer:** Salman Ghanem 
**Date:** February 26, 2026 

---

**Overall Assessment:** ⚠️ **Needs Significant Improvements**

---

## 🔴 CRITICAL ISSUES

### 1. **Missing Environment Variable Validation**

**File:** `database_utils.py` (lines 5-8)  
**Severity:** MAJOR 🔴  
**Status:** ⚠️ **Repeated from RG's Feb 22 Review**

**Current Code:**

```python
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
# No validation before use
supabase: Client = create_client(url, key)
```

**Issue:** If environment variables are missing, the application will fail with cryptic errors later in execution rather than failing fast with a clear message.

**Fixed in Current Version:** ✅ **PARTIALLY FIXED** - Lines 11-12 now include validation:

```python
if not url or not key:
    raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY in .env file!")
```

**Recommendation:** Validation is now present. Good job! However, the validation should happen **before** creating the client to avoid any initialization overhead.

---

### 2. **Inefficient Database Operations (N+1 Problem)**

**File:** `database_utils.py` (lines 17-28)  
**Severity:** MAJOR 🔴  
**Status:** ⚠️ **Repeated from RG's Feb 22 Review**

**Current Code:**

```python
formatted_items = [
    {
        "week": item.get("Week"),
        "program": item.get("Program"),
        "module": item.get("Module"),
        "topics": item.get("Topics"),
        "tasks": item.get("Tasks")
    } for item in items
]

supabase.table("schedule_data").insert(formatted_items).execute()
```

**Issue Analysis:** The current code actually **DOES** perform bulk insert correctly (contrary to RG's review which mentioned looping). However, there are still issues:

1. **No duplicate check:** Multiple runs will insert duplicate data
2. **No transaction rollback:** If insert fails midway, partial data remains
3. **No upsert capability:** Should update existing records rather than creating duplicates

**Recommendation:**

```python
# Use upsert with conflict resolution
supabase.table("schedule_data").upsert(
    formatted_items,
    on_conflict='week,program,module'  # Define unique constraint
).execute()
```

**Updated Assessment:** The bulk insert is implemented correctly, but lacks duplicate handling. RG's concern about 50 API calls is **NOT** applicable to the current code.

---

### 3. **No Error Handling in Main Workflow**

**File:** `agent.py` (lines 6-67)  
**Severity:** MAJOR 🔴  
**Status:** *(NEW issue)*

**Issue:** The `main()` function has minimal error handling:

- PDF extraction failures are not caught
- Database save failures are printed but not handled
- CrewAI execution failures will crash the application
- No rollback mechanism if one step fails

**Impact:**

- Application crashes leave no audit trail
- Partial data corruption possible
- Poor user experience with cryptic error messages

**Recommendation:**

```python
def main():
    try:
        load_dotenv()
        # ... existing validation ...
        
        raw_data = extract_logic(target_file)
        if isinstance(raw_data, str):  # Error occurred
            raise Exception(f"PDF extraction failed: {raw_data}")
        
        db_result = save_to_supabase(raw_data)
        if "Error" in db_result:
            raise Exception(f"Database save failed: {db_result}")
        
        # ... crew execution ...
        
    except Exception as e:
        logging.error(f"Application failed: {e}", exc_info=True)
        # Send notification or alert
        raise
    finally:
        # Cleanup resources if needed
        pass
```

---

### 4. **Redundant PDF Extraction**

**File:** `agent.py` (lines 20-23, 40-46)  
**Severity:** MAJOR 🔴  
**Status:** ⚠️ **Repeated from RG's Feb 22 Review**

**Issue:** PDF is extracted twice:

1. Line 22: `raw_data = extract_logic(target_file)`
2. Lines 40-46: Agent task description includes `{raw_data}` and mentions extracting from PDF

**Impact:**

- Wasted computational resources
- Inconsistent data if PDF changes between extractions
- Confusion about source of truth

**Recommendation:** Choose one approach:

**Option A:** Let agent handle everything (including extraction)

```python
share_schedule_task = Task(
    description=f"""
        1. Extract schedule data from PDF: {target_file}
        2. Save to database
        3. Create summary
    """,
    tools=[extract_schedule_data],
    agent=share_schedule_agent
)
```

**Option B:** Extract once and pass data to agent (RECOMMENDED)

```python
# Current approach is good, just remove tool from agent
# Agent should only summarize, not re-extract
```

---

## 🟡 MAJOR ISSUES

### 5. **Hard-coded File Paths**

**File:** `agent.py` (line 17)  
**Severity:** MEDIUM 🟡  

**Issue:**

```python
target_file = 'US Embassy - Weekly Schedule.pdf'
```

**Problems:**

- Not configurable without code changes
- No support for processing multiple PDFs
- Breaks if file is renamed

**Recommendation:**

```python
target_file = os.getenv('PDF_PATH', 'US Embassy - Weekly Schedule.pdf')
# Or accept as CLI argument
```

---

### 6. **Fragile Table Parsing Logic**

**File:** `extractPDF.py` (lines 10-15)  
**Severity:** MEDIUM 🟡  
**Status:** ⚠️ **Repeated from RG's Feb 22 Review** (Expanded)

**Issue:**

```python
start_index = 0
first_row_text = str(table[0][0]).lower() if table[0][0] else ""
if "week" in first_row_text or "program" in first_row_text:
    start_index = 1
```

**Problems:**

1. Assumes first page has headers, but subsequent pages may not
2. No validation that table has expected columns
3. `if len(row) >= 5` is fragile - no explanation for magic number 5
4. No handling of merged cells or irregular table structures

**Recommendation:**

```python
EXPECTED_COLUMNS = 5
HEADER_KEYWORDS = ["week", "program", "module", "topics", "tasks"]

def is_header_row(row):
    """Check if row contains header keywords"""
    if not row:
        return False
    row_text = ' '.join([str(cell).lower() for cell in row if cell])
    return any(keyword in row_text for keyword in HEADER_KEYWORDS)

def extract_logic(pdf_path: str):
    schedule_items = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                table = page.extract_table()
                if not table:
                    continue
                
                # Skip header row if present
                start_index = 1 if is_header_row(table[0]) else 0
                
                for row in table[start_index:]:
                    if not row or len(row) < EXPECTED_COLUMNS:
                        continue
                    # Validate row has meaningful data
                    if all(cell is None or str(cell).strip() == "" for cell in row):
                        continue
                    # ... rest of logic
```

---

### 7. **Insufficient Input Validation**

**File:** `database_utils.py` (line 16), `extractPDF.py` (line 6)  
**Severity:** MEDIUM 🟡  

**Issue:**

- No validation of PDF file existence or format
- No validation of extracted data structure
- No validation of data types before database insertion

**Recommendation:**

```python
# In extractPDF.py
def extract_logic(pdf_path: str):
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    if not pdf_path.lower().endswith('.pdf'):
        raise ValueError(f"File must be a PDF: {pdf_path}")
    
    # ... extraction logic ...
    
    if not schedule_items:
        raise ValueError("No data extracted from PDF")
    
    return schedule_items

# In database_utils.py
def save_to_supabase(items):
    if not items:
        raise ValueError("No items provided for database insertion")
    
    if isinstance(items, str):
        raise ValueError(f"Invalid data format: {items}")
    
    if not isinstance(items, list):
        raise TypeError("Items must be a list")
    
    # Validate each item has required fields
    required_fields = ["Week", "Program", "Module", "Topics", "Tasks"]
    for idx, item in enumerate(items):
        missing = [f for f in required_fields if f not in item]
        if missing:
            raise ValueError(f"Item {idx} missing fields: {missing}")
```

---

### 8. **Poor Logging Practices**

**File:** All files  
**Severity:** MEDIUM 🟡  

**Issue:** Using `print()` statements instead of proper logging framework

**Problems:**

- No log levels (DEBUG, INFO, WARNING, ERROR)
- No log file persistence
- Cannot adjust verbosity without code changes
- Difficult to troubleshoot production issues

**Recommendation:**

```python
import logging

# Setup logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('schedule_reminder.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Replace print statements
logger.info(f"Current Directory: {os.getcwd()}")
logger.error(f"ERROR: {target_file} not found.")
logger.debug(f"Extracted {len(raw_data)} items from PDF")
```

---

## 🟢 MINOR ISSUES

### 9. **Missing Docstrings**

**File:** `agent.py`, `database_utils.py`  
**Severity:** LOW 🟢  

**Issue:** Functions like `main()` and `save_to_supabase()` lack comprehensive docstrings

**Recommendation:**

```python
def save_to_supabase(items: list[dict]) -> str:
    """
    Saves extracted schedule items to Supabase database.
    
    Args:
        items: List of dictionaries containing schedule data with keys:
               'Week', 'Program', 'Module', 'Topics', 'Tasks'
    
    Returns:
        Success message or error description
    
    Raises:
        ValueError: If items is empty or invalid format
        Exception: If database operation fails
    
    Example:
        >>> items = [{"Week": "1", "Program": "AI", ...}]
        >>> result = save_to_supabase(items)
        >>> print(result)
        'Data successfully synced to Supabase!'
    """
```

---

### 10. **Incomplete Type Hints**

**File:** All Python files  
**Severity:** LOW 🟢  

**Issue:** Inconsistent type hint usage

**Current:**

```python
def save_to_supabase(items):  # No type hints
def extract_logic(pdf_path: str):  # Partial type hints
```

**Recommendation:**

```python
from typing import List, Dict, Union

def save_to_supabase(items: List[Dict[str, str]]) -> str:
    pass

def extract_logic(pdf_path: str) -> Union[List[Dict[str, str]], str]:
    """Returns list of items or error string"""
    pass
```

---

### 11. **Empty README.md**

**File:** `README.md`  
**Severity:** LOW 🟢  

**Issue:** README file exists but is completely empty

**Recommendation:** Create comprehensive documentation.

---

### 12. **No Requirements.txt Validation**

**File:** Project root  
**Severity:** LOW 🟢  

**Issue:** Cannot verify if `requirements.txt` exists or is up to date

**Recommendation:**
Create/update `requirements.txt` - already created by reviewer at the moment and pushed to the git branch, adjust if needed

```text
pdfplumber>=0.10.0
python-dotenv>=1.0.0
supabase>=2.0.0
crewai>=0.1.0
openai>=1.0.0
```

---

## 📊 Issue Summary Statistics

| Category | Critical | Major | Medium | Minor | Total |
| -------- | -------- | ----- | ------ | ----- | ----- |
| **Security** | 0 | 1 | 0 | 0 | 2 |
| **Software Engineering** | 2 | 2 | 2 | 0 | 6 |
| **Code Quality** | 0 | 0 | 1 | 4 | 5 |
| **TOTAL** | **2** | **3** | **3** | **4** | **13** |

---

## 🔗 Cross-Reference with RG's Feb 22 Review

| RG Issue # | Status in Current Code | This Review # |
| ---------- | ---------------------- | ------------- |
| 1. Missing Env Validation | ✅ **FIXED** (partially) | Issue #2 |
| 2. Inefficient DB Sync | ✅ **ACTUALLY CORRECT** (bulk insert exists) | Issue #3 |
| 3. Redundant Execution | ❌ **STILL PRESENT** | Issue #5 |
| 4. Fragile Tool Invocation | ⚠️ **N/A** (agent uses data, not tool) | - |
| 5. Duplicate Imports | ✅ **CLEAN** | - |
| 6. PDF Header Edge Case | ❌ **STILL PRESENT** | Issue #7 |

**Overall Progress Since RG's Review:** 2/6 issues addressed (33%)

---

## 💡 Architectural Recommendations

### 1. Separation of Concerns

Consider splitting into distinct modules:

- `extraction/` - PDF parsing logic
- `database/` - All database operations
- `agents/` - CrewAI agent definitions
- `config/` - Configuration management
- `utils/` - Shared utilities (logging, validation)

### 2. Configuration Management

```python
# config.py
from dataclasses import dataclass
from dotenv import load_dotenv
import os

@dataclass
class Config:
    openai_api_key: str
    supabase_url: str
    supabase_key: str
    pdf_path: str
    log_level: str = "INFO"
    
    @classmethod
    def from_env(cls):
        load_dotenv()
        return cls(
            openai_api_key=cls._require_env("OPENAI_API_KEY"),
            supabase_url=cls._require_env("SUPABASE_URL"),
            supabase_key=cls._require_env("SUPABASE_KEY"),
            pdf_path=os.getenv("PDF_PATH", "US Embassy - Weekly Schedule.pdf"),
            log_level=os.getenv("LOG_LEVEL", "INFO")
        )
    
    @staticmethod
    def _require_env(key: str) -> str:
        value = os.getenv(key)
        if not value:
            raise ValueError(f"Missing required environment variable: {key}")
        return value
```

### 3. Dependency Injection

```python
class ScheduleProcessor:
    def __init__(self, extractor, database, agent):
        self.extractor = extractor
        self.database = database
        self.agent = agent
    
    def process(self, pdf_path: str):
        data = self.extractor.extract(pdf_path)
        self.database.save(data)
        summary = self.agent.summarize(data)
        return summary
```

---

**Review Completed By:** Salman Ghanem
**Date:** February 26, 2026  
**Version:** 1.0
