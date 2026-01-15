from __future__ import annotations

import argparse
import docker
from datasets import load_dataset
from swebench.harness.docker_build import build_env_images, build_instance_images
from swebench.harness.test_spec.test_spec import make_test_spec


def _load_dataset(dataset: str, split: str, instance_id: str):
    ds = load_dataset(dataset, split=split)
    for row in ds:
        if row.get("instance_id") == instance_id:
            return row
    raise ValueError(f"Instance {instance_id} not found in {dataset}:{split}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="princeton-nlp/SWE-bench_Verified")
    parser.add_argument("--split", default="test")
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--arch", default="arm64")
    parser.add_argument("--namespace", default="swebench")
    parser.add_argument("--max-workers", type=int, default=1)
    parser.add_argument("--force-rebuild", action="store_true")
    args = parser.parse_args()

    row = _load_dataset(args.dataset, args.split, args.instance_id)
    spec = make_test_spec(row, namespace=args.namespace, arch=args.arch)

    client = docker.from_env()

    build_env_images(
        client,
        [spec],
        force_rebuild=args.force_rebuild,
        max_workers=args.max_workers,
        namespace=args.namespace,
    )
    build_instance_images(
        client,
        [spec],
        force_rebuild=args.force_rebuild,
        max_workers=args.max_workers,
        namespace=args.namespace,
    )

    print("Built arm64 SWE-Bench instance image:")
    print(f"  {spec.instance_image_key}")
    print("Suggested env vars for OpenHands SWE-Bench runs:")
    print("  export SWE_BENCH_ARCH=arm64")
    print("  export SWE_BENCH_IMAGE_PREFIX=swebench")
    print("  export OPENHANDS_DOCKER_PLATFORM=linux/arm64")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
