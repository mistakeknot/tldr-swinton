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
