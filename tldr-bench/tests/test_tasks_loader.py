from tldr_bench.tasks import resolve_task_file


def test_track_task_files_resolve():
    assert resolve_task_file("track_context").name == "track_context.yaml"
    assert resolve_task_file("track_frontier").name == "track_frontier.yaml"
    assert resolve_task_file("track_executable").name == "track_executable.yaml"
    assert resolve_task_file("track_dataset").name == "track_dataset.yaml"
    assert resolve_task_file("track_dataset_context").name == "track_dataset_context.yaml"
