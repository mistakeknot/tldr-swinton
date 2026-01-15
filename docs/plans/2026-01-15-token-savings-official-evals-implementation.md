# Official Eval Dataset Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Bead:** `tldr-swinton-gey` (Task reference)

**Goal:** Vendor official eval datasets (SWE-bench Lite/Verified, RepoBench, LongBench) with Git LFS and add dataset adapters + runners for token-savings benchmarks in `tldr-bench`.

**Architecture:** Store raw dataset files under `tldr-bench/data/` with per-dataset manifests, normalize to `BenchInstance`, and extend dataset loader + runners to support new kinds. Provide verification scripts and task configs for repeatable token-only runs.

**Tech Stack:** Python 3.11, uv, Git LFS, pytest.

---

### Task 1: Add Git LFS tracking + dataset skeletons

**Files:**
- Create: `.gitattributes`
- Create: `tldr-bench/data/swebench_lite/README.md`
- Create: `tldr-bench/data/swebench_lite/manifest.json`
- Create: `tldr-bench/data/swebench_verified/README.md`
- Create: `tldr-bench/data/swebench_verified/manifest.json`
- Create: `tldr-bench/data/repobench_python_v1.1/README.md`
- Create: `tldr-bench/data/repobench_python_v1.1/manifest.json`
- Create: `tldr-bench/data/longbench_v2/README.md`
- Create: `tldr-bench/data/longbench_v2/manifest.json`

**Step 1: Add LFS patterns**

Create `.gitattributes`:
```
tldr-bench/data/**/*.parquet filter=lfs diff=lfs merge=lfs -text
tldr-bench/data/**/*.json filter=lfs diff=lfs merge=lfs -text
tldr-bench/data/**/*.jsonl filter=lfs diff=lfs merge=lfs -text
```

**Step 2: Create dataset folder READMEs**

Example README content:
```
# SWE-bench Lite (vendored)
Source: https://huggingface.co/datasets/SWE-bench/SWE-bench_Lite
Files: data/*.json
Notes: Dataset files are tracked via Git LFS.
```

**Step 3: Add manifests with placeholders**

Example manifest structure:
```json
{
  "dataset": "swebench_lite",
  "source": "https://huggingface.co/datasets/SWE-bench/SWE-bench_Lite",
  "revision": "unknown",
  "files": [
    {"name": "data/dev-00000-of-00001.parquet", "bytes": 0, "sha256": ""},
    {"name": "data/test-00000-of-00001.parquet", "bytes": 0, "sha256": ""}
  ]
}
```

**Step 4: Commit**

```
git add .gitattributes tldr-bench/data/*/README.md tldr-bench/data/*/manifest.json
git commit -m "Add LFS tracking and dataset skeletons"
```

---

### Task 2: Vendor dataset files under Git LFS

**Files:**
- Add: `tldr-bench/data/swebench_lite/data/*.parquet`
- Add: `tldr-bench/data/swebench_verified/data/*.parquet`
- Add: `tldr-bench/data/repobench_python_v1.1/data/*.json` (or .parquet)
- Add: `tldr-bench/data/longbench_v2/data.json`
- Modify: `tldr-bench/data/*/manifest.json`

**Step 1: Install Git LFS and pull pointers**

Run:
```
git lfs install
```

**Step 2: Download dataset files**

Download files into each dataset folder (use official URLs). Example:
```
curl -L -o tldr-bench/data/longbench_v2/data.json \
  https://huggingface.co/datasets/THUDM/LongBench-v2/resolve/main/data.json
```

**Step 3: Update manifest sizes + hashes**

Compute SHA256 and update manifests:
```
python - <<'PY'
import hashlib, json, pathlib
path = pathlib.Path("tldr-bench/data/longbench_v2/data.json")
sha = hashlib.sha256(path.read_bytes()).hexdigest()
print(path, sha, path.stat().st_size)
PY
```

**Step 4: Commit**

```
git add tldr-bench/data
git commit -m "Vendor official eval datasets"
```

---

### Task 3: Add dataset verification tooling

**Files:**
- Create: `tldr-bench/scripts/data/verify_datasets.py`
- Create: `tldr-bench/scripts/data/lfs_setup.sh`
- Modify: `tldr-bench/README.md`

**Step 1: Write failing test**

Create `tldr-bench/tests/test_dataset_manifest.py` with:
```python
from tldr_bench.data import verify_dataset_manifests

def test_verify_manifests_ok(tmp_path):
    assert verify_dataset_manifests(tmp_path) == []
```

Expected: FAIL (module missing).

**Step 2: Implement manifest verification**

