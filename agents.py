""" 
CrewAI Agents for University Chatbot
FIX#10: Renamed "retriever" to "context_analyzer" for accuracy
- Context Analyzer Agent: Analyzes pre-retrieved chunks for relevance
- Answer Agent: Generates grounded answers from retrieved context
"""
from crewai import Agent
from langchain_openai import ChatOpenAI
import os
from dotenv import load_dotenv

load_dotenv()


def create_llm() -> ChatOpenAI:  # FIX#6: Add return type hint
    """Create OpenAI LLM instance for agents"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "❌ OPENAI_API_KEY not set!\n"
            "Please add your API key to the .env file."
        )
    
    return ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0,
        api_key=api_key
    )


def create_context_analyzer_agent(llm: ChatOpenAI) -> Agent:  # FIX#6: Add type hints
    """
    Context Analyzer Agent: Analyzes pre-retrieved chunks for relevance.
    
    Note: Actual Qdrant retrieval happens in Python (runner.py).
    This agent receives pre-fetched results and assesses their relevance.
    
    Responsibilities:
    - Receive pre-retrieved chunks from Python code
    - Analyze chunks for relevance to user question
    - Identify which chunks contain useful information
    - Pass relevant context with metadata to Answer Agent
    """
    return Agent(
        role="Context Analyzer",
        goal="Analyze pre-retrieved FAQ chunks and identify relevant information for answering questions",
        backstory="""You are an expert at analyzing document chunks from the American Center Cairo 
        & Sprints FAQ document. You receive chunks that were already retrieved from 
        the vector database, and your job is to assess which ones are relevant to the 
        users's question. You understand how to interpret questions and match them 
        with appropriate FAQ content.""",
        verbose=True,
        allow_delegation=False,
        llm=llm
    )


def create_answer_agent(llm: ChatOpenAI) -> Agent:  # FIX#6: Add type hints
    """
    Answer Agent: Generates accurate answers based on retrieved context.
    
    Responsibilities:
    - Analyze retrieved chunks
    - Generate clear, accurate answers
    - Include source citations (page numbers)
    - Say "The information is not available, you have to contact the administration" if information is missing
    """
    return Agent(
        role="Answer Generator",
        goal="Provide accurate, grounded answers to student questions using only the FAQ content",
        backstory="""You are a helpful assistant for Sprints students/users. 
        You provide clear, accurate answers based ONLY on the content from the FAQ document.
        You never make up information or provide answers that aren't supported by the FAQ.
        
        CRITICAL RULES:
        1. Only use information from the provided FAQ chunks
        2. Always cite page numbers for your sources
        3. If the FAQ doesn't contain the answer, respond: "The information is not available, you have to contact the administration"
        4. Never speculate or add information not in the FAQ
        5. Be helpful and clear in your explanations
        
        You format your responses with:
        - A clear answer
        - A "Sources used:" section listing page numbers and brief snippets""",
        verbose=True,
        allow_delegation=False,
        llm=llm
    )


if __name__ == "__main__":
    # Test agent creation
    llm = create_llm()
    context_analyzer_agent = create_context_analyzer_agent(llm)
    answer_agent = create_answer_agent(llm)
    
    print("✅ Agents created successfully!")
    print(f"📋 Context Analyzer Agent: {context_analyzer_agent.role}")
    print(f"📋 Answer Agent: {answer_agent.role}")
