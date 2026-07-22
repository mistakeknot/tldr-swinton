---
title: "Git LFS Submodule Blocks Claude Code Plugin Install"
category: build-errors
tags: [git, lfs, submodule, plugin-install, claude-code, gitmodules]
module: .gitmodules
symptoms:
  - "Smudge error: Error downloading object"
  - "This repository exceeded its LFS budget"
  - "smudge filter lfs failed"
  - "Unable to checkout in submodule path 'tldr-bench/data'"
severity: high
date_solved: 2026-02-08
date_updated: 2026-07-22
---

## Problem

When installing tldr-swinton as a Claude Code plugin, the installation fails during the repository clone phase:

```
Error downloading object: data/longbench_v2/data.json (15d61c2): Smudge error:
batch response: This repository exceeded its LFS budget.
fatal: data/longbench_v2/data.json: smudge filter lfs failed
fatal: Unable to checkout '73c7ef7e...' in submodule path 'tldr-bench/data'
```

**What's happening:**
- `claude plugin install` runs `git clone --recurse-submodules`
- The `.gitmodules` file includes a submodule entry for `tldr-bench/data`
- This submodule points to a GitHub repository with a 466MB dataset stored using Git LFS
- The LFS bandwidth quota for that repository has been exceeded
- The clone fails because it cannot fetch the LFS objects in that submodule

**Why this is a problem:**
- The benchmark dataset is completely irrelevant to plugin functionality
- The plugin should work without any benchmark data being present
- Developers installing the plugin for use in Claude Code should not be blocked by an unrelated data dependency
- The plugin installer has no way to skip submodule downloads

## Root Cause Analysis

### Submodule Configuration
The repository's `.gitmodules` file originally had:

```ini
[submodule "tldr-bench/data"]
	path = tldr-bench/data
	url = https://github.com/mistakeknot/tldr-bench-datasets.git
```

Without explicit configuration, `git clone --recurse-submodules` will:
1. Recursively initialize ALL submodules
2. Attempt to fetch all submodule contents
3. Fail if any submodule download encounters an error

### LFS Budget Exhaustion
The `tldr-bench-datasets` repository contains large benchmark files stored with Git LFS. Free GitHub LFS accounts have limited bandwidth (typically 1GB/month), which is easily exceeded by repeated clones and pulls across multiple machines or CI/CD pipelines.

### Design Conflict
- **Plugin context**: A plugin should install cleanly without side dependencies
- **Development context**: Benchmarking requires the full dataset
- **Deployment context**: Production deployment doesn't need the dataset

The `.gitmodules` configuration didn't distinguish between these contexts.

## Superseded Mitigation

Add two configuration options to the `tldr-bench/data` submodule entry in `.gitmodules`:

```ini
[submodule "tldr-bench/data"]
	path = tldr-bench/data
	url = https://github.com/mistakeknot/tldr-bench-datasets.git
	update = none
	fetchRecurseSubmodules = false
```

**What these options do:**

- **`update = none`**: Git will not automatically update this submodule during `git pull` or `git submodule update`. It must be explicitly requested.
- **`fetchRecurseSubmodules = false`**: Git will not recursively fetch this submodule during `git clone --recurse-submodules` or `git fetch --recurse-submodules`.

This stopped recursive LFS downloads, but it did not make the repository
packageable. The Intercore publisher added a tracked-tree cache in 2026. Its
copier enumerates `git ls-files` and accepts only regular files and symlinks. A
mode-160000 gitlink is exposed as a directory in an uninitialized checkout, so
the 0.8.0 release cache failed with:

```
tracked plugin path "tldr-bench/data" is not a regular file or symlink
```

## Working Solution

Remove the dataset gitlink from the plugin repository entirely, ignore the
local checkout path, and clone the dataset repository explicitly when running
official benchmarks:

```bash
git clone https://github.com/mistakeknot/tldr-bench-datasets.git tldr-bench/data
git -C tldr-bench/data lfs install
git -C tldr-bench/data lfs pull
```

This keeps the existing benchmark paths stable without placing a gitlink in
the plugin's tracked file set.

