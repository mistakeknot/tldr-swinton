# Log Schema

Each run appends a JSONL record with these fields.

Core metrics:

- task_id
- variant_id
- budget
- prompt_tokens
- completion_tokens
- tool_calls
- elapsed_ms
- success
- retries
- context_bytes
- context_tokens_estimate
- diff_hit_rate
- coverage_hit_rate
- symbol_etag_hit
- cassette_ref_ratio
- notes
- timestamp

Run metadata (optional flags):

- run_id
- task_suite
- benchmark
- dataset
- split
- instance_ids
- workspace
- max_iterations
- timeout_seconds
- tldrs_version
- shim_config
- seed
- prompt_budget
- context_strategy
- daemon_enabled
- agent
- model
- model_alias
- resolved_model
- config_id
- cli_version

System metadata (auto):

- host_os
- host_release
- host_arch
- python_version

Notes:

- `instance_ids` is populated from `--instance-ids` (comma-separated). IDs must not contain commas.

## Paired agent value run schema

`scripts/run_agent_value_eval.py` creates one run directory with:

- `metadata.json`: format version, source SHA, full hidden-corpus SHA-256,
  selected task IDs/conditions/repeats, requested model, reasoning effort,
  timeout, bootstrap seed, Codex/tldrs versions, Python version, and host data.
- `outcomes.jsonl`: append-only completed `RunOutcome` records. The stable cell
  ID is `<task>__<condition>__rNN`; resume refuses duplicate IDs.
- `traces/<cell>.jsonl`: raw Codex event stream.
- `messages/<cell>.md`: final agent message captured by Codex.
- `stderr/<cell>.log`: Codex process stderr.
- `patches/<cell>.diff`: binary-capable git patch, including newly created files.
- `graders/<cell>.stdout` and `.stderr`: hidden external-grader evidence.
- `report.json` and `report.md`: paired metrics, raw cells, fixed gates, and
  PASS/FAIL/INCONCLUSIVE verdict.

Each outcome records task, condition, repeat, agent exit/timeout, elapsed time,
patch hash, grader exit and test counts, contamination reasons, and native trace
metrics: model, input/cached/output/reasoning tokens, tool count/output bytes,
tldrs calls, raw-read calls, compactions, commands, and errors. Task success is
the external grader result, never the agent process exit code.

The fixed pilot gates are:

- no more than one additional adaptive failure;
- at least 20% median uncached-token savings on eligible tasks;
- no more than 5% median token overhead on negative controls;
- no more than 10% median latency regression;
- at least 80% routing precision.

Missing cells, baseline treatment leakage, unavailable adaptive tldrs, or other
contamination force an `INCONCLUSIVE` overall verdict.
