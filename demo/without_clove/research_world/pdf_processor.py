"""
PDF Processor

Handles:
- PDF text extraction
- Chunking for LLM context
- Metadata extraction
- Document indexing
"""

import json
import hashlib
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Iterator
import config

# Try to import PDF libraries
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    from pypdf import PdfReader
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False


@dataclass
class DocumentChunk:
    """A chunk of text from a document."""
    doc_id: str
    chunk_id: int
    text: str
    page_numbers: list[int]
    metadata: dict = field(default_factory=dict)


@dataclass
class ProcessedDocument:
    """A processed PDF document."""
    doc_id: str
    filename: str
    title: str
    num_pages: int
    num_chunks: int
    total_chars: int
    chunks: list[DocumentChunk] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "doc_id": self.doc_id,
            "filename": self.filename,
            "title": self.title,
            "num_pages": self.num_pages,
            "num_chunks": self.num_chunks,
            "total_chars": self.total_chars,
            "metadata": self.metadata,
            "chunks": [asdict(c) for c in self.chunks],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProcessedDocument":
        """Create from dictionary."""
        chunks = [DocumentChunk(**c) for c in data.pop("chunks", [])]
        return cls(**data, chunks=chunks)


class PDFProcessor:
    """
    Processes PDF files for research.

    Features:
    - Text extraction (PyMuPDF or pypdf)
    - Smart chunking for LLM context windows
    - Caching of processed documents
    - Metadata extraction
    """

    def __init__(
        self,
        pdf_dir: Path = None,
        processed_dir: Path = None,
        chunk_size: int = 4000,  # Characters per chunk
        chunk_overlap: int = 200,  # Overlap between chunks
    ):
        self.pdf_dir = pdf_dir or config.PDF_DIR
        self.processed_dir = processed_dir or config.PROCESSED_DIR
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        # Check available libraries
        if not PYMUPDF_AVAILABLE and not PYPDF_AVAILABLE:
            print("[PDF] WARNING: No PDF library available. Install pymupdf or pypdf")
            print("      pip install pymupdf  # Recommended")
            print("      pip install pypdf    # Alternative")

    def process_all(self) -> list[ProcessedDocument]:
        """Process all PDFs in the pdf directory."""
        documents = []
        pdf_files = list(self.pdf_dir.glob("*.pdf"))

        if not pdf_files:
            print(f"[PDF] No PDF files found in {self.pdf_dir}")
            return documents

        print(f"[PDF] Processing {len(pdf_files)} PDF files...")

        for pdf_path in pdf_files:
            doc = self.process_file(pdf_path)
            if doc:
                documents.append(doc)
                print(f"  - {doc.filename}: {doc.num_pages} pages, {doc.num_chunks} chunks")

        return documents

    def process_file(self, pdf_path: Path) -> ProcessedDocument | None:
        """Process a single PDF file."""
        # Check cache first
        doc_id = self._get_doc_id(pdf_path)
        cached = self._load_cached(doc_id)
        if cached:
            return cached

        # Extract text
        try:
            if PYMUPDF_AVAILABLE:
                text, metadata, num_pages = self._extract_with_pymupdf(pdf_path)
            elif PYPDF_AVAILABLE:
                text, metadata, num_pages = self._extract_with_pypdf(pdf_path)
            else:
                print(f"[PDF] Cannot process {pdf_path.name}: No PDF library")
                return None
        except Exception as e:
            print(f"[PDF] Error processing {pdf_path.name}: {e}")
            return None

        # Create chunks
        chunks = list(self._create_chunks(doc_id, text))

        # Create document
        doc = ProcessedDocument(
            doc_id=doc_id,
            filename=pdf_path.name,
            title=metadata.get("title", pdf_path.stem),
            num_pages=num_pages,
            num_chunks=len(chunks),
            total_chars=len(text),
            chunks=chunks,
            metadata=metadata,
        )

        # Cache it
        self._save_cached(doc)

        return doc

    def _extract_with_pymupdf(self, pdf_path: Path) -> tuple[str, dict, int]:
        """Extract text using PyMuPDF."""
        doc = fitz.open(pdf_path)
        text_parts = []
        metadata = {}

        # Get metadata
        meta = doc.metadata
        if meta:
            metadata = {
                "title": meta.get("title", ""),
                "author": meta.get("author", ""),
                "subject": meta.get("subject", ""),
                "keywords": meta.get("keywords", ""),
                "creator": meta.get("creator", ""),
            }

        # Extract text from each page
        for page in doc:
            text_parts.append(page.get_text())

        doc.close()
        return "\n\n".join(text_parts), metadata, len(text_parts)

    def _extract_with_pypdf(self, pdf_path: Path) -> tuple[str, dict, int]:
        """Extract text using pypdf."""
        reader = PdfReader(pdf_path)
        text_parts = []
        metadata = {}

        # Get metadata
        if reader.metadata:
            metadata = {
                "title": reader.metadata.get("/Title", ""),
                "author": reader.metadata.get("/Author", ""),
                "subject": reader.metadata.get("/Subject", ""),
            }

        # Extract text from each page
        for page in reader.pages:
            text_parts.append(page.extract_text() or "")

        return "\n\n".join(text_parts), metadata, len(text_parts)

    def _create_chunks(
        self, doc_id: str, text: str
    ) -> Iterator[DocumentChunk]:
        """Create overlapping chunks from text."""
        if not text:
            return

        # Clean text
        text = text.replace("\x00", "")  # Remove null chars

        # Split into chunks with overlap
        start = 0
        chunk_id = 0

        while start < len(text):
            end = start + self.chunk_size

            # Try to end at sentence boundary
            if end < len(text):
                # Look for sentence end in last 200 chars
                search_start = max(start + self.chunk_size - 200, start)
                for punct in [". ", ".\n", "? ", "?\n", "! ", "!\n"]:
                    pos = text.rfind(punct, search_start, end)
                    if pos > start:
                        end = pos + 1
                        break

            chunk_text = text[start:end].strip()

            if chunk_text:
                yield DocumentChunk(
                    doc_id=doc_id,
                    chunk_id=chunk_id,
                    text=chunk_text,
                    page_numbers=[],  # Would need page tracking
                )
                chunk_id += 1

            start = end - self.chunk_overlap

    def _get_doc_id(self, pdf_path: Path) -> str:
        """Generate unique document ID from file content."""
        hasher = hashlib.md5()
        with open(pdf_path, "rb") as f:
            # Hash first 1MB
            hasher.update(f.read(1024 * 1024))
        return hasher.hexdigest()[:12]

    def _load_cached(self, doc_id: str) -> ProcessedDocument | None:
        """Load cached processed document."""
        cache_path = self.processed_dir / f"{doc_id}.json"
        if cache_path.exists():
            try:
                with open(cache_path) as f:
                    return ProcessedDocument.from_dict(json.load(f))
            except Exception:
                return None
        return None

    def _save_cached(self, doc: ProcessedDocument):
        """Save processed document to cache."""
        cache_path = self.processed_dir / f"{doc.doc_id}.json"
        with open(cache_path, "w") as f:
            json.dump(doc.to_dict(), f, indent=2)

    def get_context_for_query(
        self,
        documents: list[ProcessedDocument],
        query: str,
        max_chunks: int = 5,
    ) -> str:
        """
        Get relevant context from documents for a query.

        Simple keyword matching - could be enhanced with embeddings.
        """
        query_words = set(query.lower().split())
        scored_chunks = []

        for doc in documents:
            for chunk in doc.chunks:
                # Simple relevance score: word overlap
                chunk_words = set(chunk.text.lower().split())
                overlap = len(query_words & chunk_words)
                if overlap > 0:
                    scored_chunks.append((overlap, doc.filename, chunk))

        # Sort by relevance
        scored_chunks.sort(reverse=True, key=lambda x: x[0])

        # Build context
        context_parts = []
        for _, filename, chunk in scored_chunks[:max_chunks]:
            context_parts.append(f"[From: {filename}]\n{chunk.text}")

        return "\n\n---\n\n".join(context_parts)


