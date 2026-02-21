from dotenv import load_dotenv
import pdfplumber
from crewai.tools import tool

load_dotenv()

@tool("extract_schedule_data")
def extract_schedule_data(pdf_path: str):
    """
    Useful to extract schedule information from a PDF file. 
    It parses tables and returns a list of weeks, programs, modules, topics, and tasks.
    """
    schedule_items = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                table = page.extract_table()
                if table:
                    for row in table[1:]:
                        if row and len(row) >= 5:
                            item = {
                                "Week" : row[0] if row[0] else "N/A",
                                "Program" : row[1]if row[1] else "N/A",
                                "Module" : row[2] if row[2] else "N/A",
                                "Topics" : row[3] if row[3] else "N/A",
                                "Tasks" : row[4] if row[4] else "N/A"
                            }
                        schedule_items.append(item)
                    else:
                        continue

        if not schedule_items:
            return "No valid schedule data found in the table. Please check the PDF layout."
            
        return schedule_items

    except Exception as e:
        return f"Error processing PDF: {str(e)}"
