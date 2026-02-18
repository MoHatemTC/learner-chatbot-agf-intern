"""
Text Chunking Utilities
Split documents into overlapping chunks for better retrieval
"""
import os
import re
import hashlib  # FIX#3: Import hashlib for content-based IDs
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()


class TextChunker:
    """Split text into overlapping chunks"""
    
    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 100) -> None:  # FIX#6: Add return type hint
        """
        Initialize the chunker.
        
        Args:
            chunk_size: Maximum characters per chunk
            chunk_overlap: Number of overlapping characters between chunks
        """
        self.chunk_size = int(os.getenv("CHUNK_SIZE", chunk_size))
        self.chunk_overlap = int(os.getenv("CHUNK_OVERLAP", chunk_overlap))
        print(f"📄 Chunker initialized: size={self.chunk_size}, overlap={self.chunk_overlap}")
    
    def clean_text(self, text: str) -> str:
        """
        Clean and normalize text.
        
        Args:
            text: Raw text string
            
        Returns:
            Cleaned text
        """
        # Remove multiple spaces
        text = re.sub(r'\s+', ' ', text)
        
        # Remove multiple newlines
        text = re.sub(r'\n+', '\n', text)
        
        # Strip leading/trailing whitespace
        text = text.strip()
        
        return text
    
    def chunk_text(self, text: str, metadata: Dict = None) -> List[Dict]:
        """
        Split text into overlapping chunks.
        
        Args:
            text: Text to split
            metadata: Optional metadata to attach to each chunk
            
        Returns:
            List of dictionaries with chunk text and metadata
        """
        # Clean text first
        text = self.clean_text(text)
        
        if not text:
            return []
        
        chunks = []
        start = 0
        
        while start < len(text):
            # Get chunk end position
            end = start + self.chunk_size
            
            # If not at the end, try to break at sentence or word boundary
            if end < len(text):
                # Look for sentence end (., !, ?) within the last 100 chars
                sentence_end = max(
                    text.rfind('. ', start, end),
                    text.rfind('! ', start, end),
                    text.rfind('? ', start, end)
                )
                
                if sentence_end > start:
                    end = sentence_end + 1
                else:
                    # Try word boundary
                    space = text.rfind(' ', start, end)
                    if space > start:
                        end = space
            
            # Extract chunk
            chunk_text = text[start:end].strip()
            
            if chunk_text:
                # FIX#3: Generate content-addressable chunk_id using MD5 hash
                # This ensures identical content always gets the same ID (idempotent ingestion)
                chunk_id = hashlib.md5(chunk_text.encode()).hexdigest()
                
                chunk_data = {
                    'chunk_id': chunk_id,
                    'text': chunk_text,
                    'char_start': start,
                    'char_end': end,
                }
                
                # Add custom metadata
                if metadata:
                    chunk_data.update(metadata)
                
                chunks.append(chunk_data)
            
            # Move start position (with overlap)
            new_start = end - self.chunk_overlap
            
            # Prevent infinite loop - ensure we always move forward
            if new_start <= start:
                new_start = start + 1
            
            start = new_start
            
            # Break if we've processed everything
            if end >= len(text):
                break
        
        return chunks
    
    def chunk_by_pages(self, pages_dict: Dict[int, str], base_metadata: Dict = None) -> List[Dict]:
        """
        Chunk text that's already separated by pages.
        
        Args:
            pages_dict: Dictionary mapping page_number -> text
            base_metadata: Base metadata for all chunks
            
        Returns:
            List of chunks with page metadata
        """
        all_chunks = []
        
        for page_num, page_text in pages_dict.items():
            # Create metadata for this page
            page_metadata = {'page': page_num}
            if base_metadata:
                page_metadata.update(base_metadata)
            
            # Chunk the page
            page_chunks = self.chunk_text(page_text, page_metadata)
            all_chunks.extend(page_chunks)
            
            print(f"📄 Page {page_num}: {len(page_chunks)} chunks")
        
        return all_chunks


if __name__ == "__main__":
    # Test chunker
    chunker = TextChunker(chunk_size=200, chunk_overlap=50)
    
    test_text = """
    This is the first sentence. This is the second sentence. 
    This is the third sentence. This is the fourth sentence.
    This is the fifth sentence. This is the sixth sentence.
    This is the seventh sentence. This is the eighth sentence.
    """
    
    chunks = chunker.chunk_text(test_text, metadata={'source': 'test.txt'})
    
    print(f"\n✅ Created {len(chunks)} chunks:")
    for i, chunk in enumerate(chunks):
        print(f"\nChunk {i}:")
        print(f"  Text: {chunk['text'][:100]}...")
        print(f"  Char range: {chunk['char_start']}-{chunk['char_end']}")
