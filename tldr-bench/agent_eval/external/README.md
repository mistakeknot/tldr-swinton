# External agent-value corpus

This corpus validates the Context Gateway outside the tldr-swinton repository.
Sources are prepared as clean detached checkouts from `sources.yaml`; mutation
and grader files remain in this evaluator directory and are never copied into
the model workspace.

| Source | Language | Revision | License | Tasks |
|---|---|---|---|---|
| `pallets/itsdangerous` | Python | `672971d66a2ef9f85151e53283113f33d642dabd` | BSD-3-Clause | base64 padding; key rotation |
| `google/go-cmp` | Go | `b133f1f1932e48f466f597a3346ce6f5a49a0dc1` | BSD-3-Clause | empty collections; approximate tolerance |

Prepare the ignored source checkouts:

```bash
PYTHONPATH=tldr-bench uv run python \
  tldr-bench/scripts/prepare_agent_value_sources.py \
  --manifest tldr-bench/agent_eval/external/sources.yaml \
  --output-dir tldr-bench/.agent-eval-sources
```

Validate corpus causality before spending model tokens:

```bash
PYTHONPATH=tldr-bench uv run pytest \
  tldr-bench/tests/test_agent_eval_sources.py -q
```

The validation gate materializes every mutation from the pinned source, proves
the hidden grader fails, reverses only the declared mutation, and proves the
same grader passes. Go graders add a temporary targeted test file after agent
patch capture and remove it before returning.
