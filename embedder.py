"""
Text Embeddings using OpenAI
"""
import os
import time
from functools import wraps
from openai import OpenAI, APIError, RateLimitError, APIConnectionError
from dotenv import load_dotenv

load_dotenv()


MODEL_DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


def retry_with_exponential_backoff(
    max_retries=3,
    initial_delay=1.0,
    exponential_base=2.0,
    errors=(APIError, APIConnectionError, RateLimitError)
):
    """
    Decorator to retry API calls with exponential backoff.
    
    Prevents transient failures (rate limits, network issues) from crashing ingestion.
    
    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        exponential_base: Multiplier for each retry (2.0 = double delay each time)
        errors: Tuple of exception types to retry on
        
    Returns:
        Decorated function with retry logic
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except errors as e:
                    last_exception = e
                    if attempt == max_retries:
                        print(f"❌ Max retries ({max_retries}) reached. Giving up.")
                        raise
                    
                    print(f"⚠️  API error (attempt {attempt + 1}/{max_retries + 1}): {type(e).__name__}")
                    print(f"   Retrying in {delay:.1f}s...")
                    time.sleep(delay)
                    delay *= exponential_base
            
            raise last_exception
        return wrapper
    return decorator


class EmbeddingGenerator:
    """Generate embeddings using OpenAI API"""
    
    def __init__(self, model=None):
        """
        Initialize the embedding generator.
        
        Args:
            model: OpenAI embedding model (default: text-embedding-3-small)
        """
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "❌ OPENAI_API_KEY not set!\n"
                "Please add your API key to the .env file.\n"
                "Get it from: https://platform.openai.com/api-keys"
            )
        
        self.client = OpenAI(api_key=api_key)
        self.model = model or os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
        self._cached_vector_size = None  # Cache for unknown models
        print(f"🔑 Initialized OpenAI embeddings with model: {self.model}")
    
    @retry_with_exponential_backoff()  # Add retry logic to API calls
    def embed_text(self, text):
        """
        Generate embedding for a single text.
        
        Args:
            text: Text string to embed
            
        Returns:
            List of floats representing the embedding vector
        """
        response = self.client.embeddings.create(
            input=text,
            model=self.model
        )
        return response.data[0].embedding
    
    @retry_with_exponential_backoff()  # Add retry logic to API calls
    def embed_batch(self, texts, batch_size=100):
        """
        Generate embeddings for multiple texts.
        
        Args:
            texts: List of text strings
            batch_size: Number of texts to process in one API call
            
        Returns:
            List of embedding vectors
        """
        embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            print(f"📊 Embedding batch {i//batch_size + 1} ({len(batch)} texts)...")
            
            response = self.client.embeddings.create(
                input=batch,
                model=self.model
            )
            
            batch_embeddings = [item.embedding for item in response.data]
            embeddings.extend(batch_embeddings)
        
        return embeddings
    
    def get_vector_size(self):
        """
        Get the dimension of the embedding vectors efficiently.
        
        Uses lookup table for known models, caches result for unknown models.
        Avoids repeated API calls.
        
        Returns:
            Integer dimension size
        """
        # Check lookup table first (O(1), no API call)
        if self.model in MODEL_DIMENSIONS:
            return MODEL_DIMENSIONS[self.model]
        
        # Check cache for unknown models
        if self._cached_vector_size is not None:
            return self._cached_vector_size
        
        # Fallback: fetch once and cache (only for unknown models)
        print(f"⚠️  Unknown model '{self.model}', fetching dimensions...")
        test_embedding = self.embed_text("test")
        self._cached_vector_size = len(test_embedding)
        return self._cached_vector_size


if __name__ == "__main__":
    # Test embeddings
    try:
        embedder = EmbeddingGenerator()
        
        # Test single embedding
        test_text = "This is a test sentence."
        embedding = embedder.embed_text(test_text)
        
        print(f"✅ Successfully generated embedding!")
        print(f"📏 Vector dimension: {len(embedding)}")
        print(f"📊 First 5 values: {embedding[:5]}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
