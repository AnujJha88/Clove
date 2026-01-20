#!/usr/bin/env python3
"""
AgentOS Python SDK

Client library for communicating with the AgentOS kernel via Unix domain sockets.
"""

import socket
import struct
from enum import IntEnum
from typing import Optional, Tuple
from dataclasses import dataclass


# Protocol constants
MAGIC_BYTES = 0x41474E54  # "AGNT" in hex
HEADER_SIZE = 17
MAX_PAYLOAD_SIZE = 1024 * 1024  # 1MB


class SyscallOp(IntEnum):
    """System call operations"""
    SYS_NOOP = 0x00   # For testing / echo
    SYS_THINK = 0x01  # Send prompt to LLM
    SYS_EXEC = 0x02   # Execute shell command
    SYS_READ = 0x03   # Read file
    SYS_WRITE = 0x04  # Write file
    SYS_SPAWN = 0x10  # Spawn a sandboxed agent
    SYS_KILL = 0x11   # Kill an agent
    SYS_LIST = 0x12   # List running agents
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
    SYS_EXIT = 0xFF   # Graceful shutdown


@dataclass
class Message:
    """AgentOS message"""
    agent_id: int
    opcode: SyscallOp
    payload: bytes

    def serialize(self) -> bytes:
        """Serialize message to wire format"""
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
        """Deserialize message from wire format"""
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
        """Get payload as string"""
        return self.payload.decode('utf-8', errors='replace')


