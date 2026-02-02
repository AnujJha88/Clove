"""Clove incident response lab orchestrator."""
from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any, Dict

from utils import ensure_sdk_on_path, load_config, normalize_limits, write_json

ensure_sdk_on_path()
from clove_sdk import CloveClient  # noqa: E402

AGENTS = [
    "log_watcher",
    "anomaly_triager",
    "remediation_executor",
    "auditor",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clove incident response lab")
    parser.add_argument("--run-id", default=time.strftime("run_%Y%m%d_%H%M%S"))
    parser.add_argument("--configs-dir", default="configs")
    parser.add_argument("--artifacts-dir", default="artifacts")
    parser.add_argument("--logs-dir", default="logs")
    parser.add_argument("--socket-path", default="/tmp/clove.sock")
    parser.add_argument("--sandboxed", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--network", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--record-execution", action="store_true", default=False)
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


def wait_for_event(client: CloveClient, event_type: str, timeout_s: int = 10) -> Dict[str, Any] | None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        result = client.recv_messages()
        for msg in result.get("messages", []):
            payload = msg.get("message", {})
            if payload.get("type") == event_type:
                return payload
        time.sleep(0.2)
    return None


def wait_for_acks(client: CloveClient, expected_agents: list[str], timeout_s: int = 10) -> dict[str, bool]:
    """Wait for init_ack messages from all expected agents."""
    acks = {agent: False for agent in expected_agents}
    deadline = time.time() + timeout_s

    while time.time() < deadline:
        if all(acks.values()):
            break
        result = client.recv_messages()
        for msg in result.get("messages", []):
            payload = msg.get("message", {})
            if payload.get("type") == "init_ack":
                agent = payload.get("agent")
                if agent in acks:
                    acks[agent] = True
                    print(f"[orchestrator] Received init_ack from {agent}")
        time.sleep(0.1)

    return acks


def build_permissions(base_dir: Path, logs_dir: Path, artifacts_dir: Path) -> Dict[str, Dict[str, Any]]:
    # fnmatch with FNM_PATHNAME means * doesn't match /
    # So we need patterns for each directory level we want to allow
    # Pattern: dir/* matches files in dir, dir/*/* matches one level deeper, etc.
    read_paths = [
        str(base_dir / "*"),
        str(base_dir / "*" / "*"),
        str(base_dir / "*" / "*" / "*"),
        str(logs_dir / "*"),
        str(logs_dir / "*" / "*"),
        str(artifacts_dir / "*"),
        str(artifacts_dir / "*" / "*"),
    ]
    write_paths = [
        str(logs_dir / "*"),
        str(logs_dir / "*" / "*"),
        str(artifacts_dir / "*"),
        str(artifacts_dir / "*" / "*"),
    ]
    remediation = {
        "filesystem": {
            "read": read_paths,
            "write": write_paths,
        },
        "max_exec_time_ms": 2000,
    }
    auditor = {
        "filesystem": {
            "read": read_paths,
            "write": write_paths,
        },
        "max_exec_time_ms": 2000,
    }
    return {
        "remediation_executor": remediation,
        "auditor": auditor,
    }


def main() -> int:
    args = parse_args()
    base_dir = Path(__file__).resolve().parent
    configs_dir = (base_dir / args.configs_dir).resolve()
    artifacts_dir = (base_dir / args.artifacts_dir).resolve()
    logs_dir = (base_dir / args.logs_dir).resolve()

    scenario = load_config(configs_dir / "scenario.json")
    limits_config = load_config(configs_dir / "clove_limits.json")

    log_lines = scenario.get("log_lines", [])
    rules = scenario.get("rules", {})
    playbook = scenario.get("remediation_playbook", {})

    run_artifacts_dir = artifacts_dir / args.run_id
    run_logs_dir = logs_dir / args.run_id
    run_artifacts_dir.mkdir(parents=True, exist_ok=True)
    run_logs_dir.mkdir(parents=True, exist_ok=True)

    log_path = run_logs_dir / "system.log"
    log_path.write_text("\n".join(log_lines) + "\n")

    stage_limits = limits_config.get("limits", {})
    restart_policy = limits_config.get("restart_policy", "on-failure")
    max_restarts = int(limits_config.get("max_restarts", 1))
    restart_window = int(limits_config.get("restart_window", 60))

    print("[orchestrator] Starting incident response lab")
    print(f"[orchestrator] run_id={args.run_id}")

    client = CloveClient(socket_path=args.socket_path)
    if not client.connect():
        print("[orchestrator] ERROR: Failed to connect to Clove kernel")
        return 1

    try:
        client.register_name("orchestrator")
        client.set_permissions(level="unrestricted")

        if args.record_execution:
            client.start_recording(include_exec=True)

        permissions = build_permissions(base_dir, logs_dir, artifacts_dir)
        agents: dict[str, int] = {}

        # Track socket IDs by name (resolved after registration)
        socket_ids: dict[str, int] = {}

        for agent in AGENTS:
            script_path = base_dir / "agents" / f"{agent}.py"
            limits = normalize_limits(stage_limits.get(agent, {}))

            spawn_result = client.spawn(
                name=agent,
                script=str(script_path),
                sandboxed=args.sandboxed,
                network=args.network,
                limits=limits,
                restart_policy=restart_policy,
                max_restarts=max_restarts,
                restart_window=restart_window,
            )

            if not spawn_result or spawn_result.get("status") != "running":
                print(f"[orchestrator] ERROR: Failed to spawn {agent}: {spawn_result}")
                return 1

            agents[agent] = int(spawn_result.get("id", 0))

            if not wait_for_name(client, agent):
                print(f"[orchestrator] ERROR: {agent} did not register")
                return 1

        # Set permissions using socket IDs (from send_message response)
        # This ensures we're setting permissions for the actual connected agent
        for agent in AGENTS:
            # Send a ping to get the resolved socket ID
            ping_result = client.send_message({"type": "ping"}, to_name=agent)
            socket_id = ping_result.get("delivered_to", 0)

            # Validate socket ID - fail explicitly if invalid
            if not socket_id or socket_id == 0:
                print(f"[orchestrator] ERROR: Could not resolve socket ID for {agent}")
                return 1

            socket_ids[agent] = socket_id

            if agent in permissions:
                client.set_permissions(permissions=permissions[agent], agent_id=socket_id)
            else:
                client.set_permissions(level="readonly", agent_id=socket_id)

        init_message = {
            "type": "init",
            "run_id": args.run_id,
            "artifacts_dir": str(artifacts_dir),
            "logs_dir": str(logs_dir),
            "rules": rules,
            "remediation_playbook": playbook,
            "reply_to": "orchestrator",
        }

        for agent in AGENTS:
            client.send_message(init_message, to_name=agent)

        # Wait for init acknowledgments instead of sleeping
        acks = wait_for_acks(client, AGENTS, timeout_s=10)
        missing_acks = [agent for agent, acked in acks.items() if not acked]
        if missing_acks:
            print(f"[orchestrator] WARN: Missing init_ack from: {missing_acks}")
            # Continue anyway, but log warning

        client.send_message({
            "type": "scan_logs",
            "log_path": str(log_path)
        }, to_name="log_watcher")

        scan_result = wait_for_event(client, "scan_complete", timeout_s=15)
        incident_count = 0
        if scan_result:
            client.send_message(scan_result, to_name="auditor")
            incident_count = scan_result.get("count", 0)
        else:
            print("[orchestrator] WARN: log scan timed out")

        time.sleep(1.0)

        # Include incident count in finalize message to help auditor know what to expect
        client.send_message({
            "type": "finalize",
            "incident_count": incident_count
        }, to_name="auditor")

        audit_report = wait_for_event(client, "audit_report", timeout_s=15)
        if audit_report:
            if audit_report.get("error"):
                print(f"[orchestrator] ERROR: audit report failed: {audit_report.get('error')}")
            else:
                print(f"[orchestrator] audit report: {audit_report.get('path')}")
        else:
            print("[orchestrator] WARN: auditor did not respond")

        if args.dump_audit:
            audit = client.get_audit_log(limit=200)
            write_json(run_logs_dir / "audit_log.json", audit)

        if args.record_execution:
            client.stop_recording()
            recording = client.get_recording_status(export=True)
            write_json(run_logs_dir / "execution_recording.json", recording)

        for agent in AGENTS:
            client.send_message({"type": "shutdown"}, to_name=agent)

    finally:
        client.disconnect()

    print("[orchestrator] Done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