Add `tldr_bench/data/__init__.py` and `verify_dataset_manifests()` to scan
`tldr-bench/data/*/manifest.json`, confirm files exist, and verify sha256.

**Step 3: Wire scripts**

- `scripts/data/verify_datasets.py` calls `verify_dataset_manifests()`.
- `scripts/data/lfs_setup.sh` runs `git lfs install` and validates `.gitattributes`.

**Step 4: Run tests**

```
uv run pytest tldr-bench/tests/test_dataset_manifest.py -q
```
Expected: PASS.

**Step 5: Commit**

```
git add tldr-bench/scripts/data tldr-bench/tests/test_dataset_manifest.py \
  tldr-bench/tldr_bench/data/__init__.py tldr-bench/README.md
git commit -m "Add dataset manifest verification"
```

---

### Task 4: Implement dataset adapters + loader support

**Files:**
- Create: `tldr-bench/tldr_bench/datasets/repobench.py`
- Create: `tldr-bench/tldr_bench/datasets/longbench.py`
- Modify: `tldr-bench/tldr_bench/datasets/loader.py`
- Modify: `tldr-bench/tldr_bench/datasets/__init__.py`
- Modify: `tldr-bench/tldr_bench/datasets/schema.py`

**Step 1: Add split support**

Update `BenchInstance` to include `split: str | None = None` and include it in
`to_dict()` when set.

**Step 2: Write adapter tests**

Add fixtures under `tldr-bench/tests/fixtures/datasets/` and tests:
- `tests/test_repobench_adapter.py`
- `tests/test_longbench_adapter.py`

Example test shape:
```python
from tldr_bench.datasets.repobench import normalize_record

def test_repobench_prompt():
    record = {"id": "x", "prompt": "code", "completion": "out"}
    inst = normalize_record(record)
    assert inst.prompt == "code"
    assert inst.instance_id == "x"
```
Expected: FAIL (module missing).

**Step 3: Implement adapters**

`repobench.py` should:
- Choose `instance_id` from `id` or `task_id`.
- Use `prompt` from `prompt` or `input`.
- Store `completion` in metadata if present.

`longbench.py` should:
- Use `dataset` + `id` to build `instance_id`.
- Use `input` as prompt.
- Store `output`/`answers` in metadata.

**Step 4: Update loader**

Extend `_detect_kind()`:
- Detect `"repobench"` by filename or `repo_name`/`completion` keys.
- Detect `"longbench"` by filename or `input`/`output` keys.

Wire `load_dataset()` to call new adapters.

**Step 5: Run tests**

```
uv run pytest tldr-bench/tests/test_repobench_adapter.py \
  tldr-bench/tests/test_longbench_adapter.py -q
```
Expected: PASS.

**Step 6: Commit**

```
git add tldr-bench/tldr_bench/datasets \
  tldr-bench/tests/test_repobench_adapter.py \
  tldr-bench/tests/test_longbench_adapter.py
git commit -m "Add RepoBench and LongBench adapters"
```

---

### Task 5: Add task configs for new datasets

**Files:**
- Modify: `tldr-bench/tldr_bench/tasks/curated.yaml`
- Create: `tldr-bench/tldr_bench/tasks/official_datasets.yaml`

**Step 1: Add dataset tasks**

Example task entry:
```yaml
- id: swebench-lite-tokens
  runner: dataset
  dataset_path: tldr-bench/data/swebench_lite/data/test-00000-of-00001.parquet
  dataset_kind: swebench
```

**Step 2: Update loader if needed**

Ensure `resolve_task_file()` can load `official_datasets.yaml`.

**Step 3: Commit**

```
git add tldr-bench/tldr_bench/tasks/curated.yaml \
  tldr-bench/tldr_bench/tasks/official_datasets.yaml
git commit -m "Add official dataset task configs"
```

---

### Task 6: README updates (tldr-bench)

**Files:**
- Modify: `tldr-bench/README.md`

**Step 1: Add data setup section**

Include:
- `git lfs install` and `git lfs pull`
- dataset locations under `data/`
- `scripts/data/verify_datasets.py` usage

**Step 2: Add token-only run examples**

Examples:
```
python scripts/run_bench.py --tasks official_datasets --variant baselines
```

**Step 3: Commit**

```
git add tldr-bench/README.md
git commit -m "Document official dataset setup"
```

---

### Task 7: End-to-end verification

**Step 1: Run dataset verification**

```
python tldr-bench/scripts/data/verify_datasets.py
```
Expected: no errors.

**Step 2: Dry-run task listing**

```
python tldr-bench/scripts/run_bench.py --tasks official_datasets --list-tasks
```
Expected: task IDs printed.

**Step 3: Commit results note (optional)**

If any changes from verification scripts: commit with a short message.

