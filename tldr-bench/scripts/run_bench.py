import argparse

from tldr_bench.runners.openhands_runner import run_task
from tldr_bench.tasks import load_tasks, resolve_task_file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--help-variants", action="store_true")
    parser.add_argument("--list-tasks", action="store_true")
    parser.add_argument("--tasks", default=None)
    parser.add_argument("--variant", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.help_variants:
        print("baselines, difflens, symbolkite, cassette, coveragelens")
        return 0
    if args.tasks:
        task_file = resolve_task_file(args.tasks)
        tasks = load_tasks(task_file)
        if args.list_tasks:
            for task in tasks:
                print(task.get("id", "<missing-id>"))
            return 0
        if args.variant and not args.dry_run:
            for task in tasks:
                run_task(task, args.variant)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
