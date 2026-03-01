"""Unit tests for retrieval evaluation harness."""

from utils.codebase_chat_eval import (
    load_eval_cases,
    find_expected_rank,
    compute_metrics,
    compute_difficulty_metrics,
    compute_quality_score,
    aggregate_reports,
    evaluate_gates,
)


def test_load_eval_cases_parses_jsonl_dataset(tmp_path):
    dataset = tmp_path / "eval.jsonl"
    dataset.write_text(
        "\n".join([
            '{"id":"c1","question":"where is routing?","expected_files":["src/router.jsx"]}',
            '{"question":"where is chat ui?","expected_files":["ui/codebase_chat.py"]}',
        ]),
        encoding="utf-8",
    )

    cases = load_eval_cases(str(dataset))
    assert len(cases) == 2
    assert cases[0].case_id == "c1"
    assert cases[1].case_id.startswith("case_")
    assert cases[1].expected_files == ["ui/codebase_chat.py"]


def test_find_expected_rank_supports_suffix_match():
    retrieved = [
        "/tmp/project/src/main.jsx",
        "/tmp/project/analyzers/semantic_code_search.py",
        "/tmp/project/ui/codebase_chat.py",
    ]
    rank = find_expected_rank(retrieved, ["analyzers/semantic_code_search.py"])
    assert rank == 2


def test_compute_metrics_reports_hit_mrr_and_grounded_rate():
    rows = [
        {"rank": 1, "grounded": True, "latency_ms": 100.0},
        {"rank": 3, "grounded": False, "latency_ms": 200.0},
        {"rank": None, "grounded": False, "latency_ms": 300.0},
    ]
    metrics = compute_metrics(rows, top_k=3)
    assert metrics["total_cases"] == 3.0
    assert round(metrics["hit_at_k"], 3) == 0.667
    assert round(metrics["mrr"], 3) == 0.444
    assert round(metrics["grounded_rate"], 3) == 0.333
    assert round(metrics["avg_latency_ms"], 1) == 200.0
    assert round(metrics["p95_latency_ms"], 1) == 300.0


def test_evaluate_gates_pass_and_fail():
    metrics = {
        "total_cases": 120.0,
        "hit_at_k": 0.92,
        "mrr": 0.81,
        "grounded_rate": 0.97,
    }
    passed, failed_rules = evaluate_gates(
        metrics,
        min_cases=100,
        min_hit_at_k=0.90,
        min_mrr=0.75,
        min_grounded_rate=0.95,
    )
    assert passed is True
    assert failed_rules == []

    failed, fail_rules = evaluate_gates(
        metrics,
        min_cases=150,
        min_hit_at_k=0.95,
        min_mrr=0.85,
        min_grounded_rate=0.99,
    )
    assert failed is False
    assert len(fail_rules) == 4


def test_compute_difficulty_metrics_and_quality_score():
    rows = [
        {"rank": 1, "grounded": True, "difficulty": "easy", "latency_ms": 100.0},
        {"rank": 2, "grounded": True, "difficulty": "medium", "latency_ms": 180.0},
        {"rank": None, "grounded": False, "difficulty": "hard", "latency_ms": 210.0},
    ]
    by_difficulty = compute_difficulty_metrics(rows, top_k=3)
    assert set(by_difficulty.keys()) == {"easy", "medium", "hard"}
    assert by_difficulty["easy"]["hit_at_k"] == 1.0

    score = compute_quality_score(compute_metrics(rows, top_k=3))
    assert 0.0 <= score <= 100.0


def test_aggregate_reports_combines_rows_and_scores():
    report_a = {
        "repo_path": "/tmp/a",
        "metrics": {"hit_at_k": 1.0, "mrr": 1.0, "grounded_rate": 1.0, "avg_latency_ms": 120.0, "p95_latency_ms": 120.0, "total_cases": 1.0},
        "quality_score": 99.0,
        "rows": [{"rank": 1, "grounded": True, "category": "core", "difficulty": "easy", "latency_ms": 120.0}],
    }
    report_b = {
        "repo_path": "/tmp/b",
        "metrics": {"hit_at_k": 0.0, "mrr": 0.0, "grounded_rate": 0.0, "avg_latency_ms": 500.0, "p95_latency_ms": 500.0, "total_cases": 1.0},
        "quality_score": 5.0,
        "rows": [{"rank": None, "grounded": False, "category": "core", "difficulty": "hard", "latency_ms": 500.0}],
    }
    combined = aggregate_reports([report_a, report_b], top_k=3)
    assert int(combined["metrics"]["total_cases"]) == 2
    assert len(combined["repos"]) == 2
    assert 0.0 <= combined["quality_score"] <= 100.0
