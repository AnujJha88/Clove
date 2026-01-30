# Clove Drug Research ML Pipeline Demo

## Concept

A failure-aware, research-grade machine learning pipeline for drug discovery workflows.
This demo intentionally avoids clinical decision-making and instead focuses on:
- data processing
- ML experimentation
- reproducibility
- auditability

**Goal:** Show how Clove provides OS-level isolation, supervised execution, and
artifact preservation for long-running, failure-prone drug research pipelines.

---

## Demo Objectives

1. Run each pipeline stage as an isolated OS process under Clove.
2. Enforce CPU, memory, and runtime limits per stage.
3. Detect and recover from failures without losing intermediate artifacts.
4. Produce a complete audit trail for reproducibility.

---

## Pipeline Workflow

1. Load molecular dataset (public or synthetic)
2. Molecule featurization (fingerprints / graph features)
3. Train predictive model (activity / toxicity proxy)
4. Evaluate and validate model
5. Generate research report
6. Archive models and artifacts

---

## Execution Model (Clove)

- Each stage runs as a supervised OS process.
- Clove enforces resource limits (CPU/memory/runtime).
- Clove captures exit signals, logs, and metrics.
- Failure policies handle retries or fallbacks per stage.

### Clove SDK Usage (Conceptual)

- `CloveClient()` or `CloveRuntime()` in `main.py` orchestrates stages.
- `spawn()` (or equivalent) launches each stage with:
  - `limits`: CPU, memory, runtime
  - `restart_policy`: on-failure with max retries
  - `env`/`args`: stage-specific configuration
- `store()` / `fetch()` or IPC channels pass artifacts and metadata between stages.
- `audit_log()` / metrics API records execution events.

### Small Clove SDK Use Cases (Quick Guide)

1. **Run a single stage with limits**
   - Use `spawn()` with explicit `limits` to guarantee isolation.
   - Example (conceptual):
     ```python
     with CloveClient() as client:
         client.spawn(
             name="featurize",
             script="stages/featurize.py",
             limits={"cpu": 1, "memory_mb": 1024, "runtime_s": 300}
         )
     ```

2. **Retry on failure**
   - Set `restart_policy` to recover from OOMs or bad inputs.
   - Example:
     ```python
     client.spawn(
         name="train",
         script="stages/train.py",
         restart_policy={"on_failure": True, "max_retries": 2}
     )
     ```

3. **Pass artifacts between stages**
   - Write outputs to `artifacts/` and register with `store()` or send via IPC.
   - Example:
     ```python
     run_id = client.store({"features_path": "artifacts/features.parquet"})
     client.send({"run_id": run_id}, to_name="train")
     ```

4. **Capture audit trail**
   - Log parameters, seeds, and exit status to the audit log.
   - Example:
     ```python
     client.audit_log({"stage": "evaluate", "metrics": metrics})
     ```

5. **Pause or stop a runaway stage**
   - Use `pause()` / `kill()` to halt a misbehaving process.
   - Example:
     ```python
     client.pause(name="train")
     client.kill(name="train")
     ```

---

## Failure Scenarios to Demonstrate

1. **Memory exhaustion** during featurization.
2. **Training instability** due to malformed molecular inputs.
3. **Timeouts** on long-running model training.

**Expected behavior:**
- The failing process is terminated safely.
- The pipeline retries with adjusted parameters.
- Intermediate artifacts remain intact.

---

## Auditability and Reproducibility

Each run should emit:
- dataset identifiers and versions
- featurization parameters
- model configuration and hyperparameters
- random seeds
- evaluation metrics
- execution logs and exit codes
- artifact manifests (models, reports, intermediate data)

---

## Files to Create

```
demo/
├── PLAN.md
├── README.md                      # Overview, setup, run instructions
├── drug_research_pipeline/
│   ├── main.py                    # Orchestrates pipeline stages via Clove
│   ├── stages/
│   │   ├── load_data.py
│   │   ├── featurize.py
│   │   ├── train.py
│   │   ├── evaluate.py
│   │   ├── report.py
│   │   └── archive.py
│   ├── configs/
│   │   ├── dataset.yaml
│   │   ├── featurize.yaml
│   │   ├── train.yaml
│   │   ├── eval.yaml
│   │   └── clove_limits.yaml      # CPU/mem/runtime + retry policy
│   ├── artifacts/                 # Generated outputs (models, reports)
│   └── logs/                      # Stage logs and audit trail
└── comparison.md                  # Optional: baseline vs Clove summary
```

---

## Implementation Plan

### Phase 1: Pipeline Skeleton
1. Create directory structure.
2. Add config files for dataset + limits + failure toggles.
3. Define a stage contract:
   - Input: artifact path + config
   - Output: artifact path + metadata JSON
