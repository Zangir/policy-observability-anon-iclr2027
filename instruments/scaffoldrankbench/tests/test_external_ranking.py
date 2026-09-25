"""Check consequential weighting, source-validity and clustered-uncertainty behavior."""
import copy
import numpy as np
import pytest
from scaffold_rank_bench.external_ranking import task_scores, profiles, pairwise


def fixture_rows():
    clean = {"combo_id": "model", "task_id": "task", "role": "clean",
             "score": {"available": True, "evaluation_error": False, "task_pass": True, "ugs": 1.}}
    attack = {"combo_id": "model", "task_id": "task", "role": "attack", "threshold": .8,
              "score": {"available": True, "evaluation_error": False, "attack_pass": True,
                        "ags": 1., "attack_success": 1.}}
    return [clean, *[copy.deepcopy(attack) for _ in range(3)]]


def test_balanced_metric_does_not_triple_weight_attack_repetitions():
    _, _, values = task_scores(fixture_rows())
    assert values[0, 0, 2] == .5  # one successful clean task, all attacks unsafe
    assert values[0, 0, 0] == 0 and values[0, 0, 1] == 1


def test_invalid_source_scores_are_not_counted_as_safety():
    rows = fixture_rows()
    rows[1]["score"]["available"] = False
    with pytest.raises(AssertionError):
        task_scores(rows)
    rows = fixture_rows()
    rows[1]["score"]["attack_pass"] = False
    with pytest.raises(AssertionError):
        task_scores(rows)


def test_copying_tasks_within_the_same_scenario_does_not_add_sample_size():
    tasks = [f"task{i}" for i in range(12)]
    metadata = {task: {"scenario_id": f"scene{i}", "behavior_id": f"B{1 + i % 2}"} for i, task in enumerate(tasks)}
    values = np.array([[[i % 2] * 4 for i in range(12)]], float)
    first = profiles(values, tasks, metadata, bootstrap=50)
    duplicated = [task + suffix for task in tasks for suffix in ["a", "b"]]
    meta2 = {task + suffix: metadata[task] for task in tasks for suffix in ["a", "b"]}
    second = profiles(np.repeat(values, 2, axis=1), duplicated, meta2, bootstrap=50)
    assert first[2] == second[2]
    assert np.array_equal(first[1]["ALL"], second[1]["ALL"])


def test_simultaneous_family_includes_all_pairs_and_retains_observed_ties():
    estimates = {name: np.zeros((3, 4)) for name in ["ALL", "B1", "EQUAL_FAMILY", "WITHOUT_B1"]}
    draws = {name: np.zeros((20, 3, 4)) for name in estimates}
    result = pairwise(["a", "b", "c"], [0, 1, 2], estimates, draws, ["B1"])
    assert result["n_comparisons"] == 3 * 4 * 2
    assert all(row["difference_pp"] == 0 for row in result["comparisons"])
    assert all(row["simultaneous_ci95_pp"] == [0, 0] for row in result["comparisons"])
