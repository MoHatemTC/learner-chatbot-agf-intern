"""
RAGAS Evaluation for Weekly Schedule Reminder Agent
By Salman Ghanem - 2024-06-20

This script evaluates the performance of the schedule reminder agent using RAGAS metrics:
- Faithfulness: Measures how accurately the agent's response is grounded in the source data
- Answer Relevancy: Evaluates how relevant the answer is to the question
- Context Precision: Measures the quality of retrieved context
- Context Recall: Evaluates if all relevant information was retrieved

=================================================================================
✅ EVALUATION ACCURACY VERIFICATION:
=================================================================================

1. ✅ AGENT CONFIGURATION: The test agent (create_test_agent) uses the EXACT
   configuration from agent.py:
   - Role: 'Academic Success & Schedule Coordinator'
   - Goal: 'Deliver upcoming session times and deadlines from the Program Plan accurately.'
   - Backstory: Identical supportive assistant description
   - allow_delegation: False
   
   Note: Only difference is verbose=False (for cleaner test output) vs verbose=True
   in production. This does not affect agent behavior, only output verbosity.

2. ✅ TEST DATA: Sample data and test cases are extracted from the ACTUAL PDF file
   "US Embassy - Weekly Schedule.pdf" in this directory, including:
   - Recorded Videos for Project Accelerator & Agile, SW Engineering
   - Tasks Deadline: Saturday, 14th December @ 11:59 PM
   - Live Session #1: Sunday, December 15 @ 7:30 PM
   - Expert: Omar Sherif
   
   Test questions and ground truth are based on real schedule content to ensure
   fair and realistic evaluation of agent performance.

=================================================================================
INTEGRATION INSTRUCTIONS FOR CODE WRITER:
=================================================================================

CURRENT STATE: This evaluation script works standalone and replicates the agent
configuration from agent.py to perform testing.

RECOMMENDED REFACTORING: To ensure evaluation tests the ACTUAL production agent,
the code writer should refactor agent.py to expose reusable functions:

    # In agent.py - ADD these functions:
    
    def create_schedule_agent(verbose=True):
        '''Create and return the schedule coordinator agent'''
        return Agent(
            role='Academic Success & Schedule Coordinator',
            goal='Deliver upcoming session times and deadlines from the Program Plan accurately.',
            backstory='''You are a supportive assistant for Sprints AI learners. 
            You excel at turning complex PDF schedules into friendly, actionable reminders. 
            Your mission is to ensure no learner ever misses a live session or a deadline.''',
            verbose=verbose,
            allow_delegation=False
        )
    
    def run_schedule_crew(schedule_data, verbose=True, custom_description=None):
        '''Run the schedule crew with the given data'''
        agent = create_schedule_agent(verbose=verbose)
        
        description = custom_description or f'''
            Review the following schedule data extracted from the PDF:
            {schedule_data}
            1. Identify the upcoming Week's sessions, topics, and deadlines.
            2. Distinguish clearly between 'Recorded Videos' and 'Live Sessions'.
            3. Create a clean, easy-to-read summary.
        '''
        
        task = Task(
            description=description,
            expected_output='''A friendly summary of the week's schedule...''',
            agent=agent
        )
        
        crew = Crew(agents=[agent], tasks=[task], verbose=verbose)
        result = crew.kickoff()
        return str(result)

THEN UPDATE THIS FILE:
    1. Uncomment the import line marked "# AFTER REFACTORING"
    2. Comment out the create_test_agent() function
    3. Uncomment get_agent_response_from_codebase() function
    4. Update run_evaluation_with_test_data() to use the codebase function

This ensures evaluation tests the ACTUAL production agent, not a replica.
=================================================================================
"""

import os
import sys
import warnings
from dotenv import load_dotenv
from datasets import Dataset
from ragas import evaluate

# Fix Unicode encoding for Windows terminal
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Suppress deprecation warnings for RAGAS imports
warnings.filterwarnings('ignore', category=DeprecationWarning, module='ragas')

# Use working import path (old path works fine with RAGAS 0.4.3)
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
)

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from crewai import Agent, Task, Crew
from extractPDF import extract_logic

# AFTER REFACTORING: Uncomment this to use the actual codebase agent
# from agent import create_schedule_agent, run_schedule_crew

# Load environment variables
load_dotenv()

# =============================================================================
# ACTUAL DATA FROM PDF: "US Embassy - Weekly Schedule.pdf"
# =============================================================================
# This data is extracted directly from the actual PDF file in the directory
# to ensure evaluation is based on real schedule content, not synthetic data.

