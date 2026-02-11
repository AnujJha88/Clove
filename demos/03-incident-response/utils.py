"""Shared helpers for the incident response lab service."""
from __future__ import annotations

import fcntl
import json
import os
import re
import select
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from clove_sdk import CloveClient


def lab_root() -> Path:
    return Path(__file__).resolve().parent


def repo_root() -> Path:
    return lab_root().parents[1]


def ensure_sdk_on_path() -> None:
    sdk_path = repo_root() / "agents" / "python_sdk"
    if sdk_path.exists() and str(sdk_path) not in sys.path:
        sys.path.insert(0, str(sdk_path))


def load_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    suffix = path.suffix.lower()
    raw = path.read_text()
    if suffix == ".json":
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {"value": data}
    return {}


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True))


def log_line(log_path: Path, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {message}\n")


def log(agent: str, level: str, msg: str) -> None:
    ts = datetime.now().isoformat(timespec='milliseconds')
    print(f"{ts} [{agent}] {level}: {msg}", file=sys.stderr, flush=True)


def validate_path_within(path: Path, base: Path) -> Path:
    resolved = path.resolve()
    base_resolved = base.resolve()
    if not str(resolved).startswith(str(base_resolved) + "/") and resolved != base_resolved:
        raise ValueError(f"Path {path} escapes base directory {base}")
    return resolved


def normalize_limits(limits: Dict[str, Any]) -> Dict[str, Any]:
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


_message_buffers: Dict[int, list] = {}


def wait_for_message(
    client: "CloveClient",
    poll_interval: float = 0.2,
    expected_type: str | None = None,
    timeout_s: float = 30.0,
) -> Dict[str, Any]:
    client_id = id(client)
    if client_id not in _message_buffers:
        _message_buffers[client_id] = []

    buffer = _message_buffers[client_id]
    deadline = time.time() + timeout_s

    while time.time() < deadline:
        for i, payload in enumerate(buffer):
            if expected_type is None or payload.get("type") == expected_type:
                buffer.pop(i)
                return payload

        result = client.recv_messages()
        for msg in result.get("messages", []):
            payload = msg.get("message", {})
            if not payload:
                continue
            buffer.append(payload)

        for i, payload in enumerate(buffer):
            if expected_type is None or payload.get("type") == expected_type:
                buffer.pop(i)
                return payload

        time.sleep(poll_interval)

    raise TimeoutError(f"No message received within {timeout_s}s (expected_type={expected_type})")


def check_sdk_result(result: dict, operation: str, agent: str = "agent") -> bool:
    if not result.get("success"):
        error = result.get("error", "unknown error")
        log(agent, "ERROR", f"SDK {operation} failed: {error}")
        return False
    return True


def safe_shell_arg(value: str) -> str:
    return shlex.quote(value)


def safe_py_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


# =============================================================================
# Log tailing utilities for real log monitoring
# =============================================================================

@dataclass
class LogEntry:
    """A single log entry from any source."""
    source: str
    line: str
    timestamp: float = field(default_factory=time.time)
    source_type: str = "file"  # "file", "journal", "custom"


class FileTailer:
    """Non-blocking tail of multiple log files with rotation detection."""

    def __init__(self, file_paths: List[str]):
        self.files: Dict[str, Dict[str, Any]] = {}
        for path in file_paths:
            self._open_file(path)

    def _open_file(self, path: str) -> bool:
        """Open a file for tailing, storing its inode for rotation detection."""
        try:
            if not os.path.exists(path):
                return False

            fh = open(path, "r", encoding="utf-8", errors="replace")
            # Seek to end for tail behavior
            fh.seek(0, os.SEEK_END)

            # Set non-blocking mode
            fd = fh.fileno()
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            stat = os.fstat(fd)
            self.files[path] = {
                "handle": fh,
                "inode": stat.st_ino,
                "path": path,
            }
            return True
        except (OSError, IOError):
            return False

    def _check_rotation(self, path: str) -> None:
        """Check if a file has been rotated and reopen if needed."""
        if path not in self.files:
            return

        info = self.files[path]
        try:
            current_stat = os.stat(path)
            if current_stat.st_ino != info["inode"]:
                # File was rotated, reopen
                info["handle"].close()
                del self.files[path]
                self._open_file(path)
        except (OSError, IOError):
            pass

    def poll(self, timeout_ms: int = 100) -> List[LogEntry]:
        """Poll all files for new lines (non-blocking)."""
        entries = []

        # Check for rotation periodically
        for path in list(self.files.keys()):
            self._check_rotation(path)

        if not self.files:
            return entries

        # Use select for efficient polling
        readable_fds = [info["handle"] for info in self.files.values()]
        try:
            readable, _, _ = select.select(readable_fds, [], [], timeout_ms / 1000.0)
        except (ValueError, OSError):
            readable = []

        for info in self.files.values():
            fh = info["handle"]
            if fh not in readable:
                continue

            try:
                while True:
                    line = fh.readline()
                    if not line:
                        break
                    line = line.rstrip("\n\r")
                    if line:
                        entries.append(LogEntry(
                            source=info["path"],
                            line=line,
                            source_type="file",
                        ))
            except (IOError, BlockingIOError):
                pass

        return entries

    def close(self) -> None:
        """Close all file handles."""
        for info in self.files.values():
            try:
                info["handle"].close()
            except (OSError, IOError):
                pass
        self.files.clear()


class JournalTailer:
    """Tail systemd journal using journalctl subprocess."""

    def __init__(self, config: Dict[str, Any]):
        self.enabled = config.get("enabled", True)
        self.units = config.get("units", [])
        self.priority = config.get("priority", "warning")
        self.process: Optional[subprocess.Popen] = None
        self._buffer = ""

        if self.enabled:
            self._start_journalctl()

    def _start_journalctl(self) -> bool:
        """Start journalctl subprocess for tailing."""
        try:
            cmd = [
                "journalctl",
                "--follow",
                "--no-pager",
                "--output=short-iso",
                f"--priority={self.priority}",
                "--since=now",
            ]

            # Add unit filters if specified
            for unit in self.units:
                cmd.extend(["--unit", unit])

            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )

            # Set non-blocking on stdout
            if self.process.stdout:
                fd = self.process.stdout.fileno()
                flags = fcntl.fcntl(fd, fcntl.F_GETFL)
                fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            return True
        except (OSError, FileNotFoundError):
            self.enabled = False
            return False

    def poll(self) -> List[LogEntry]:
        """Poll journalctl for new entries."""
        entries = []

        if not self.enabled or not self.process or not self.process.stdout:
            return entries

        # Check if process is still running
        if self.process.poll() is not None:
            self._start_journalctl()
            return entries

        try:
            while True:
                line = self.process.stdout.readline()
                if not line:
                    break
                line = line.rstrip("\n\r")
                if line and not line.startswith("-- "):  # Skip journal markers
                    entries.append(LogEntry(
                        source="journalctl",
                        line=line,
                        source_type="journal",
                    ))
        except (IOError, BlockingIOError):
            pass

        return entries

    def close(self) -> None:
        """Stop journalctl subprocess."""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                self.process.kill()
            self.process = None


