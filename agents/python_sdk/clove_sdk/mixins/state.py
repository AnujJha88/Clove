"""State store syscalls.

Provides key-value storage: store, fetch, delete, list keys.
"""

from typing import Any, Optional, TYPE_CHECKING

from ..protocol import SyscallOp
from ..models import StoreResult, FetchResult, DeleteResult, KeysResult

if TYPE_CHECKING:
    from ..transport import Transport


class StateMixin:
    """Mixin for state store operations.

    Requires _transport attribute of type Transport.
    """

    _transport: 'Transport'

    def store(
        self,
        key: str,
        value: Any,
        scope: str = "global",
        ttl: Optional[int] = None
    ) -> StoreResult:
        """Store a key-value pair in the shared state store.

        Args:
            key: Storage key
            value: Value to store (must be JSON-serializable)
            scope: Storage scope - "global", "agent", or "session"
            ttl: Time-to-live in seconds (optional)

        Returns:
            StoreResult with success status
        """
        payload = {
            "key": key,
            "value": value,
            "scope": scope
        }
        if ttl is not None:
            payload["ttl"] = ttl

        result = self._transport.call_json(SyscallOp.SYS_STORE, payload)

        return StoreResult(
            success=result.get("success", False),
            error=result.get("error")
        )

    def fetch(self, key: str) -> FetchResult:
        """Fetch a value from the shared state store.

        Args:
            key: Storage key to fetch

        Returns:
            FetchResult with value if found
        """
        result = self._transport.call_json(
            SyscallOp.SYS_FETCH,
            {"key": key}
        )

        # Kernel returns "exists", SDK model uses "found"
        found = result.get("exists", result.get("found", False))

        return FetchResult(
            success=result.get("success", False),
            value=result.get("value"),
            found=found,
            error=result.get("error")
        )

    def delete_key(self, key: str) -> DeleteResult:
        """Delete a key from the shared state store.

        Args:
            key: Storage key to delete

        Returns:
            DeleteResult with deletion status
        """
        result = self._transport.call_json(
            SyscallOp.SYS_DELETE,
            {"key": key}
        )

        return DeleteResult(
            success=result.get("success", False),
            deleted=result.get("deleted", False),
            error=result.get("error")
        )

    def list_keys(self, prefix: str = "") -> KeysResult:
        """List keys in the shared state store.

        Args:
            prefix: Optional prefix to filter keys

        Returns:
            KeysResult with list of matching keys
        """
        payload = {"prefix": prefix} if prefix else {}

        result = self._transport.call_json(SyscallOp.SYS_KEYS, payload)

        return KeysResult(
            success=result.get("success", False),
            keys=result.get("keys", []),
            count=result.get("count", 0),
            error=result.get("error")
        )