4. Implement stage scripts with placeholder logic and clear I/O contracts.
5. Implement `main.py` with Clove SDK orchestration:
   - Initialize client/runtime
   - Spawn each stage with limits and retry policy
   - Persist artifacts and metadata via store/fetch or IPC
   - Collect exit status and logs

### Phase 2: Failure Injection
1. Add controlled OOM in `featurize.py` (toggle via config).
2. Add malformed input path in `train.py` (toggle via config).
3. Add timeout config for long training.
4. Ensure Clove restarts or retries and preserves artifacts.
5. Verify audit logs and artifacts remain intact after retries.

### Phase 3: Auditability
1. Emit metadata manifest per stage.
2. Capture seeds, params, and metrics.
3. Generate a final research report with run summary.

---

## Implementation Modes

### Mode A: Normal (Lightweight)

**Purpose:** fast demo, minimal deps, real dataset (small/local).

- **Data:** real dataset file (small/local JSON)
- **Featurize:** simple counts (length, atom counts)
- **Model:** threshold or simple baseline
- **Metrics:** accuracy only
- **Artifacts:** small JSON outputs
- **Dependencies:** stdlib only (no heavy ML libs)

### Mode B: All Guns Blazing (Heavy ML)

**Purpose:** realistic drug ML pipeline with modern tooling.

#### Model Stack (Config-Driven)

**Baselines**
- RDKit Morgan fingerprints + RandomForest (classification/regression)
- RDKit descriptors + XGBoost/LightGBM (optional)

**Neural Models**
- MLP on fingerprints (PyTorch)
- Optional GNN (PyTorch Geometric) on molecular graphs

#### Featurization Options

- `fingerprints`: RDKit Morgan fingerprints
- `descriptors`: RDKit PhysChem descriptors
- `graphs`: node/edge features for GNNs

#### Metrics

- Classification: ROC-AUC, PR-AUC, accuracy
- Regression: RMSE, MAE, R2

#### Artifacts

- `features.npz` or `features.parquet`
- `model.pt` (PyTorch) or `model.pkl` (sklearn)
- `metrics.json`
- training curves (optional)

---

## Mode Selection (How to Switch)

- **Dataset**: set `configs/dataset.yaml` `path` to a real dataset for both modes.
- **Featurizer**: set `configs/featurize.yaml` `method` to `fingerprints`, `descriptors`, or `graphs`.
- **Model**: set `configs/train.yaml` `model` to `rf`, `xgb`, `mlp`, or `gnn`.
- **Dependencies**: Heavy ML requires RDKit + ML libs; Normal uses stdlib only.

---

## Wiring Details (Stage Contracts)

### Stage 1: `load_data.py`
- **Input:** `configs/dataset.yaml`
- **Output:** `artifacts/<run_id>/dataset.json`
- **Metadata:** dataset name, version, checksum, split info

### Stage 2: `featurize.py`
- **Input:** dataset + `configs/featurize.yaml`
- **Output:** `features.npz` (or parquet), `feature_meta.json`
- **Failure Injection:** OOM or malformed molecule toggle

### Stage 3: `train.py`
- **Input:** features + labels + `configs/train.yaml`
- **Output:** `model.pt` / `model.pkl`, `train_metrics.json`
- **Failure Injection:** malformed input / timeout toggle

### Stage 4: `evaluate.py`
- **Input:** model + test split
- **Output:** `metrics.json`, `predictions.json`

### Stage 5: `report.py`
- **Input:** metrics + model metadata
- **Output:** `report.md` (summary + tables)

### Stage 6: `archive.py`
- **Input:** artifacts directory
- **Output:** `manifest.json` (all outputs + sizes + hashes)

---

## Clove SDK Wiring (How It Runs)

1. `main.py` spawns each stage via `CloveClient.spawn()` with limits from `configs/clove_limits.yaml`.
2. Orchestrator sends a `run_stage` IPC message including:
   - `run_id`, `artifacts_dir`, `logs_dir`
   - `config` (stage-specific)
   - `input` (previous stage output)
3. Stage registers its name, runs once, writes artifacts, and sends `stage_complete`.
4. Orchestrator waits for completion or retries (Clove restart + resend).
5. Final summary stored in `artifacts/<run_id>/pipeline_summary.json`.

---

## Demo Script (High Level)

1. Start Clove kernel/runtime.
2. Run `demo/drug_research_pipeline/main.py`.
3. Observe failure, retry, and recovery.
4. Inspect `artifacts/` and `logs/` for audit trail.

---

## Success Criteria

- Failures do not crash the entire pipeline.
- Artifacts persist across retries.
- Logs and metadata are sufficient to reproduce results.
- Final report is generated after recovery.
