"""Shared helpers for the drug research pipeline demo."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict


def pipeline_root() -> Path:
    return Path(__file__).resolve().parent


def repo_root() -> Path:
    return pipeline_root().parents[1]


def ensure_sdk_on_path() -> None:
    sdk_path = repo_root() / "agents" / "python_sdk"
    if sdk_path.exists() and str(sdk_path) not in sys.path:
        sys.path.insert(0, str(sdk_path))


def load_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    suffix = path.suffix.lower()
    raw = path.read_text()
    if suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except Exception:
            return {}
        data = yaml.safe_load(raw) or {}
        return data if isinstance(data, dict) else {"value": data}
    if suffix == ".json":
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True))


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def log_line(log_path: Path, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {message}\n")


def maybe_fail_once(run_dir: Path, stage: str, config: Dict[str, Any]) -> None:
    if not config.get("fail_once"):
        return
    marker = run_dir / f".{stage}.failed_once"
    if marker.exists():
        return
    marker.write_text("1")
    mode = config.get("fail_mode", "exception")
    if mode == "exit":
        raise SystemExit(1)
    if mode == "memory":
        raise MemoryError("Simulated OOM")
    if mode == "malformed":
        raise ValueError("Simulated malformed input")
    if mode == "timeout":
        time.sleep(config.get("sleep_seconds", 5))
    raise RuntimeError(config.get("fail_message", "Simulated failure"))


def normalize_limits(limits: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(limits) if limits else {}
    if "memory_mb" in normalized and "memory" not in normalized:
        normalized["memory"] = int(normalized["memory_mb"]) * 1024 * 1024
    if "cpu" in normalized and "cpu_quota" not in normalized:
        normalized["cpu_quota"] = int(normalized["cpu"]) * 100000
    return normalized


def wait_for_message(
    client,
    poll_interval: float = 0.2,
    expected_type: str | None = None,
    expected_stage: str | None = None,
) -> Dict[str, Any]:
    while True:
        result = client.recv_messages()
        for msg in result.get("messages", []):
            payload = msg.get("message", {})
            if payload:
                if expected_type and payload.get("type") != expected_type:
                    continue
                if expected_stage and payload.get("stage") != expected_stage:
                    continue
                return payload
        time.sleep(poll_interval)
