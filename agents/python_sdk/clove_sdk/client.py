#!/usr/bin/env python3
"""Clove Python SDK - Main Client.

Thin facade over domain-specific mixins providing a unified API
for communicating with the Clove kernel.

Example:
    with CloveClient() as client:
        info = client.hello()
        result = client.exec("ls -la")
        print(result.stdout)
"""

import base64
from typing import Optional, Dict, Any

from .protocol import SyscallOp, Message, DEFAULT_SOCKET_PATH
from .transport import Transport
from .models import KernelInfo
from .exceptions import ConnectionError

# Import all mixins
from .mixins.agents import AgentsMixin
from .mixins.filesystem import FilesystemMixin
from .mixins.ipc import IPCMixin
from .mixins.state import StateMixin
from .mixins.events import EventsMixin
from .mixins.metrics import MetricsMixin
from .mixins.world import WorldMixin
from .mixins.tunnel import TunnelMixin
from .mixins.audit import AuditMixin
from .mixins.recording import RecordingMixin


class CloveClient(
    AgentsMixin,
    FilesystemMixin,
    IPCMixin,
    StateMixin,
    EventsMixin,
    MetricsMixin,
    WorldMixin,
    TunnelMixin,
    AuditMixin,
    RecordingMixin
):
    """Client for communicating with the Clove kernel.

    Provides a unified API for all kernel operations through
    domain-specific mixins.

    Example:
        # Context manager (recommended)
        with CloveClient() as client:
            info = client.hello()
            result = client.exec("ls -la")
            if result.success:
                print(result.stdout)

        # Manual connection
        client = CloveClient()
        client.connect()
        try:
            agents = client.list_agents()
        finally:
            client.disconnect()
    """

    def __init__(self, socket_path: str = DEFAULT_SOCKET_PATH):
        """Initialize client.

        Args:
            socket_path: Path to kernel Unix domain socket
        """
        self._transport = Transport(socket_path)

    @property
    def socket_path(self) -> str:
        """Get the socket path."""
        return self._transport.socket_path

    @property
    def agent_id(self) -> int:
        """Get the agent ID assigned by kernel."""
        return self._transport.agent_id

    @property
    def connected(self) -> bool:
        """Check if client is connected to kernel."""
        return self._transport.connected

    def connect(self) -> bool:
        """Connect to the Clove kernel.

        Returns:
            True if connected successfully

        Note:
            For new code, prefer using the context manager which
            raises ConnectionError on failure.
        """
        try:
            self._transport.connect()
            return True
        except ConnectionError:
            return False

    def disconnect(self) -> None:
        """Disconnect from the kernel."""
        self._transport.disconnect()

    def hello(self) -> KernelInfo:
        """Query kernel version and capabilities.

        Returns:
            KernelInfo with version, capabilities, and agent_id
        """
        result = self._transport.call_json(SyscallOp.SYS_HELLO, {})

        return KernelInfo(
            version=result.get("version", "unknown"),
            capabilities=result.get("capabilities", []),
            agent_id=result.get("agent_id", self.agent_id),
            uptime_seconds=result.get("uptime", 0.0)
        )

    def echo(self, message: str) -> Optional[str]:
        """Echo a message (for testing).

        Args:
            message: Message to echo

        Returns:
            Echoed message or None on failure
        """
        response = self._transport.call(SyscallOp.SYS_NOOP, message)
        return response.payload_str if response else None

    def noop(self, message: str) -> Optional[str]:
        """Alias for echo - send a NOOP message (for testing)."""
        return self.echo(message)

    def think(
        self,
        prompt: str,
        image: Optional[bytes] = None,
        image_mime_type: str = "image/jpeg",
        system_instruction: Optional[str] = None,
        thinking_level: Optional[str] = None,
        temperature: Optional[float] = None,
        model: Optional[str] = None,
        async_: bool = False,
        request_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Send a prompt to the LLM via local LLM service.

        Args:
            prompt: Text prompt for the LLM
            image: Optional image bytes for multimodal input
            image_mime_type: MIME type of image (default: image/jpeg)
            system_instruction: Optional system instruction
            thinking_level: Optional thinking level hint
            temperature: Optional temperature parameter
            model: Optional model override
            async_: Run asynchronously (not currently supported)
            request_id: ID for async result tracking (not currently supported)

        Returns:
            Dict with 'success', 'content', 'tokens', and optionally 'error'
        """
        from .llm_service import call_llm_service

        payload: Dict[str, Any] = {"prompt": prompt}

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

        if async_ or request_id is not None:
            payload["async"] = False  # Not currently supported

        result = call_llm_service(payload)

        # Report LLM usage to kernel if connected
        if self._transport.connected and result.get("success"):
            tokens = int(result.get("tokens", 0) or 0)
            report = {"tokens": tokens, "success": True}
            try:
                self._transport.call_json(SyscallOp.SYS_LLM_REPORT, report)
            except Exception:
                pass  # Don't fail if reporting fails

        return result

    def exit(self) -> bool:
        """Request graceful exit.

        Returns:
            True if exit request was sent successfully
        """
        try:
            self._transport.call(SyscallOp.SYS_EXIT)
            return True
        except Exception:
            return False

    # Low-level methods for backwards compatibility

    def send(self, opcode: SyscallOp, payload: bytes | str = b'') -> bool:
        """Send a message to the kernel (low-level).

        Args:
            opcode: Syscall operation code
            payload: Message payload

        Returns:
            True if sent successfully
        """
        try:
            self._transport.send(opcode, payload)
            return True
        except Exception:
            return False

    def recv(self) -> Optional[Message]:
        """Receive a message from the kernel (low-level).

        Returns:
            Received Message or None on failure
        """
        try:
            return self._transport.recv()
        except Exception:
            return None

    def call(self, opcode: SyscallOp, payload: bytes | str = b'') -> Optional[Message]:
        """Send a message and wait for response (low-level).

        Args:
            opcode: Syscall operation code
            payload: Message payload

        Returns:
            Response Message or None on failure
        """
        try:
            return self._transport.call(opcode, payload)
        except Exception:
            return None

    def __enter__(self) -> 'CloveClient':
        """Context manager entry - connect to kernel."""
        self._transport.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - disconnect from kernel."""
        self._transport.disconnect()


# Backwards compatibility alias
AgentOSClient = CloveClient


def connect(socket_path: str = DEFAULT_SOCKET_PATH) -> CloveClient:
    """Create and connect a client.

    Args:
        socket_path: Path to kernel Unix domain socket

    Returns:
        Connected CloveClient instance

    Raises:
        ConnectionError: If connection fails
    """
    client = CloveClient(socket_path)
    client._transport.connect()
    return client