class AgentOSClient:
    """Client for communicating with AgentOS kernel"""

    def __init__(self, socket_path: str = '/tmp/agentos.sock'):
        self.socket_path = socket_path
        self._sock: Optional[socket.socket] = None
        self._agent_id = 0

    def connect(self) -> bool:
        """Connect to the AgentOS kernel"""
        try:
            self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._sock.connect(self.socket_path)
            return True
        except Exception as e:
            print(f"Failed to connect: {e}")
            return False

    def disconnect(self):
        """Disconnect from the kernel"""
        if self._sock:
            self._sock.close()
            self._sock = None

    def send(self, opcode: SyscallOp, payload: bytes | str = b'') -> bool:
        """Send a message to the kernel"""
        if not self._sock:
            return False

        if isinstance(payload, str):
            payload = payload.encode('utf-8')

        msg = Message(agent_id=self._agent_id, opcode=opcode, payload=payload)
        try:
            self._sock.sendall(msg.serialize())
            return True
        except Exception as e:
            print(f"Send failed: {e}")
            return False

    def recv(self) -> Optional[Message]:
        """Receive a message from the kernel"""
        if not self._sock:
            return None

        try:
            # Read header first
            header_data = self._recv_exact(HEADER_SIZE)
            if not header_data:
                return None

            # Parse header to get payload size
            magic, agent_id, opcode, payload_size = struct.unpack('<IIBQ', header_data)

            if magic != MAGIC_BYTES:
                print(f"Invalid magic bytes: 0x{magic:08x}")
                return None

            # Read payload
            payload = b''
            if payload_size > 0:
                payload = self._recv_exact(payload_size)
                if not payload:
                    return None

            # Update our agent ID from response
            self._agent_id = agent_id

            return Message(agent_id=agent_id, opcode=SyscallOp(opcode), payload=payload)
        except Exception as e:
            print(f"Receive failed: {e}")
            return None

    def _recv_exact(self, n: int) -> Optional[bytes]:
        """Receive exactly n bytes"""
        data = b''
        while len(data) < n:
            chunk = self._sock.recv(n - len(data))
            if not chunk:
                return None
            data += chunk
        return data

    def call(self, opcode: SyscallOp, payload: bytes | str = b'') -> Optional[Message]:
        """Send a message and wait for response"""
        if not self.send(opcode, payload):
            return None
        return self.recv()

    # Convenience methods
    def echo(self, message: str) -> Optional[str]:
        """Echo a message (for testing)"""
        response = self.call(SyscallOp.SYS_NOOP, message)
        return response.payload_str if response else None

    def think(self, prompt: str,
              image: bytes = None,
              image_mime_type: str = "image/jpeg",
              system_instruction: str = None,
              thinking_level: str = None,
              temperature: float = None,
              model: str = None) -> dict:
        """Send a prompt to the LLM via Gemini API.

        Args:
            prompt: The text prompt to send
            image: Optional image bytes for multimodal input
            image_mime_type: MIME type of image (default: "image/jpeg")
            system_instruction: Optional system instruction for the model
            thinking_level: Optional thinking level ("low", "medium", "high")
            temperature: Optional temperature for generation (0.0-1.0)
            model: Optional model name (default: gemini-2.0-flash)

        Returns:
            dict with 'success', 'content', 'tokens', and optionally 'error'
        """
        import json
        import base64

        # Build request payload
        payload = {"prompt": prompt}

        if image:
            payload["image"] = {
                "data": base64.b64encode(image).decode(),
                "mime_type": image_mime_type
            }

        if system_instruction:
            payload["system_instruction"] = system_instruction

        if thinking_level:
            payload["thinking_level"] = thinking_level

        if temperature is not None:
            payload["temperature"] = temperature

        if model:
            payload["model"] = model

        # Send JSON payload
        response = self.call(SyscallOp.SYS_THINK, json.dumps(payload))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": True, "content": response.payload_str, "error": None}
        return {"success": False, "content": "", "error": "No response from kernel"}

    def exit(self) -> bool:
        """Request graceful exit"""
        response = self.call(SyscallOp.SYS_EXIT)
        return response is not None

    def spawn(self, name: str, script: str, sandboxed: bool = True,
              network: bool = False, limits: dict = None) -> Optional[dict]:
        """Spawn a new sandboxed agent"""
        import json
        payload = {
            "name": name,
            "script": script,
            "sandboxed": sandboxed,
            "network": network
        }
        if limits:
            payload["limits"] = limits

        response = self.call(SyscallOp.SYS_SPAWN, json.dumps(payload))
        if response:
            return json.loads(response.payload_str)
        return None

    def kill(self, name: str = None, agent_id: int = None) -> bool:
        """Kill a running agent"""
        import json
        payload = {}
        if name:
            payload["name"] = name
        elif agent_id:
            payload["id"] = agent_id
        else:
            return False

        response = self.call(SyscallOp.SYS_KILL, json.dumps(payload))
        if response:
            result = json.loads(response.payload_str)
            return result.get("killed", False)
        return False

    def list_agents(self) -> list:
        """List all running agents"""
        import json
        response = self.call(SyscallOp.SYS_LIST)
        if response:
            return json.loads(response.payload_str)
        return []

    def exec(self, command: str, cwd: str = None, timeout: int = 30) -> dict:
        """Execute a shell command.

        Args:
            command: The shell command to execute
            cwd: Optional working directory
            timeout: Timeout in seconds (default: 30)

        Returns:
            dict with 'success', 'stdout', 'stderr', 'exit_code'
        """
        import json
        payload = {
            "command": command,
            "timeout": timeout
        }
        if cwd:
            payload["cwd"] = cwd

        response = self.call(SyscallOp.SYS_EXEC, json.dumps(payload))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "stdout": "", "stderr": response.payload_str, "exit_code": -1}
        return {"success": False, "stdout": "", "stderr": "No response from kernel", "exit_code": -1}

    def read_file(self, path: str) -> dict:
        """Read a file's contents.

        Args:
            path: Path to the file to read

        Returns:
            dict with 'success', 'content', 'size'
        """
        import json
        payload = {"path": path}

        response = self.call(SyscallOp.SYS_READ, json.dumps(payload))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "content": "", "size": 0, "error": response.payload_str}
        return {"success": False, "content": "", "size": 0, "error": "No response from kernel"}

    def write_file(self, path: str, content: str, mode: str = "write") -> dict:
        """Write content to a file.

        Args:
            path: Path to the file to write
            content: Content to write
            mode: "write" (overwrite) or "append"

        Returns:
            dict with 'success', 'bytes_written'
        """
        import json
        payload = {
            "path": path,
            "content": content,
            "mode": mode
        }

        response = self.call(SyscallOp.SYS_WRITE, json.dumps(payload))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "bytes_written": 0, "error": response.payload_str}
        return {"success": False, "bytes_written": 0, "error": "No response from kernel"}

    # =========================================================================
    # IPC - Inter-Agent Communication
    # =========================================================================

    def register_name(self, name: str) -> dict:
        """Register this agent with a name for IPC.

        Args:
            name: Unique name for this agent (e.g., "worker-1", "orchestrator")

        Returns:
            dict with 'success', 'agent_id', 'name'
        """
        import json
        payload = {"name": name}

        response = self.call(SyscallOp.SYS_REGISTER, json.dumps(payload))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "error": response.payload_str}
        return {"success": False, "error": "No response from kernel"}

    def send_message(self, message: dict, to: int = None, to_name: str = None) -> dict:
        """Send a message to another agent.

        Args:
            message: The message payload (any JSON-serializable dict)
            to: Target agent ID
            to_name: Target agent name (alternative to 'to')

        Returns:
            dict with 'success', 'delivered_to'
        """
        import json
        payload = {"message": message}

        if to is not None:
            payload["to"] = to
        if to_name is not None:
            payload["to_name"] = to_name

        response = self.call(SyscallOp.SYS_SEND, json.dumps(payload))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "error": response.payload_str}
        return {"success": False, "error": "No response from kernel"}

    def recv_messages(self, max_messages: int = 10) -> dict:
        """Receive pending messages from other agents.

        Args:
            max_messages: Maximum number of messages to retrieve (default: 10)

        Returns:
            dict with 'success', 'messages' (list), 'count'
            Each message has: 'from', 'from_name', 'message', 'age_ms'
        """
        import json
        payload = {"max": max_messages}

        response = self.call(SyscallOp.SYS_RECV, json.dumps(payload))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "messages": [], "count": 0, "error": response.payload_str}
        return {"success": False, "messages": [], "count": 0, "error": "No response from kernel"}

    def broadcast(self, message: dict, include_self: bool = False) -> dict:
        """Broadcast a message to all registered agents.

        Args:
            message: The message payload (any JSON-serializable dict)
            include_self: Whether to include self in broadcast (default: False)

        Returns:
            dict with 'success', 'delivered_count'
        """
        import json
        payload = {
            "message": message,
            "include_self": include_self
        }

        response = self.call(SyscallOp.SYS_BROADCAST, json.dumps(payload))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "delivered_count": 0, "error": response.payload_str}
        return {"success": False, "delivered_count": 0, "error": "No response from kernel"}

    # =========================================================================
    # Permissions
    # =========================================================================

    def get_permissions(self) -> dict:
        """Get this agent's permissions.

        Returns:
            dict with 'success', 'permissions'
        """
        import json
        response = self.call(SyscallOp.SYS_GET_PERMS, "{}")
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "error": response.payload_str}
        return {"success": False, "error": "No response from kernel"}

    def set_permissions(self, permissions: dict = None, level: str = None,
                       agent_id: int = None) -> dict:
        """Set agent permissions.

        Args:
            permissions: Full permissions dict (optional)
            level: Permission level: "unrestricted", "standard", "sandboxed", "readonly", "minimal"
            agent_id: Target agent ID (default: self)

        Returns:
            dict with 'success', 'agent_id'
        """
        import json
        payload = {}

        if permissions:
            payload["permissions"] = permissions
        if level:
            payload["level"] = level
        if agent_id is not None:
            payload["agent_id"] = agent_id

        response = self.call(SyscallOp.SYS_SET_PERMS, json.dumps(payload))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "error": response.payload_str}
        return {"success": False, "error": "No response from kernel"}

    # =========================================================================
    # State Store
    # =========================================================================

    def store(self, key: str, value, scope: str = "global", ttl: int = None) -> dict:
        """Store a key-value pair in the shared state store.

        Args:
            key: The key to store
            value: The value to store (must be JSON-serializable)
            scope: "global" (all agents), "agent" (only this agent), "session" (until restart)
            ttl: Time-to-live in seconds (optional)

        Returns:
            dict with 'success', 'key'
        """
        import json
        payload = {
            "key": key,
            "value": value,
            "scope": scope
        }
        if ttl is not None:
            payload["ttl"] = ttl

        response = self.call(SyscallOp.SYS_STORE, json.dumps(payload))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "error": response.payload_str}
        return {"success": False, "error": "No response from kernel"}

    def fetch(self, key: str) -> dict:
        """Fetch a value from the shared state store.

        Args:
            key: The key to fetch

        Returns:
            dict with 'success', 'exists', 'value', 'scope'
        """
        import json
        payload = {"key": key}

        response = self.call(SyscallOp.SYS_FETCH, json.dumps(payload))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "error": response.payload_str}
        return {"success": False, "error": "No response from kernel"}

    def delete_key(self, key: str) -> dict:
        """Delete a key from the shared state store.

        Args:
            key: The key to delete

        Returns:
            dict with 'success', 'deleted'
        """
        import json
        payload = {"key": key}

        response = self.call(SyscallOp.SYS_DELETE, json.dumps(payload))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "error": response.payload_str}
        return {"success": False, "error": "No response from kernel"}

    def list_keys(self, prefix: str = "") -> dict:
        """List keys in the shared state store.

        Args:
            prefix: Optional prefix to filter keys

        Returns:
            dict with 'success', 'keys', 'count'
        """
        import json
        payload = {"prefix": prefix} if prefix else {}

        response = self.call(SyscallOp.SYS_KEYS, json.dumps(payload))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "error": response.payload_str}
        return {"success": False, "error": "No response from kernel"}

    # =========================================================================
    # HTTP
    # =========================================================================

    def http(self, url: str, method: str = "GET", headers: dict = None,
             body: str = None, timeout: int = 30) -> dict:
        """Make an HTTP request.

        Args:
            url: The URL to request
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            headers: Optional request headers
            body: Optional request body (for POST/PUT)
            timeout: Request timeout in seconds

        Returns:
            dict with 'success', 'body', 'status_code'

        Note:
            Requires HTTP permission and domain to be in whitelist.
        """
        import json
        payload = {
            "url": url,
            "method": method,
            "timeout": timeout
        }

        if headers:
            payload["headers"] = headers
        if body:
            payload["body"] = body

        response = self.call(SyscallOp.SYS_HTTP, json.dumps(payload))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "body": "", "error": response.payload_str}
        return {"success": False, "body": "", "error": "No response from kernel"}

    # =========================================================================
    # Events (Pub/Sub)
    # =========================================================================

    def subscribe(self, event_types: list) -> dict:
        """Subscribe to kernel events.

        Args:
            event_types: List of event types to subscribe to.
                Available: "AGENT_SPAWNED", "AGENT_EXITED", "MESSAGE_RECEIVED",
                          "STATE_CHANGED", "SYSCALL_BLOCKED", "RESOURCE_WARNING", "CUSTOM"

        Returns:
            dict with 'success', 'subscribed' (list of types)
        """
        import json
        payload = {"event_types": event_types}

        response = self.call(SyscallOp.SYS_SUBSCRIBE, json.dumps(payload))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "error": response.payload_str}
        return {"success": False, "error": "No response from kernel"}

    def unsubscribe(self, event_types: list) -> dict:
        """Unsubscribe from kernel events.

        Args:
            event_types: List of event types to unsubscribe from

        Returns:
            dict with 'success', 'unsubscribed' (list of types)
        """
        import json
        payload = {"event_types": event_types}

        response = self.call(SyscallOp.SYS_UNSUBSCRIBE, json.dumps(payload))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "error": response.payload_str}
        return {"success": False, "error": "No response from kernel"}

    def poll_events(self, max_events: int = 10) -> dict:
        """Poll for pending events.

        Args:
            max_events: Maximum number of events to retrieve (default: 10)

        Returns:
            dict with 'success', 'events' (list), 'count'
            Each event has: 'type', 'data', 'source_agent_id', 'age_ms'
        """
        import json
        payload = {"max": max_events}

        response = self.call(SyscallOp.SYS_POLL_EVENTS, json.dumps(payload))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "events": [], "count": 0, "error": response.payload_str}
        return {"success": False, "events": [], "count": 0, "error": "No response from kernel"}

    def emit_event(self, event_type: str, data: dict = None) -> dict:
        """Emit a custom event to all subscribers.

        Args:
            event_type: Should be "CUSTOM" for user events
            data: Event data payload

        Returns:
            dict with 'success', 'delivered_to' (count)
        """
        import json
        payload = {
            "event_type": event_type,
            "data": data or {}
        }

        response = self.call(SyscallOp.SYS_EMIT, json.dumps(payload))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "error": response.payload_str}
        return {"success": False, "error": "No response from kernel"}

    # =========================================================================
    # World Simulation Methods
    # =========================================================================

    def world_create(self, name: str, config: dict = None) -> dict:
        """Create a new simulated world.

        Args:
            name: Name for the world
            config: World configuration with optional keys:
                - virtual_filesystem: {initial_files: {...}, writable_patterns: [...]}
                - network: {mode: "mock", mock_responses: {...}}
                - chaos: {enabled: bool, failure_rate: float, ...}

        Returns:
            dict with 'success', 'world_id', 'name'
        """
        import json
        payload = {
            "name": name,
            "config": config or {}
        }

        response = self.call(SyscallOp.SYS_WORLD_CREATE, json.dumps(payload))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "error": response.payload_str}
        return {"success": False, "error": "No response from kernel"}

    def world_destroy(self, world_id: str, force: bool = False) -> dict:
        """Destroy a world.

        Args:
            world_id: ID of the world to destroy
            force: If True, destroy even if agents are in the world

        Returns:
            dict with 'success', 'world_id'
        """
        import json
        payload = {
            "world_id": world_id,
            "force": force
        }

        response = self.call(SyscallOp.SYS_WORLD_DESTROY, json.dumps(payload))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "error": response.payload_str}
        return {"success": False, "error": "No response from kernel"}

    def world_list(self) -> dict:
        """List all active worlds.

        Returns:
            dict with 'success', 'worlds' (list), 'count'
        """
        import json

        response = self.call(SyscallOp.SYS_WORLD_LIST, "{}")
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "worlds": [], "count": 0, "error": response.payload_str}
        return {"success": False, "worlds": [], "count": 0, "error": "No response from kernel"}

    def world_join(self, world_id: str) -> dict:
        """Join a world.

        When in a world, file and network operations are routed through the
        world's virtual filesystem and network mock.

        Args:
            world_id: ID of the world to join

        Returns:
            dict with 'success', 'world_id'
        """
        import json
        payload = {"world_id": world_id}

        response = self.call(SyscallOp.SYS_WORLD_JOIN, json.dumps(payload))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "error": response.payload_str}
        return {"success": False, "error": "No response from kernel"}

    def world_leave(self) -> dict:
        """Leave the current world.

        Returns:
            dict with 'success'
        """
        import json

        response = self.call(SyscallOp.SYS_WORLD_LEAVE, "{}")
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "error": response.payload_str}
        return {"success": False, "error": "No response from kernel"}

    def world_event(self, world_id: str, event_type: str, params: dict = None) -> dict:
        """Inject a chaos event into a world.

        Event types include:
            - "disk_full": Simulate full disk
            - "disk_fail": Simulate disk failure
            - "network_partition": Simulate network outage
            - "slow_io": Inject I/O latency

        Args:
            world_id: ID of the world
            event_type: Type of chaos event
            params: Optional parameters for the event

        Returns:
            dict with 'success', 'world_id', 'event_type'
        """
        import json
        payload = {
            "world_id": world_id,
            "event_type": event_type,
            "params": params or {}
        }

        response = self.call(SyscallOp.SYS_WORLD_EVENT, json.dumps(payload))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "error": response.payload_str}
        return {"success": False, "error": "No response from kernel"}

    def world_state(self, world_id: str) -> dict:
        """Get the current state and metrics of a world.

        Args:
            world_id: ID of the world

        Returns:
            dict with 'success', 'state' containing metrics
        """
        import json
        payload = {"world_id": world_id}

        response = self.call(SyscallOp.SYS_WORLD_STATE, json.dumps(payload))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "error": response.payload_str}
        return {"success": False, "error": "No response from kernel"}

    def world_snapshot(self, world_id: str) -> dict:
        """Create a snapshot of a world's state.

        The snapshot can be used to restore the world later.

        Args:
            world_id: ID of the world

        Returns:
            dict with 'success', 'snapshot' (JSON object)
        """
        import json
        payload = {"world_id": world_id}

        response = self.call(SyscallOp.SYS_WORLD_SNAPSHOT, json.dumps(payload))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "error": response.payload_str}
        return {"success": False, "error": "No response from kernel"}

    def world_restore(self, snapshot: dict, new_world_id: str = None) -> dict:
        """Restore a world from a snapshot.

        Args:
            snapshot: The snapshot object from world_snapshot()
            new_world_id: Optional ID for the restored world (auto-generated if not provided)

        Returns:
            dict with 'success', 'world_id'
        """
        import json
        payload = {
            "snapshot": snapshot,
            "new_world_id": new_world_id or ""
        }

        response = self.call(SyscallOp.SYS_WORLD_RESTORE, json.dumps(payload))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "error": response.payload_str}
        return {"success": False, "error": "No response from kernel"}

    # =========================================================================
    # Tunnel (Remote Connectivity) Methods
    # =========================================================================

    def tunnel_connect(self, relay_url: str, machine_id: str = None,
                      token: str = None) -> dict:
        """Connect the kernel to a relay server for remote agent access.

        Args:
            relay_url: WebSocket URL of the relay server (e.g., ws://localhost:8765)
            machine_id: This machine's identifier
            token: Authentication token for the relay

        Returns:
            dict with 'success', 'relay_url', 'machine_id'
        """
        import json
        payload = {
            "relay_url": relay_url
        }
        if machine_id:
            payload["machine_id"] = machine_id
        if token:
            payload["token"] = token

        response = self.call(SyscallOp.SYS_TUNNEL_CONNECT, json.dumps(payload))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "error": response.payload_str}
        return {"success": False, "error": "No response from kernel"}

    def tunnel_disconnect(self) -> dict:
        """Disconnect the kernel from the relay server.

        Returns:
            dict with 'success'
        """
        import json

        response = self.call(SyscallOp.SYS_TUNNEL_DISCONNECT, "{}")
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "error": response.payload_str}
        return {"success": False, "error": "No response from kernel"}

    def tunnel_status(self) -> dict:
        """Get the current tunnel connection status.

        Returns:
            dict with 'success', 'connected', 'relay_url', 'machine_id',
                 'remote_agent_count'
        """
        import json

        response = self.call(SyscallOp.SYS_TUNNEL_STATUS, "{}")
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "error": response.payload_str}
        return {"success": False, "error": "No response from kernel"}

    def tunnel_list_remotes(self) -> dict:
        """List remote agents currently connected through the tunnel.

        Returns:
            dict with 'success', 'agents' (list), 'count'
            Each agent has: 'agent_id', 'name', 'connected_at'
        """
        import json

        response = self.call(SyscallOp.SYS_TUNNEL_LIST_REMOTES, "{}")
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "agents": [], "error": response.payload_str}
        return {"success": False, "agents": [], "error": "No response from kernel"}

    def tunnel_config(self, relay_url: str = None, machine_id: str = None,
                     token: str = None, reconnect_interval: int = None) -> dict:
        """Configure tunnel settings without connecting.

        Args:
            relay_url: WebSocket URL of the relay server
            machine_id: This machine's identifier
            token: Authentication token
            reconnect_interval: Seconds between reconnect attempts

        Returns:
            dict with 'success'
        """
        import json
        payload = {}
        if relay_url:
            payload["relay_url"] = relay_url
        if machine_id:
            payload["machine_id"] = machine_id
        if token:
            payload["token"] = token
        if reconnect_interval is not None:
            payload["reconnect_interval"] = reconnect_interval

        response = self.call(SyscallOp.SYS_TUNNEL_CONFIG, json.dumps(payload))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "error": response.payload_str}
        return {"success": False, "error": "No response from kernel"}

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()


# Convenience function for quick testing
def connect(socket_path: str = '/tmp/agentos.sock') -> AgentOSClient:
    """Create and connect a client"""
    client = AgentOSClient(socket_path)
    if not client.connect():
        raise ConnectionError(f"Failed to connect to {socket_path}")
    return client
 

if __name__ == '__main__': 
    # Quick test
    print("AgentOS Python SDK")
    print("==================")
    print(f"Socket path: /tmp/agentos.sock")
    print(f"Header size: {HEADER_SIZE} bytes")
    print(f"Magic bytes: 0x{MAGIC_BYTES:08X}")
    print()
    print("Usage:")
    print("  from agentos import AgentOSClient")
    print("  ")
    print("  with AgentOSClient() as client:")
    print("      response = client.echo('Hello!')")
    print("      print(response)")
