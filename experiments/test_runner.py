from collections import Counter

from experiments.runner import build_tasks


def test_experiment_tiers_match_the_frozen_attempt_counts():
    smoke = build_tasks("smoke")
    quick = build_tasks("quick")
    full = build_tasks("full")

    assert len(smoke) == 6
    assert len(quick) == 36
    assert len(full) == 905
    assert Counter(task.fault_matrix for task in full) == {
        "loss": 200,
        "delay": 140,
        "reordering": 200,
        "corruption": 100,
        "duplication": 100,
        "timeout": 90,
        "combined": 75,
    }


def test_task_seeds_are_unique_and_stable_before_filtering():
    first = build_tasks("full", base_seed=123_456)
    repeated = build_tasks("full", base_seed=123_456)

    assert [task.seed for task in first] == [task.seed for task in repeated]
    assert [task.seed for task in first] == list(range(123_456, 123_456 + 905))
    assert len({task.seed for task in first}) == len(first)
