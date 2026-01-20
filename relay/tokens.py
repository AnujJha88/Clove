#!/usr/bin/env python3
"""
AgentOS Relay Server - Token Persistence

Manages persistent storage of authentication tokens.
Provides secure token generation, storage, and validation.
"""

import json
import os
import secrets
import hashlib
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


# Default tokens data directory
TOKENS_DATA_DIR = Path(os.environ.get('TOKENS_DATA_DIR', '/var/lib/agentos/tokens'))


@dataclass
class TokenRecord:
    """Record of an authentication token."""
    id: str
    type: str  # machine, agent
    name: str
    token_hash: str  # SHA-256 hash of the token (never store plaintext)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    expires_at: Optional[str] = None
    revoked: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Type-specific fields
    machine_id: Optional[str] = None  # For machine tokens
    target_machine: Optional[str] = None  # For agent tokens

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_public_dict(self) -> Dict[str, Any]:
        """Return dict without sensitive fields."""
        d = self.to_dict()
        del d['token_hash']
        return d

    @classmethod
    def from_dict(cls, data: Dict) -> 'TokenRecord':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def is_expired(self) -> bool:
        """Check if token is expired."""
        if not self.expires_at:
            return False
        return datetime.now() > datetime.fromisoformat(self.expires_at)

    def is_valid(self) -> bool:
        """Check if token is valid (not revoked and not expired)."""
        return not self.revoked and not self.is_expired()


class TokenStore:
    """Persistent storage for authentication tokens."""

    def __init__(self, data_dir: Path = None):
        self.data_dir = data_dir or TOKENS_DATA_DIR
        self.tokens: Dict[str, TokenRecord] = {}
        self._load_state()

    def _hash_token(self, token: str) -> str:
        """Hash a token using SHA-256."""
        return hashlib.sha256(token.encode()).hexdigest()

    def _generate_token(self) -> str:
        """Generate a secure random token."""
        return secrets.token_urlsafe(32)

    def _generate_token_id(self) -> str:
        """Generate a unique token ID."""
        return secrets.token_hex(16)

    def _load_state(self):
        """Load tokens from disk."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        state_file = self.data_dir / 'tokens.json'

        if state_file.exists():
            try:
                with open(state_file) as f:
                    data = json.load(f)
                    for tid, tdata in data.get('tokens', {}).items():
                        self.tokens[tid] = TokenRecord.from_dict(tdata)
                logger.info(f"Loaded {len(self.tokens)} tokens from state")
            except Exception as e:
                logger.error(f"Failed to load token state: {e}")

    def _save_state(self):
        """Save tokens to disk."""
        state_file = self.data_dir / 'tokens.json'
        try:
            data = {
                'tokens': {tid: t.to_dict() for tid, t in self.tokens.items()},
                'updated_at': datetime.now().isoformat()
            }
            # Secure file permissions (owner read/write only)
            with open(state_file, 'w') as f:
                json.dump(data, f, indent=2)
            os.chmod(state_file, 0o600)
        except Exception as e:
            logger.error(f"Failed to save token state: {e}")

    def create_machine_token(self, machine_id: str, name: str = "") -> str:
        """Create a new machine token."""
        token = self._generate_token()
        token_id = self._generate_token_id()

        record = TokenRecord(
            id=token_id,
            type='machine',
            name=name or f'machine-{machine_id[:8]}',
            token_hash=self._hash_token(token),
            machine_id=machine_id
        )

        self.tokens[token_id] = record
        self._save_state()

        logger.info(f"Created machine token: {token_id} for {machine_id}")
        return token

    def store_agent_token(self, token: str, target_machine: str,
                         name: str = "", expires_hours: int = 24) -> str:
        """Store an agent token (created by auth manager)."""
        token_id = self._generate_token_id()

        expires_at = None
        if expires_hours > 0:
            expires_at = (datetime.now() + timedelta(hours=expires_hours)).isoformat()

        record = TokenRecord(
            id=token_id,
            type='agent',
            name=name or 'agent-token',
            token_hash=self._hash_token(token),
            target_machine=target_machine,
            expires_at=expires_at
        )

        self.tokens[token_id] = record
        self._save_state()

        logger.info(f"Stored agent token: {token_id} for {target_machine}")
        return token_id

    def validate_token(self, token: str) -> Optional[TokenRecord]:
        """Validate a token and return its record if valid."""
        token_hash = self._hash_token(token)

        for record in self.tokens.values():
            if record.token_hash == token_hash:
                if record.is_valid():
                    return record
                else:
                    logger.warning(f"Invalid token attempt: {record.id} "
                                  f"(revoked={record.revoked}, expired={record.is_expired()})")
                    return None

        return None

    def revoke_token(self, token_id: str) -> bool:
        """Revoke a token by ID."""
        if token_id not in self.tokens:
            return False

        self.tokens[token_id].revoked = True
        self._save_state()

        logger.info(f"Revoked token: {token_id}")
        return True

    def delete_token(self, token_id: str) -> bool:
        """Delete a token by ID."""
        if token_id not in self.tokens:
            return False

        del self.tokens[token_id]
        self._save_state()

        logger.info(f"Deleted token: {token_id}")
        return True

    def get_token(self, token_id: str) -> Optional[Dict[str, Any]]:
        """Get token info by ID (without the hash)."""
        record = self.tokens.get(token_id)
        return record.to_public_dict() if record else None

    def list_tokens(self) -> List[Dict[str, Any]]:
        """List all tokens (without sensitive data)."""
        return [t.to_public_dict() for t in self.tokens.values()]

    def list_machine_tokens(self) -> List[Dict[str, Any]]:
        """List all machine tokens."""
        return [
            t.to_public_dict() for t in self.tokens.values()
            if t.type == 'machine'
        ]

    def list_agent_tokens(self, target_machine: str = None) -> List[Dict[str, Any]]:
        """List agent tokens, optionally filtered by target machine."""
        tokens = [t for t in self.tokens.values() if t.type == 'agent']

        if target_machine:
            tokens = [t for t in tokens if t.target_machine == target_machine]

        return [t.to_public_dict() for t in tokens]

    def cleanup_expired(self) -> int:
        """Remove expired tokens. Returns count of removed tokens."""
        expired = [tid for tid, t in self.tokens.items() if t.is_expired()]

        for tid in expired:
            del self.tokens[tid]

        if expired:
            self._save_state()
            logger.info(f"Cleaned up {len(expired)} expired tokens")

        return len(expired)


# Singleton instance
_token_store: Optional[TokenStore] = None


def get_token_store(data_dir: Path = None) -> TokenStore:
    """Get or create the global token store instance."""
    global _token_store
    if _token_store is None:
        _token_store = TokenStore(data_dir)
    return _token_store
