"""Events (Pub/Sub) syscalls.

Provides event subscription, polling, and emission.
"""

from typing import List, Dict, Any, Optional, TYPE_CHECKING

from ..protocol import SyscallOp
from ..models import (
    KernelEvent,
    SubscribeResult,
    PollEventsResult,
    EmitResult,
    AsyncResult,
    PollAsyncResult,
    PermissionsInfo,
    HttpResult,
)

if TYPE_CHECKING:
    from ..transport import Transport


class EventsMixin:
    """Mixin for event pub/sub and async operations.

    Requires _transport attribute of type Transport.
    """

    _transport: 'Transport'

    def subscribe(self, event_types: List[str]) -> SubscribeResult:
        """Subscribe to kernel events.

        Args:
            event_types: List of event types to subscribe to

        Returns:
            SubscribeResult with subscribed event types
        """
        result = self._transport.call_json(
            SyscallOp.SYS_SUBSCRIBE,
            {"event_types": event_types}
        )

        return SubscribeResult(
            success=result.get("success", False),
            subscribed=result.get("subscribed", []),
            error=result.get("error")
        )

    def unsubscribe(self, event_types: List[str]) -> SubscribeResult:
        """Unsubscribe from kernel events.

        Args:
            event_types: List of event types to unsubscribe from

        Returns:
            SubscribeResult with remaining subscriptions
        """
        result = self._transport.call_json(
            SyscallOp.SYS_UNSUBSCRIBE,
            {"event_types": event_types}
        )

        return SubscribeResult(
            success=result.get("success", False),
            subscribed=result.get("subscribed", []),
            error=result.get("error")
        )

    def poll_events(self, max_events: int = 10) -> PollEventsResult:
        """Poll for pending events.

        Args:
            max_events: Maximum number of events to retrieve

        Returns:
            PollEventsResult with list of events
        """
        result = self._transport.call_json(
            SyscallOp.SYS_POLL_EVENTS,
            {"max": max_events}
        )

        events: List[KernelEvent] = []
        for evt_data in result.get("events", []):
            events.append(KernelEvent(
                event_type=evt_data.get("event_type", ""),
                data=evt_data.get("data", {}),
                timestamp=evt_data.get("timestamp", 0.0),
                source_agent=evt_data.get("source_agent")
            ))

        return PollEventsResult(
            success=result.get("success", False),
            events=events,
            count=result.get("count", len(events)),
            error=result.get("error")
        )

    def emit_event(
        self,
        event_type: str,
        data: Optional[Dict[str, Any]] = None
    ) -> EmitResult:
        """Emit a custom event to all subscribers.

        Args:
            event_type: Type of event to emit
            data: Event payload data

        Returns:
            EmitResult with delivery count
        """
        payload = {
            "event_type": event_type,
            "data": data or {}
        }

        result = self._transport.call_json(SyscallOp.SYS_EMIT, payload)

        return EmitResult(
            success=result.get("success", False),
            delivered_to=result.get("delivered_to", 0),
            error=result.get("error")
        )

    def poll_async(self, max_results: int = 10) -> PollAsyncResult:
        """Poll for completed async syscall results.

        Args:
            max_results: Maximum number of results to retrieve

        Returns:
            PollAsyncResult with list of async results
        """
        result = self._transport.call_json(
            SyscallOp.SYS_ASYNC_POLL,
            {"max": max_results}
        )

        results: List[AsyncResult] = []
        for res_data in result.get("results", []):
            results.append(AsyncResult(
                request_id=res_data.get("request_id", 0),
                opcode=res_data.get("opcode", 0),
                success=res_data.get("success", False),
                result=res_data.get("result", {}),
                error=res_data.get("error")
            ))

        return PollAsyncResult(
            success=result.get("success", False),
            results=results,
            count=result.get("count", len(results)),
            error=result.get("error")
        )

    # Permissions methods (related to events/access)

    def get_permissions(self) -> PermissionsInfo:
        """Get this agent's permissions.

        Returns:
            PermissionsInfo with current permissions
        """
        result = self._transport.call_json(SyscallOp.SYS_GET_PERMS, {})

        return PermissionsInfo(
            success=result.get("success", False),
            level=result.get("level"),
            paths=result.get("paths", []),
            commands=result.get("commands", []),
            domains=result.get("domains", []),
            error=result.get("error")
        )

    def set_permissions(
        self,
        permissions: Optional[Dict[str, Any]] = None,
        level: Optional[str] = None,
        agent_id: Optional[int] = None
    ) -> PermissionsInfo:
        """Set agent permissions.

        Args:
            permissions: Permissions dict with paths, commands, domains
            level: Permission level preset
            agent_id: Target agent ID (for setting other agents' permissions)

        Returns:
            PermissionsInfo with updated permissions
        """
        payload: Dict[str, Any] = {}
        if permissions:
            payload["permissions"] = permissions
        if level:
            payload["level"] = level
        if agent_id is not None:
            payload["agent_id"] = agent_id

        result = self._transport.call_json(SyscallOp.SYS_SET_PERMS, payload)

        return PermissionsInfo(
            success=result.get("success", False),
            level=result.get("level"),
            paths=result.get("paths", []),
            commands=result.get("commands", []),
            domains=result.get("domains", []),
            error=result.get("error")
        )

    # HTTP (network syscall, fits here as it's event-like async)

    def http(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        body: Optional[str] = None,
        timeout: int = 30,
        async_: bool = False,
        request_id: Optional[int] = None
    ) -> HttpResult:
        """Make an HTTP request.

        Args:
            url: Request URL
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            headers: Request headers
            body: Request body
            timeout: Timeout in seconds
            async_: Run asynchronously (poll with poll_async)
            request_id: ID for async result tracking

        Returns:
            HttpResult with response data
        """
        payload: Dict[str, Any] = {
            "url": url,
            "method": method,
            "timeout": timeout,
            "async": async_
        }
        if headers:
            payload["headers"] = headers
        if body:
            payload["body"] = body
        if request_id is not None:
            payload["request_id"] = request_id

        result = self._transport.call_json(SyscallOp.SYS_HTTP, payload)

        return HttpResult(
            success=result.get("success", False),
            status_code=result.get("status_code", 0),
            body=result.get("body", ""),
            headers=result.get("headers", {}),
            error=result.get("error"),
            async_request_id=result.get("request_id")
        )
