"""Stage: generate research report (placeholder)."""
from __future__ import annotations

from pathlib import Path

from utils import ensure_sdk_on_path, log_line, maybe_fail_once, read_json, wait_for_message, write_json

ensure_sdk_on_path()
from clove_sdk import CloveClient  # noqa: E402

STAGE_NAME = "report"


def main() -> int:
    client = CloveClient()
    if not client.connect():
        print("[report] ERROR: Failed to connect to Clove kernel")
        return 1

    try:
        client.register_name(STAGE_NAME)
        message = wait_for_message(client, expected_type="run_stage", expected_stage=STAGE_NAME)

        run_id = message.get("run_id", "run_000")
        artifacts_dir = Path(message.get("artifacts_dir", "artifacts"))
        logs_dir = Path(message.get("logs_dir", "logs"))
        config = message.get("config", {})
        input_payload = message.get("input", {})
        reply_to = message.get("reply_to", "orchestrator")

        run_dir = artifacts_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        log_path = logs_dir / run_id / f"{STAGE_NAME}.log"

        log_line(log_path, "stage start")
        maybe_fail_once(run_dir, STAGE_NAME, config)

        metrics_path = Path(input_payload.get("metrics_path", run_dir / "metrics.json"))
        model_path = Path(input_payload.get("model_path", run_dir / "model.json"))
        dataset_path = Path(input_payload.get("dataset_path", run_dir / "dataset.json"))

        metrics = read_json(metrics_path)
        model = read_json(model_path)
        dataset = read_json(dataset_path).get("molecules", [])

        report_lines = [
            "# Drug Research Pipeline Report",
            "",
            f"Run ID: {run_id}",
            "",
            "## Dataset",
            f"- Molecules: {len(dataset)}",
            "",
            "## Model",
            f"- Strategy: {model.get('strategy', 'n/a')}",
            f"- Feature: {model.get('feature', 'n/a')}",
            f"- Threshold: {model.get('threshold', 'n/a')}",
            "",
            "## Metrics",
            f"- Accuracy: {metrics.get('accuracy', 'n/a')}",
            "",
            "## Notes",
            "- This is a synthetic, non-clinical demo.",
        ]

        report_path = run_dir / "report.md"
        report_path.write_text("\n".join(report_lines), encoding="utf-8")

        output = {
            "report_path": str(report_path),
            "metrics_path": str(metrics_path),
            "model_path": str(model_path),
            "dataset_path": str(dataset_path),
        }
        metadata = {
            "format": "markdown",
        }
        stage_result = {
            "type": "stage_complete",
            "stage": STAGE_NAME,
            "run_id": run_id,
            "status": "ok",
            "output": output,
            "metadata": metadata,
        }

        write_json(run_dir / f"{STAGE_NAME}.json", stage_result)
        client.store(f"pipeline:{run_id}:{STAGE_NAME}", stage_result, scope="global")
        client.send_message(stage_result, to_name=reply_to)
        log_line(log_path, "stage complete")
    finally:
        client.disconnect()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
