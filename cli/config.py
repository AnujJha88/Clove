#!/usr/bin/env python3
"""
Clove CLI Configuration Management

Manages ~/.clove/config.yaml and provides access to configuration values.
"""

import os
import yaml
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any


DEFAULT_CONFIG_DIR = Path.home() / '.clove'
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / 'config.yaml'


@dataclass
class Config:
    """Clove CLI Configuration"""

    # Relay server settings
    relay_url: str = "ws://localhost:8765"
    relay_api_url: str = "http://localhost:8766"

    # AWS settings
    aws_region: str = "us-east-1"
    aws_instance_type: str = "t3.micro"
    aws_ami_id: str = ""  # Auto-detect if empty

    # GCP settings
    gcp_project: str = ""
    gcp_zone: str = "us-central1-a"
    gcp_machine_type: str = "n1-standard-1"

    # Docker settings
    docker_image: str = "clove/kernel:latest"
    docker_network: str = "clove-network"

    # SSH settings
    ssh_key_path: str = str(Path.home() / '.ssh' / 'clove.pem')

    # General settings
    default_instance_type: str = "small"  # small, medium, large

    # Authentication
    api_token: str = ""

    # Machine registry (local cache)
    machines: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Config file path (not saved to file)
    config_path: str = field(default="", repr=False)

    def save(self):
        """Save configuration to file."""
        config_path = Path(self.config_path) if self.config_path else DEFAULT_CONFIG_FILE
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert to dict and remove non-persistent fields
        data = asdict(self)
        del data['config_path']

        with open(config_path, 'w') as f:
            yaml.safe_dump(data, f, default_flow_style=False)

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> 'Config':
        """Load configuration from file."""
        path = Path(config_path) if config_path else DEFAULT_CONFIG_FILE

        if not path.exists():
            # Return default config
            cfg = cls()
            cfg.config_path = str(path)
            return cfg

        with open(path) as f:
            data = yaml.safe_load(f) or {}

        # Create config with loaded data
        cfg = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        cfg.config_path = str(path)
        return cfg

    def add_machine(self, machine_id: str, info: Dict[str, Any]):
        """Add a machine to local registry."""
        self.machines[machine_id] = info
        self.save()

    def remove_machine(self, machine_id: str) -> bool:
        """Remove a machine from local registry."""
        if machine_id in self.machines:
            del self.machines[machine_id]
            self.save()
            return True
        return False

    def get_machine(self, machine_id: str) -> Optional[Dict[str, Any]]:
        """Get machine info from local registry."""
        return self.machines.get(machine_id)

    def list_machines(self) -> Dict[str, Dict[str, Any]]:
        """List all machines in local registry."""
        return self.machines


# Singleton instance
_config: Optional[Config] = None


def get_config(config_path: Optional[str] = None) -> Config:
    """Get or create the global config instance."""
    global _config
    if _config is None or (config_path and config_path != _config.config_path):
        _config = Config.load(config_path)
    return _config


def ensure_config_dir():
    """Ensure the config directory exists."""
    DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # Create tokens directory
    tokens_dir = DEFAULT_CONFIG_DIR / 'tokens'
    tokens_dir.mkdir(exist_ok=True)

    return DEFAULT_CONFIG_DIR
