"""Shared utilities for all CLOVE demos.

Provides common helpers for configuration, logging, SDK path management,
and inter-agent communication.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from clove_sdk import CloveClient


def repo_root() -> Path:
    """Get the CLOVE repository root directory."""
    return Path(__file__).resolve().parents[2]


def demos_root() -> Path:
    """Get the demos directory root."""
    return Path(__file__).resolve().parent.parent


def ensure_sdk_on_path() -> None:
    """Add the Python SDK to sys.path if not already present."""
    sdk_path = repo_root() / "agents" / "python_sdk"
    if sdk_path.exists() and str(sdk_path) not in sys.path:
        sys.path.insert(0, str(sdk_path))


def load_config(path: Path) -> Dict[str, Any]:
    """Load configuration from YAML or JSON file.

    Args:
        path: Path to config file (.yaml, .yml, or .json)

    Returns:
        Configuration dictionary, empty dict if file doesn't exist or parse fails
    """
    if not path.exists():
        return {}

    suffix = path.suffix.lower()
    raw = path.read_text()

    if suffix in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError:
            print("Warning: PyYAML not installed, cannot load YAML config", file=sys.stderr)
            return {}
        try:
            data = yaml.safe_load(raw) or {}
            return data if isinstance(data, dict) else {"value": data}
        except yaml.YAMLError:
            return {}

    if suffix == ".json":
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {"value": data}
        except json.JSONDecodeError:
            return {}

    return {}


def write_json(path: Path, data: Dict[str, Any], indent: int = 2) -> None:
    """Write data to JSON file, creating parent directories if needed.

    Args:
        path: Output file path
        data: Data to serialize
        indent: JSON indentation level
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=indent, sort_keys=True))


def read_json(path: Path) -> Dict[str, Any]:
    """Read JSON file, returning empty dict if not found or invalid.

    Args:
        path: Path to JSON file

    Returns:
        Parsed JSON data or empty dict
    """
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def log_line(log_path: Path, message: str) -> None:
    """Append a timestamped log line to a file.

    Args:
        log_path: Path to log file
        message: Message to log
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {message}\n")


def log(agent: str, level: str, msg: str) -> None:
    """Print a structured log message to stderr.

    Args:
        agent: Agent/component name
        level: Log level (INFO, WARNING, ERROR, etc.)
        msg: Log message
    """
    ts = datetime.now().isoformat(timespec='milliseconds')
    print(f"{ts} [{agent}] {level}: {msg}", file=sys.stderr, flush=True)


def normalize_limits(limits: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize resource limits to kernel-expected format.

    Converts human-friendly values (memory_mb, cpu) to kernel values
    (memory in bytes, cpu_quota in microseconds).

    Args:
        limits: Dict with memory_mb, cpu, etc.

    Returns:
        Normalized limits dict with memory, cpu_quota, etc.
    """
    normalized = dict(limits) if limits else {}

    if "memory_mb" in normalized:
        memory_mb = int(normalized["memory_mb"])
        if memory_mb <= 0 or memory_mb > 16384:
            raise ValueError(f"Invalid memory_mb: {memory_mb} (must be 1-16384)")
        if "memory" not in normalized:
            normalized["memory"] = memory_mb * 1024 * 1024

    if "cpu" in normalized:
        cpu = int(normalized["cpu"])
        if cpu <= 0 or cpu > 128:
            raise ValueError(f"Invalid cpu: {cpu} (must be 1-128)")
        if "cpu_quota" not in normalized:
            normalized["cpu_quota"] = cpu * 100000

    return normalized


# Message buffer for wait_for_message (keyed by client id)
_message_buffers: Dict[int, List[Dict[str, Any]]] = {}


def wait_for_message(
    client: "CloveClient",
    poll_interval: float = 0.2,
    expected_type: Optional[str] = None,
    expected_stage: Optional[str] = None,
    timeout_s: float = 30.0,
) -> Dict[str, Any]:
    """Wait for a message from the kernel, with optional filtering.

    Args:
        client: CloveClient instance
        poll_interval: Seconds between poll attempts
        expected_type: Only return messages with this "type" field
        expected_stage: Only return messages with this "stage" field
        timeout_s: Maximum seconds to wait

    Returns:
        Message payload dict

    Raises:
        TimeoutError: If no matching message within timeout
    """
    client_id = id(client)
    if client_id not in _message_buffers:
        _message_buffers[client_id] = []

    buffer = _message_buffers[client_id]
    deadline = time.time() + timeout_s

    def matches(payload: Dict[str, Any]) -> bool:
        if expected_type and payload.get("type") != expected_type:
            return False
        if expected_stage and payload.get("stage") != expected_stage:
            return False
        return True

    while time.time() < deadline:
        # Check buffer first
        for i, payload in enumerate(buffer):
            if matches(payload):
                buffer.pop(i)
                return payload

        # Poll for new messages
        result = client.recv_messages()
        for msg in result.messages if hasattr(result, 'messages') else result.get("messages", []):
            payload = msg.message if hasattr(msg, 'message') else msg.get("message", {})
            if payload:
                buffer.append(payload)

        # Check buffer again after receiving
        for i, payload in enumerate(buffer):
            if matches(payload):
                buffer.pop(i)
                return payload

        time.sleep(poll_interval)

    raise TimeoutError(
        f"No message received within {timeout_s}s "
        f"(expected_type={expected_type}, expected_stage={expected_stage})"
    )


def clear_message_buffer(client: "CloveClient") -> None:
    """Clear the message buffer for a client.

    Args:
        client: CloveClient instance
    """
    client_id = id(client)
    if client_id in _message_buffers:
        _message_buffers[client_id].clear()
