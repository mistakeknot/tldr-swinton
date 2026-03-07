# Related Projects

| Project | What | Path |
|---------|------|------|
| **interbench** | Eval/regression for tldrs outputs | `core/interbench` (in Demarch monorepo) |

**interbench sync**: When adding new tldrs formats or flags, 4 interbench files must stay in sync. Use the automated check:
```bash
tldrs manifest | python3 /home/mk/projects/Demarch/core/interbench/scripts/check_tldrs_sync.py
```
Or use the `/tldrs-interbench-sync` skill for guided remediation.

## tldr-bench Datasets

Benchmark datasets live in the `tldr-bench/data` submodule (`github.com/mistakeknot/tldr-bench-datasets`).
```bash
git submodule update --init --recursive
cd tldr-bench/data && git lfs install && git lfs pull && cd -
```
Do not add large dataset files directly -- update the datasets repo and bump the submodule.

## Dev Reference

Debugging, testing, version history, and contributor procedures are in `docs/dev-reference.md`.
