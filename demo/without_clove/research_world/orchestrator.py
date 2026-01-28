"""
Research Orchestrator

Main controller for long-running research:
- Manages research phases
- Coordinates agents
- Handles checkpointing
- Generates final report
"""

import asyncio
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable
from enum import Enum

from api_pool import APIKeyPool, LLMClient, get_pool
from pdf_processor import PDFProcessor, ProcessedDocument, create_sample_data
from agents import (
    ResearchAgent, Finding, AgentState,
    LiteratureReviewer, DataAnalyst, MethodologyExpert, Synthesizer, Critic,
    create_research_team,
)
from checkpoint import CheckpointManager, ResearchLog
from report_generator import ReportGenerator
import config


class ResearchPhase(Enum):
    INIT = "initialization"
    DATA_LOADING = "loading_data"
    LITERATURE_REVIEW = "literature_review"
    DATA_ANALYSIS = "data_analysis"
    METHODOLOGY_REVIEW = "methodology_review"
    SYNTHESIS = "synthesis"
    CRITICAL_REVIEW = "critical_review"
    REPORT_GENERATION = "report_generation"
    COMPLETED = "completed"


class ResearchOrchestrator:
    """
    Orchestrates multi-hour research tasks.

    Workflow:
    1. Initialize with research task and data
    2. Load and process documents
    3. Run multiple research phases with specialized agents
    4. Checkpoint progress periodically
    5. Generate comprehensive report
    """

    def __init__(
        self,
        research_task: str,
        max_hours: float = None,
        api_keys: list[str] = None,
    ):
        self.research_task = research_task
        self.max_hours = max_hours or config.MAX_RESEARCH_HOURS
        self.start_time = None
        self.end_time = None

        # Initialize components
        self.pool = APIKeyPool(api_keys) if api_keys else get_pool()
        self.client = LLMClient(self.pool)
        self.pdf_processor = PDFProcessor()
        self.checkpoint_manager = CheckpointManager()
        self.log = ResearchLog()
        self.report_generator = ReportGenerator(self.client)

        # State
        self.current_phase = ResearchPhase.INIT
        self.documents: list[ProcessedDocument] = []
        self.findings: list[Finding] = []
        self.agents: dict[str, ResearchAgent] = {}

        # Progress tracking
        self.tasks_completed = 0
        self.total_tasks = 0

    async def run(self) -> Path:
        """
        Run the complete research workflow.

        Returns:
            Path to the generated report
        """
        self.start_time = datetime.now()
        self.log.start_session(self.research_task)

        print("=" * 60)
        print("  RESEARCH WORLD")
        print("  Long-Running Multi-Agent Research System")
        print("=" * 60)
        print(f"\n  Task: {self.research_task}")
        print(f"  Max Duration: {self.max_hours} hours")
        print(f"  API Keys: {len(self.pool.keys)} available")
        print()
        print("=" * 60)
        print()

        try:
            # Phase 1: Load data
            await self._phase_load_data()

            # Phase 2: Literature review
            await self._phase_literature_review()

            # Phase 3: Data analysis
            await self._phase_data_analysis()

            # Phase 4: Methodology review
            await self._phase_methodology_review()

            # Phase 5: Critical review
            await self._phase_critical_review()

            # Phase 6: Synthesis
            await self._phase_synthesis()

            # Phase 7: Generate report
            report_path = await self._phase_report()

            self.current_phase = ResearchPhase.COMPLETED
            self.end_time = datetime.now()

            # Final summary
            self._print_summary()
            self.log.end_session("Completed successfully")

            return report_path

        except KeyboardInterrupt:
            print("\n[!] Research interrupted by user")
            self._save_checkpoint("interrupted")
            raise

        except Exception as e:
            print(f"\n[!] Research failed: {e}")
            self._save_checkpoint("failed")
            self.log.log_error("orchestrator", str(e))
            raise

    async def _phase_load_data(self):
        """Phase 1: Load and process documents."""
        self.current_phase = ResearchPhase.DATA_LOADING
        self.log.log_event("PHASE", "orchestrator", "Starting data loading")

        print("\n" + "=" * 40)
        print("PHASE 1: Data Loading")
        print("=" * 40)

        # Create sample data if no PDFs exist
        pdf_files = list(config.PDF_DIR.glob("*.pdf"))
        txt_files = list(config.PDF_DIR.glob("*.txt"))

        if not pdf_files and not txt_files:
            print("[Data] No documents found, creating samples...")
            create_sample_data()
            txt_files = list(config.PDF_DIR.glob("*.txt"))

        # Process PDFs
        if pdf_files:
            self.documents = self.pdf_processor.process_all()
            print(f"[Data] Processed {len(self.documents)} PDF documents")

        # Also load text files
        for txt_file in txt_files:
            content = txt_file.read_text()
            doc = ProcessedDocument(
                doc_id=txt_file.stem[:12],
                filename=txt_file.name,
                title=txt_file.stem,
                num_pages=1,
                num_chunks=1,
                total_chars=len(content),
                chunks=[],
                metadata={},
            )
            # Create single chunk
            from pdf_processor import DocumentChunk
            doc.chunks.append(DocumentChunk(
                doc_id=doc.doc_id,
                chunk_id=0,
                text=content,
                page_numbers=[1],
            ))
            self.documents.append(doc)
            print(f"[Data] Loaded text file: {txt_file.name}")

        print(f"[Data] Total documents: {len(self.documents)}")

    async def _phase_literature_review(self):
        """Phase 2: Literature review."""
        self.current_phase = ResearchPhase.LITERATURE_REVIEW
        self.log.log_event("PHASE", "orchestrator", "Starting literature review")

        print("\n" + "=" * 40)
        print("PHASE 2: Literature Review")
        print("=" * 40)

        agent = LiteratureReviewer()
        self.agents["literature_reviewer"] = agent

        # Get context from documents
        context = self._get_document_context()

        # Research tasks for literature review
        tasks = [
            f"What are the key findings about {self.research_task}?",
            f"What is the current state of evidence regarding {self.research_task}?",
            f"What are the most cited studies or important papers about {self.research_task}?",
        ]

        for task in tasks:
            if self._should_stop():
                break

            finding = await agent.research(task, context, self.findings)
            self.findings.append(finding)
            self.log.log_finding(finding)
            self._save_checkpoint("auto")

        print(f"[Literature] Generated {len(agent.state.findings)} findings")

    async def _phase_data_analysis(self):
        """Phase 3: Data analysis."""
        self.current_phase = ResearchPhase.DATA_ANALYSIS
        self.log.log_event("PHASE", "orchestrator", "Starting data analysis")

        print("\n" + "=" * 40)
        print("PHASE 3: Data Analysis")
        print("=" * 40)

        agent = DataAnalyst()
        self.agents["data_analyst"] = agent

        context = self._get_document_context()

        tasks = [
            f"What quantitative data exists about {self.research_task}?",
            f"What are the effect sizes and statistical significance of findings?",
            f"Are there any notable trends or patterns in the data?",
        ]

        for task in tasks:
            if self._should_stop():
                break

            finding = await agent.research(task, context, self.findings)
            self.findings.append(finding)
            self.log.log_finding(finding)

        print(f"[Analysis] Generated {len(agent.state.findings)} findings")

    async def _phase_methodology_review(self):
        """Phase 4: Methodology review."""
        self.current_phase = ResearchPhase.METHODOLOGY_REVIEW
        self.log.log_event("PHASE", "orchestrator", "Starting methodology review")

        print("\n" + "=" * 40)
        print("PHASE 4: Methodology Review")
        print("=" * 40)

        agent = MethodologyExpert()
        self.agents["methodology_expert"] = agent

        context = self._get_document_context()

        tasks = [
            f"What research methods were used to study {self.research_task}?",
            f"Are there any methodological concerns or limitations?",
            f"How generalizable are the findings?",
        ]

        for task in tasks:
            if self._should_stop():
                break

            finding = await agent.research(task, context, self.findings)
            self.findings.append(finding)
            self.log.log_finding(finding)

        print(f"[Methodology] Generated {len(agent.state.findings)} findings")

    async def _phase_critical_review(self):
        """Phase 5: Critical review."""
        self.current_phase = ResearchPhase.CRITICAL_REVIEW
        self.log.log_event("PHASE", "orchestrator", "Starting critical review")

        print("\n" + "=" * 40)
        print("PHASE 5: Critical Review")
        print("=" * 40)

        agent = Critic()
        self.agents["critic"] = agent

        context = self._get_document_context()

        tasks = [
            f"What are the gaps in the evidence about {self.research_task}?",
            f"What counter-arguments or alternative explanations exist?",
            f"What biases might affect the findings?",
        ]

        for task in tasks:
            if self._should_stop():
                break

            finding = await agent.research(task, context, self.findings)
            self.findings.append(finding)
            self.log.log_finding(finding)

        print(f"[Critic] Generated {len(agent.state.findings)} findings")

    async def _phase_synthesis(self):
        """Phase 6: Synthesis."""
        self.current_phase = ResearchPhase.SYNTHESIS
        self.log.log_event("PHASE", "orchestrator", "Starting synthesis")

        print("\n" + "=" * 40)
        print("PHASE 6: Synthesis")
        print("=" * 40)

        agent = Synthesizer()
        self.agents["synthesizer"] = agent

        # Synthesizer uses findings from other agents, not documents
        tasks = [
            f"Synthesize all findings about {self.research_task} into key themes",
            f"What is the overall conclusion regarding {self.research_task}?",
            f"What are the most actionable insights?",
        ]

        for task in tasks:
            if self._should_stop():
                break

            finding = await agent.research(task, "", self.findings)
            self.findings.append(finding)
            self.log.log_finding(finding)

        print(f"[Synthesis] Generated {len(agent.state.findings)} findings")

    async def _phase_report(self) -> Path:
        """Phase 7: Report generation."""
        self.current_phase = ResearchPhase.REPORT_GENERATION
        self.log.log_event("PHASE", "orchestrator", "Generating report")

        print("\n" + "=" * 40)
        print("PHASE 7: Report Generation")
        print("=" * 40)

        elapsed = self._get_elapsed_hours()
        document_names = [d.filename for d in self.documents]

        report = await self.report_generator.generate_report(
            research_task=self.research_task,
            findings=self.findings,
            documents=document_names,
            elapsed_hours=elapsed,
            metadata={
                "num_agents": len(self.agents),
                "num_api_keys": len(self.pool.keys),
                "model": config.MODEL_NAME,
            },
        )

        report_path = self.report_generator.save_report(
            report=report,
            research_task=self.research_task,
        )

        return report_path

    def _get_document_context(self, max_chars: int = 10000) -> str:
        """Get context from all documents."""
        context_parts = []
        total_chars = 0

        for doc in self.documents:
            for chunk in doc.chunks:
                if total_chars + len(chunk.text) > max_chars:
                    break
                context_parts.append(f"[{doc.filename}]\n{chunk.text}")
                total_chars += len(chunk.text)

        return "\n\n---\n\n".join(context_parts)

    def _get_elapsed_hours(self) -> float:
        """Get elapsed time in hours."""
        if not self.start_time:
            return 0
        elapsed = datetime.now() - self.start_time
        return elapsed.total_seconds() / 3600

    def _should_stop(self) -> bool:
        """Check if we should stop research."""
        return self._get_elapsed_hours() >= self.max_hours

    def _save_checkpoint(self, reason: str):
        """Save a checkpoint."""
        self.checkpoint_manager.save_checkpoint(
            research_task=self.research_task,
            status=reason,
            elapsed_hours=self._get_elapsed_hours(),
            findings=self.findings,
            agent_states=[a.state for a in self.agents.values()],
            documents_processed=[d.filename for d in self.documents],
            current_phase=self.current_phase.value,
        )

    def _print_summary(self):
        """Print research summary."""
        elapsed = self._get_elapsed_hours()

        print("\n" + "=" * 60)
        print("  RESEARCH COMPLETED")
        print("=" * 60)
        print(f"\n  Task: {self.research_task}")
        print(f"  Duration: {elapsed:.1f} hours")
        print(f"  Documents: {len(self.documents)}")
        print(f"  Findings: {len(self.findings)}")
        print(f"  Agents used: {len(self.agents)}")
        print()

        # API pool status
        self.pool.print_status()

        # Findings by confidence
        high = sum(1 for f in self.findings if f.confidence >= 0.8)
        medium = sum(1 for f in self.findings if 0.5 <= f.confidence < 0.8)
        low = sum(1 for f in self.findings if f.confidence < 0.5)
        print(f"\n  Findings by confidence:")
        print(f"    High: {high}")
        print(f"    Medium: {medium}")
        print(f"    Low: {low}")
        print()


async def run_research(
    task: str,
    max_hours: float = 4,
    api_keys: list[str] = None,
) -> Path:
    """
    Run a research task.

    Args:
        task: The research question/task
        max_hours: Maximum hours to run
        api_keys: List of API keys (optional)

    Returns:
        Path to generated report
    """
    orchestrator = ResearchOrchestrator(
        research_task=task,
        max_hours=max_hours,
        api_keys=api_keys,
    )
    return await orchestrator.run()
