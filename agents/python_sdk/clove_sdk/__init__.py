"""Clove SDK - Python client for the Clove kernel.

A modular SDK for communicating with the Clove microkernel runtime.

Example:
    from clove_sdk import CloveClient

    with CloveClient() as client:
        info = client.hello()
        print(f"Connected to kernel v{info.version}")

        result = client.exec("ls -la")
        if result.success:
            print(result.stdout)
"""

# Protocol
from .protocol import SyscallOp, Message, MAGIC_BYTES, HEADER_SIZE, DEFAULT_SOCKET_PATH

# Client
from .client import CloveClient, AgentOSClient, connect

# Exceptions
from .exceptions import (
    CloveError,
    ConnectionError,
    ProtocolError,
    TimeoutError,
    SyscallError,
    PermissionDenied,
    AgentNotFound,
    StateKeyNotFound,
    WorldNotFound,
    TunnelError,
    ValidationError,
)

# Models
from .models import (
    # Core
    KernelInfo,
    ExecResult,
    FileContent,
    WriteResult,
    # Agents
    AgentInfo,
    AgentState,
    SpawnResult,
    # IPC
    IPCMessage,
    SendResult,
    RecvResult,
    BroadcastResult,
    RegisterResult,
    # State
    StoreResult,
    FetchResult,
    DeleteResult,
    KeysResult,
    # Permissions
    PermissionsInfo,
    # HTTP
    HttpResult,
    # Events
    KernelEvent,
    SubscribeResult,
    PollEventsResult,
    EmitResult,
    AsyncResult,
    PollAsyncResult,
    # Metrics
    SystemMetrics,
    AgentMetrics,
    AllAgentsMetrics,
    CgroupMetrics,
    # World
    WorldInfo,
    WorldCreateResult,
    WorldListResult,
    WorldState,
    WorldSnapshot,
    # Tunnel
    TunnelStatus,
    TunnelRemotesResult,
    # Audit
    AuditEntry,
    AuditLogResult,
    AuditConfigResult,
    # Recording
    RecordingStatus,
    ReplayStatus,
    # Generic
    OperationResult,
)

# Agentic
from .agentic import AgenticLoop, Tool, run_task

__version__ = "0.2.0"

__all__ = [
    # Version
    "__version__",

    # Protocol
    "SyscallOp",
    "Message",
    "MAGIC_BYTES",
    "HEADER_SIZE",
    "DEFAULT_SOCKET_PATH",

    # Client
    "CloveClient",
    "AgentOSClient",  # Backwards compatibility
    "connect",

    # Exceptions
    "CloveError",
    "ConnectionError",
    "ProtocolError",
    "TimeoutError",
    "SyscallError",
    "PermissionDenied",
    "AgentNotFound",
    "StateKeyNotFound",
    "WorldNotFound",
    "TunnelError",
    "ValidationError",

    # Models - Core
    "KernelInfo",
    "ExecResult",
    "FileContent",
    "WriteResult",

    # Models - Agents
    "AgentInfo",
    "AgentState",
    "SpawnResult",

    # Models - IPC
    "IPCMessage",
    "SendResult",
    "RecvResult",
    "BroadcastResult",
    "RegisterResult",

    # Models - State
    "StoreResult",
    "FetchResult",
    "DeleteResult",
    "KeysResult",

    # Models - Permissions
    "PermissionsInfo",

    # Models - HTTP
    "HttpResult",

    # Models - Events
    "KernelEvent",
    "SubscribeResult",
    "PollEventsResult",
    "EmitResult",
    "AsyncResult",
    "PollAsyncResult",

    # Models - Metrics
    "SystemMetrics",
    "AgentMetrics",
    "AllAgentsMetrics",
    "CgroupMetrics",

    # Models - World
    "WorldInfo",
    "WorldCreateResult",
    "WorldListResult",
    "WorldState",
    "WorldSnapshot",

    # Models - Tunnel
    "TunnelStatus",
    "TunnelRemotesResult",

    # Models - Audit
    "AuditEntry",
    "AuditLogResult",
    "AuditConfigResult",

    # Models - Recording
    "RecordingStatus",
    "ReplayStatus",

    # Models - Generic
    "OperationResult",

    # Agentic
    "AgenticLoop",
    "Tool",
    "run_task",
]