class MultiSourceLogTailer:
    """Unified tailer for multiple log sources."""

    def __init__(self, config: Dict[str, Any]):
        self.sources_config = config

        # Initialize file tailers
        file_paths = []
        files_config = config.get("files", {})
        if files_config.get("enabled", True):
            file_paths.extend(files_config.get("paths", []))

        custom_config = config.get("custom", {})
        if custom_config.get("enabled", True):
            file_paths.extend(custom_config.get("paths", []))

        self.file_tailer = FileTailer(file_paths)

        # Initialize journal tailer
        journal_config = config.get("journalctl", {})
        self.journal_tailer = JournalTailer(journal_config)

        # Track active sources
        self.active_sources: Dict[str, bool] = {}
        self._update_active_sources()

    def _update_active_sources(self) -> None:
        """Update which sources are active."""
        self.active_sources = {
            "files": bool(self.file_tailer.files),
            "journal": self.journal_tailer.enabled and self.journal_tailer.process is not None,
        }

    def poll(self, timeout_ms: int = 100) -> List[LogEntry]:
        """Poll all sources for new log entries."""
        entries = []
        entries.extend(self.file_tailer.poll(timeout_ms))
        entries.extend(self.journal_tailer.poll())
        self._update_active_sources()
        return entries

    def get_status(self) -> Dict[str, Any]:
        """Get status of all log sources."""
        return {
            "files": {
                "active": list(self.file_tailer.files.keys()),
                "count": len(self.file_tailer.files),
            },
            "journal": {
                "enabled": self.journal_tailer.enabled,
                "running": self.journal_tailer.process is not None and self.journal_tailer.process.poll() is None,
            },
            "sources_active": self.active_sources,
        }

    def close(self) -> None:
        """Close all tailers."""
        self.file_tailer.close()
        self.journal_tailer.close()


