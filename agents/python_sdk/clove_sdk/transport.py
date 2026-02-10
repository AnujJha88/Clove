"""Socket transport for Clove kernel communication.

Handles low-level socket connection, message serialization, and I/O.
"""

import json
import socket
import struct
from typing import Optional, Union, Dict, Any

from .protocol import (
    Message,
    SyscallOp,
    HEADER_SIZE,
    MAGIC_BYTES,
    DEFAULT_SOCKET_PATH,
)
from .exceptions import ConnectionError, ProtocolError


class Transport:
    """Low-level socket transport for kernel communication.

    Manages the Unix domain socket connection and provides methods
    for sending/receiving wire protocol messages.

    Example:
        transport = Transport()
        transport.connect()
        response = transport.call_json(SyscallOp.SYS_HELLO, {})
        transport.disconnect()
    """

    def __init__(self, socket_path: str = DEFAULT_SOCKET_PATH):
        """Initialize transport.

        Args:
            socket_path: Path to kernel Unix domain socket
        """
        self.socket_path = socket_path
        self._sock: Optional[socket.socket] = None
        self._agent_id: int = 0

    @property
    def agent_id(self) -> int:
        """Get the agent ID assigned by kernel."""
        return self._agent_id

    @property
    def connected(self) -> bool:
        """Check if transport is connected."""
        return self._sock is not None

    def connect(self) -> None:
        """Connect to kernel.

        Raises:
            ConnectionError: If connection fails
        """
        if self._sock is not None:
            return  # Already connected

        try:
            self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._sock.connect(self.socket_path)
        except OSError as e:
            self._sock = None
            raise ConnectionError(f"Failed to connect to {self.socket_path}: {e}")

    def disconnect(self) -> None:
        """Disconnect from kernel."""
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass  # Ignore close errors
            finally:
                self._sock = None

    def send(self, opcode: SyscallOp, payload: Union[bytes, str, Dict[str, Any]] = b'') -> None:
        """Send message to kernel.

        Args:
            opcode: Syscall operation code
            payload: Message payload (bytes, string, or dict for JSON)

        Raises:
            ConnectionError: If not connected or send fails
        """
        if not self._sock:
            raise ConnectionError("Not connected to kernel")

        # Convert payload to bytes
        if isinstance(payload, dict):
            payload = json.dumps(payload).encode('utf-8')
        elif isinstance(payload, str):
            payload = payload.encode('utf-8')

        msg = Message(agent_id=self._agent_id, opcode=opcode, payload=payload)

        try:
            self._sock.sendall(msg.serialize())
        except OSError as e:
            raise ConnectionError(f"Send failed: {e}")

    def recv(self) -> Message:
        """Receive message from kernel.

        Returns:
            Received Message object

        Raises:
            ConnectionError: If not connected or connection closed
            ProtocolError: If received data is invalid
        """
        if not self._sock:
            raise ConnectionError("Not connected to kernel")

        # Read header
        header_data = self._recv_exact(HEADER_SIZE)
        magic, agent_id, opcode, payload_size = struct.unpack('<IIBQ', header_data)

        if magic != MAGIC_BYTES:
            raise ProtocolError(f"Invalid magic bytes: 0x{magic:08x}")

        # Read payload
        payload = self._recv_exact(payload_size) if payload_size > 0 else b''

        # Update our agent ID from response
        self._agent_id = agent_id

        return Message(agent_id=agent_id, opcode=SyscallOp(opcode), payload=payload)

    def call(self, opcode: SyscallOp, payload: Union[bytes, str, Dict[str, Any]] = b'') -> Message:
        """Send request and wait for response.

        Args:
            opcode: Syscall operation code
            payload: Message payload

        Returns:
            Response Message from kernel

        Raises:
            ConnectionError: If not connected
            ProtocolError: If response is invalid
        """
        self.send(opcode, payload)
        return self.recv()

    def call_json(self, opcode: SyscallOp, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send request with JSON payload and parse JSON response.

        Args:
            opcode: Syscall operation code
            payload: Dict to send as JSON (default: empty dict)

        Returns:
            Parsed JSON response as dict

        Raises:
            ConnectionError: If not connected
            ProtocolError: If response is not valid JSON
        """
        response = self.call(opcode, payload or {})

        try:
            return json.loads(response.payload_str)
        except json.JSONDecodeError as e:
            raise ProtocolError(f"Invalid JSON response: {e}")

    def _recv_exact(self, n: int) -> bytes:
        """Receive exactly n bytes from socket.

        Args:
            n: Number of bytes to receive

        Returns:
            Received bytes

        Raises:
            ConnectionError: If connection closed before receiving all bytes
        """
        data = b''
        while len(data) < n:
            try:
                chunk = self._sock.recv(n - len(data))
            except OSError as e:
                raise ConnectionError(f"Receive failed: {e}")

            if not chunk:
                raise ConnectionError("Connection closed by kernel")
            data += chunk
        return data

    def __enter__(self) -> 'Transport':
        """Context manager entry - connect to kernel."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - disconnect from kernel."""
        self.disconnect()
