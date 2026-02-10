"""Response models for Clove SDK.

Typed dataclasses for all kernel responses, replacing bare dict returns.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Any, Dict
from enum import Enum


# ========== Core ==========

@dataclass
class KernelInfo:
    """Kernel version and capabilities from SYS_HELLO."""
    version: str
    capabilities: List[str]
    agent_id: int
    uptime_seconds: float = 0.0


@dataclass
class ExecResult:
    """Result of shell command execution."""
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: Optional[float] = None
    async_request_id: Optional[int] = None


@dataclass
class FileContent:
    """Result of file read operation."""
    success: bool
    content: str
    size: int
    error: Optional[str] = None


@dataclass
class WriteResult:
    """Result of file write operation."""
    success: bool
    bytes_written: int
    error: Optional[str] = None


# ========== Agents ==========

class AgentState(Enum):
    """Agent lifecycle states."""
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    STARTING = "starting"
    CRASHED = "crashed"


@dataclass
class AgentInfo:
    """Information about a running agent."""
    id: int
    name: str
    pid: int
    state: AgentState
    uptime_seconds: float = 0.0
    memory_bytes: Optional[int] = None
    cpu_percent: Optional[float] = None


@dataclass
class SpawnResult:
    """Result of agent spawn operation."""
    success: bool
    agent_id: Optional[int] = None
    pid: Optional[int] = None
    error: Optional[str] = None


# ========== IPC ==========

@dataclass
class IPCMessage:
    """Message received from another agent."""
    from_agent: int
    from_name: Optional[str]
    message: Dict[str, Any]
    timestamp: float


@dataclass
class SendResult:
    """Result of send message operation."""
    success: bool
    delivered: bool = False
    error: Optional[str] = None


@dataclass
class RecvResult:
    """Result of receive messages operation."""
    success: bool
    messages: List[IPCMessage] = field(default_factory=list)
    count: int = 0
    error: Optional[str] = None


@dataclass
class BroadcastResult:
    """Result of broadcast operation."""
    success: bool
    delivered_count: int = 0
    error: Optional[str] = None


@dataclass
class RegisterResult:
    """Result of agent name registration."""
    success: bool
    error: Optional[str] = None


# ========== State Store ==========

@dataclass
class StoreResult:
    """Result of state store operation."""
    success: bool
    error: Optional[str] = None


@dataclass
class FetchResult:
    """Result of state fetch operation."""
    success: bool
    value: Any = None
    found: bool = False
    error: Optional[str] = None


@dataclass
class DeleteResult:
    """Result of state delete operation."""
    success: bool
    deleted: bool = False
    error: Optional[str] = None


@dataclass
class KeysResult:
    """Result of list keys operation."""
    success: bool
    keys: List[str] = field(default_factory=list)
    count: int = 0
    error: Optional[str] = None


# ========== Permissions ==========

@dataclass
class PermissionsInfo:
    """Agent permissions configuration."""
    success: bool
    level: Optional[str] = None
    paths: List[str] = field(default_factory=list)
    commands: List[str] = field(default_factory=list)
    domains: List[str] = field(default_factory=list)
    error: Optional[str] = None


# ========== HTTP ==========

@dataclass
class HttpResult:
    """Result of HTTP request."""
    success: bool
    status_code: int = 0
    body: str = ""
    headers: Dict[str, str] = field(default_factory=dict)
    error: Optional[str] = None
    async_request_id: Optional[int] = None


# ========== Events ==========

@dataclass
class KernelEvent:
    """Event from kernel pub/sub system."""
    event_type: str
    data: Dict[str, Any]
    timestamp: float
    source_agent: Optional[int] = None


@dataclass
class SubscribeResult:
    """Result of event subscription."""
    success: bool
    subscribed: List[str] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class PollEventsResult:
    """Result of polling for events."""
    success: bool
    events: List[KernelEvent] = field(default_factory=list)
    count: int = 0
    error: Optional[str] = None


@dataclass
class EmitResult:
    """Result of emitting an event."""
    success: bool
    delivered_to: int = 0
    error: Optional[str] = None


# ========== Async ==========

@dataclass
class AsyncResult:
    """Result from async syscall polling."""
    request_id: int
    opcode: int
    success: bool
    result: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class PollAsyncResult:
    """Result of polling for async results."""
    success: bool
    results: List[AsyncResult] = field(default_factory=list)
    count: int = 0
    error: Optional[str] = None


# ========== Metrics ==========

@dataclass
class SystemMetrics:
    """System-wide metrics."""
    success: bool = True
    cpu_percent: float = 0.0
    memory_used_bytes: int = 0
    memory_total_bytes: int = 0
    memory_percent: float = 0.0
    disk_used_bytes: int = 0
    disk_total_bytes: int = 0
    disk_percent: float = 0.0
    network_rx_bytes: int = 0
    network_tx_bytes: int = 0
    load_average: List[float] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class AgentMetrics:
    """Metrics for a specific agent."""
    agent_id: int
    name: str = ""
    cpu_percent: float = 0.0
    memory_bytes: int = 0
    memory_percent: float = 0.0
    syscalls_count: int = 0
    uptime_seconds: float = 0.0
    state: str = "unknown"


@dataclass
class AllAgentsMetrics:
    """Metrics for all agents."""
    success: bool
    agents: List[AgentMetrics] = field(default_factory=list)
    count: int = 0
    error: Optional[str] = None


@dataclass
class CgroupMetrics:
    """Cgroup resource metrics."""
    success: bool
    cpu_usage_usec: int = 0
    memory_current: int = 0
    memory_limit: int = 0
    pids_current: int = 0
    pids_limit: int = 0
    error: Optional[str] = None


# ========== World ==========

@dataclass
class WorldInfo:
    """Information about a simulation world."""
    id: str
    name: str
    agent_count: int = 0
    created_at: float = 0.0


@dataclass
class WorldCreateResult:
    """Result of world creation."""
    success: bool
    world_id: Optional[str] = None
    error: Optional[str] = None


@dataclass
class WorldListResult:
    """Result of listing worlds."""
    success: bool
    worlds: List[WorldInfo] = field(default_factory=list)
    count: int = 0
    error: Optional[str] = None


@dataclass
class WorldState:
    """Current state of a world."""
    success: bool
    id: str = ""
    name: str = ""
    agents: List[int] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    chaos_events_injected: int = 0
    error: Optional[str] = None


@dataclass
class WorldSnapshot:
    """World snapshot data."""
    success: bool
    snapshot_id: Optional[str] = None
    snapshot_data: Optional[str] = None
    error: Optional[str] = None


# ========== Tunnel ==========

@dataclass
class TunnelStatus:
    """Tunnel connection status."""
    success: bool
    connected: bool = False
    relay_url: Optional[str] = None
    machine_id: Optional[str] = None
    latency_ms: Optional[float] = None
    connected_since: Optional[float] = None
    error: Optional[str] = None


@dataclass
class TunnelRemotesResult:
    """List of remote agents connected through tunnel."""
    success: bool
    agents: List[Dict[str, Any]] = field(default_factory=list)
    count: int = 0
    error: Optional[str] = None


# ========== Audit ==========

@dataclass
class AuditEntry:
    """Single audit log entry."""
    id: int
    timestamp: float
    category: str
    agent_id: Optional[int]
    action: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditLogResult:
    """Result of audit log query."""
    success: bool
    entries: List[AuditEntry] = field(default_factory=list)
    count: int = 0
    error: Optional[str] = None


@dataclass
class AuditConfigResult:
    """Result of audit config update."""
    success: bool
    config: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


# ========== Recording ==========

@dataclass
class RecordingStatus:
    """Execution recording status."""
    success: bool
    active: bool = False
    entry_count: int = 0
    started_at: Optional[float] = None
    recording_data: Optional[str] = None  # Only when export=True
    error: Optional[str] = None


@dataclass
class ReplayStatus:
    """Execution replay status."""
    success: bool
    active: bool = False
    progress: float = 0.0  # 0.0 to 1.0
    total_entries: int = 0
    entries_replayed: int = 0
    entries_skipped: int = 0
    errors: List[str] = field(default_factory=list)
    error: Optional[str] = None


# ========== Generic ==========

@dataclass
class OperationResult:
    """Generic operation result for simple success/error responses."""
    success: bool
    error: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