def parse_syslog_line(line: str) -> Dict[str, Any]:
    """Parse a standard syslog line into components."""
    # Standard syslog format: "Mon DD HH:MM:SS hostname process[pid]: message"
    # Or ISO format from journalctl: "YYYY-MM-DDTHH:MM:SS+TZ hostname process[pid]: message"

    result = {
        "raw": line,
        "timestamp": None,
        "hostname": None,
        "process": None,
        "pid": None,
        "message": line,
    }

    # Try ISO format first (journalctl --output=short-iso)
    iso_match = re.match(
        r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{4})\s+(\S+)\s+(\S+?)(?:\[(\d+)\])?:\s*(.*)$",
        line
    )
    if iso_match:
        result["timestamp"] = iso_match.group(1)
        result["hostname"] = iso_match.group(2)
        result["process"] = iso_match.group(3)
        result["pid"] = iso_match.group(4)
        result["message"] = iso_match.group(5)
        return result

    # Try standard syslog format
    syslog_match = re.match(
        r"^(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+(\S+)\s+(\S+?)(?:\[(\d+)\])?:\s*(.*)$",
        line
    )
    if syslog_match:
        result["timestamp"] = syslog_match.group(1)
        result["hostname"] = syslog_match.group(2)
        result["process"] = syslog_match.group(3)
        result["pid"] = syslog_match.group(4)
        result["message"] = syslog_match.group(5)
        return result

    return result


def extract_ip_from_log(line: str) -> Optional[str]:
    """Extract an IP address from a log line."""
    # Match IPv4 addresses
    match = re.search(r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b', line)
    if match:
        ip = match.group(1)
        # Basic validation
        parts = ip.split('.')
        if all(0 <= int(p) <= 255 for p in parts):
            return ip
    return None


def extract_user_from_log(line: str) -> Optional[str]:
    """Extract a username from a log line."""
    # Common patterns: "user=xxx", "for xxx", "from xxx", "user xxx"
    patterns = [
        r'user[=:\s]+([a-zA-Z0-9_-]+)',
        r'for\s+(?:invalid\s+user\s+)?([a-zA-Z0-9_-]+)',
        r'from\s+([a-zA-Z0-9_-]+)@',
    ]
    for pattern in patterns:
        match = re.search(pattern, line, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


# =============================================================================
# IP and user validation utilities for remediation safety
# =============================================================================

# Protected system users that should never have sessions revoked
PROTECTED_USERS = frozenset([
    "root", "www-data", "postgres", "mysql",
    "nobody", "daemon", "systemd-network", "systemd-resolve",
    "sshd", "messagebus", "avahi", "cups", "dbus",
])


def is_valid_ip(ip: str) -> bool:
    """Validate IP address format.

    Args:
        ip: IP address string to validate

    Returns:
        True if valid IPv4 format, False otherwise
    """
    if not ip:
        return False

    pattern = r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$"
    match = re.match(pattern, ip)
    if not match:
        return False

    return all(0 <= int(g) <= 255 for g in match.groups())


def is_internal_ip(ip: str) -> bool:
    """Check if IP is in private/internal ranges.

    Private ranges:
    - 10.0.0.0/8
    - 172.16.0.0/12
    - 192.168.0.0/16
    - 127.0.0.0/8 (loopback)

    Args:
        ip: IP address string to check

    Returns:
        True if IP is in a private range, False otherwise
    """
    if not ip or not is_valid_ip(ip):
        return False

    parts = ip.split(".")
    if len(parts) != 4:
        return False

    try:
        octets = [int(p) for p in parts]
    except ValueError:
        return False

    # 10.0.0.0/8
    if octets[0] == 10:
        return True
    # 172.16.0.0/12
    if octets[0] == 172 and 16 <= octets[1] <= 31:
        return True
    # 192.168.0.0/16
    if octets[0] == 192 and octets[1] == 168:
        return True
    # 127.0.0.0/8 (loopback)
    if octets[0] == 127:
        return True

    return False


def is_protected_user(user: str) -> bool:
    """Check if user is a protected system user.

    Args:
        user: Username to check

    Returns:
        True if user is in PROTECTED_USERS set
    """
    if not user:
        return False
    return user.lower() in PROTECTED_USERS
