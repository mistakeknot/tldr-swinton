import argparse
import json
import os
from pathlib import Path

from tldr_bench.runners.router import run_task as run_task_router
from tldr_bench.results import default_results_path
from tldr_bench.logger import JsonlLogger
from tldr_bench.meta import system_metadata
from tldr_bench.tasks import load_tasks, resolve_task_file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--help-variants", action="store_true")
    parser.add_argument("--list-tasks", action="store_true")
    parser.add_argument("--tasks", default=None)
    parser.add_argument("--variant", default=None)
    parser.add_argument("--filter", default=None)
    parser.add_argument("--allow-cli", action="store_true")
    parser.add_argument("--print-results", action="store_true")
    parser.add_argument("--agent", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--model-alias", default=None)
    parser.add_argument("--resolved-model", default=None)
    parser.add_argument("--config-id", default=None)
    parser.add_argument("--cli-version", default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--task-suite", default=None)
    parser.add_argument("--benchmark", default=None)
    parser.add_argument("--dataset", default=None)
    parser.add_argument("--split", default=None)
    parser.add_argument("--instance-ids", default=None)
    parser.add_argument("--workspace", default=None)
    parser.add_argument("--max-iterations", type=int, default=None)
    parser.add_argument("--timeout-seconds", type=int, default=None)
    parser.add_argument("--tldrs-version", default=None)
    parser.add_argument("--shim-config", default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--prompt-budget", type=int, default=None)
    parser.add_argument("--context-strategy", default=None)
    parser.add_argument("--daemon-enabled", action="store_true", default=None)
    parser.add_argument("--results-file", default=None)
    parser.add_argument("--results-prefix", default=None)
    parser.add_argument("--results-dir", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.help_variants:
        print("baselines, difflens, symbolkite, cassette, coveragelens")
        return 0
    if args.tasks:
        task_file = resolve_task_file(args.tasks)
        if args.dry_run or args.list_tasks:
            tasks = load_tasks(task_file)
        else:
            tasks = load_tasks(task_file)
        filters = [token.strip() for token in (args.filter or "").split(",") if token.strip()]

        def matches(task_id: str) -> bool:
            if not filters:
                return True
            return any(token in task_id for token in filters)

        if args.list_tasks:
            for task in tasks:
                if not matches(task.get("id", "")):
                    continue
                print(task.get("id", "<missing-id>"))
            return 0
        if args.variant:
            logger = None
            if args.print_results:
                if args.results_file:
                    path = Path(args.results_file)
                else:
                    if args.results_dir:
                        os.environ["TLDR_BENCH_RESULTS_DIR"] = args.results_dir
                    prefix = args.results_prefix if args.results_prefix else "run-"
                    path = default_results_path(prefix=prefix)
                logger = JsonlLogger(path)
            host_metadata = system_metadata()
            instance_ids = None
            if args.instance_ids:
                instance_ids = [
                    token.strip()
                    for token in args.instance_ids.split(",")
                    if token.strip()
                ]
            for task in tasks:
                task_id = task.get("id", "")
                if not matches(task_id):
                    continue
                if task.get("bench_command") and not args.allow_cli:
                    continue
                if args.dry_run:
                    print(task_id)
                    continue
                run_config = {
                    "tokenizer_model": args.resolved_model or args.model,
                }
                result = run_task_router(task, args.variant, run_config)
                result.update(host_metadata)
                if args.agent:
                    result["agent"] = args.agent
                if args.model:
                    result["model"] = args.model
                if args.model_alias:
                    result["model_alias"] = args.model_alias
                if args.resolved_model:
                    result["resolved_model"] = args.resolved_model
                if args.config_id:
                    result["config_id"] = args.config_id
                if args.cli_version:
                    result["cli_version"] = args.cli_version
                if args.run_id:
                    result["run_id"] = args.run_id
                if args.task_suite:
                    result["task_suite"] = args.task_suite
                if args.benchmark:
                    result["benchmark"] = args.benchmark
                if args.dataset:
                    result["dataset"] = args.dataset
                if args.split:
                    result["split"] = args.split
                if instance_ids:
                    result["instance_ids"] = instance_ids
                if args.workspace:
                    result["workspace"] = args.workspace
                if args.max_iterations is not None:
                    result["max_iterations"] = args.max_iterations
                if args.timeout_seconds is not None:
                    result["timeout_seconds"] = args.timeout_seconds
                if args.tldrs_version:
                    result["tldrs_version"] = args.tldrs_version
                if args.shim_config:
                    result["shim_config"] = args.shim_config
                if args.seed is not None:
                    result["seed"] = args.seed
                if args.prompt_budget is not None:
                    result["prompt_budget"] = args.prompt_budget
                if args.context_strategy:
                    result["context_strategy"] = args.context_strategy
                if args.daemon_enabled is not None:
                    result["daemon_enabled"] = args.daemon_enabled
                if args.print_results:
                    print(json.dumps(result))
                    if logger:
                        logger.log_with_timestamp(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
