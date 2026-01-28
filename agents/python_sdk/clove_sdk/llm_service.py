#!/usr/bin/env python3
"""
Local LLM service wrapper for the SDK.

Runs agents/llm_service/llm_service.py as a subprocess and returns JSON output.
"""

from __future__ import annotations

import json
import os
import sys
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional


def _find_llm_service() -> Optional[Path]:
    override = os.environ.get("CLOVE_LLM_SERVICE_PATH")
    if override:
        path = Path(override).expanduser()
        if path.is_file():
            return path

    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "llm_service" / "llm_service.py",  # agents/llm_service/llm_service.py
        here.parents[3] / "agents" / "llm_service" / "llm_service.py",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def call_llm_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    script_path = _find_llm_service()
    if not script_path:
        return {
            "success": False,
            "error": "LLM service not found. Set CLOVE_LLM_SERVICE_PATH or install agents/llm_service.",
            "content": "",
        }

    try:
        proc = subprocess.run(
            [sys.executable, str(script_path)],
            input=json.dumps(payload) + "\n",
            text=True,
            capture_output=True,
            check=False,
        )
    except Exception as exc:
        return {"success": False, "error": str(exc), "content": ""}

    stdout = (proc.stdout or "").strip().splitlines()
    if not stdout:
        err = (proc.stderr or "").strip()
        return {"success": False, "error": err or "No response from LLM service", "content": ""}

    last_line = stdout[-1].strip()
    try:
        return json.loads(last_line)
    except json.JSONDecodeError:
        return {"success": False, "error": "Invalid JSON from LLM service", "content": last_line}