SAMPLE_SCHEDULE_DATA = [
    {
        "Week": "Recorded\nVideos",
        "Program": "Project\nAccelrator &\nAgile",
        "Module": "All Program",
        "Topics": "N/A",
        "Tasks": "Organizing a Hackathon\nEvent"
    },
    {
        "Week": "Recorded\nVideos",
        "Program": "SW Engineering",
        "Module": "All Program",
        "Topics": "- Recap\n- Case Studies\n- Q&A\n- What's next",
        "Tasks": "Build Software Design\nDiagrams for a Portfolio\nWebsite Version Control\nwith Git"
    },
    {
        "Week": "Tasks Deadline",
        "Program": "Saturday, 14th December @ 11:59 PM",
        "Module": "N/A",
        "Topics": "N/A",
        "Tasks": "N/A"
    },
    {
        "Week": "Live Session #1",
        "Program": "Sunday, December 15 @ 7:30 PM",
        "Module": "N/A",
        "Topics": "N/A",
        "Tasks": "N/A"
    },
    {
        "Week": "Expert",
        "Program": "Omar Sherif",
        "Module": "N/A",
        "Topics": "N/A",
        "Tasks": "N/A"
    }
]

# Test cases with questions and expected answers based on the ACTUAL PDF content
TEST_CASES = [
    {
        "question": "What recorded video topics are available for SW Engineering?",
        "ground_truth": "The SW Engineering recorded videos cover Recap, Case Studies, Q&A, and What's next.",
        "contexts": ["Recorded Videos: SW Engineering - All Program - Topics: Recap, Case Studies, Q&A, What's next"]
    },
    {
        "question": "What tasks need to be completed for the SW Engineering module?",
        "ground_truth": "You need to build Software Design Diagrams for a Portfolio and learn about Website Version Control with Git.",
        "contexts": ["Recorded Videos: SW Engineering - Tasks: Build Software Design Diagrams for a Portfolio, Website Version Control with Git"]
    },
    {
        "question": "When is the tasks deadline?",
        "ground_truth": "The tasks deadline is Saturday, 14th December at 11:59 PM.",
        "contexts": ["Tasks Deadline: Saturday, 14th December @ 11:59 PM"]
    },
    {
        "question": "When is Live Session #1 scheduled?",
        "ground_truth": "Live Session #1 is scheduled for Sunday, December 15 at 7:30 PM.",
        "contexts": ["Live Session #1: Sunday, December 15 @ 7:30 PM"]
    },
    {
        "question": "Who is the expert for the live session?",
        "ground_truth": "The expert for the live session is Omar Sherif.",
        "contexts": ["Expert: Omar Sherif"]
    },
    {
        "question": "What is the task for the Project Accelerator & Agile program?",
        "ground_truth": "The task is Organizing a Hackathon Event.",
        "contexts": ["Recorded Videos: Project Accelerator & Agile - All Program - Tasks: Organizing a Hackathon Event"]
    }
]


# =============================================================================
# CURRENT IMPLEMENTATION: Standalone test agent (replicates agent.py behavior)
# =============================================================================

def create_test_agent():
    """
    TEMPORARY: Creates a test agent that replicates the configuration in agent.py
    
    ⚠️ WARNING: This is a replica of the production agent. Changes to agent.py
    will NOT be reflected here unless manually updated.
    
    ✅ AFTER REFACTORING: Replace this with the actual create_schedule_agent()
    function from agent.py by following the integration instructions at the top.
    """
    return Agent(
        role='Academic Success & Schedule Coordinator',
        goal='Deliver upcoming session times and deadlines from the Program Plan accurately.',
        backstory='''You are a supportive assistant for Sprints AI learners. 
        You excel at turning complex PDF schedules into friendly, actionable reminders. 
        Your mission is to ensure no learner ever misses a live session or a deadline.''',
        verbose=False,
        allow_delegation=False
    )


def get_agent_response(schedule_data, question):
    """
    CURRENT: Get response from the test agent for a specific question
    
    ⚠️ This creates its own agent instance for testing purposes.
    
    ✅ AFTER REFACTORING: Use get_agent_response_from_codebase() instead
    """
    agent = create_test_agent()
    
    task = Task(
        description=f"""
            Review the following schedule data:
            {schedule_data}

            Answer the following question based ONLY on the schedule data provided:
            {question}

            Be concise, accurate, and helpful. Only include information present in the schedule data.
        """,
        expected_output="A clear, accurate answer based only on the provided schedule data.",
        agent=agent
    )

    crew = Crew(
        agents=[agent],
        tasks=[task],
        verbose=False
    )

    result = crew.kickoff()
    return str(result)


# =============================================================================
# FUTURE IMPLEMENTATION: Use actual codebase agent (after refactoring)
# =============================================================================

