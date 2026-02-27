import pdfplumber
import os
from crewai.tools import tool

def extract_logic(pdf_path: str):
    """Loops through ALL pages to find ALL schedule tables."""
    if not pdf_path or not os.path.exists(pdf_path):
        return f"Error: File {pdf_path} not found."
    
    all_items = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            print(f"Scanning {len(pdf.pages)} pages...")
            
            for page_num, page in enumerate(pdf.pages):
                table = page.extract_table()
                if not table:
                    continue
                
                # IMPROVEMENT: Smarter header detection (Salman's reliability fix)
                first_row_str = str(table[0]).lower()
                start_index = 1 if any(h in first_row_str for h in ["week", "program", "module"]) else 0
                
                rows_found = 0
                for row in table[start_index:]:
                    if row and any(row): 
                        clean_row = [str(cell).replace('\n', ' ').strip() if cell else "N/A" for cell in row]
                        
                        # Pad row if columns are missing to prevent IndexError
                        while len(clean_row) < 5:
                            clean_row.append("N/A")

                        all_items.append({
                            "Week": clean_row[0],
                            "Program": clean_row[1],
                            "Module": clean_row[2],
                            "Topics": clean_row[3],
                            "Tasks": clean_row[4]
                        })
                        rows_found += 1
                
                print(f"Page {page_num + 1}: Found {rows_found} rows")

        return all_items
    except Exception as e:
        return f"Error during extraction: {str(e)}"

@tool("extract_schedule_data")
def extract_schedule_data(pdf_path: str):
    """
    Mandatory docstring for CrewAI: Extracts table data from the PDF 
    and returns a structured list of weeks and tasks.
    """
    return extract_logic(pdf_path)