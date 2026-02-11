"""Agent: health_monitor - tracks real system metrics via psutil.

Tracks:
- CPU usage (real)
- Memory usage (real)
- Disk usage (real)
- System load

All configuration is read from the init message config.
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils import ensure_sdk_on_path, wait_for_message, log

ensure_sdk_on_path()
from clove_sdk import CloveClient  # noqa: E402

# Try to import psutil, provide fallback if not available
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

AGENT_NAME = "health_monitor"


@dataclass
class SystemMetrics:
    """Tracks real system metrics."""
    name: str
    thresholds: Dict[str, float]
    cpu: float = 0.0
    memory: float = 0.0
    disk: float = 0.0
    latency_ms: float = 0.0
    error_rate: float = 0.0
    status: str = "ok"
    last_update: float = field(default_factory=time.time)

    def update_real(self) -> None:
        """Update metrics with real system values from psutil."""
        if not PSUTIL_AVAILABLE:
            # Fallback to zeros if psutil not available
            self.last_update = time.time()
            return

        # CPU - non-blocking call (uses cached value from previous interval)
        self.cpu = psutil.cpu_percent(interval=None)

        # Memory
        mem = psutil.virtual_memory()
        self.memory = mem.percent

        # Disk
        try:
            disk = psutil.disk_usage('/')
            self.disk = disk.percent
        except (OSError, FileNotFoundError):
            self.disk = 0.0

        # Error rate - we use 0 for real monitoring (no simulated errors)
        self.error_rate = 0.0

        # Latency - approximate using disk I/O wait time or load average
        try:
            load1, load5, load15 = psutil.getloadavg()
            # Use 1-minute load average scaled to latency estimate
            # This is a rough approximation
            self.latency_ms = load1 * 10  # Scale factor
        except (OSError, AttributeError):
            self.latency_ms = 0.0

        # Update status based on thresholds
        self._update_status()
        self.last_update = time.time()

    def _update_status(self) -> None:
        """Update status based on threshold violations."""
        cpu_thresh = self.thresholds.get("cpu", 80)
        mem_thresh = self.thresholds.get("memory", 85)
        disk_thresh = self.thresholds.get("disk", 90)

        if self.cpu > cpu_thresh or self.memory > mem_thresh or self.disk > disk_thresh:
            self.status = "warn"
        else:
            self.status = "ok"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cpu": round(self.cpu, 1),
            "memory": round(self.memory, 1),
            "disk": round(self.disk, 1),
            "latency_ms": round(self.latency_ms, 1),
            "error_rate": round(self.error_rate, 2),
            "status": self.status,
        }

    def check_thresholds(self) -> list[tuple[str, float, float]]:
        """Check for threshold violations. Returns list of (metric, value, threshold)."""
        violations = []
        cpu_thresh = self.thresholds.get("cpu", 80)
        if self.cpu > cpu_thresh:
            violations.append(("cpu", self.cpu, cpu_thresh))
        mem_thresh = self.thresholds.get("memory", 85)
        if self.memory > mem_thresh:
            violations.append(("memory", self.memory, mem_thresh))
        disk_thresh = self.thresholds.get("disk", 90)
        if self.disk > disk_thresh:
            violations.append(("disk", self.disk, disk_thresh))
        lat_thresh = self.thresholds.get("latency_ms", 500)
        if self.latency_ms > lat_thresh:
            violations.append(("latency_ms", self.latency_ms, lat_thresh))
        err_thresh = self.thresholds.get("error_rate", 5)
        if self.error_rate > err_thresh:
            violations.append(("error_rate", self.error_rate, err_thresh))
        return violations


def main() -> int:
    client = CloveClient()
    if not client.connect():
        log(AGENT_NAME, "ERROR", "Failed to connect to Clove kernel")
        return 1

    if not PSUTIL_AVAILABLE:
        log(AGENT_NAME, "WARN", "psutil not available, metrics will be zeros. Install with: pip install psutil")

    try:
        client.register_name(AGENT_NAME)

        try:
            init = wait_for_message(client, expected_type="init", timeout_s=30.0)
        except TimeoutError as e:
            log(AGENT_NAME, "ERROR", f"Timeout waiting for init: {e}")
            return 1

        run_id = init.get("run_id", "run_000")
        config = init.get("config", {})

        # Get config values
        system_names = config.get("systems", ["web", "auth", "database", "network"])

        health_config = config.get("health", {})
        thresholds = health_config.get("thresholds", {
            "cpu": 80.0,
            "memory": 85.0,
            "disk": 90.0,
            "latency_ms": 500.0,
            "error_rate": 5.0,
        })
        update_interval = health_config.get("update_interval_seconds", 5.0)

        service_config = config.get("service", {})
        heartbeat_interval = service_config.get("heartbeat_interval_seconds", 5)

        client.send_message({"type": "init_ack", "agent": AGENT_NAME}, to_name="orchestrator")

        # Initialize a single system metrics object for real monitoring
        # All "systems" share the same real host metrics
        system_metrics = SystemMetrics(
            name="host",
            thresholds=thresholds,
        )

        # Initialize per-system metrics that share real values
        systems: Dict[str, SystemMetrics] = {
            name: SystemMetrics(
                name=name,
                thresholds=thresholds,
            ) for name in system_names
        }

        # Prime the CPU measurement (first call returns 0)
        if PSUTIL_AVAILABLE:
            psutil.cpu_percent(interval=None)

        monitoring = False
        last_update = 0.0
        last_heartbeat = time.time()

        while True:
            current_time = time.time()

            # Send heartbeat
            if current_time - last_heartbeat >= heartbeat_interval:
                client.send_message({
                    "type": "heartbeat",
                    "agent": AGENT_NAME,
                    "systems_monitored": len(systems),
                    "psutil_available": PSUTIL_AVAILABLE,
                }, to_name="orchestrator")
                last_heartbeat = current_time

            # Check for messages
            result = client.recv_messages()
            for msg in result.get("messages", []):
                payload = msg.get("message", {})
                msg_type = payload.get("type")

                if msg_type == "start_monitoring":
                    monitoring = True
                    log(AGENT_NAME, "INFO", "Started monitoring (real metrics)")

                elif msg_type == "stop_monitoring":
                    monitoring = False
                    log(AGENT_NAME, "INFO", "Stopped monitoring")

                elif msg_type == "shutdown":
                    log(AGENT_NAME, "INFO", "Received shutdown")
                    return 0

            if monitoring and (current_time - last_update) >= update_interval:
                # Get real system metrics once
                system_metrics.update_real()

                # Apply same metrics to all logical systems
                for name, system in systems.items():
                    system.cpu = system_metrics.cpu
                    system.memory = system_metrics.memory
                    system.disk = system_metrics.disk
                    system.latency_ms = system_metrics.latency_ms
                    system.error_rate = system_metrics.error_rate
                    system._update_status()
                    system.last_update = current_time

                    # Check for threshold violations
                    violations = system.check_thresholds()
                    for metric, value, threshold in violations:
                        # Send alert
                        client.send_message({
                            "type": "health_alert",
                            "system": system.name,
                            "metric": metric,
                            "value": value,
                            "threshold": threshold,
                            "status": system.status,
                        }, to_name="orchestrator")

                        client.send_message({
                            "type": "health_alert",
                            "system": system.name,
                            "metric": metric,
                            "value": value,
                            "threshold": threshold,
                        }, to_name="anomaly_triager")

                    # Send health update
                    client.send_message({
                        "type": "health_update",
                        "system": system.name,
                        "health": system.to_dict(),
                    }, to_name="orchestrator")

                    # Store metrics
                    client.store(
                        f"health:{run_id}:{system.name}:{int(current_time)}",
                        {
                            "system": system.name,
                            "timestamp": current_time,
                            **system.to_dict(),
                        },
                        scope="global"
                    )

                last_update = current_time

            time.sleep(0.1)

    except Exception as e:
        log(AGENT_NAME, "ERROR", f"Exception: {e}")
        return 1
    finally:
        client.disconnect()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
