import pdfplumber
from crewai.tools import tool

def extract_logic(pdf_path: str):
    """The actual python logic to parse the PDF"""
    schedule_items = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                table = page.extract_table()
                if table:
                    start_index = 0
                    first_row_text = str(table[0][0]).lower() if table[0][0] else ""
                    if "week" in first_row_text or "program" in first_row_text:
                        start_index = 1
                    
                    for row in table[start_index:]:
                        if row and len(row) >= 5:
                            item = {
                                "Week" : row[0] if row[0] else "N/A",
                                "Program" : row[1] if row[1] else "N/A",
                                "Module" : row[2] if row[2] else "N/A",
                                "Topics" : row[3] if row[3] else "N/A",
                                "Tasks" : row[4] if row[4] else "N/A"
                            }
                            schedule_items.append(item)
        return schedule_items
    except Exception as e:
        return f"Error processing PDF: {str(e)}"

@tool("extract_schedule_data")
def extract_schedule_data(pdf_path: str):
    """
    Useful to extract schedule information from a PDF file. 
    It parses tables and returns a list of weeks, programs, modules, topics, and tasks.
    """
    return extract_logic(pdf_path)