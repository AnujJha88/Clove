"""World simulation syscalls.

Provides world creation, management, chaos injection, and snapshots.
"""

from typing import Optional, Dict, Any, TYPE_CHECKING

from ..protocol import SyscallOp
from ..models import (
    WorldInfo,
    WorldCreateResult,
    WorldListResult,
    WorldState,
    WorldSnapshot,
    OperationResult,
)

if TYPE_CHECKING:
    from ..transport import Transport


class WorldMixin:
    """Mixin for world simulation operations.

    Requires _transport attribute of type Transport.
    """

    _transport: 'Transport'

    def world_create(
        self,
        name: str,
        config: Optional[Dict[str, Any]] = None
    ) -> WorldCreateResult:
        """Create a new simulated world.

        Args:
            name: World name
            config: World configuration dict

        Returns:
            WorldCreateResult with world_id on success
        """
        payload = {
            "name": name,
            "config": config or {}
        }

        result = self._transport.call_json(SyscallOp.SYS_WORLD_CREATE, payload)

        return WorldCreateResult(
            success=result.get("success", False),
            world_id=result.get("world_id"),
            error=result.get("error")
        )

    def world_destroy(self, world_id: str, force: bool = False) -> OperationResult:
        """Destroy a world.

        Args:
            world_id: World ID to destroy
            force: Force destruction even if agents are attached

        Returns:
            OperationResult with success status
        """
        payload = {
            "world_id": world_id,
            "force": force
        }

        result = self._transport.call_json(SyscallOp.SYS_WORLD_DESTROY, payload)

        return OperationResult(
            success=result.get("success", False),
            error=result.get("error")
        )

    def world_list(self) -> WorldListResult:
        """List all active worlds.

        Returns:
            WorldListResult with list of worlds
        """
        result = self._transport.call_json(SyscallOp.SYS_WORLD_LIST, {})

        worlds = []
        for world_data in result.get("worlds", []):
            worlds.append(WorldInfo(
                id=world_data.get("id", ""),
                name=world_data.get("name", ""),
                agent_count=world_data.get("agent_count", 0),
                created_at=world_data.get("created_at", 0.0)
            ))

        return WorldListResult(
            success=result.get("success", False),
            worlds=worlds,
            count=result.get("count", len(worlds)),
            error=result.get("error")
        )

    def world_join(self, world_id: str) -> OperationResult:
        """Join a world.

        Args:
            world_id: World ID to join

        Returns:
            OperationResult with success status
        """
        result = self._transport.call_json(
            SyscallOp.SYS_WORLD_JOIN,
            {"world_id": world_id}
        )

        return OperationResult(
            success=result.get("success", False),
            error=result.get("error")
        )

    def world_leave(self) -> OperationResult:
        """Leave the current world.

        Returns:
            OperationResult with success status
        """
        result = self._transport.call_json(SyscallOp.SYS_WORLD_LEAVE, {})

        return OperationResult(
            success=result.get("success", False),
            error=result.get("error")
        )

    def world_event(
        self,
        world_id: str,
        event_type: str,
        params: Optional[Dict[str, Any]] = None
    ) -> OperationResult:
        """Inject a chaos event into a world.

        Args:
            world_id: Target world ID
            event_type: Type of chaos event
            params: Event parameters

        Returns:
            OperationResult with success status
        """
        payload = {
            "world_id": world_id,
            "event_type": event_type,
            "params": params or {}
        }

        result = self._transport.call_json(SyscallOp.SYS_WORLD_EVENT, payload)

        return OperationResult(
            success=result.get("success", False),
            error=result.get("error")
        )

    def world_state(self, world_id: str) -> WorldState:
        """Get the current state and metrics of a world.

        Args:
            world_id: World ID to query

        Returns:
            WorldState with current world info
        """
        result = self._transport.call_json(
            SyscallOp.SYS_WORLD_STATE,
            {"world_id": world_id}
        )

        return WorldState(
            success=result.get("success", False),
            id=result.get("id", world_id),
            name=result.get("name", ""),
            agents=result.get("agents", []),
            metrics=result.get("metrics", {}),
            chaos_events_injected=result.get("chaos_events_injected", 0),
            error=result.get("error")
        )

    def world_snapshot(self, world_id: str) -> WorldSnapshot:
        """Create a snapshot of a world's state.

        Args:
            world_id: World ID to snapshot

        Returns:
            WorldSnapshot with snapshot data
        """
        result = self._transport.call_json(
            SyscallOp.SYS_WORLD_SNAPSHOT,
            {"world_id": world_id}
        )

        return WorldSnapshot(
            success=result.get("success", False),
            snapshot_id=result.get("snapshot_id"),
            snapshot_data=result.get("snapshot_data"),
            error=result.get("error")
        )

    def world_restore(
        self,
        snapshot: Dict[str, Any],
        new_world_id: Optional[str] = None
    ) -> WorldCreateResult:
        """Restore a world from a snapshot.

        Args:
            snapshot: Snapshot data dict
            new_world_id: Optional new world ID (generates if not provided)

        Returns:
            WorldCreateResult with restored world ID
        """
        payload = {
            "snapshot": snapshot,
            "new_world_id": new_world_id or ""
        }

        result = self._transport.call_json(SyscallOp.SYS_WORLD_RESTORE, payload)

        return WorldCreateResult(
            success=result.get("success", False),
            world_id=result.get("world_id"),
            error=result.get("error")
        )
