"""
Quick script to test Qdrant Cloud connection
"""
import os
from dotenv import load_dotenv
from qdrant_client import QdrantClient

# Load environment variables
load_dotenv()

def test_connection():
    print("🔄 Testing Qdrant Cloud connection...")
    print(f"Mode: {os.getenv('QDRANT_MODE')}")
    print(f"URL: {os.getenv('QDRANT_URL')}")
    print(f"API Key: {'*' * 20}{os.getenv('QDRANT_API_KEY')[-10:] if os.getenv('QDRANT_API_KEY') else 'None'}")
    print()
    
    try:
        # Create client
        client = QdrantClient(
            url=os.getenv('QDRANT_URL'),
            api_key=os.getenv('QDRANT_API_KEY')
        )
        
        # Test connection by listing collections
        collections = client.get_collections()
        
        print("✅ Connection successful!")
        print(f"\nFound {len(collections.collections)} collection(s):")
        for collection in collections.collections:
            print(f"  • {collection.name}")
            
        # Get collection info if exists
        collection_name = os.getenv('COLLECTION_NAME', 'Sprints_FQA_Collection')
        try:
            collection_info = client.get_collection(collection_name)
            print(f"\n📊 Collection '{collection_name}' details:")
            print(f"  • Vectors count: {collection_info.points_count}")
            print(f"  • Vector size: {collection_info.config.params.vectors}")
        except Exception as e:
            print(f"\n⚠️  Collection '{collection_name}' not found (this is normal if you haven't ingested data yet)")
            
    except Exception as e:
        print(f"❌ Connection failed!")
        print(f"Error: {str(e)}")
        return False
    
    return True

if __name__ == "__main__":
    test_connection()
