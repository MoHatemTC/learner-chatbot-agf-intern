"""
Qdrant Client Configuration and Connection
Handles both local and cloud Qdrant instances
"""
import os
import sys  #For exit on connection failure
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
from qdrant_client.http.exceptions import UnexpectedResponse  # For connection errors
from dotenv import load_dotenv

load_dotenv()

def get_qdrant_client():
    """
    Create and return a Qdrant client with connection validation.
    
    For local mode (default): Uses Docker container at localhost:6333
    For cloud mode: Uses Qdrant Cloud URL and API key
    
    Raises helpful error if Qdrant is not accessible.
    """
    mode = os.getenv("QDRANT_MODE", "local")
    
    if mode == "local":
        # Local Qdrant (Docker)
        url = os.getenv("QDRANT_URL", "http://localhost:6333")
        print(f"📦 Connecting to local Qdrant at {url}")
        
        try:
            # Create client (check_compatibility removed for broader version support)
            client = QdrantClient(url=url, timeout=5)
            # Test connection immediately
            client.get_collections()
            return client
        except Exception as e:
            print(f"\n❌ Failed to connect to Qdrant at {url}")
            print(f"Error: {type(e).__name__}: {e}")
            print("\n🔧 Troubleshooting Steps:")
            print("1. Is Docker Desktop running?")
            print("   - Check for green whale icon in system tray (Windows)")
            print("   - Or in menu bar (macOS)")
            print("\n2. Is Qdrant container running?")
            print("   - Run: docker-compose ps")
            print("   - Should show 'qdrant' service as 'Up'")
            print("\n3. Start Qdrant if not running:")
            print("   - Run: docker-compose up -d")
            print("   - Wait 5-10 seconds for it to start")
            print("   - Verify at: http://localhost:6333/dashboard")
            print("\n4. Check Docker logs for errors:")
            print("   - Run: docker-compose logs qdrant")
            print("\n5. Restart Qdrant if needed:")
            print("   - Run: docker-compose restart qdrant")
            raise ConnectionError(
                f"Cannot connect to Qdrant at {url}. "
                "Make sure Docker Desktop is running and Qdrant container is started (docker-compose up -d)."
            ) from e
    else:
        # Qdrant Cloud
        url = os.getenv("QDRANT_URL")
        api_key = os.getenv("QDRANT_API_KEY")
        
        if not url or not api_key:
            raise ValueError(
                "For cloud mode, set QDRANT_URL and QDRANT_API_KEY in .env"
            )
        
        print(f"☁️  Connecting to Qdrant Cloud at {url}")
        try:
            # Use longer timeout for cloud (network latency + larger payloads)
            client = QdrantClient(url=url, api_key=api_key, timeout=60)
            client.get_collections()  # Test connection
            return client
        except Exception as e:
            raise ConnectionError(
                f"Cannot connect to Qdrant Cloud at {url}. Check your URL and API key."
            ) from e


def create_collection(client, collection_name, vector_size=1536, image_vector_size=None):
    """
    Create a Qdrant collection for storing document embeddings.
    Supports dual vectors: text embeddings + optional image embeddings.
    
    Args:
        client: QdrantClient instance
        collection_name: Name of the collection
        vector_size: Dimension of text embeddings (1536 for text-embedding-3-small)
        image_vector_size: Optional dimension of image embeddings (for hybrid mode)
    """
    # Check if collection already exists
    collections = client.get_collections().collections
    collection_names = [col.name for col in collections]
    
    if collection_name in collection_names:
        print(f"✅ Collection '{collection_name}' already exists")
        return
    
    # Configure vectors - use named vectors for hybrid approach
    if image_vector_size:
        # Hybrid mode: both text and image embeddings
        vectors_config = {
            "text": VectorParams(
                size=vector_size,
                distance=Distance.COSINE
            ),
            "image": VectorParams(
                size=image_vector_size,
                distance=Distance.COSINE
            )
        }
        print(f"🎨 Creating hybrid collection with text({vector_size}) + image({image_vector_size}) vectors")
    else:
        # Text-only mode (backward compatible)
        vectors_config = VectorParams(
            size=vector_size,
            distance=Distance.COSINE
        )
        print(f"📝 Creating text-only collection with vector size {vector_size}")
    
    # Create collection
    client.create_collection(
        collection_name=collection_name,
        vectors_config=vectors_config
    )
    print(f"✅ Created collection '{collection_name}'")


def search_similar(client, collection_name, query_vector, top_k=5, score_threshold=0.5, vector_name=None):
    """
    Search for similar vectors in the collection.
    
    Args:
        client: QdrantClient instance
        collection_name: Name of the collection to search
        query_vector: Query embedding vector
        top_k: Number of results to return
        score_threshold: Minimum similarity score (0-1)
        vector_name: Name of the vector to search (e.g., "text" or "image" for hybrid collections)
    
    Returns:
        List of search results with payload and metadata
    """
    search_params = {
        "collection_name": collection_name,
        "query": query_vector,
        "limit": top_k,
        "score_threshold": score_threshold,
        "with_payload": True
    }
    
    # Add vector name for named vectors (hybrid mode)
    if vector_name:
        search_params["using"] = vector_name
    
    results = client.query_points(**search_params).points
    
    return results


if __name__ == "__main__":
    # Test connection
    try:
        client = get_qdrant_client()
        print("✅ Successfully connected to Qdrant!")
        
        # List existing collections
        collections = client.get_collections()
        print(f"📚 Existing collections: {[col.name for col in collections.collections]}")
        
    except Exception as e:
        print(f"❌ Error connecting to Qdrant: {e}")
        print("\n💡 If using local mode, make sure Docker is running:")
        print("   docker run -p 6333:6333 qdrant/qdrant")
