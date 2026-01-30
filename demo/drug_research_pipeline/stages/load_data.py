"""Stage: load molecular dataset (synthetic placeholder)."""
from __future__ import annotations

import random
from pathlib import Path

from utils import ensure_sdk_on_path, log_line, maybe_fail_once, wait_for_message, write_json

ensure_sdk_on_path()
from clove_sdk import CloveClient  # noqa: E402

STAGE_NAME = "load_data"

SMILES_POOL = [
    "CCO",
    "CCN",
    "CCC",
    "C1=CC=CC=C1",
    "CC(=O)O",
    "CC(C)O",
    "CNC",
    "COC",
    "CCS",
    "C=CC",
    "CN(C)C",
    "CCCl",
]


def main() -> int:
    client = CloveClient()
    if not client.connect():
        print("[load_data] ERROR: Failed to connect to Clove kernel")
        return 1

    try:
        client.register_name(STAGE_NAME)
        message = wait_for_message(client, expected_type="run_stage", expected_stage=STAGE_NAME)

        run_id = message.get("run_id", "run_000")
        artifacts_dir = Path(message.get("artifacts_dir", "artifacts"))
        logs_dir = Path(message.get("logs_dir", "logs"))
        config = message.get("config", {})
        reply_to = message.get("reply_to", "orchestrator")

        run_dir = artifacts_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        log_path = logs_dir / run_id / f"{STAGE_NAME}.log"

        log_line(log_path, "stage start")
        maybe_fail_once(run_dir, STAGE_NAME, config)

        dataset_path = run_dir / "dataset.json"
        seed = int(config.get("seed", 1337))
        num_molecules = int(config.get("num_molecules", 12))
        rng = random.Random(seed)

        molecules = []
        for idx in range(num_molecules):
            smiles = SMILES_POOL[idx % len(SMILES_POOL)]
            label = 1 if ("N" in smiles or len(smiles) % 2 == 0) else 0
            molecules.append({
                "id": f"m{idx+1}",
                "smiles": smiles,
                "label": label,
                "activity": round(rng.random(), 4),
            })

        write_json(dataset_path, {"molecules": molecules})

        output = {
            "dataset_path": str(dataset_path),
            "count": len(molecules),
        }
        metadata = {
            "seed": seed,
            "num_molecules": num_molecules,
            "label_rule": "contains N or even length",
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
