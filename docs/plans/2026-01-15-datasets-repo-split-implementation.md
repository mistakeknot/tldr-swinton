# Dataset Repo Split Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Bead:** `tldr-swinton-gey` (Task reference)

**Goal:** Move vendored datasets into a separate repo under `~/tldr-bench-datasets`, then point `tldr-swinton` to it via submodule so `mistakeknot/tldr-swinton` stays pushable.

**Architecture:** Create a dataset-only repo containing `tldr-bench/data` plus LFS config, then replace `tldr-swinton/tldr-bench/data` with a submodule pointing to the dataset repo. Update docs and tooling to use the submodule and avoid LFS in the main repo.

**Tech Stack:** Git, Git LFS, Python 3.11, uv.

---

### Task 1: Create dataset-only repo at `~/tldr-bench-datasets`

**Files:**
- Create: `~/tldr-bench-datasets/.gitattributes`
- Create: `~/tldr-bench-datasets/README.md`
- Create: `~/tldr-bench-datasets/data/...` (copied from `tldr-swinton/tldr-bench/data`)

**Step 1: Prepare repo directory**

Run:
```
rm -rf ~/tldr-bench-datasets
mkdir -p ~/tldr-bench-datasets
cd ~/tldr-bench-datasets

git init
```

**Step 2: Add LFS patterns**

Create `~/tldr-bench-datasets/.gitattributes`:
```
data/**/*.parquet filter=lfs diff=lfs merge=lfs -text
data/**/*.json filter=lfs diff=lfs merge=lfs -text
data/**/*.jsonl filter=lfs diff=lfs merge=lfs -text
data.json filter=lfs diff=lfs merge=lfs -text
```

**Step 3: Copy datasets**

Run:
```
cp -R /Users/sma/tldr-swinton/tldr-bench/data ./data
```

**Step 4: Add README**

Create `~/tldr-bench-datasets/README.md` describing dataset usage and LFS.

**Step 5: Commit**

```
git add .gitattributes README.md data

git commit -m "Add official eval datasets"
```

**Step 6: Push**

Add remote and push:
```
git remote add origin https://github.com/mistakeknot/tldr-bench-datasets.git
```

If remote already has conflicting history, confirm and then:
```
git push --force origin main
```

---

### Task 2: Replace `tldr-swinton/tldr-bench/data` with submodule

**Files:**
- Remove: `tldr-bench/data/**`
- Modify: `.gitattributes` (remove if unused)
- Modify: `tldr-bench/README.md`
- Modify: `tldr-bench/scripts/data/lfs_setup.sh`

**Step 1: Remove existing data directory**

```
cd /Users/sma/tldr-swinton

git rm -r tldr-bench/data
```

**Step 2: Remove .gitattributes (LFS patterns no longer needed)**

```
rm .gitattributes
```

**Step 3: Add submodule**

```
git submodule add https://github.com/mistakeknot/tldr-bench-datasets.git tldr-bench/data
```

**Step 4: Update README**

Update `tldr-bench/README.md` to instruct:
- `git submodule update --init --recursive`
- `git lfs install` + `git lfs pull` inside `tldr-bench/data`

**Step 5: Update LFS helper script**

Modify `tldr-bench/scripts/data/lfs_setup.sh` to operate in `tldr-bench/data`:
```
# use git -C "$ROOT_DIR/tldr-bench/data" lfs install
```

**Step 6: Commit**

```
git add .gitmodules tldr-bench/README.md tldr-bench/scripts/data/lfs_setup.sh

git add -u

git commit -m "Split datasets into submodule"
```

---

### Task 3: Verification

**Step 1: Submodule init**

```
git submodule update --init --recursive
```

**Step 2: Verify datasets**

```
uv run python tldr-bench/scripts/data/verify_datasets.py
```
Expected: `OK`

**Step 3: Push tldr-swinton**

```
git push
```
