"""Tests for benchmark prompt pack quality gates."""

from utils.codebase_chat_eval import load_eval_cases


def test_benchmark_pack_has_at_least_100_cases():
    cases = load_eval_cases("data/eval/codebase_chat_benchmark_120.jsonl")
    assert len(cases) >= 100


def test_benchmark_pack_contains_multiple_categories():
    cases = load_eval_cases("data/eval/codebase_chat_benchmark_120.jsonl")
    categories = {case.category for case in cases}
    assert len(categories) >= 8
