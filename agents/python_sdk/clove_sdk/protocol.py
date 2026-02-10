"""Clove wire protocol definitions.

Binary protocol for communication between agents and the kernel.
"""

import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


# Protocol constants
MAGIC_BYTES = 0x41474E54  # "AGNT" in hex
HEADER_SIZE = 17
MAX_PAYLOAD_SIZE = 1024 * 1024  # 1MB
DEFAULT_SOCKET_PATH = '/tmp/clove.sock'
DEFAULT_TIMEOUT = 30


class SyscallOp(IntEnum):
    """System call operations supported by the kernel."""

    # Core operations
    SYS_NOOP = 0x00   # For testing / echo
    SYS_THINK = 0x01  # Send prompt to LLM
    SYS_EXEC = 0x02   # Execute shell command
    SYS_READ = 0x03   # Read file
    SYS_WRITE = 0x04  # Write file

    # Agent lifecycle
    SYS_SPAWN = 0x10  # Spawn a sandboxed agent
    SYS_KILL = 0x11   # Kill an agent
    SYS_LIST = 0x12   # List running agents
    SYS_PAUSE = 0x14  # Pause an agent
    SYS_RESUME = 0x15 # Resume a paused agent

    # IPC - Inter-Agent Communication
    SYS_SEND = 0x20       # Send message to another agent
    SYS_RECV = 0x21       # Receive pending messages
    SYS_BROADCAST = 0x22  # Broadcast message to all agents
    SYS_REGISTER = 0x23   # Register agent name

    # State Store
    SYS_STORE = 0x30      # Store key-value pair
    SYS_FETCH = 0x31      # Retrieve value by key
    SYS_DELETE = 0x32     # Delete a key
    SYS_KEYS = 0x33       # List keys with optional prefix

    # Permissions
    SYS_GET_PERMS = 0x40  # Get own permissions
    SYS_SET_PERMS = 0x41  # Set agent permissions

    # Network
    SYS_HTTP = 0x50       # Make HTTP request

    # Events (Pub/Sub)
    SYS_SUBSCRIBE = 0x60    # Subscribe to event types
    SYS_UNSUBSCRIBE = 0x61  # Unsubscribe from events
    SYS_POLL_EVENTS = 0x62  # Get pending events
    SYS_EMIT = 0x63         # Emit custom event

    # Execution Recording & Replay
    SYS_RECORD_START = 0x70   # Start recording execution
    SYS_RECORD_STOP = 0x71    # Stop recording
    SYS_RECORD_STATUS = 0x72  # Get recording status
    SYS_REPLAY_START = 0x73   # Start replay
    SYS_REPLAY_STATUS = 0x74  # Get replay status

    # Audit Logging
    SYS_GET_AUDIT_LOG = 0x76     # Get audit log entries
    SYS_SET_AUDIT_CONFIG = 0x77  # Configure audit logging

    # Async Results
    SYS_ASYNC_POLL = 0x80  # Poll async syscall results

    # World Simulation
    SYS_WORLD_CREATE = 0xA0    # Create world from config
    SYS_WORLD_DESTROY = 0xA1   # Destroy world
    SYS_WORLD_LIST = 0xA2      # List active worlds
    SYS_WORLD_JOIN = 0xA3      # Join agent to world
    SYS_WORLD_LEAVE = 0xA4     # Remove agent from world
    SYS_WORLD_EVENT = 0xA5     # Inject chaos event
    SYS_WORLD_STATE = 0xA6     # Get world metrics
    SYS_WORLD_SNAPSHOT = 0xA7  # Save world state
    SYS_WORLD_RESTORE = 0xA8   # Restore from snapshot

    # Remote Connectivity (Tunnel)
    SYS_TUNNEL_CONNECT = 0xB0      # Connect kernel to relay server
    SYS_TUNNEL_DISCONNECT = 0xB1   # Disconnect from relay
    SYS_TUNNEL_STATUS = 0xB2       # Get tunnel connection status
    SYS_TUNNEL_LIST_REMOTES = 0xB3 # List connected remote agents
    SYS_TUNNEL_CONFIG = 0xB4       # Configure tunnel settings

    # Metrics
    SYS_METRICS_SYSTEM = 0xC0      # Get system-wide metrics
    SYS_METRICS_AGENT = 0xC1       # Get metrics for specific agent
    SYS_METRICS_ALL_AGENTS = 0xC2  # Get metrics for all agents
    SYS_METRICS_CGROUP = 0xC3      # Get cgroup metrics

    # Kernel info / capabilities
    SYS_LLM_REPORT = 0xF0  # Report SDK LLM usage to kernel
    SYS_HELLO = 0xFE       # Handshake / capability query
    SYS_EXIT = 0xFF        # Graceful shutdown


@dataclass
class Message:
    """Clove wire protocol message.

    Wire format (17-byte header + variable payload):
        [Magic:4B "AGNT"] [Agent ID:4B] [Opcode:1B] [Payload Length:8B] [Payload:var]
    """
    agent_id: int
    opcode: SyscallOp
    payload: bytes

    def serialize(self) -> bytes:
        """Serialize message to wire format."""
        header = struct.pack(
            '<IIBQ',  # little-endian: uint32, uint32, uint8, uint64
            MAGIC_BYTES,
            self.agent_id,
            self.opcode,
            len(self.payload)
        )
        return header + self.payload

    @classmethod
    def deserialize(cls, data: bytes) -> Optional['Message']:
        """Deserialize message from wire format.

        Returns None if data is invalid or incomplete.
        """
        if len(data) < HEADER_SIZE:
            return None

        magic, agent_id, opcode, payload_size = struct.unpack('<IIBQ', data[:HEADER_SIZE])

        if magic != MAGIC_BYTES:
            return None

        if payload_size > MAX_PAYLOAD_SIZE:
            return None

        if len(data) < HEADER_SIZE + payload_size:
            return None

        payload = data[HEADER_SIZE:HEADER_SIZE + payload_size]
        return cls(agent_id=agent_id, opcode=SyscallOp(opcode), payload=payload)

    @property
    def payload_str(self) -> str:
        """Get payload as UTF-8 string."""
        return self.payload.decode('utf-8', errors='replace')
