"""
Multimodal Image Embeddings and OCR using Google Gemini
- Generates embeddings from page images to capture visual context
- Performs OCR using Gemini Vision API (no external OCR needed!)
"""
import os
import time
from functools import wraps
from typing import List, Union
import google.generativeai as genai
from PIL import Image
from dotenv import load_dotenv

load_dotenv()


def retry_with_exponential_backoff(
    max_retries=3,
    initial_delay=1.0,
    exponential_base=2.0,
):
    """
    Decorator to retry API calls with exponential backoff.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
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


class MultimodalEmbedder:
    """Generate multimodal embeddings and perform OCR using Google Gemini"""
    
    def __init__(self, model="models/gemini-embedding-001", vision_model="models/gemini-2.0-flash"):
        """
        Initialize the multimodal embedder.
        
        Args:
            model: Gemini embedding model for text (models/gemini-embedding-001 is the current model)
            vision_model: Gemini vision model for OCR (models/gemini-2.0-flash or models/gemini-2.5-flash)
        
        Note: As of 2026, Gemini's embedding models primarily support text.
              We use Vision models for OCR and text embeddings for vector storage.
              Updated model names: gemini-embedding-001 for embeddings, gemini-2.0-flash for vision.
        """
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "❌ GEMINI_API_KEY not set!\n"
                "Please add your API key to the .env file.\n"
                "Get it from: https://makersuite.google.com/app/apikey"
            )
        
        genai.configure(api_key=api_key)
        self.model = model
        self.vision_model = vision_model
        self._cached_vector_size = None
        
        # Initialize vision model for OCR
        self.ocr_model = genai.GenerativeModel(vision_model)
        
        print(f"🖼️  Initialized Gemini text embeddings with model: {self.model}")
        print(f"🔤 Initialized Gemini Vision OCR with model: {self.vision_model}")
    
    @retry_with_exponential_backoff()
    def embed_image(self, image: Union[str, Image.Image]) -> List[float]:
        """
        Generate embedding for an image by first describing it with Vision API,
        then embedding the description.
        
        Note: Gemini doesn't support direct image embeddings, so we use a two-step approach:
        1. Vision model describes the image content
        2. Text embedding model embeds the description
        
        Args:
            image: PIL Image object or path to image file
            
        Returns:
            List of floats representing the embedding vector
        """
        # Load image if path provided
        if isinstance(image, str):
            image = Image.open(image)
        
        # Step 1: Use vision model to describe the image
        prompt = "Describe this page image in detail, including all visible text, layout elements, diagrams, and tables. Be comprehensive."
        description_response = self.ocr_model.generate_content([prompt, image])
        description = description_response.text if description_response and description_response.text else "Empty page"
        
        # Step 2: Embed the text description
        result = genai.embed_content(
            model=self.model,
            content=description,
            task_type="retrieval_document"
        )
        
        return result['embedding']
    
    @retry_with_exponential_backoff()
    def embed_batch_images(self, images: List[Union[str, Image.Image]], batch_size=10) -> List[List[float]]:
        """
        Generate embeddings for multiple images.
        
        Note: Gemini API processes images one at a time, but we batch the requests
        
        Args:
            images: List of PIL Image objects or paths
            batch_size: Number of images to process in parallel (for progress tracking)
            
        Returns:
            List of embedding vectors
        """
        embeddings = []
        
        for i in range(0, len(images), batch_size):
            batch = images[i:i + batch_size]
            print(f"🖼️  Embedding image batch {i//batch_size + 1} ({len(batch)} images)...")
            
            for img in batch:
                embedding = self.embed_image(img)
                embeddings.append(embedding)
                
                # Small delay to respect rate limits
                time.sleep(0.1)
        
        return embeddings
    
    @retry_with_exponential_backoff()
    def ocr_image(self, image: Union[str, Image.Image], has_images: bool = False) -> str:
        """
        Extract text AND describe visual elements from an image using Gemini Vision API.
        
        Args:
            image: PIL Image object or path to image file
            has_images: Whether the page contains images/diagrams (uses enhanced prompt)
            
        Returns:
            Extracted text and visual descriptions from the image
        """
        # Load image if path provided
        if isinstance(image, str):
            image = Image.open(image)
        
        # Use enhanced prompt if page has images/diagrams
        if has_images:
            prompt = """Analyze this page image comprehensively and provide:

1. ALL VISIBLE TEXT: Extract all text exactly as it appears, preserving layout and formatting.

2. VISUAL ELEMENTS: Describe any charts, diagrams, images, tables, or graphics in detail, including:
   - What the visual shows
   - Key data points or labels
   - Relationships or patterns illustrated
   - Any text within images or diagrams

3. LAYOUT: Note the overall structure and how text relates to visual elements.

Be thorough and comprehensive. This information will be used for semantic search, so include all details that someone might search for."""
        else:
            # Text-focused prompt for pages without images
            prompt = "Extract all text from this image accurately. Preserve layout, formatting, tables, and structure as much as possible. Be comprehensive and include all visible text."
        
        response = self.ocr_model.generate_content([prompt, image])
        
        # Extract text from response with better error handling
        if response:
            if hasattr(response, 'text') and response.text:
                return response.text.strip()
            elif hasattr(response, 'parts') and response.parts:
                # Try to extract from parts if direct text access fails
                text_parts = [part.text for part in response.parts if hasattr(part, 'text')]
                if text_parts:
                    return '\n'.join(text_parts).strip()
        
        # Log warning if extraction failed
        print(f"⚠️  Gemini Vision returned empty or invalid response")
        return ""
    
    def get_vector_size(self) -> int:
        """
        Get the dimension of the embedding vectors.
        
        Returns:
            Integer dimension size
        """
        if self._cached_vector_size is not None:
            return self._cached_vector_size
        
        # Test with simple text embedding (faster than image)
        print(f"📏 Detecting vector dimension for {self.model}...")
        test_embedding = genai.embed_content(
            model=self.model,
            content="test",
            task_type="retrieval_document"
        )
        self._cached_vector_size = len(test_embedding['embedding'])
        print(f"✅ Vector dimension: {self._cached_vector_size}")
        
        return self._cached_vector_size


if __name__ == "__main__":
    # Test multimodal embeddings
    try:
        embedder = MultimodalEmbedder()
        
        # Create test image
        test_image = Image.new('RGB', (200, 200), color='blue')
        
        # Generate embedding
        embedding = embedder.embed_image(test_image)
        
        print(f"✅ Successfully generated image embedding!")
        print(f"📏 Vector dimension: {len(embedding)}")
        print(f"📊 First 5 values: {embedding[:5]}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
