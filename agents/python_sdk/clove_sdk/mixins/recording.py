"""Execution recording and replay syscalls.

Provides syscall recording, export, and replay functionality.
"""

from typing import Optional, List, TYPE_CHECKING

from ..protocol import SyscallOp
from ..models import RecordingStatus, ReplayStatus

if TYPE_CHECKING:
    from ..transport import Transport


class RecordingMixin:
    """Mixin for execution recording and replay.

    Requires _transport attribute of type Transport.
    """

    _transport: 'Transport'

    def start_recording(
        self,
        include_think: bool = False,
        include_http: bool = False,
        include_exec: bool = False,
        filter_agents: Optional[List[int]] = None,
        max_entries: int = 50000
    ) -> RecordingStatus:
        """Start recording syscall execution for later replay.

        Args:
            include_think: Include LLM calls (non-deterministic)
            include_http: Include HTTP calls (non-deterministic)
            include_exec: Include exec calls (may be non-deterministic)
            filter_agents: Only record these agent IDs (empty = all)
            max_entries: Maximum entries to keep in buffer

        Returns:
            RecordingStatus with recording state
        """
        payload = {
            "include_think": include_think,
            "include_http": include_http,
            "include_exec": include_exec,
            "max_entries": max_entries
        }
        if filter_agents:
            payload["filter_agents"] = filter_agents

        result = self._transport.call_json(SyscallOp.SYS_RECORD_START, payload)

        return RecordingStatus(
            success=result.get("success", False),
            active=result.get("active", False),
            entry_count=result.get("entry_count", 0),
            started_at=result.get("started_at"),
            error=result.get("error")
        )

    def stop_recording(self) -> RecordingStatus:
        """Stop recording syscall execution.

        Returns:
            RecordingStatus with final entry count
        """
        result = self._transport.call_json(SyscallOp.SYS_RECORD_STOP, {})

        return RecordingStatus(
            success=result.get("success", False),
            active=False,
            entry_count=result.get("entry_count", 0),
            error=result.get("error")
        )

    def get_recording_status(self, export: bool = False) -> RecordingStatus:
        """Get current recording status and optionally export the recording.

        Args:
            export: If True, include the full recording data in response

        Returns:
            RecordingStatus with recording state and optionally data
        """
        result = self._transport.call_json(
            SyscallOp.SYS_RECORD_STATUS,
            {"export": export}
        )

        return RecordingStatus(
            success=result.get("success", False),
            active=result.get("active", False),
            entry_count=result.get("entry_count", 0),
            started_at=result.get("started_at"),
            recording_data=result.get("recording_data") if export else None,
            error=result.get("error")
        )

    def start_replay(self, recording_data: str) -> ReplayStatus:
        """Start replaying a recorded execution session.

        Args:
            recording_data: JSON string of recorded execution entries

        Returns:
            ReplayStatus with replay state
        """
        result = self._transport.call_json(
            SyscallOp.SYS_REPLAY_START,
            {"recording": recording_data}
        )

        return ReplayStatus(
            success=result.get("success", False),
            active=result.get("active", False),
            total_entries=result.get("total_entries", 0),
            entries_replayed=0,
            entries_skipped=0,
            error=result.get("error")
        )

    def get_replay_status(self) -> ReplayStatus:
        """Get current replay status and progress.

        Returns:
            ReplayStatus with replay progress
        """
        result = self._transport.call_json(SyscallOp.SYS_REPLAY_STATUS, {})

        return ReplayStatus(
            success=result.get("success", False),
            active=result.get("active", False),
            progress=result.get("progress", 0.0),
            total_entries=result.get("total_entries", 0),
            entries_replayed=result.get("entries_replayed", 0),
            entries_skipped=result.get("entries_skipped", 0),
            errors=result.get("errors", []),
            error=result.get("error")
        )
