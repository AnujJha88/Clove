"""Clove drug research pipeline orchestrator.

Spawns each stage as an isolated OS process and coordinates execution via IPC.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Dict, Any

from utils import ensure_sdk_on_path, load_config, normalize_limits, write_json

ensure_sdk_on_path()
from clove_sdk import CloveClient  # noqa: E402

STAGES = [
    "load_data",
    "featurize",
    "train",
    "evaluate",
    "report",
    "archive",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clove drug research pipeline")
    parser.add_argument("--run-id", default=time.strftime("run_%Y%m%d_%H%M%S"))
    parser.add_argument("--configs-dir", default="configs")
    parser.add_argument("--artifacts-dir", default="artifacts")
    parser.add_argument("--logs-dir", default="logs")
    parser.add_argument("--socket-path", default="/tmp/clove.sock")
    parser.add_argument("--sandboxed", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--network", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--dump-audit", action="store_true", default=False)
    return parser.parse_args()


def wait_for_name(client: CloveClient, name: str, timeout_s: int = 10) -> bool:
    start = time.time()
    while time.time() - start < timeout_s:
        result = client.send_message({"type": "ping"}, to_name=name)
        if result.get("success"):
            return True
        time.sleep(0.2)
    return False


def wait_for_stage(client: CloveClient, stage: str, timeout_s: int) -> Dict[str, Any] | None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        result = client.recv_messages()
        for msg in result.get("messages", []):
            payload = msg.get("message", {})
            if payload.get("type") == "stage_complete" and payload.get("stage") == stage:
                return payload
        time.sleep(0.2)
    return None


def build_stage_message(
    stage: str,
    run_id: str,
    artifacts_dir: Path,
    logs_dir: Path,
    config: Dict[str, Any],
    input_payload: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "type": "run_stage",
        "stage": stage,
        "run_id": run_id,
        "artifacts_dir": str(artifacts_dir),
        "logs_dir": str(logs_dir),
        "config": config,
        "input": input_payload,
        "reply_to": "orchestrator",
        "force": False,
    }


def main() -> int:
    args = parse_args()
    base_dir = Path(__file__).resolve().parent
    configs_dir = (base_dir / args.configs_dir).resolve()
    artifacts_dir = (base_dir / args.artifacts_dir).resolve()
    logs_dir = (base_dir / args.logs_dir).resolve()

    config_map = {
        "dataset": load_config(configs_dir / "dataset.yaml"),
        "featurize": load_config(configs_dir / "featurize.yaml"),
        "train": load_config(configs_dir / "train.yaml"),
        "evaluate": load_config(configs_dir / "eval.yaml"),
    }
    limits_config = load_config(configs_dir / "clove_limits.yaml")

    stage_limits = limits_config.get("limits", {})
    stage_timeouts = limits_config.get("timeouts", {})
    retry_policy = limits_config.get("retries", {}).get("default", {})
    max_attempts = int(retry_policy.get("max_attempts", 3))
    resend_interval = float(retry_policy.get("resend_interval_s", 2))

    restart_policy = limits_config.get("restart_policy", "on-failure")
    max_restarts = int(limits_config.get("max_restarts", 2))
    restart_window = int(limits_config.get("restart_window", 300))

    print("[orchestrator] Starting pipeline")
    print(f"[orchestrator] run_id={args.run_id}")
    print(f"[orchestrator] artifacts_dir={artifacts_dir}")
    print(f"[orchestrator] logs_dir={logs_dir}")

    client = CloveClient(socket_path=args.socket_path)
    if not client.connect():
        print("[orchestrator] ERROR: Failed to connect to Clove kernel")
        return 1

    try:
        client.register_name("orchestrator")

        input_payload: Dict[str, Any] = {}
        results: Dict[str, Any] = {}

        for stage in STAGES:
            script_path = base_dir / "stages" / f"{stage}.py"
            stage_limit = normalize_limits(stage_limits.get(stage, {}))
            stage_timeout = int(stage_timeouts.get(stage, 60))

            spawn_result = client.spawn(
                name=stage,
                script=str(script_path),
                sandboxed=args.sandboxed,
                network=args.network,
                limits=stage_limit,
                restart_policy=restart_policy,
                max_restarts=max_restarts,
                restart_window=restart_window,
            )

            if not spawn_result or spawn_result.get("status") != "running":
                print(f"[orchestrator] ERROR: Failed to spawn {stage}: {spawn_result}")
                return 1

            if not wait_for_name(client, stage):
                print(f"[orchestrator] ERROR: {stage} did not register")
                return 1

            stage_config = {}
            if stage == "load_data":
                stage_config = config_map.get("dataset", {})
            elif stage in ("featurize", "train"):
                stage_config = config_map.get(stage, {})
            elif stage == "evaluate":
                stage_config = config_map.get("evaluate", {})

            message = build_stage_message(
                stage=stage,
                run_id=args.run_id,
                artifacts_dir=artifacts_dir,
                logs_dir=logs_dir,
                config=stage_config,
                input_payload=input_payload,
            )

            attempts = 0
            stage_result = None
            while attempts < max_attempts and stage_result is None:
                attempts += 1
                client.send_message(message, to_name=stage)
                stage_result = wait_for_stage(client, stage, stage_timeout)
                if stage_result is None:
                    print(f"[orchestrator] WARN: {stage} timed out (attempt {attempts})")
                    time.sleep(resend_interval)

            if stage_result is None:
                print(f"[orchestrator] ERROR: {stage} failed after {max_attempts} attempts")
                return 1

            results[stage] = stage_result
            input_payload = stage_result.get("output", {})
            print(f"[orchestrator] {stage} complete: {stage_result.get('status')}")

        write_json(artifacts_dir / args.run_id / "pipeline_summary.json", results)
        print("[orchestrator] Pipeline complete")

        if args.dump_audit:
            audit = client.get_audit_log(limit=200)
            write_json(logs_dir / args.run_id / "audit_log.json", audit)
    finally:
        client.disconnect()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
