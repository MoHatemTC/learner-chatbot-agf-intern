"""
Runner - Execute the CrewAI workflow
Orchestrates retrieval and answer generation
"""
import os
from crewai import Crew, Process
from dotenv import load_dotenv

from agents import create_llm, create_context_analyzer_agent, create_answer_agent  #Import factories instead of instances
from tasks import create_retrieval_task, create_answer_task
from embedder import EmbeddingGenerator
from qdrant_utils import get_qdrant_client

load_dotenv()


class ChatbotRunner:
    """Orchestrate the chatbot workflow"""
    
    def __init__(self):
        """Initialize the runner with all components"""
        print("🚀 Initializing Chatbot Runner...")
        
        # This prevents app crashes before UI starts if there are configuration errors
        llm = create_llm()
        self.context_analyzer_agent = create_context_analyzer_agent(llm)
        self.answer_agent = create_answer_agent(llm)
        
        # Initialize components
        self.embedder = EmbeddingGenerator()
        self.qdrant_client = get_qdrant_client()
        self.collection_name = os.getenv("COLLECTION_NAME", "sprints_faq")
        self.top_k = int(os.getenv("TOP_K", 7))
        self.score_threshold = 0.3  # Minimum similarity score (lower = more lenient)
        
        print("✅ Runner initialized")
    
    def search_document(self, question: str):
        """
        Search for relevant chunks in the document.
        
        Args:
            question: User's question
            
        Returns:
            List of search results from Qdrant
        """
        # Generate query embedding
        query_vector = self.embedder.embed_text(question)
        
        # Search Qdrant - use "text" vector for hybrid collections
        try:
            results = self.qdrant_client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=self.top_k,
                score_threshold=self.score_threshold,
                with_payload=True,
                using="text"  # Search the "text" vector (for hybrid collections)
            ).points
        except Exception as e:
            # Fallback: try without specifying vector name (for non-hybrid collections)
            if "vector name" in str(e).lower() or "not existing vector" in str(e).lower():
                print("ℹ️  Trying search without named vectors (non-hybrid collection)...")
                results = self.qdrant_client.query_points(
                    collection_name=self.collection_name,
                    query=query_vector,
                    limit=self.top_k,
                    score_threshold=self.score_threshold,
                    with_payload=True
                ).points
            else:
                raise
        
        return results
    
    def answer_question(self, question: str):
        """
        Answer a question using the CrewAI workflow.
        
        Args:
            question: User's question
            
        Returns:
            Dictionary with answer and sources
        """
        print(f"\n🔍 Searching for: '{question}'")
        
        # Search for relevant chunks
        results = self.search_document(question)
        
        print(f"📚 Found {len(results)} relevant chunks")
        
        # Check if we have relevant results
        if not results:
            return {
                'answer': "I am unable to answer you since your question is beyond my knowledge. Contact the administration for more information.",
                'sources': [],
                'raw_results': []
            }
        
        # Create tasks
        # Retrieval happens here in Python, not by agent
        retrieval_task = create_retrieval_task(
            self.context_analyzer_agent,  # Use instance agents
            question, 
            lambda q: results  # Pass pre-fetched results
        )
        
        answer_task = create_answer_task(
            self.answer_agent,  # Use instance agents
            question
        )
        
        # Set up task dependencies
        answer_task.context = [retrieval_task]
        
        # Create and run crew
        crew = Crew(
            agents=[self.context_analyzer_agent, self.answer_agent],  # Use instance agents
            tasks=[retrieval_task, answer_task],
            process=Process.sequential,
            verbose=True
        )
        
        print("\n🤖 Running CrewAI workflow...")
        result = crew.kickoff()
        
        # Extract sources from results
        sources = []
        for res in results:
            sources.append({
                'page': res.payload.get('page'),
                'score': res.score,
                'text': res.payload.get('text')[:200] + "..."  # First 200 chars
            })
        
        return {
            'answer': str(result),
            'sources': sources,
            'raw_results': results
        }
    
    def interactive_mode(self):
        """Run in interactive CLI mode"""
        print("\n" + "="*60)
        print("🎓 ACC|Sprints Chatbot - Interactive Mode")
        print("="*60)
        print("Ask your common questions without waiting for a human to respond!")
        print("Type 'quit' or 'exit' to stop.\n")
        
        while True:
            question = input("❓ Your question: ").strip()
            
            if not question:
                continue
            
            if question.lower() in ['quit', 'exit', 'q']:
                print("👋 Goodbye!")
                break
            
            try:
                result = self.answer_question(question)
                
                print("\n💬 Answer:")
                print("-" * 60)
                print(result['answer'])
                print("-" * 60)
                
                if result['sources']:
                    print("\n📖 Sources:")
                    for source in result['sources']:
                        print(f"  • Page {source['page']} (score: {source['score']:.3f})")
                        print(f"    {source['text']}")
                
                print("\n")
                
            except Exception as e:
                print(f"❌ Error: {e}")
                print("Please try again.\n")


def main():
    """Main entry point"""
    try:
        runner = ChatbotRunner()
        runner.interactive_mode()
    except Exception as e:
        print(f"❌ Failed to start chatbot: {e}")
        print("\nMake sure:")
        print("1. Qdrant is running (if docker is locally used: docker run -p 6333:6333 qdrant/qdrant)")
        print("2. You've run the ingestion script (python ingest.py Your_FAQ_Document.pdf)")
        print("3. Your .env file has OPENAI_API_KEY set, and your Qdrant connection details if not using local mode.")


if __name__ == "__main__":
    main()