# ✅ AFTER REFACTORING: Uncomment this function and use it instead
"""
def get_agent_response_from_codebase(schedule_data, question):
    '''
    Get response from the ACTUAL production agent in agent.py
    
    This ensures evaluation tests the real agent behavior, not a replica.
    '''
    custom_description = f'''
        Review the following schedule data:
        {schedule_data}

        Answer the following question based ONLY on the schedule data provided:
        {question}

        Be concise, accurate, and helpful. Only include information present in the schedule data.
    '''
    
    # Use the actual production function from agent.py
    result = run_schedule_crew(schedule_data, verbose=False, custom_description=custom_description)
    return result
"""

# =============================================================================


def format_schedule_as_context(schedule_data):
    """Format schedule data as context strings
    
    Handles the actual PDF structure which includes:
    - Recorded Videos entries
    - Tasks Deadline entries  
    - Live Session entries
    - Expert entries
    """
    contexts = []
    for item in schedule_data:
        week_type = item.get('Week', 'N/A')
        program = item.get('Program', 'N/A')
        module = item.get('Module', 'N/A')
        topics = item.get('Topics', 'N/A')
        tasks = item.get('Tasks', 'N/A')
        
        # Format based on entry type
        if week_type and week_type != 'N/A':
            context = f"{week_type}: {program}"
            if module != 'N/A':
                context += f" - {module}"
            if topics != 'N/A':
                context += f" - Topics: {topics}"
            if tasks != 'N/A':
                context += f" - Tasks: {tasks}"
        else:
            context = f"{program}"
            
        contexts.append(context)
    return contexts


def run_evaluation_with_test_data():
    """Run RAGAS evaluation using predefined test data"""
    print("=" * 80)
    print("RAGAS EVALUATION - Weekly Schedule Reminder Agent")
    print("⚠️  CURRENT MODE: Using standalone test agent (replica of agent.py)")
    print("✅  RECOMMENDED: Refactor agent.py and switch to production agent")
    print("=" * 80)

    # Prepare evaluation data
    questions = []
    answers = []
    contexts = []
    ground_truths = []

    print("\n📝 Generating agent responses for test cases...\n")
    print("ℹ️  Currently using a test agent replica. See file header for integration steps.\n")
    
    for i, test_case in enumerate(TEST_CASES, 1):
        print(f"Processing test case {i}/{len(TEST_CASES)}: {test_case['question']}")
        
        # CURRENT: Using standalone test agent
        # AFTER REFACTORING: Replace with get_agent_response_from_codebase()
        response = get_agent_response(SAMPLE_SCHEDULE_DATA, test_case['question'])
        
        questions.append(test_case['question'])
        answers.append(response)
        contexts.append(test_case['contexts'])
        ground_truths.append(test_case['ground_truth'])
        
        print(f"  ✓ Response generated\n")

    # Create dataset for RAGAS
    dataset_dict = {
        'question': questions,
        'answer': answers,
        'contexts': contexts,
        'ground_truth': ground_truths
    }

    dataset = Dataset.from_dict(dataset_dict)

    print("\n🔍 Running RAGAS evaluation...\n")
    
    # Initialize LLM and embeddings for RAGAS
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    embeddings = OpenAIEmbeddings()
    
    # Run evaluation - metrics are already instantiated, don't call with ()
    try:
        result = evaluate(
            dataset,
            metrics=[
                faithfulness,
                answer_relevancy,
                context_precision,
                context_recall,
            ],
            llm=llm,
            embeddings=embeddings,
        )
        return result
    except Exception as e:
        print(f"\n❌ Evaluation error: {str(e)}")
        print("\nℹ️  This might be a RAGAS version compatibility issue.")
        print("Try: pip install --upgrade ragas langchain-openai langchain-community")
        return None


