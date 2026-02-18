"""
Hybrid PDF Ingestion Pipeline
Load, parse, chunk, embed, and store PDF documents in Qdrant
Supports:
- Text extraction with Gemini Vision OCR fallback
- Dual embeddings: text chunks (OpenAI) + page images (Gemini)
- Named vectors in Qdrant for hybrid search capability
- PyMuPDF for all PDF operations
"""

import os
import uuid
import hashlib
import fitz  # PyMuPDF
from PIL import Image
import io
from dotenv import load_dotenv

from qdrant_client.models import PointStruct
from chunking import TextChunker
from embedder import EmbeddingGenerator
from multimodal_embedder import MultimodalEmbedder
from qdrant_utils import get_qdrant_client, create_collection

load_dotenv()


def generate_deterministic_id(source: str, page: int, chunk_id: int) -> str:
    """
    Generate deterministic UUID from content metadata.
    Convert SHA-256 hash to UUID format (Qdrant requirement).
    This prevents duplicate vectors when re-running ingestion.
    Same content → same ID → Qdrant updates existing point instead of creating duplicate.
    
    Args:
        source: Source filename
        page: Page number
        chunk_id: Chunk ID within the page
        
    Returns:
        Deterministic UUID string (format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)
    """
    content = f"{source}|{page}|{chunk_id}"
    hash_bytes = hashlib.sha256(content.encode()).digest()
    # Use first 128 bits (16 bytes) of SHA-256 to create UUID
    return str(uuid.UUID(bytes=hash_bytes[:16]))


