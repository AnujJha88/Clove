"""Audit logging syscalls.

Provides audit log retrieval and configuration.
"""

from typing import Optional, List, Dict, Any, TYPE_CHECKING

from ..protocol import SyscallOp
from ..models import AuditEntry, AuditLogResult, AuditConfigResult

if TYPE_CHECKING:
    from ..transport import Transport


class AuditMixin:
    """Mixin for audit logging operations.

    Requires _transport attribute of type Transport.
    """

    _transport: 'Transport'

    def get_audit_log(
        self,
        category: Optional[str] = None,
        agent_id: Optional[int] = None,
        since_id: int = 0,
        limit: int = 100
    ) -> AuditLogResult:
        """Get audit log entries with optional filtering.

        Args:
            category: Filter by category (SECURITY, AGENT_LIFECYCLE, IPC, etc.)
            agent_id: Filter by agent ID
            since_id: Get entries after this ID
            limit: Maximum entries to return (default 100)

        Returns:
            AuditLogResult with list of entries
        """
        payload: Dict[str, Any] = {"limit": limit}
        if category:
            payload["category"] = category
        if agent_id is not None:
            payload["agent_id"] = agent_id
        if since_id:
            payload["since_id"] = since_id

        result = self._transport.call_json(SyscallOp.SYS_GET_AUDIT_LOG, payload)

        entries: List[AuditEntry] = []
        for entry_data in result.get("entries", []):
            entries.append(AuditEntry(
                id=entry_data.get("id", 0),
                timestamp=entry_data.get("timestamp", 0.0),
                category=entry_data.get("category", ""),
                agent_id=entry_data.get("agent_id"),
                action=entry_data.get("action", ""),
                details=entry_data.get("details", {})
            ))

        return AuditLogResult(
            success=result.get("success", False),
            entries=entries,
            count=result.get("count", len(entries)),
            error=result.get("error")
        )

    def set_audit_config(
        self,
        max_entries: Optional[int] = None,
        log_syscalls: Optional[bool] = None,
        log_security: Optional[bool] = None,
        log_lifecycle: Optional[bool] = None,
        log_ipc: Optional[bool] = None,
        log_state: Optional[bool] = None,
        log_resource: Optional[bool] = None,
        log_network: Optional[bool] = None,
        log_world: Optional[bool] = None
    ) -> AuditConfigResult:
        """Configure audit logging.

        Args:
            max_entries: Maximum entries to keep in memory
            log_syscalls: Log all syscalls (verbose)
            log_security: Log security events
            log_lifecycle: Log agent lifecycle events
            log_ipc: Log IPC events
            log_state: Log state store events
            log_resource: Log resource events
            log_network: Log network events
            log_world: Log world simulation events

        Returns:
            AuditConfigResult with current config
        """
        payload: Dict[str, Any] = {}

        if max_entries is not None:
            payload["max_entries"] = max_entries
        if log_syscalls is not None:
            payload["log_syscalls"] = log_syscalls
        if log_security is not None:
            payload["log_security"] = log_security
        if log_lifecycle is not None:
            payload["log_lifecycle"] = log_lifecycle
        if log_ipc is not None:
            payload["log_ipc"] = log_ipc
        if log_state is not None:
            payload["log_state"] = log_state
        if log_resource is not None:
            payload["log_resource"] = log_resource
        if log_network is not None:
            payload["log_network"] = log_network
        if log_world is not None:
            payload["log_world"] = log_world

        result = self._transport.call_json(SyscallOp.SYS_SET_AUDIT_CONFIG, payload)

        return AuditConfigResult(
            success=result.get("success", False),
            config=result.get("config", {}),
            error=result.get("error")
        )
