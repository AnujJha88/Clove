"""Agent: event_simulator - generates realistic attack events for demos.

Provides scenario-based event injection for demonstrations and testing.
Simulates various attack patterns like brute force, SQL injection, port scans, etc.
"""
from __future__ import annotations

import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils import ensure_sdk_on_path, wait_for_message, log

ensure_sdk_on_path()
from clove_sdk import CloveClient  # noqa: E402

AGENT_NAME = "event_simulator"

# Attack scenario definitions
ATTACK_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "brute_force": {
        "description": "SSH brute force attack simulation",
        "events": [
            {"type": "FAILED_LOGIN", "severity": "medium", "user": "admin", "system": "auth"},
            {"type": "FAILED_LOGIN", "severity": "medium", "user": "root", "system": "auth"},
            {"type": "FAILED_LOGIN", "severity": "medium", "user": "administrator", "system": "auth"},
            {"type": "INVALID_USER", "severity": "medium", "user": "test", "system": "auth"},
            {"type": "INVALID_USER", "severity": "medium", "user": "guest", "system": "auth"},
            {"type": "BRUTE_FORCE", "severity": "critical", "user": "admin", "system": "auth"},
        ],
        "timing": {"burst": 5, "interval_ms": 200, "jitter_ms": 50},
    },
    "sql_injection": {
        "description": "SQL injection attack on web application",
        "events": [
            {"type": "HTTP_ERROR", "severity": "medium", "system": "web", "path": "/api/users"},
            {"type": "SLOW_QUERY", "severity": "medium", "system": "database"},
            {"type": "SQL_INJECTION", "severity": "critical", "system": "web", "path": "/api/login"},
            {"type": "SQL_INJECT", "severity": "critical", "system": "database"},
        ],
        "timing": {"burst": 2, "interval_ms": 500, "jitter_ms": 100},
    },
    "port_scan": {
        "description": "Network reconnaissance via port scanning",
        "events": [
            {"type": "CONN_TIMEOUT", "severity": "low", "system": "network", "port": 21},
            {"type": "CONN_TIMEOUT", "severity": "low", "system": "network", "port": 23},
            {"type": "CONN_TIMEOUT", "severity": "low", "system": "network", "port": 25},
            {"type": "FW_DENY", "severity": "medium", "system": "network", "port": 445},
            {"type": "FW_DENY", "severity": "medium", "system": "network", "port": 3389},
            {"type": "PORT_SCAN", "severity": "high", "system": "network"},
        ],
        "timing": {"burst": 3, "interval_ms": 100, "jitter_ms": 20},
    },
    "data_exfil": {
        "description": "Data exfiltration attempt",
        "events": [
            {"type": "UNAUTH_ACCESS", "severity": "high", "system": "database", "user": "app_user"},
            {"type": "SLOW_QUERY", "severity": "medium", "system": "database"},
            {"type": "BW_SPIKE", "severity": "medium", "system": "network"},
            {"type": "DATA_EXFIL", "severity": "critical", "system": "network"},
            {"type": "C2_BEACON", "severity": "critical", "system": "network"},
        ],
        "timing": {"burst": 1, "interval_ms": 2000, "jitter_ms": 500},
    },
    "privilege_escalation": {
        "description": "Privilege escalation attack",
        "events": [
            {"type": "FAILED_LOGIN", "severity": "medium", "user": "www-data", "system": "auth"},
            {"type": "PATH_TRAVERSAL", "severity": "high", "system": "web", "path": "/etc/passwd"},
            {"type": "PRIV_ESC", "severity": "critical", "system": "auth", "user": "www-data"},
        ],
        "timing": {"burst": 1, "interval_ms": 1000, "jitter_ms": 200},
    },
    "ddos": {
        "description": "Distributed denial of service pattern",
        "events": [
            {"type": "RATE_LIMIT", "severity": "medium", "system": "web"},
            {"type": "RATE_LIMIT", "severity": "medium", "system": "web"},
            {"type": "CONN_TIMEOUT", "severity": "low", "system": "network"},
            {"type": "BW_SPIKE", "severity": "medium", "system": "network"},
            {"type": "POOL_EXHAUSTED", "severity": "medium", "system": "database"},
            {"type": "DDOS_DETECT", "severity": "critical", "system": "network"},
        ],
        "timing": {"burst": 10, "interval_ms": 50, "jitter_ms": 10},
    },
    "mixed_demo": {
        "description": "Mixed scenario for presentations - shows variety of attacks",
        "includes": ["brute_force", "sql_injection", "port_scan"],
        "timing": {"scenario_gap_ms": 5000},
    },
}

