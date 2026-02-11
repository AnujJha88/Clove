"""
Checkpoint System

Saves and restores research progress:
- Periodic auto-save
- Manual checkpoints
- Recovery from crashes
- Research state persistence
"""

import json
import asyncio
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Any

from agents import Finding, AgentState
import config


@dataclass
class ResearchCheckpoint:
    """A checkpoint of research progress."""
    checkpoint_id: str
    timestamp: datetime
    research_task: str
    status: str
    elapsed_hours: float
    findings: list[dict]
    agent_states: list[dict]
    documents_processed: list[str]
    current_phase: str
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "checkpoint_id": self.checkpoint_id,
            "timestamp": self.timestamp.isoformat(),
            "research_task": self.research_task,
            "status": self.status,
            "elapsed_hours": self.elapsed_hours,
            "findings": self.findings,
            "agent_states": self.agent_states,
            "documents_processed": self.documents_processed,
            "current_phase": self.current_phase,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ResearchCheckpoint":
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


class CheckpointManager:
    """
    Manages research checkpoints.

    Features:
    - Auto-save at configurable intervals
    - Manual checkpoint creation
    - List and load previous checkpoints
    - Clean old checkpoints
    """

    def __init__(
        self,
        checkpoint_dir: Path = None,
        auto_save_interval: int = None,  # Minutes
    ):
        self.checkpoint_dir = checkpoint_dir or config.CHECKPOINT_DIR
        self.auto_save_interval = auto_save_interval or config.CHECKPOINT_INTERVAL_MINUTES
        self._auto_save_task = None
        self._current_state = {}

    def save_checkpoint(
        self,
        research_task: str,
        status: str,
        elapsed_hours: float,
        findings: list[Finding],
        agent_states: list[AgentState],
        documents_processed: list[str],
        current_phase: str,
        metadata: dict = None,
    ) -> Path:
        """Save a checkpoint to disk."""
        checkpoint_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        checkpoint = ResearchCheckpoint(
            checkpoint_id=checkpoint_id,
            timestamp=datetime.now(),
            research_task=research_task,
            status=status,
            elapsed_hours=elapsed_hours,
            findings=[f.to_dict() for f in findings],
            agent_states=[s.to_dict() for s in agent_states],
            documents_processed=documents_processed,
            current_phase=current_phase,
            metadata=metadata or {},
        )

        # Save to file
        filename = f"checkpoint_{checkpoint_id}.json"
        filepath = self.checkpoint_dir / filename

        with open(filepath, "w") as f:
            json.dump(checkpoint.to_dict(), f, indent=2)

        print(f"[Checkpoint] Saved: {filename}")
        return filepath

    def load_checkpoint(self, checkpoint_id: str = None) -> ResearchCheckpoint | None:
        """
        Load a checkpoint from disk.

        If checkpoint_id is None, loads the most recent checkpoint.
        """
        if checkpoint_id:
            filepath = self.checkpoint_dir / f"checkpoint_{checkpoint_id}.json"
        else:
            # Find most recent
            checkpoints = sorted(self.checkpoint_dir.glob("checkpoint_*.json"))
            if not checkpoints:
                return None
            filepath = checkpoints[-1]

        if not filepath.exists():
            return None

        with open(filepath) as f:
            data = json.load(f)

        return ResearchCheckpoint.from_dict(data)

    def list_checkpoints(self) -> list[dict]:
        """List all available checkpoints."""
        checkpoints = []

        for filepath in sorted(self.checkpoint_dir.glob("checkpoint_*.json")):
            try:
                with open(filepath) as f:
                    data = json.load(f)
                checkpoints.append({
                    "checkpoint_id": data["checkpoint_id"],
                    "timestamp": data["timestamp"],
                    "research_task": data["research_task"][:50],
                    "status": data["status"],
                    "elapsed_hours": data["elapsed_hours"],
                    "num_findings": len(data.get("findings", [])),
                })
            except Exception:
                continue

        return checkpoints

    def delete_old_checkpoints(self, keep_last: int = 10):
        """Delete old checkpoints, keeping the most recent ones."""
        checkpoints = sorted(self.checkpoint_dir.glob("checkpoint_*.json"))

        if len(checkpoints) <= keep_last:
            return

        to_delete = checkpoints[:-keep_last]
        for filepath in to_delete:
            filepath.unlink()
            print(f"[Checkpoint] Deleted old: {filepath.name}")

    async def start_auto_save(
        self,
        get_state_fn,  # Function that returns current state
    ):
        """Start auto-save background task."""
        self._auto_save_task = asyncio.create_task(
            self._auto_save_loop(get_state_fn)
        )

    async def stop_auto_save(self):
        """Stop auto-save background task."""
        if self._auto_save_task:
            self._auto_save_task.cancel()
            try:
                await self._auto_save_task
            except asyncio.CancelledError:
                pass

    async def _auto_save_loop(self, get_state_fn):
        """Auto-save loop."""
        while True:
            await asyncio.sleep(self.auto_save_interval * 60)

            try:
                state = get_state_fn()
                if state:
                    self.save_checkpoint(**state)
            except Exception as e:
                print(f"[Checkpoint] Auto-save error: {e}")


class ResearchLog:
    """
    Logs research activity for auditing and debugging.
    """

    def __init__(self, log_dir: Path = None):
        self.log_dir = log_dir or config.LOGS_DIR
        self.log_file = None
        self._start_time = None

    def start_session(self, research_task: str):
        """Start a new logging session."""
        self._start_time = datetime.now()
        filename = f"research_{self._start_time.strftime('%Y%m%d_%H%M%S')}.log"
        self.log_file = self.log_dir / filename

        self._write(f"Research Session Started")
        self._write(f"Task: {research_task}")
        self._write("-" * 60)

    def log_event(self, event_type: str, agent_id: str, message: str):
        """Log an event."""
        self._write(f"[{event_type}] [{agent_id}] {message}")

    def log_finding(self, finding: Finding):
        """Log a finding."""
        self._write(f"[FINDING] [{finding.agent_role}]")
        self._write(f"  Content: {finding.content[:200]}...")
        self._write(f"  Confidence: {finding.confidence}")

    def log_error(self, agent_id: str, error: str):
        """Log an error."""
        self._write(f"[ERROR] [{agent_id}] {error}")

    def log_status(self, status: dict):
        """Log current status."""
        self._write("[STATUS]")
        for key, value in status.items():
            self._write(f"  {key}: {value}")

    def end_session(self, summary: str):
        """End the logging session."""
        elapsed = datetime.now() - self._start_time if self._start_time else 0
        self._write("-" * 60)
        self._write(f"Session ended. Duration: {elapsed}")
        self._write(f"Summary: {summary}")

    def _write(self, message: str):
        """Write to log file."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {message}\n"

        if self.log_file:
            with open(self.log_file, "a") as f:
                f.write(line)

        # Also print to console
        print(line.strip())
