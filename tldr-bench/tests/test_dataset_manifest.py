from tldr_bench.data import verify_dataset_manifests


def test_verify_manifests_ok(tmp_path):
    assert verify_dataset_manifests(tmp_path) == []
