"""Stage: evaluate model (placeholder)."""
from __future__ import annotations

from pathlib import Path

from utils import ensure_sdk_on_path, log_line, maybe_fail_once, read_json, wait_for_message, write_json

ensure_sdk_on_path()
from clove_sdk import CloveClient  # noqa: E402

STAGE_NAME = "evaluate"


def main() -> int:
    client = CloveClient()
    if not client.connect():
        print("[evaluate] ERROR: Failed to connect to Clove kernel")
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

        model_path = Path(input_payload.get("model_path", run_dir / "model.json"))
        features_path = Path(input_payload.get("features_path", run_dir / "features.json"))
        dataset_path = Path(input_payload.get("dataset_path", run_dir / "dataset.json"))

        model = read_json(model_path)
        features = read_json(features_path).get("features", [])
        dataset = read_json(dataset_path).get("molecules", [])
        labels = {mol.get("id"): mol.get("label", 0) for mol in dataset}

        threshold = float(model.get("threshold", 0))
        correct = 0
        total = 0
        for feat in features:
            pred = 1 if feat.get("length", 0) >= threshold else 0
            label = labels.get(feat.get("id"), 0)
            correct += 1 if pred == label else 0
            total += 1

        accuracy = round(correct / total, 4) if total else 0.0
        metrics = {"accuracy": accuracy, "total": total}

        metrics_path = run_dir / "metrics.json"
        write_json(metrics_path, metrics)

        output = {
            "metrics_path": str(metrics_path),
            "model_path": str(model_path),
            "features_path": str(features_path),
            "dataset_path": str(dataset_path),
        }
        metadata = {
            "metrics": config.get("metrics", ["accuracy"]),
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
