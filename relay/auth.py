#!/usr/bin/env python3
"""
AgentOS Relay Server - Authentication Module

Handles token validation and machine/agent registry.
"""

import os
import secrets
import hashlib
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Set
from datetime import datetime


@dataclass
class MachineInfo:
    """Information about a registered machine (kernel)"""
    machine_id: str
    token_hash: str  # SHA-256 hash of the token
    registered_at: datetime = field(default_factory=datetime.now)
    last_seen: Optional[datetime] = None
    allowed_agents: Set[str] = field(default_factory=set)  # Agent names allowed to connect
    metadata: Dict = field(default_factory=dict)


@dataclass
class AgentToken:
    """Token for remote agent authentication"""
    token_hash: str
    agent_name: str
    target_machine: str  # Machine ID this agent can connect to
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    permissions: Dict = field(default_factory=dict)


class AuthManager:
    """Manages authentication for kernels and remote agents"""

    def __init__(self):
        # machine_id -> MachineInfo
        self.machines: Dict[str, MachineInfo] = {}
        # token_hash -> AgentToken
        self.agent_tokens: Dict[str, AgentToken] = {}
        # Load from environment or config
        self._load_config()

    def _load_config(self):
        """Load machine tokens from environment variables"""
        # Format: MACHINE_TOKEN_<machine_id>=<token>
        for key, value in os.environ.items():
            if key.startswith("MACHINE_TOKEN_"):
                machine_id = key[14:].lower()  # Remove prefix and lowercase
                self.register_machine(machine_id, value)

    def _hash_token(self, token: str) -> str:
        """Hash a token using SHA-256"""
        return hashlib.sha256(token.encode()).hexdigest()

    def register_machine(self, machine_id: str, token: str,
                        allowed_agents: Set[str] = None, metadata: Dict = None) -> bool:
        """Register a machine with its token"""
        token_hash = self._hash_token(token)
        self.machines[machine_id] = MachineInfo(
            machine_id=machine_id,
            token_hash=token_hash,
            allowed_agents=allowed_agents or set(),
            metadata=metadata or {}
        )
        return True

    def validate_machine(self, machine_id: str, token: str) -> bool:
        """Validate machine credentials"""
        if machine_id not in self.machines:
            # In development mode, auto-register machines
            if os.environ.get("RELAY_DEV_MODE", "").lower() == "true":
                self.register_machine(machine_id, token)
                return True
            return False

        machine = self.machines[machine_id]
        token_hash = self._hash_token(token)

        if machine.token_hash == token_hash:
            machine.last_seen = datetime.now()
            return True
        return False

    def create_agent_token(self, agent_name: str, target_machine: str,
                          expires_in_hours: int = 24) -> str:
        """Create a new agent token"""
        token = secrets.token_urlsafe(32)
        token_hash = self._hash_token(token)

        expires_at = None
        if expires_in_hours > 0:
            expires_at = datetime.fromtimestamp(
                time.time() + expires_in_hours * 3600
            )

        self.agent_tokens[token_hash] = AgentToken(
            token_hash=token_hash,
            agent_name=agent_name,
            target_machine=target_machine,
            expires_at=expires_at
        )

        return token

    def validate_agent_token(self, token: str, target_machine: str) -> Optional[AgentToken]:
        """Validate an agent token and check if it can connect to target machine"""
        token_hash = self._hash_token(token)

        if token_hash not in self.agent_tokens:
            # In development mode, allow any token
            if os.environ.get("RELAY_DEV_MODE", "").lower() == "true":
                return AgentToken(
                    token_hash=token_hash,
                    agent_name="dev-agent",
                    target_machine=target_machine
                )
            return None

        agent_token = self.agent_tokens[token_hash]

        # Check expiration
        if agent_token.expires_at and datetime.now() > agent_token.expires_at:
            del self.agent_tokens[token_hash]
            return None

        # Check target machine
        if agent_token.target_machine != "*" and agent_token.target_machine != target_machine:
            return None

        return agent_token

    def is_agent_allowed(self, machine_id: str, agent_name: str) -> bool:
        """Check if an agent is allowed to connect to a machine"""
        if machine_id not in self.machines:
            return False

        machine = self.machines[machine_id]

        # Empty set means all agents are allowed
        if not machine.allowed_agents:
            return True

        return agent_name in machine.allowed_agents

    def revoke_agent_token(self, token: str) -> bool:
        """Revoke an agent token"""
        token_hash = self._hash_token(token)
        if token_hash in self.agent_tokens:
            del self.agent_tokens[token_hash]
            return True
        return False

    def get_machine_info(self, machine_id: str) -> Optional[MachineInfo]:
        """Get information about a machine"""
        return self.machines.get(machine_id)

    def list_machines(self) -> Dict[str, Dict]:
        """List all registered machines (without sensitive info)"""
        return {
            mid: {
                "machine_id": m.machine_id,
                "registered_at": m.registered_at.isoformat(),
                "last_seen": m.last_seen.isoformat() if m.last_seen else None,
                "metadata": m.metadata
            }
            for mid, m in self.machines.items()
        }


# Singleton instance
_auth_manager: Optional[AuthManager] = None


def get_auth_manager() -> AuthManager:
    """Get the global auth manager instance"""
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = AuthManager()
    return _auth_manager
