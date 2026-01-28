"""
Research World - Multi-Agent Research System

A system for running long-duration research tasks with:
- Multiple specialized AI agents
- API key pool with rotation
- PDF document processing
- Automatic checkpointing
- Comprehensive report generation
"""

from .orchestrator import run_research, ResearchOrchestrator
from .agents import (
    ResearchAgent,
    LiteratureReviewer,
    DataAnalyst,
    MethodologyExpert,
    Synthesizer,
    Critic,
    create_research_team,
)
from .api_pool import APIKeyPool, LLMClient, get_pool, get_client
from .pdf_processor import PDFProcessor, create_sample_data
from .checkpoint import CheckpointManager, ResearchLog
from .report_generator import ReportGenerator

__all__ = [
    "run_research",
    "ResearchOrchestrator",
    "ResearchAgent",
    "LiteratureReviewer",
    "DataAnalyst",
    "MethodologyExpert",
    "Synthesizer",
    "Critic",
    "create_research_team",
    "APIKeyPool",
    "LLMClient",
    "get_pool",
    "get_client",
    "PDFProcessor",
    "create_sample_data",
    "CheckpointManager",
    "ResearchLog",
    "ReportGenerator",
]

__version__ = "1.0.0"
