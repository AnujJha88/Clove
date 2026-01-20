#!/usr/bin/env python3
"""
AgentOS Relay Server - Fleet Manager

Manages the fleet of deployed AgentOS kernels.
Tracks machine metadata, status, and deployment information.
"""

import json
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


# Default fleet data directory
FLEET_DATA_DIR = Path(os.environ.get('FLEET_DATA_DIR', '/var/lib/agentos/fleet'))


@dataclass
class MachineRecord:
    """Record of a deployed machine."""
    machine_id: str
    provider: str  # docker, aws, gcp, local
    ip_address: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_seen: Optional[str] = None
    status: str = "registered"  # registered, connected, disconnected, removed
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'MachineRecord':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class FleetManager:
    """Manages the fleet of AgentOS machines."""

    def __init__(self, data_dir: Path = None):
        self.data_dir = data_dir or FLEET_DATA_DIR
        self.machines: Dict[str, MachineRecord] = {}
        self._load_state()

    def _load_state(self):
        """Load fleet state from disk."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        state_file = self.data_dir / 'machines.json'

        if state_file.exists():
            try:
                with open(state_file) as f:
                    data = json.load(f)
                    for mid, mdata in data.get('machines', {}).items():
                        self.machines[mid] = MachineRecord.from_dict(mdata)
                logger.info(f"Loaded {len(self.machines)} machines from state")
            except Exception as e:
                logger.error(f"Failed to load fleet state: {e}")

    def _save_state(self):
        """Save fleet state to disk."""
        state_file = self.data_dir / 'machines.json'
        try:
            data = {
                'machines': {mid: m.to_dict() for mid, m in self.machines.items()},
                'updated_at': datetime.now().isoformat()
            }
            with open(state_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save fleet state: {e}")

    def register_machine(self, machine_id: str, provider: str,
                        ip_address: str = "", metadata: Dict = None) -> MachineRecord:
        """Register a new machine in the fleet."""
        if machine_id in self.machines:
            # Update existing machine
            machine = self.machines[machine_id]
            machine.provider = provider
            machine.ip_address = ip_address
            if metadata:
                machine.metadata.update(metadata)
            machine.status = "registered"
        else:
            # Create new machine record
            machine = MachineRecord(
                machine_id=machine_id,
                provider=provider,
                ip_address=ip_address,
                metadata=metadata or {}
            )
            self.machines[machine_id] = machine

        self._save_state()
        logger.info(f"Registered machine: {machine_id} ({provider})")
        return machine

    def remove_machine(self, machine_id: str) -> bool:
        """Remove a machine from the fleet."""
        if machine_id not in self.machines:
            return False

        del self.machines[machine_id]
        self._save_state()
        logger.info(f"Removed machine: {machine_id}")
        return True

    def get_machine(self, machine_id: str) -> Optional[Dict[str, Any]]:
        """Get machine information."""
        machine = self.machines.get(machine_id)
        return machine.to_dict() if machine else None

    def list_machines(self) -> Dict[str, Dict[str, Any]]:
        """List all machines."""
        return {mid: m.to_dict() for mid, m in self.machines.items()}

    def update_machine_status(self, machine_id: str, status: str):
        """Update machine status (connected/disconnected)."""
        if machine_id in self.machines:
            self.machines[machine_id].status = status
            self.machines[machine_id].last_seen = datetime.now().isoformat()
            self._save_state()

    def mark_connected(self, machine_id: str):
        """Mark a machine as connected."""
        self.update_machine_status(machine_id, "connected")

    def mark_disconnected(self, machine_id: str):
        """Mark a machine as disconnected."""
        self.update_machine_status(machine_id, "disconnected")

    def get_machines_by_provider(self, provider: str) -> List[Dict[str, Any]]:
        """Get machines filtered by provider."""
        return [
            m.to_dict() for m in self.machines.values()
            if m.provider == provider
        ]

    def get_connected_machines(self) -> List[Dict[str, Any]]:
        """Get all connected machines."""
        return [
            m.to_dict() for m in self.machines.values()
            if m.status == "connected"
        ]

    def get_summary(self) -> Dict[str, Any]:
        """Get fleet summary statistics."""
        by_provider = {}
        by_status = {}

        for m in self.machines.values():
            by_provider[m.provider] = by_provider.get(m.provider, 0) + 1
            by_status[m.status] = by_status.get(m.status, 0) + 1

        return {
            'total_machines': len(self.machines),
            'by_provider': by_provider,
            'by_status': by_status
        }


# Singleton instance
_fleet_manager: Optional[FleetManager] = None


def get_fleet_manager(data_dir: Path = None) -> FleetManager:
    """Get or create the global fleet manager instance."""
    global _fleet_manager
    if _fleet_manager is None:
        _fleet_manager = FleetManager(data_dir)
    return _fleet_manager