def run_evaluation_with_pdf(pdf_path):
    """Run RAGAS evaluation using actual PDF data"""
    print("=" * 80)
    print("RAGAS EVALUATION - Weekly Schedule Reminder Agent")
    print(f"Using PDF: {pdf_path}")
    print("⚠️  CURRENT MODE: Using standalone test agent (replica of agent.py)")
    print("✅  RECOMMENDED: Refactor agent.py and switch to production agent")
    print("=" * 80)

    # Extract data from PDF
    print("\n📄 Extracting schedule from PDF...")
    schedule_data = extract_logic(pdf_path)
    
    if isinstance(schedule_data, str) or not schedule_data:
        print(f"❌ Error: Could not extract data from PDF")
        return None

    print(f"✓ Extracted {len(schedule_data)} schedule items\n")

    # For PDF evaluation, we'll use the test cases but with real PDF data
    questions = []
    answers = []
    contexts = []
    ground_truths = []

    all_contexts = format_schedule_as_context(schedule_data)

    print("📝 Generating agent responses...\n")
    print("ℹ️  Currently using a test agent replica. See file header for integration steps.\n")
    
    for i, test_case in enumerate(TEST_CASES, 1):
        print(f"Processing question {i}/{len(TEST_CASES)}: {test_case['question']}")
        
        # CURRENT: Using standalone test agent
        # AFTER REFACTORING: Replace with get_agent_response_from_codebase()
        response = get_agent_response(schedule_data, test_case['question'])
        
        questions.append(test_case['question'])
        answers.append(response)
        contexts.append(all_contexts)  # Use all schedule data as context
        ground_truths.append(test_case['ground_truth'])
        
        print(f"  ✓ Response generated\n")

    # Create dataset for RAGAS
    dataset_dict = {
        'question': questions,
        'answer': answers,
        'contexts': contexts,
        'ground_truth': ground_truths
    }

    dataset = Dataset.from_dict(dataset_dict)

    print("\n🔍 Running RAGAS evaluation...\n")
    
    # Initialize LLM and embeddings for RAGAS
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    embeddings = OpenAIEmbeddings()
    
    # Run evaluation - metrics are already instantiated, don't call with ()
    try:
        result = evaluate(
            dataset,
            metrics=[
                faithfulness,
                answer_relevancy,
                context_precision,
                context_recall,
            ],
            llm=llm,
            embeddings=embeddings,
        )
        return result
    except Exception as e:
        print(f"\n❌ Evaluation error: {str(e)}")
        print("\nℹ️  This might be a RAGAS version compatibility issue.")
        print("Try: pip install --upgrade ragas langchain-openai langchain-community")
        return None


def print_evaluation_results(result):
    """Pretty print the evaluation results"""
    print("\n" + "=" * 80)
    print("📊 EVALUATION RESULTS")
    print("=" * 80)
    
    if result is None:
        print("❌ Evaluation failed or returned no results")
        return
    
    # Print overall scores
    print("\n📈 Overall Metrics:")
    print("-" * 80)
    
    metrics = {
        'faithfulness': '🎯 Faithfulness',
        'answer_relevancy': '✨ Answer Relevancy',
        'context_precision': '🔍 Context Precision',
        'context_recall': '📚 Context Recall'
    }
    
    # Access RAGAS EvaluationResult using dictionary-style access
    # result[metric_key] returns a list of scores, we take the mean
    for metric_key, metric_name in metrics.items():
        try:
            score_list = result[metric_key]
            if score_list and len(score_list) > 0:
                score = sum(score_list) / len(score_list)
                print(f"{metric_name:.<50} {score:.4f}")
            else:
                print(f"{metric_name:.<50} N/A")
        except Exception as e:
            print(f"{metric_name:.<50} Error: {str(e)}")
    
    print("\n" + "=" * 80)
    
    # Interpretation guide
    print("\n📖 Score Interpretation:")
    print("-" * 80)
    print("Faithfulness:      How well answers are grounded in source data (0-1, higher is better)")
    print("Answer Relevancy:  How relevant answers are to questions (0-1, higher is better)")
    print("Context Precision: Quality of retrieved context (0-1, higher is better)")
    print("Context Recall:    Completeness of retrieved context (0-1, higher is better)")
    print("\n✅ Good scores: > 0.7  |  ⚠️  Needs improvement: < 0.5")
    print("=" * 80)


def main():
    """Main execution function"""
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY not found in .env file! RAGAS requires OpenAI API.")

    print("\n🚀 Starting RAGAS Evaluation\n")
    print("=" * 80)
    print("⚠️  IMPORTANT NOTICE")
    print("=" * 80)
    print("This evaluation currently uses a REPLICA of the agent from agent.py.")
    print("To test the ACTUAL production agent, the code writer should refactor")
    print("agent.py following the instructions at the top of this file.")
    print("=" * 80)
    print()
    
    # Option 1: Evaluate with predefined test data
    print("Running evaluation with test data...\n")
    result = run_evaluation_with_test_data()
    print_evaluation_results(result)
    
    # Option 2: Uncomment to evaluate with actual PDF
    # pdf_path = 'US Embassy - Weekly Schedule.pdf'
    # if os.path.exists(pdf_path):
    #     print("\n\nRunning evaluation with PDF data...\n")
    #     result_pdf = run_evaluation_with_pdf(pdf_path)
    #     print_evaluation_results(result_pdf)
    # else:
    #     print(f"\n⚠️  PDF file '{pdf_path}' not found. Skipping PDF evaluation.")


if __name__ == "__main__":
    main()