**Effect on developer workflows:**
- Developers who need benchmark data clone it explicitly using the commands above.
- This explicit step ensures they understand they're downloading large LFS objects
- It separates "install the plugin" (automatic) from "fetch benchmark data" (opt-in)

### Implementation Status
✅ **COMPLETED** — the dataset repository is no longer a tracked submodule; `tldr-bench/data/` is an ignored opt-in checkout.

## Prevention Strategy

### For This Project
1. ✅ Assert the plugin's tracked tree contains no mode-160000 gitlinks
2. ✅ Test `claude plugin install tldr-swinton` on a clean machine to confirm it works
3. Document in `AGENTS.md` that benchmark data initialization is opt-in

### General Guidelines
- **Never put large LFS data in submodules of repos that also serve as plugins/packages**
  - `update = none` avoids downloads but does not make a gitlink packageable
- **Prefer separate hosting for large datasets**
  - Consider hosting benchmark data on S3, Hugging Face Datasets, or a dedicated data repository
  - Link to it in documentation rather than embedding it as a submodule
- **Document submodule handling for plugins**
  - Make it clear which submodules are required vs. optional
  - Provide installation instructions for optional data
- **Test plugin installation from a clean machine**
  - After any `.gitmodules` change, verify on a fresh clone
  - Simulate the exact `claude plugin install` workflow

### Testing Checklist
- [ ] `git clone <repo>` succeeds without fetching benchmark data
- [ ] `claude plugin install tldr-swinton` succeeds on a machine with no prior checkout
- [ ] Plugin commands work (`/tldrs-find`, `/tldrs-context`, etc.)
- [ ] Explicitly cloning `tldr-bench-datasets` into `tldr-bench/data` succeeds
- [ ] `uv run pytest` passes in the cloned repository

## Technical Details

### Git Configuration Reference

**Relevant `.gitmodules` options:**

| Option | Default | Effect |
|--------|---------|--------|
| `path` | (required) | Local directory for submodule |
| `url` | (required) | Remote repository URL |
| `update` | `checkout` | How to update: `none`, `checkout`, `rebase`, `merge` |
| `fetchRecurseSubmodules` | `true` | Whether `fetch --recurse-submodules` includes this submodule |
| `ignore` | `none` | Ignore submodule in `git status` output |

**Related git config:**

```bash
# View current submodule configuration
git config --file .gitmodules --list

# Temporarily skip submodule initialization
git clone --no-recurse-submodules <repo>

# Manual submodule update (after cloning with --no-recurse-submodules)
git submodule update --init --recursive

# Initialize only specific submodule
git submodule update --init tldr-bench/data
```

### How Claude Code Plugin Installer Works

Claude Code's plugin installer uses git commands internally:

```bash
# Typical install flow (simplified)
git clone --recurse-submodules https://github.com/mistakeknot/interagency-marketplace.git
cd interagency-marketplace
# ...reads .claude-plugin/marketplace.json to find tldr-swinton
git clone --recurse-submodules https://github.com/mistakeknot/tldr-swinton.git plugins/tldr-swinton
```

The `--recurse-submodules` flag is used to ensure complete repository state, but it conflicts with opt-in data dependencies.

### Why Not Keep the Gitlink?

- **`.gitignore`**: Works only after the gitlink is removed from the index; it then keeps the opt-in checkout local
- **`sparse-checkout`**: Requires explicit setup and isn't inherited by clone
- **`.gitmodules` configuration**: Can suppress updates, but the gitlink remains in `git ls-files` and breaks tracked-tree packaging

## Related Issues

- LFS bandwidth exhaustion is common with free accounts
- Many projects have similar conflicts between "plugin mode" and "development mode"
- The benchmark data isn't actually needed until `uv run pytest` is invoked
- Optional dependencies in git are underutilized; most repos put everything in .gitmodules

## See Also

- `.gitmodules` — Contains only package-compatible development submodules
- `AGENTS.md` — Development workflow documentation
- `docs/agent-workflow.md` — Full agent integration guide
- `tldr-bench/data` — Ignored path for an opt-in dataset checkout
