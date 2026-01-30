# Clove Drug Research Pipeline Demo (Scaffold)

This demo shows a failure-aware ML pipeline for drug research using the Clove SDK.
Each stage is run as an isolated OS process, supervised by the Clove kernel.

## What it does

Pipeline stages:
1. Load synthetic dataset
2. Featurize molecules
3. Train a placeholder model
4. Evaluate metrics
5. Generate a report
6. Archive artifacts

## Prereqs

- Clove kernel running (`./build/clove_kernel` or `sudo ./build/clove_kernel`)
- Python 3.10+
- Optional: `pip install pyyaml` for config parsing

## Run

From repo root:

```bash
python3 demo/drug_research_pipeline/main.py
```

Artifacts and logs go to:

- `demo/drug_research_pipeline/artifacts/<run_id>/`
- `demo/drug_research_pipeline/logs/<run_id>/`

## Failure injection

Toggle failures in configs:

- `configs/featurize.yaml`: `fail_once: true`, `fail_mode: memory|exception|exit|timeout`
- `configs/train.yaml`: `fail_once: true`, `fail_mode: malformed|exception|exit|timeout`

The stage will fail once, then succeed on retry (Clove restart policy + orchestrator resend).

## Clove SDK calls used

- `spawn()` for process isolation and resource limits
- `register_name()`, `send_message()`, `recv_messages()` for IPC
- `store()` for persisting stage outputs
- `get_audit_log()` (optional via `--dump-audit`)

## Notes

- This is a synthetic, non-clinical demo.
- Replace the placeholder stages with real dataset/model logic later.
