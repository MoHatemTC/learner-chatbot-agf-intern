import pandas as pd
from database_utils import get_supabase

def create_base_spreadsheet():
    supabase = get_supabase()
    # Fetch all records to build the gold standard
    res = supabase.table("schedule").select("*").execute()
    df = pd.DataFrame(res.data)
    
    # Create placeholders for the evaluation
    df['user_question'] = df.apply(lambda x: f"What is the schedule for Week {x['week_number']} of the {('Mobile' if x['course_id']==1 else 'AI/ML')} course?", axis=1)
    df['expected_answer'] = "" # You will manually fill a few of these to be 'perfect'
    
    df.to_csv("gold_standard_template.csv", index=False)
    print("Template created: gold_standard_template.csv. Fill the 'expected_answer' column for 50 rows.")

if __name__ == "__main__":
    create_base_spreadsheet()