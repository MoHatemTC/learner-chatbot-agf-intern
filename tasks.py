"""
CrewAI Tasks for the University Chatbot
Defines the workflow for retrieval and answer generation
"""
from crewai import Task


def create_retrieval_task(agent, question: str, search_function):
    """
    Task for the Context Analyzer Agent.
    
    Args:
        agent: The context analyzer agent
        question: User's question
        search_function: Function to search Qdrant (returns pre-fetched results)
    """
    # Search performed by Python code in runner.py, not by agent
    results = search_function(question)
    
    # Format results for the agent
    if not results:
        context = "No relevant information found in the documents."
    else:
        context = "Retrieved chunks from the documents:\n\n"
        for i, result in enumerate(results, 1):
            context += f"--- Chunk {i} (Page {result.payload.get('page')}, Score: {result.score:.3f}) ---\n"
            context += f"{result.payload.get('text')}\n\n"
    
    return Task(
        description=f"""Analyze the following question and the retrieved information:
        
Question: {question}

Retrieved Information:
{context}

Your task:
1. Review the retrieved chunks
2. Determine if they contain relevant information to answer the question
3. Pass the relevant chunks and their page numbers to the Answer Generator
4. If no relevant information was found, indicate this clearly
""",
        agent=agent,
        expected_output="""A summary of the retrieved information including:
- Which chunks are relevant
- The page numbers where information was found
- A brief assessment of whether the question can be answered"""
    )


def create_answer_task(agent, question: str, retrieval_context: str = None):
    """
    Task for the Answer Agent.
    
    Args:
        agent: The answer agent
        question: User's question
        retrieval_context: Context from retrieval task (optional, for direct calls)
    """
    context_instruction = ""
    if retrieval_context:
        context_instruction = f"\n\nContext from retrieval:\n{retrieval_context}"
    
    return Task(
        description=f"""Generate a clear, accurate answer to the user's or student's question using ONLY 
the information from the document chunks.

Question: {question}
{context_instruction}

CRITICAL REQUIREMENTS:
1. Base your answer ONLY on the provided document content
2. If the chunks don't contain the answer, respond: "I am unable to answer you since your question is beyond my knowledge. Contact the administration."
3. Include a "Sources used:" section with:
   - Page number(s)
   - Brief snippet or description of what was found
4. Be helpful and clear
5. Do not speculate or add information not in the document

Format your response as:
[Your clear answer here]

Sources used:
- Page X: [brief description or snippet]
- Page Y: [brief description or snippet]
""",
        agent=agent,
        expected_output="""A complete answer with:
1. Clear, direct response to the question OR "I am unable to answer you since your question is beyond my knowledge. Contact the administration."
2. Sources used section with page numbers and snippets"""
    )


if __name__ == "__main__":
    print("✅ Task templates created successfully!")
