import argparse
import json

from tldr_bench.runners.openhands_runner import run_task
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
            for task in tasks:
                task_id = task.get("id", "")
                if not matches(task_id):
                    continue
                if task.get("bench_command") and not args.allow_cli:
                    continue
                if args.dry_run:
                    print(task_id)
                    continue
                result = run_task(task, args.variant)
                if args.print_results:
                    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
