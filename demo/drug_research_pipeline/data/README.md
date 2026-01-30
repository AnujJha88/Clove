# Dataset Preparation Guide

This demo expects a small molecule dataset in JSON format.

## Folder

Put datasets in:

```
demo/drug_research_pipeline/data/
```

## Expected JSON schema

```json
{
  "molecules": [
    {
      "id": "m1",
      "smiles": "CCO",
      "label": 1,
      "activity": 0.42
    }
  ]
}
```

### Field notes

- `id` (string): unique molecule id
- `smiles` (string): SMILES string
- `label` (int): 0/1 class label
- `activity` (float): optional continuous proxy

## Update config

Point the pipeline to your dataset by editing:

`demo/drug_research_pipeline/configs/dataset.yaml`

Example:

```yaml
name: "custom_dataset"
version: "v1"
path: "data/my_dataset.json"
seed: 1337
num_molecules: 0
```

If `path` is set, the loader can be updated later to prefer the file over synthetic generation.

## Quick validation (optional)

```bash
python3 - <<'PY'
import json
from pathlib import Path
p = Path('demo/drug_research_pipeline/data/my_dataset.json')
obj = json.loads(p.read_text())
assert 'molecules' in obj and isinstance(obj['molecules'], list)
print('ok:', len(obj['molecules']))
PY
```
