"""IPC (Inter-Process Communication) syscalls.

Provides agent-to-agent messaging: send, receive, broadcast, register.
"""

from typing import Optional, Dict, Any, List, TYPE_CHECKING

from ..protocol import SyscallOp
from ..models import (
    IPCMessage,
    SendResult,
    RecvResult,
    BroadcastResult,
    RegisterResult,
)

if TYPE_CHECKING:
    from ..transport import Transport


class IPCMixin:
    """Mixin for inter-agent communication.

    Requires _transport attribute of type Transport.
    """

    _transport: 'Transport'

    def register_name(self, name: str) -> RegisterResult:
        """Register this agent with a name for IPC.

        Other agents can then send messages using this name.

        Args:
            name: Unique name to register

        Returns:
            RegisterResult with success status
        """
        result = self._transport.call_json(
            SyscallOp.SYS_REGISTER,
            {"name": name}
        )

        return RegisterResult(
            success=result.get("success", False),
            error=result.get("error")
        )

    def register(self, name: str) -> RegisterResult:
        """Alias for register_name."""
        return self.register_name(name)

    def send_message(
        self,
        message: Dict[str, Any],
        to: Optional[int] = None,
        to_name: Optional[str] = None
    ) -> SendResult:
        """Send a message to another agent.

        Args:
            message: Message payload (dict)
            to: Target agent ID (mutually exclusive with to_name)
            to_name: Target agent name (mutually exclusive with to)

        Returns:
            SendResult with delivery status
        """
        payload: Dict[str, Any] = {"message": message}

        if to is not None:
            payload["to"] = to
        if to_name is not None:
            payload["to_name"] = to_name

        result = self._transport.call_json(SyscallOp.SYS_SEND, payload)

        # Kernel returns "delivered_to" (agent ID), not "delivered" (bool)
        # If success is true and delivered_to is set, delivery succeeded
        delivered_to = result.get("delivered_to")
        delivered = result.get("delivered", delivered_to is not None and delivered_to > 0)

        return SendResult(
            success=result.get("success", False),
            delivered=delivered,
            error=result.get("error")
        )

    def recv_messages(self, max_messages: int = 10) -> RecvResult:
        """Receive pending messages from other agents.

        Args:
            max_messages: Maximum number of messages to retrieve

        Returns:
            RecvResult with list of messages
        """
        import time

        result = self._transport.call_json(
            SyscallOp.SYS_RECV,
            {"max": max_messages}
        )

        messages: List[IPCMessage] = []
        now = time.time()
        for msg_data in result.get("messages", []):
            # Kernel returns "age_ms", SDK uses "timestamp"
            # Convert age_ms to approximate timestamp
            age_ms = msg_data.get("age_ms", 0)
            timestamp = msg_data.get("timestamp", now - (age_ms / 1000.0))

            messages.append(IPCMessage(
                from_agent=msg_data.get("from", 0),
                from_name=msg_data.get("from_name"),
                message=msg_data.get("message", {}),
                timestamp=timestamp
            ))

        return RecvResult(
            success=result.get("success", False),
            messages=messages,
            count=result.get("count", len(messages)),
            error=result.get("error")
        )

    def broadcast(
        self,
        message: Dict[str, Any],
        include_self: bool = False
    ) -> BroadcastResult:
        """Broadcast a message to all registered agents.

        Args:
            message: Message payload (dict)
            include_self: Include self in broadcast recipients

        Returns:
            BroadcastResult with delivery count
        """
        payload = {
            "message": message,
            "include_self": include_self
        }

        result = self._transport.call_json(SyscallOp.SYS_BROADCAST, payload)

        return BroadcastResult(
            success=result.get("success", False),
            delivered_count=result.get("delivered_count", 0),
            error=result.get("error")
        )