def create_sample_data():
    """Create sample text files if no PDFs available."""
    sample_dir = config.PDF_DIR

    # Create sample research documents as text files
    samples = [
        {
            "name": "diabetes_metformin_review.txt",
            "content": """
REVIEW: Metformin in Type 2 Diabetes Management

ABSTRACT
Metformin remains the first-line pharmacological treatment for type 2 diabetes mellitus (T2DM).
This review summarizes current evidence on its efficacy, safety, and mechanisms of action.

INTRODUCTION
Type 2 diabetes affects over 400 million people worldwide. Metformin, a biguanide, has been
used for over 60 years and remains the cornerstone of T2DM treatment.

MECHANISM OF ACTION
Metformin primarily works by:
1. Reducing hepatic glucose production via AMPK activation
2. Improving insulin sensitivity in peripheral tissues
3. Decreasing intestinal glucose absorption
4. Potentially affecting gut microbiome composition

EFFICACY
Clinical trials demonstrate:
- HbA1c reduction: 1.0-1.5% on average
- Fasting glucose reduction: 25-30 mg/dL
- Body weight: Neutral to slight reduction
- Cardiovascular outcomes: Reduced CV mortality in UKPDS

SAFETY PROFILE
Common side effects (10-25%):
- Gastrointestinal: Nausea, diarrhea, abdominal discomfort
- Usually transient, improved with extended-release formulation

Rare but serious:
- Lactic acidosis: 0.03 cases per 1000 patient-years
- Vitamin B12 deficiency with long-term use

CONCLUSIONS
Metformin remains the optimal first-line agent due to:
- Proven efficacy in glucose reduction
- Cardiovascular benefits
- Low hypoglycemia risk
- Cost-effectiveness
- Long-term safety data
"""
        },
        {
            "name": "sglt2_inhibitors_cardio.txt",
            "content": """
SGLT2 Inhibitors: Cardiovascular and Renal Outcomes

ABSTRACT
Sodium-glucose cotransporter 2 (SGLT2) inhibitors represent a paradigm shift in diabetes
treatment, demonstrating benefits beyond glucose control.

KEY FINDINGS FROM MAJOR TRIALS

EMPA-REG OUTCOME (Empagliflozin)
- 14% reduction in MACE (CV death, MI, stroke)
- 38% reduction in CV death
- 35% reduction in heart failure hospitalization
- 39% reduction in nephropathy progression

CANVAS Program (Canagliflozin)
- 14% reduction in MACE
- 33% reduction in heart failure hospitalization
- Increased amputation risk (addressed with monitoring)

DECLARE-TIMI 58 (Dapagliflozin)
- 17% reduction in CV death/heart failure hospitalization
- 24% reduction in renal outcomes

MECHANISMS OF CARDIOVASCULAR BENEFIT
1. Hemodynamic effects: Reduced preload, afterload
2. Metabolic shift: Increased ketone utilization by heart
3. Reduced arterial stiffness
4. Anti-inflammatory effects
5. Improved endothelial function

RENAL PROTECTION
- Reduced intraglomerular pressure
- Decreased albuminuria
- Slowed eGFR decline
- CREDENCE trial: 30% reduction in renal outcomes

CLINICAL IMPLICATIONS
SGLT2 inhibitors are now recommended for:
- T2DM with established CV disease
- T2DM with heart failure
- T2DM with chronic kidney disease
- Independent of baseline HbA1c in these populations

SAFETY CONSIDERATIONS
- Genital mycotic infections: 5-10%
- DKA risk: Rare, monitor during acute illness
- Volume depletion: Caution in elderly
"""
        },
        {
            "name": "glp1_agonists_obesity.txt",
            "content": """
GLP-1 Receptor Agonists: From Diabetes to Obesity Treatment

INTRODUCTION
Glucagon-like peptide-1 (GLP-1) receptor agonists have emerged as powerful tools
for both glycemic control and weight management.

MECHANISM OF ACTION
1. Glucose-dependent insulin secretion
2. Glucagon suppression
3. Delayed gastric emptying
4. Central appetite suppression
5. Potential beta-cell preservation

WEIGHT LOSS EFFICACY

Semaglutide (STEP Trials)
- STEP 1: 14.9% weight loss vs 2.4% placebo
- STEP 2 (diabetes): 9.6% weight loss
- STEP 3 (with lifestyle): 16.0% weight loss
- STEP 4: Weight regain after discontinuation

Tirzepatide (SURMOUNT Trials)
- Dual GIP/GLP-1 agonist
- Up to 22.5% weight loss at highest dose
- Superior to semaglutide in head-to-head trials

CARDIOVASCULAR OUTCOMES

LEADER (Liraglutide)
- 13% reduction in MACE
- 22% reduction in CV death

SUSTAIN-6 (Semaglutide)
- 26% reduction in MACE
- 39% reduction in non-fatal stroke

SELECT (Semaglutide in Obesity without Diabetes)
- 20% reduction in MACE
- Established CV benefit independent of diabetes

TOLERABILITY
- GI side effects most common: nausea, vomiting, diarrhea
- Usually transient with gradual dose titration
- Rare: Pancreatitis, gallbladder events, thyroid concerns

CLINICAL POSITIONING
- First-line for T2DM with obesity
- Consider for T2DM with CV disease
- FDA-approved for obesity (semaglutide 2.4mg, tirzepatide)
"""
        },
    ]

    created = []
    for sample in samples:
        path = sample_dir / sample["name"]
        if not path.exists():
            path.write_text(sample["content"])
            created.append(path.name)

    if created:
        print(f"[PDF] Created sample documents: {', '.join(created)}")

    return created