class HybridPDFIngestor:
    """Ingest PDF documents into Qdrant with hybrid text+image embeddings"""
    
    def __init__(self, use_hybrid=True, ocr_threshold=50, always_use_gemini=False):
        """
        Initialize the hybrid PDF ingestor.
        
        Args:
            use_hybrid: Enable hybrid text+image embeddings (default: True)
            ocr_threshold: Minimum characters to skip OCR (default: 50) - used when always_use_gemini=False
            always_use_gemini: Always use Gemini Vision for ALL pages to capture visual content (default: False)
        """
        print("🚀 Initializing Hybrid PDF Ingestor...")
        print(f"   Mode: {'Hybrid (Text + Image)' if use_hybrid else 'Text Only'}")
        print(f"   OCR Strategy: {'Always use Gemini Vision' if always_use_gemini else f'Smart detection (threshold: {ocr_threshold} chars)'}")
        
        # Configuration
        self.use_hybrid = use_hybrid
        self.ocr_threshold = ocr_threshold
        self.always_use_gemini = always_use_gemini
        
        # Initialize components
        self.chunker = TextChunker()
        self.embedder = EmbeddingGenerator()
        
        # Initialize multimodal embedder if hybrid mode
        if self.use_hybrid:
            try:
                self.multimodal_embedder = MultimodalEmbedder()
                image_vector_size = self.multimodal_embedder.get_vector_size()
            except Exception as e:
                print(f"⚠️  Failed to initialize multimodal embedder: {e}")
                print("   Falling back to text-only mode")
                self.use_hybrid = False
                self.multimodal_embedder = None
                image_vector_size = None
        else:
            self.multimodal_embedder = None
            image_vector_size = None
        
        # Qdrant setup
        self.qdrant_client = get_qdrant_client()
        self.collection_name = os.getenv("COLLECTION_NAME", "FAQ_collection")
        
        # Get vector sizes
        text_vector_size = self.embedder.get_vector_size()
        print(f"📏 Text vector dimension: {text_vector_size}")
        if image_vector_size:
            print(f"📏 Image vector dimension: {image_vector_size}")
        
        # Create collection with hybrid support if needed
        create_collection(
            self.qdrant_client, 
            self.collection_name, 
            vector_size=text_vector_size,
            image_vector_size=image_vector_size
        )
    
    def has_images_or_diagrams(self, page: fitz.Page) -> bool:
        """
        Detect if a PDF page contains images or diagrams using PyMuPDF.
        
        Args:
            page: PyMuPDF page object
            
        Returns:
            True if page contains images/diagrams, False otherwise
        """
        try:
            # Get list of images on the page
            image_list = page.get_images(full=False)
            return len(image_list) > 0
        except Exception as e:
            print(f"⚠️  Image detection failed: {e}")
            return False
    
    def ocr_page_with_gemini(self, pdf_doc: fitz.Document, page_num: int, has_images: bool = False) -> str:
        """
        Extract text AND describe visual elements from a PDF page using Gemini Vision.
        (Renders page to image internally - use ocr_page_with_gemini_from_image if image already exists)
        
        Args:
            pdf_doc: PyMuPDF document object
            page_num: Page number (0-indexed for PyMuPDF)
            has_images: Whether the page contains images/diagrams
            
        Returns:
            Extracted text and visual descriptions from Gemini Vision
        """
        # Check if multimodal embedder is available
        if self.multimodal_embedder is None:
            print(f"⚠️  Gemini Vision skipped for page {page_num + 1}: Not available (text-only mode)")
            return ""
        
        try:
            # Get the page
            page = pdf_doc[page_num]
            
            # Render page to image (PIL)
            pix = page.get_pixmap(dpi=150)
            img_data = pix.pil_tobytes(format="PNG")
            image = Image.open(io.BytesIO(img_data))
            
            # Use Gemini Vision for comprehensive extraction
            # Use enhanced OCR if page has images/diagrams
            text = self.multimodal_embedder.ocr_image(image, has_images=has_images)
            
            if not text:
                print(f"⚠️  Gemini Vision returned empty text for page {page_num + 1}")
                return ""
            
            return text.strip()
            
        except Exception as e:
            print(f"❌ Gemini Vision failed for page {page_num + 1}: {type(e).__name__}: {str(e)}")
            import traceback
            print(f"   Traceback: {traceback.format_exc()[:200]}...")
            return ""
    
    def ocr_page_with_gemini_from_image(self, image: Image.Image, page_num: int, has_images: bool = False) -> str:
        """
        Extract text AND describe visual elements from a pre-rendered page image using Gemini Vision.
        (Optimized: uses existing image instead of rendering again)
        
        Args:
            image: PIL Image object of the page
            page_num: Page number (1-indexed for display)
            has_images: Whether the page contains images/diagrams
            
        Returns:
            Extracted text and visual descriptions from Gemini Vision
        """
        # Check if multimodal embedder is available
        if self.multimodal_embedder is None:
            print(f"⚠️  Gemini Vision skipped for page {page_num}: Not available (text-only mode)")
            return ""
        
        try:
            # Use Gemini Vision for comprehensive extraction
            text = self.multimodal_embedder.ocr_image(image, has_images=has_images)
            
            if not text:
                print(f"⚠️  Gemini Vision returned empty text for page {page_num}")
                return ""
            
            return text.strip()
            
        except Exception as e:
            print(f"❌ Gemini Vision failed for page {page_num}: {type(e).__name__}: {str(e)}")
            import traceback
            print(f"   Traceback: {traceback.format_exc()[:200]}...")
            return ""
    
    def load_pdf(self, pdf_path: str, page_images: dict = None) -> dict:
        """
        Load and parse a PDF file with intelligent Gemini Vision processing.
        Uses PyMuPDF for text extraction with smart Gemini Vision enhancement.
        
        Strategy:
        - If always_use_gemini=True: Use Gemini Vision for ALL pages
        - Otherwise: Use Gemini Vision if:
          a) Text extraction is poor (< threshold chars), OR
          b) Page contains images/diagrams (which may have important visual info)
        
        Args:
            pdf_path: Path to the PDF file
            page_images: Optional dict mapping page_number (1-indexed) -> PIL Image.
                        If provided, uses cached images for Gemini Vision (optimization).
            
        Returns:
            Tuple of (pages_dict, metadata_dict) where:
            - pages_dict: Dictionary mapping page_number -> text
            - metadata_dict: Dictionary mapping page_number -> content_type metadata
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        
        mode_str = "with cached images" if page_images else "with intelligent Gemini Vision processing"
        print(f"📖 Loading PDF {mode_str}: {pdf_path}")
        pdf_doc = fitz.open(pdf_path)
        
        pages = {}
        page_metadata = {}  # FIX#2: Track content type per page
        ocr_count = 0
        image_page_count = 0
        
        for page_num in range(len(pdf_doc)):
            page = pdf_doc[page_num]
            text = page.get_text()
            
            # Check if text extraction was successful
            if text:
                text = text.strip()
            
            # Detect if page has images/diagrams
            has_images = self.has_images_or_diagrams(page)
            if has_images:
                image_page_count += 1
            
            # Decide whether to use Gemini Vision
            use_gemini = False
            reason = ""
            
            if self.always_use_gemini:
                use_gemini = True
                reason = "always_use_gemini=True"
            elif not text or len(text) < self.ocr_threshold:
                use_gemini = True
                reason = f"poor text extraction ({len(text) if text else 0} chars < {self.ocr_threshold})"
            elif has_images:
                use_gemini = True
                reason = "page contains images/diagrams"
            
            # Use Gemini Vision if needed
            if use_gemini:
                print(f"  Page {page_num + 1}: Using Gemini Vision ({reason})...")
                
                # Use cached image if available (optimization), otherwise render on-demand
                if page_images and (page_num + 1) in page_images:
                    gemini_text = self.ocr_page_with_gemini_from_image(
                        page_images[page_num + 1], 
                        page_num + 1, 
                        has_images=has_images
                    )
                else:
                    gemini_text = self.ocr_page_with_gemini(pdf_doc, page_num, has_images=has_images)
                
                if gemini_text:
                    # FIX#2: Track content type based on what was combined
                    # Combine PyMuPDF text with Gemini output for richer content
                    if text and len(text) >= self.ocr_threshold:
                        # Page has good text + images: combine both
                        text = f"{text}\n\n[Visual Content Description]\n{gemini_text}"
                        content_type = "text_with_visual_analysis"  # FIX#2: Mixed content
                    else:
                        # Low quality text: use Gemini output
                        text = gemini_text
                        content_type = "image_analysis_only"  # FIX#2: Pure visual analysis
                    ocr_count += 1
                else:
                    # Gemini failed - use what we have
                    content_type = "text_only"  # FIX#2: Only primary text
                    if not text:
                        # Gemini failed and no text: skip this page
                        print(f"⚠️  Page {page_num + 1}: Both PyMuPDF and Gemini Vision failed")
                        continue
            else:
                # Not using Gemini - pure text extraction
                content_type = "text_only"  # FIX#2: Only primary text
            
            if text:
                pages[page_num + 1] = text  # Store with 1-indexed page numbers
                page_metadata[page_num + 1] = {"content_type": content_type}  # FIX#2: Store metadata
                print(f"  Page {page_num + 1}: {len(text)} characters{' (enhanced with Gemini)' if use_gemini and gemini_text else ''}")
        
        pdf_doc.close()
        print(f"✅ Loaded {len(pages)} pages from PDF")
        print(f"   📊 Stats: {ocr_count} pages processed with Gemini Vision, {image_page_count} pages contain images")
        return pages, page_metadata  # FIX#2: Return metadata along with pages
    
    def convert_pdf_to_images(self, pdf_path: str) -> dict:
        """
        Convert PDF pages to images using PyMuPDF.
        Renders all pages once - images are reused for both OCR and embeddings (optimization).
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Dictionary mapping page_number -> PIL Image
        """
        pdf_doc = fitz.open(pdf_path)
        
        page_images = {}
        for page_num in range(len(pdf_doc)):
            page = pdf_doc[page_num]
            # Render page to image at 150 DPI
            pix = page.get_pixmap(dpi=150)
            # Convert to PIL Image
            img_data = pix.pil_tobytes(format="PNG")
            img = Image.open(io.BytesIO(img_data))
            
            page_images[page_num + 1] = img  # Store with 1-indexed page numbers
            print(f"  Page {page_num + 1}: {img.size[0]}x{img.size[1]} pixels")
        
        pdf_doc.close()
        print(f"✅ Rendered {len(page_images)} pages (will be reused for OCR + embeddings)")
        return page_images
    
    def ingest_pdf(self, pdf_path: str):
        """
        Complete hybrid ingestion pipeline (OPTIMIZED):
        1. Convert PDF pages to images first (if hybrid mode) - renders once
        2. Load PDF text with OCR fallback (uses cached images for Gemini Vision)
        3. Chunk text with content_type metadata  # FIX#2
        4. Generate text embeddings
        5. Generate image embeddings (reuses same cached images)
        6. Store in Qdrant with named vectors and content_type metadata  # FIX#2
        
        Args:
            pdf_path: Path to the PDF file
        """
        # Extract filename
        filename = os.path.basename(pdf_path)
        
        # OPTIMIZATION: Convert PDF to images FIRST if hybrid mode
        # This allows both OCR and embeddings to use the same rendered images
        page_images = None
        if self.use_hybrid:
            print("🖼️  Step 1: Converting PDF pages to images (for OCR + embeddings reuse)...")
            page_images = self.convert_pdf_to_images(pdf_path)
        
        # FIX#2: Load PDF text with metadata (will use cached images for Gemini Vision if available)
        print("\n📖 Step 2: Extracting text content...")
        pages, page_metadata = self.load_pdf(pdf_path, page_images=page_images)
        
        # Chunk pages
        print("\n📄 Step 3: Chunking text...")
        base_metadata = {'source': filename}
        chunks = self.chunker.chunk_by_pages(pages, base_metadata)
        
        # FIX#2: Add content_type metadata to each chunk based on its page
        for chunk in chunks:
            page_num = chunk.get('page')
            if page_num in page_metadata:
                chunk['content_type'] = page_metadata[page_num]['content_type']
            else:
                chunk['content_type'] = 'text_only'  # Default fallback
        
        print(f"✅ Created {len(chunks)} total chunks")
        
        # Generate text embeddings
        print("\n🔢 Step 4: Generating text embeddings...")
        chunk_texts = [chunk['text'] for chunk in chunks]
        text_embeddings = self.embedder.embed_batch(chunk_texts)
        print(f"✅ Generated {len(text_embeddings)} text embeddings")
        
        # Generate image embeddings if hybrid mode (reuses cached images)
        image_embeddings_map = {}
        if self.use_hybrid and page_images:
            print("\n🖼️  Step 5: Generating image embeddings (reusing cached images)...")
            sorted_pages = sorted(page_images.keys())
            page_images_list = [page_images[p] for p in sorted_pages]
            image_embeddings_list = self.multimodal_embedder.embed_batch_images(page_images_list)
            image_embeddings_map = dict(zip(sorted_pages, image_embeddings_list))
            print(f"✅ Generated {len(image_embeddings_map)} image embeddings")
        
        # Prepare points for Qdrant
        print("\n💾 Step 6: Preparing data for Qdrant...")
        points = []
        for i, (chunk, text_embedding) in enumerate(zip(chunks, text_embeddings)):
            # Use deterministic IDs
            point_id = generate_deterministic_id(
                source=chunk.get('source'),
                page=chunk.get('page'),
                chunk_id=chunk.get('chunk_id')
            )
            
            # Prepare vector(s)
            if self.use_hybrid and image_embeddings_map:
                # Hybrid mode: named vectors for text and image
                page_num = chunk.get('page')
                image_embedding = image_embeddings_map.get(page_num)
                
                if image_embedding:
                    vector = {
                        'text': text_embedding,
                        'image': image_embedding
                    }
                else:
                    # Fallback to text-only if image embedding missing
                    vector = {'text': text_embedding}
            else:
                # Text-only mode
                vector = text_embedding
            
            point = PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    'text': chunk['text'],
                    'source': chunk.get('source'),
                    'page': chunk.get('page'),
                    'chunk_id': chunk.get('chunk_id'),
                    'char_start': chunk.get('char_start'),
                    'char_end': chunk.get('char_end'),
                    'content_type': chunk.get('content_type', 'text_only'),  # FIX#2: Store content type
                }
            )
            points.append(point)
        
        # Upload to Qdrant in batches
        print(f"\n☁️  Uploading {len(points)} points to Qdrant in batches...")
        
        # Use smaller batch size for cloud to avoid timeouts
        qdrant_mode = os.getenv("QDRANT_MODE", "local")
        batch_size = 5 if qdrant_mode == "cloud" else 100
        
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            print(f"  Uploading batch {i//batch_size + 1}/{(len(points) + batch_size - 1)//batch_size} ({len(batch)} points)...")
            
            # Retry logic for cloud uploads
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    self.qdrant_client.upsert(
                        collection_name=self.collection_name,
                        points=batch
                    )
                    break  # Success
                except Exception as e:
                    if attempt < max_retries - 1:
                        print(f"    ⚠️  Upload failed (attempt {attempt + 1}/{max_retries}), retrying...")
                        import time
                        time.sleep(2)  # Wait before retry
                    else:
                        print(f"    ❌ Upload failed after {max_retries} attempts")
                        raise
        
        print(f"✅ Successfully ingested '{filename}' into collection '{self.collection_name}'")
        
        # Print collection info (with error handling for hybrid collections)
        try:
            collection_info = self.qdrant_client.get_collection(self.collection_name)
            print(f"📊 Collection now has {collection_info.points_count} total points")
        except Exception as e:
            print(f"ℹ️  Could not fetch collection info (non-critical): {type(e).__name__}")
    
    def search(self, query: str, top_k: int = 5, search_mode: str = 'text'):
        """
        Search for similar chunks given a query.
        Uses text-only search since visual content is already in text chunks.
        
        Args:
            query: Search query text
            top_k: Number of results to return
            search_mode: 'text' (default) or 'both' (future: image search)
            
        Returns:
            List of search results
        """
        # Embed query as text
        query_vector = self.embedder.embed_text(query)
        
        # Text-only search (visual content is in text chunks via Gemini descriptions)
        try:
            using_vector = 'text' if self.use_hybrid else None
            results = self.qdrant_client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=top_k,
                with_payload=True,
                using=using_vector
            ).points
            return results
        except Exception:
            # Fallback: no named vector (for non-hybrid collections)
            results = self.qdrant_client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=top_k,
                with_payload=True
            ).points
            return results


def main():
    """Main ingestion script"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python ingest_hybrid.py <path_to_pdf> [OPTIONS]")
        print("Example: python ingest_hybrid.py document.pdf")
        print("\nOptions:")
        print("  --text-only       Disable hybrid mode (text embeddings only)")
        print("  --always-gemini   Always use Gemini Vision for ALL pages (captures images/diagrams)")
        print("\nRecommended: Use --always-gemini to ensure visual content is never missed")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    use_hybrid = '--text-only' not in sys.argv
    always_use_gemini = '--always-gemini' in sys.argv
    
    try:
        ingestor = HybridPDFIngestor(use_hybrid=use_hybrid, always_use_gemini=always_use_gemini)
        ingestor.ingest_pdf(pdf_path)
        
        # Test search (with error handling - non-critical)
        try:
            print("\n" + "="*60)
            print("🔍 Testing search functionality...")
            test_query = "What are the admission requirements?"
            results = ingestor.search(test_query, top_k=3)
            
            print(f"\nQuery: '{test_query}'")
            print(f"Found {len(results)} results:\n")
            
            for i, result in enumerate(results, 1):
                print(f"Result {i} (score: {result.score:.3f}):")
                print(f"  Page: {result.payload.get('page')}")
                print(f"  Text: {result.payload.get('text')[:200]}...")
                print()
        except Exception as test_error:
            print(f"ℹ️  Test search skipped (non-critical): {type(test_error).__name__}")
            print("   Ingestion completed successfully. Use runner.py for queries.")
        
    except Exception as e:
        print(f"❌ Error during ingestion: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
