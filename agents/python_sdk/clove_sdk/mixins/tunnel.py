"""Tunnel (remote connectivity) syscalls.

Provides relay server connection and remote agent management.
"""

from typing import Optional, TYPE_CHECKING

from ..protocol import SyscallOp
from ..models import TunnelStatus, TunnelRemotesResult, OperationResult

if TYPE_CHECKING:
    from ..transport import Transport


class TunnelMixin:
    """Mixin for tunnel/relay operations.

    Requires _transport attribute of type Transport.
    """

    _transport: 'Transport'

    def tunnel_connect(
        self,
        relay_url: str,
        machine_id: Optional[str] = None,
        token: Optional[str] = None
    ) -> TunnelStatus:
        """Connect the kernel to a relay server for remote agent access.

        Args:
            relay_url: WebSocket URL of relay server
            machine_id: Optional machine identifier
            token: Authentication token

        Returns:
            TunnelStatus with connection info
        """
        payload = {"relay_url": relay_url}
        if machine_id:
            payload["machine_id"] = machine_id
        if token:
            payload["token"] = token

        result = self._transport.call_json(SyscallOp.SYS_TUNNEL_CONNECT, payload)

        return TunnelStatus(
            success=result.get("success", False),
            connected=result.get("connected", False),
            relay_url=result.get("relay_url"),
            machine_id=result.get("machine_id"),
            latency_ms=result.get("latency_ms"),
            connected_since=result.get("connected_since"),
            error=result.get("error")
        )

    def tunnel_disconnect(self) -> OperationResult:
        """Disconnect the kernel from the relay server.

        Returns:
            OperationResult with success status
        """
        result = self._transport.call_json(SyscallOp.SYS_TUNNEL_DISCONNECT, {})

        return OperationResult(
            success=result.get("success", False),
            error=result.get("error")
        )

    def tunnel_status(self) -> TunnelStatus:
        """Get the current tunnel connection status.

        Returns:
            TunnelStatus with connection info
        """
        result = self._transport.call_json(SyscallOp.SYS_TUNNEL_STATUS, {})

        return TunnelStatus(
            success=result.get("success", False),
            connected=result.get("connected", False),
            relay_url=result.get("relay_url"),
            machine_id=result.get("machine_id"),
            latency_ms=result.get("latency_ms"),
            connected_since=result.get("connected_since"),
            error=result.get("error")
        )

    def tunnel_list_remotes(self) -> TunnelRemotesResult:
        """List remote agents currently connected through the tunnel.

        Returns:
            TunnelRemotesResult with list of remote agents
        """
        result = self._transport.call_json(SyscallOp.SYS_TUNNEL_LIST_REMOTES, {})

        return TunnelRemotesResult(
            success=result.get("success", False),
            agents=result.get("agents", []),
            count=result.get("count", 0),
            error=result.get("error")
        )

    def tunnel_config(
        self,
        relay_url: Optional[str] = None,
        machine_id: Optional[str] = None,
        token: Optional[str] = None,
        reconnect_interval: Optional[int] = None
    ) -> TunnelStatus:
        """Configure tunnel settings without connecting.

        Args:
            relay_url: WebSocket URL of relay server
            machine_id: Machine identifier
            token: Authentication token
            reconnect_interval: Reconnect interval in seconds

        Returns:
            TunnelStatus with current config
        """
        payload = {}
        if relay_url:
            payload["relay_url"] = relay_url
        if machine_id:
            payload["machine_id"] = machine_id
        if token:
            payload["token"] = token
        if reconnect_interval is not None:
            payload["reconnect_interval"] = reconnect_interval

        result = self._transport.call_json(SyscallOp.SYS_TUNNEL_CONFIG, payload)

        return TunnelStatus(
            success=result.get("success", False),
            connected=result.get("connected", False),
            relay_url=result.get("relay_url"),
            machine_id=result.get("machine_id"),
            error=result.get("error")
        )
