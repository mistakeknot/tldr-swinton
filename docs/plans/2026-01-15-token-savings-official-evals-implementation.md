# Official Eval Dataset Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Bead:** `tldr-swinton-gey` (Task reference)

**Goal:** Provide official eval datasets (SWE-bench Lite/Verified, RepoBench, LongBench) via a dedicated datasets repo + submodule, and add dataset adapters + runners for token-savings benchmarks in `tldr-bench`.

**Architecture:** Store raw dataset files in the `tldr-bench-datasets` repo (with LFS there), mount as the `tldr-bench/data` submodule, normalize to `BenchInstance`, and extend dataset loader + runners to support new kinds. Provide verification scripts and task configs for repeatable token-only runs.

**Tech Stack:** Python 3.11, uv, Git LFS (in dataset repo), pytest.

---

### Task 1: Dataset repo + submodule (Implemented)

**Files:**
- Submodule: `tldr-bench/data` -> `https://github.com/mistakeknot/tldr-bench-datasets.git`
- Dataset repo: `~/tldr-bench-datasets` (contains `.gitattributes` + `data/` + manifests)

**Step 1: Verify submodule wiring**

```
git submodule status tldr-bench/data
git -C tldr-bench/data status -s
```

**Step 2: Verify dataset repo LFS config**

```
cat ~/tldr-bench-datasets/.gitattributes
```

**Step 3: Verify manifests present**

```
ls tldr-bench/data/data/swebench_lite
ls tldr-bench/data/data/swebench_verified
ls tldr-bench/data/data/repobench_python_v1.1
ls tldr-bench/data/data/longbench_v2
```

---

### Task 2: Add dataset verification tooling (Implemented)

**Files:**
- Create: `tldr-bench/scripts/data/verify_datasets.py`
- Create: `tldr-bench/scripts/data/lfs_setup.sh`
- Modify: `tldr-bench/README.md`

**Step 1: Run tests**

```
uv run pytest tldr-bench/tests/test_dataset_manifest.py -q
```
Expected: PASS.

---

### Task 3: Implement dataset adapters + loader support (Implemented)

**Files:**
- Create: `tldr-bench/tldr_bench/datasets/repobench.py`
- Create: `tldr-bench/tldr_bench/datasets/longbench.py`
- Modify: `tldr-bench/tldr_bench/datasets/loader.py`
- Modify: `tldr-bench/tldr_bench/datasets/__init__.py`
- Modify: `tldr-bench/tldr_bench/datasets/schema.py`

**Step 1: Run tests**

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