# Suspicious IP ranges for realistic simulation
SUSPICIOUS_IP_RANGES = [
    "185.220.101",  # Known Tor exit nodes
    "45.155.205",   # Suspicious hosting
    "194.26.192",   # VPN/proxy services
    "89.248.167",   # Scanner networks
    "141.98.10",    # Bulletproof hosting
]


class EventSimulator:
    """Generates realistic attack events for demonstrations."""

    def __init__(self, client: CloveClient, run_id: str, config: Dict[str, Any]):
        self.client = client
        self.run_id = run_id
        self.config = config
        self.event_counter = 0
        self.active_scenario: Optional[str] = None
        self.scenario_events: List[Dict[str, Any]] = []
        self.scenario_index = 0

    def generate_realistic_ip(self) -> str:
        """Generate a realistic external IP address."""
        if random.random() < 0.7:
            # Use suspicious IP range
            prefix = random.choice(SUSPICIOUS_IP_RANGES)
            return f"{prefix}.{random.randint(1, 254)}"
        else:
            # Random external IP
            return f"{random.randint(1, 223)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}"

    def generate_log_line(self, event: Dict[str, Any]) -> str:
        """Generate a realistic log line for an event."""
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")
        event_type = event.get("type", "UNKNOWN")
        system = event.get("system", "unknown")
        ip = event.get("source_ip", self.generate_realistic_ip())
        user = event.get("user", "")

        templates = {
            "FAILED_LOGIN": f"{timestamp} sshd[{random.randint(1000,9999)}]: Failed password for {user} from {ip} port {random.randint(40000,65000)} ssh2",
            "INVALID_USER": f"{timestamp} sshd[{random.randint(1000,9999)}]: Invalid user {user} from {ip} port {random.randint(40000,65000)} ssh2",
            "BRUTE_FORCE": f"{timestamp} security[{random.randint(1000,9999)}]: BRUTE_FORCE detected from {ip} - {random.randint(10,50)} failed attempts",
            "SQL_INJECTION": f"{timestamp} webapp[{random.randint(1000,9999)}]: SQL_INJECTION attempt from {ip}: ' OR 1=1--",
            "SQL_INJECT": f"{timestamp} mysql[{random.randint(1000,9999)}]: SQL_INJECT blocked: suspicious query from {ip}",
            "PORT_SCAN": f"{timestamp} firewall[{random.randint(1000,9999)}]: PORT_SCAN detected from {ip} - scanned {random.randint(100,1000)} ports",
            "DATA_EXFIL": f"{timestamp} dlp[{random.randint(1000,9999)}]: DATA_EXFIL alert: {random.randint(10,500)}MB transferred to {ip}",
            "C2_BEACON": f"{timestamp} nids[{random.randint(1000,9999)}]: C2_BEACON detected: periodic connection to {ip}:443",
            "PRIV_ESC": f"{timestamp} kernel[{random.randint(1000,9999)}]: PRIV_ESC: user {user} gained root access",
            "DDOS_DETECT": f"{timestamp} firewall[{random.randint(1000,9999)}]: DDOS_DETECT: {random.randint(10000,100000)} req/s from {random.randint(50,500)} IPs",
            "PATH_TRAVERSAL": f"{timestamp} webapp[{random.randint(1000,9999)}]: PATH_TRAVERSAL attempt from {ip}: ../../../etc/passwd",
            "XSS_ATTEMPT": f"{timestamp} webapp[{random.randint(1000,9999)}]: XSS_ATTEMPT from {ip}: <script>alert(1)</script>",
            "RATE_LIMIT": f"{timestamp} nginx[{random.randint(1000,9999)}]: RATE_LIMIT exceeded for {ip}: {random.randint(100,500)} req/min",
            "HTTP_ERROR": f"{timestamp} nginx[{random.randint(1000,9999)}]: HTTP_ERROR 500 from {ip} on {event.get('path', '/api')}",
            "SLOW_QUERY": f"{timestamp} mysql[{random.randint(1000,9999)}]: SLOW_QUERY: {random.randint(5,30)}s query on table users",
            "CONN_TIMEOUT": f"{timestamp} network[{random.randint(1000,9999)}]: CONN_TIMEOUT to port {event.get('port', 80)} from {ip}",
            "FW_DENY": f"{timestamp} firewall[{random.randint(1000,9999)}]: FW_DENY: blocked {ip} on port {event.get('port', 445)}",
            "BW_SPIKE": f"{timestamp} network[{random.randint(1000,9999)}]: BW_SPIKE: {random.randint(500,2000)}Mbps outbound",
            "POOL_EXHAUSTED": f"{timestamp} mysql[{random.randint(1000,9999)}]: POOL_EXHAUSTED: max connections reached",
            "UNAUTH_ACCESS": f"{timestamp} security[{random.randint(1000,9999)}]: UNAUTH_ACCESS: {user} accessed restricted table",
        }

        return templates.get(event_type, f"{timestamp} {system}[0]: {event_type} event")

    def expand_scenario(self, scenario_name: str) -> List[Dict[str, Any]]:
        """Expand a scenario into a list of events."""
        scenario = ATTACK_SCENARIOS.get(scenario_name)
        if not scenario:
            return []

        # Handle composite scenarios
        if "includes" in scenario:
            events = []
            for sub_scenario in scenario["includes"]:
                events.extend(self.expand_scenario(sub_scenario))
                # Add gap between scenarios
                gap_ms = scenario.get("timing", {}).get("scenario_gap_ms", 3000)
                if events:
                    events[-1]["_delay_after_ms"] = gap_ms
            return events

        # Regular scenario - expand events based on timing
        events = []
        timing = scenario.get("timing", {})
        burst = timing.get("burst", 1)
        base_interval = timing.get("interval_ms", 500)
        jitter = timing.get("jitter_ms", 0)

        for event_template in scenario.get("events", []):
            for _ in range(burst):
                event = dict(event_template)
                event["source_ip"] = self.generate_realistic_ip()
                event["_delay_after_ms"] = base_interval + random.randint(-jitter, jitter)
                events.append(event)

        return events

    def start_scenario(self, scenario_name: str) -> bool:
        """Start running a scenario."""
        if scenario_name not in ATTACK_SCENARIOS:
            log(AGENT_NAME, "WARN", f"Unknown scenario: {scenario_name}")
            return False

        self.active_scenario = scenario_name
        self.scenario_events = self.expand_scenario(scenario_name)
        self.scenario_index = 0

        log(AGENT_NAME, "INFO", f"Started scenario '{scenario_name}' with {len(self.scenario_events)} events")
        return True

    def get_next_event(self) -> Optional[Dict[str, Any]]:
        """Get the next event from active scenario."""
        if not self.active_scenario or self.scenario_index >= len(self.scenario_events):
            return None

        event = self.scenario_events[self.scenario_index]
        self.scenario_index += 1

        # Check if scenario complete
        if self.scenario_index >= len(self.scenario_events):
            log(AGENT_NAME, "INFO", f"Scenario '{self.active_scenario}' complete")
            self.active_scenario = None

        return event

    def create_incident(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Create a full incident from an event template."""
        self.event_counter += 1
        incident_id = f"sim_{self.run_id}_{self.event_counter:04d}"

        return {
            "id": incident_id,
            "run_id": self.run_id,
            "type": event.get("type", "UNKNOWN"),
            "severity": event.get("severity", "medium"),
            "title": f"[SIM] {event.get('type', 'Unknown')} event",
            "system": event.get("system", "unknown"),
            "source_ip": event.get("source_ip"),
            "user": event.get("user"),
            "port": event.get("port"),
            "path": event.get("path"),
            "line": self.generate_log_line(event),
            "source": "event_simulator",
            "source_type": "simulated",
            "detected_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": "detected",
            "simulated": True,
        }


def main() -> int:
    client = CloveClient()
    if not client.connect():
        log(AGENT_NAME, "ERROR", "Failed to connect to Clove kernel")
        return 1

    try:
        client.register_name(AGENT_NAME)

        try:
            init = wait_for_message(client, expected_type="init", timeout_s=30.0)
        except TimeoutError as e:
            log(AGENT_NAME, "ERROR", f"Timeout waiting for init: {e}")
            return 1

        run_id = init.get("run_id", "run_000")
        mode = init.get("mode", "continuous")
        config = init.get("config", {})

        simulator_config = config.get("event_simulator", {})
        enabled = simulator_config.get("enabled", True)
        default_scenario = simulator_config.get("default_scenario")
        auto_start = simulator_config.get("auto_start", False)

        service_config = config.get("service", {})
        heartbeat_interval = service_config.get("heartbeat_interval_seconds", 5)

        simulator = EventSimulator(client, run_id, simulator_config)

        # Send init acknowledgment
        client.send_message({"type": "init_ack", "agent": AGENT_NAME}, to_name="orchestrator")

        # Auto-start default scenario if configured
        if enabled and auto_start and default_scenario:
            simulator.start_scenario(default_scenario)

        last_heartbeat = time.time()
        last_event_time = time.time()
        pending_delay_ms = 0

        while True:
            current_time = time.time()

            # Send heartbeat
            if mode == "continuous" and current_time - last_heartbeat >= heartbeat_interval:
                client.send_message({
                    "type": "heartbeat",
                    "agent": AGENT_NAME,
                    "events_generated": simulator.event_counter,
                    "active_scenario": simulator.active_scenario,
                }, to_name="orchestrator")
                last_heartbeat = current_time

            # Check for IPC messages
            try:
                message = wait_for_message(client, timeout_s=0.1)
                msg_type = message.get("type")

                if msg_type == "start_scenario":
                    scenario_name = message.get("scenario", default_scenario)
                    if scenario_name:
                        simulator.start_scenario(scenario_name)
                        client.send_message({
                            "type": "scenario_started",
                            "scenario": scenario_name,
                            "event_count": len(simulator.scenario_events),
                        }, to_name=message.get("reply_to", "orchestrator"))

                elif msg_type == "inject_event":
                    # Direct event injection
                    event = message.get("event", {})
                    if event:
                        incident = simulator.create_incident(event)
                        client.store(f"incident:{run_id}:{incident['id']}", incident, scope="global")
                        client.send_message({
                            "type": "anomaly_detected",
                            "incident": incident,
                        }, to_name="anomaly_triager")
                        client.send_message({
                            "type": "log_event",
                            "incident_id": incident["id"],
                            "severity": incident["severity"],
                            "system": incident["system"],
                            "event_type": incident["type"],
                            "source": "simulator",
                        }, to_name="orchestrator")

                elif msg_type == "stop_scenario":
                    simulator.active_scenario = None
                    simulator.scenario_events = []
                    log(AGENT_NAME, "INFO", "Scenario stopped")

                elif msg_type == "list_scenarios":
                    scenarios = {
                        name: {"description": s.get("description", "")}
                        for name, s in ATTACK_SCENARIOS.items()
                    }
                    client.send_message({
                        "type": "scenarios_list",
                        "scenarios": scenarios,
                    }, to_name=message.get("reply_to", "orchestrator"))

                elif msg_type == "shutdown":
                    log(AGENT_NAME, "INFO", "Received shutdown")
                    break

            except TimeoutError:
                pass

            # Generate events from active scenario
            if enabled and simulator.active_scenario:
                # Check if delay has passed
                elapsed_ms = (current_time - last_event_time) * 1000
                if elapsed_ms >= pending_delay_ms:
                    event = simulator.get_next_event()
                    if event:
                        incident = simulator.create_incident(event)
                        client.store(f"incident:{run_id}:{incident['id']}", incident, scope="global")

                        # Send to log_watcher pipeline
                        client.send_message({
                            "type": "anomaly_detected",
                            "incident": incident,
                        }, to_name="anomaly_triager")

                        # Notify orchestrator for dashboard
                        client.send_message({
                            "type": "log_event",
                            "incident_id": incident["id"],
                            "severity": incident["severity"],
                            "system": incident["system"],
                            "event_type": incident["type"],
                            "source": "simulator",
                        }, to_name="orchestrator")

                        pending_delay_ms = event.get("_delay_after_ms", 500)
                        last_event_time = current_time

            time.sleep(0.05)

    except TimeoutError as e:
        log(AGENT_NAME, "ERROR", f"Fatal timeout: {e}")
        return 1
    finally:
        client.disconnect()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
