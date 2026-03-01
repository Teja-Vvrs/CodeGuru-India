"""Evaluation harness for codebase chat retrieval quality."""

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from analyzers.repo_analyzer import RepoAnalyzer
from analyzers.semantic_code_search import SemanticCodeSearch

DEFAULT_BENCHMARK_EXCLUDES = (
    "data/eval/",
    "utils/generate_benchmark_pack.py",
    "tests/",
)

GATE_PROFILES = {
    "baseline": {
        "min_cases": 100,
        "min_hit_at_k": 0.55,
        "min_mrr": 0.35,
        "min_grounded_rate": 0.95,
    },
    "production": {
        "min_cases": 100,
        "min_hit_at_k": 0.70,
        "min_mrr": 0.50,
        "min_grounded_rate": 0.97,
    },
    "strict": {
        "min_cases": 100,
        "min_hit_at_k": 0.80,
        "min_mrr": 0.60,
        "min_grounded_rate": 0.98,
    },
}


@dataclass
class EvalCase:
    """Single evaluation prompt with expected evidence files."""
    case_id: str
    question: str
    expected_files: List[str]
    category: str = "general"
    difficulty: str = "medium"


class _NoopOrchestrator:
    """Minimal orchestrator stub for deterministic local evaluation."""

    def generate_completion(self, prompt, max_tokens=300, temperature=0.0):
        return ""


def load_eval_cases(dataset_path: str) -> List[EvalCase]:
    """Load eval cases from JSONL file."""
    path = Path(dataset_path)
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")

    cases: List[EvalCase] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            payload = json.loads(line)
            question = str(payload.get("question", "")).strip()
            expected_files = payload.get("expected_files", [])
            if not question or not isinstance(expected_files, list) or not expected_files:
                raise ValueError(f"Invalid case at line {line_no}: {line}")
            case_id = str(payload.get("id") or f"case_{line_no}")
            cases.append(EvalCase(
                case_id=case_id,
                question=question,
                expected_files=[str(item) for item in expected_files if str(item).strip()],
                category=str(payload.get("category", "general")).strip() or "general",
                difficulty=str(payload.get("difficulty", "medium")).strip() or "medium",
            ))
    return cases


def _normalize_path(path: str) -> str:
    return str(path or "").replace("\\", "/").strip().lower()


def _path_is_excluded(path: str, exclude_patterns: List[str]) -> bool:
    normalized = _normalize_path(path)
    for pattern in exclude_patterns:
        token = _normalize_path(pattern)
        if token and token in normalized:
            return True
    return False


def _default_excludes_for_dataset(dataset_path: str) -> List[str]:
    dataset_name = Path(dataset_path).name.lower()
    if "benchmark" in dataset_name:
        return list(DEFAULT_BENCHMARK_EXCLUDES)
    return ["data/eval/", "utils/generate_benchmark_pack.py"]


def _prune_search_index(search: SemanticCodeSearch, exclude_patterns: List[str]) -> None:
    """Remove excluded files from all indexed search structures."""
    if not exclude_patterns:
        return

    search.code_chunks = [
        chunk for chunk in search.code_chunks
        if not _path_is_excluded(chunk.file_path, exclude_patterns)
    ]
    search.file_summaries = {
        file_path: summary
        for file_path, summary in search.file_summaries.items()
        if not _path_is_excluded(file_path, exclude_patterns)
    }

    if hasattr(search, "file_symbols"):
        search.file_symbols = {
            file_path: symbols
            for file_path, symbols in search.file_symbols.items()
            if not _path_is_excluded(file_path, exclude_patterns)
        }

    if hasattr(search, "symbol_index"):
        filtered_index = {}
        for key, symbols in search.symbol_index.items():
            filtered = [
                symbol for symbol in symbols
                if not _path_is_excluded(getattr(symbol, "file_path", ""), exclude_patterns)
            ]
            if filtered:
                filtered_index[key] = filtered
        search.symbol_index = filtered_index

    if hasattr(search, "repository_map"):
        for attr in (
            "entry_points",
            "routing_files",
            "api_files",
            "state_files",
            "ui_files",
            "data_files",
            "debug_files",
            "config_files",
        ):
            values = getattr(search.repository_map, attr, set())
            filtered = {item for item in values if not _path_is_excluded(item, exclude_patterns)}
            setattr(search.repository_map, attr, filtered)

        symbol_to_files = {}
        for key, files in getattr(search.repository_map, "symbol_to_files", {}).items():
            filtered_files = {item for item in files if not _path_is_excluded(item, exclude_patterns)}
            if filtered_files:
                symbol_to_files[key] = filtered_files
        search.repository_map.symbol_to_files = symbol_to_files


def find_expected_rank(retrieved_files: List[str], expected_files: List[str]) -> Optional[int]:
    """Find the best (lowest) rank where an expected file appears."""
    expected_norm = [_normalize_path(path) for path in expected_files]
    best_rank: Optional[int] = None

    for index, file_path in enumerate(retrieved_files, start=1):
        candidate = _normalize_path(file_path)
        matched = any(
            candidate == expected
            or candidate.endswith(expected)
            or expected.endswith(candidate)
            for expected in expected_norm
        )
        if matched:
            best_rank = index if best_rank is None else min(best_rank, index)
    return best_rank


def compute_metrics(rows: List[Dict[str, object]], top_k: int) -> Dict[str, float]:
    """Compute retrieval metrics from per-case rows."""
    total = len(rows)
    if total == 0:
        return {
            "total_cases": 0,
            "hit_at_k": 0.0,
            "mrr": 0.0,
            "grounded_rate": 0.0,
            "avg_latency_ms": 0.0,
            "p95_latency_ms": 0.0,
        }

    hits = 0
    reciprocal_rank_sum = 0.0
    grounded = 0
    latencies: List[float] = []

    for row in rows:
        rank = row.get("rank")
        if isinstance(rank, int) and rank > 0 and rank <= top_k:
            hits += 1
        if isinstance(rank, int) and rank > 0:
            reciprocal_rank_sum += 1.0 / rank
        if bool(row.get("grounded")):
            grounded += 1
        latency = row.get("latency_ms")
        if isinstance(latency, (int, float)):
            latencies.append(float(latency))

    latencies.sort()
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    if latencies:
        p95_idx = min(len(latencies) - 1, int(round((len(latencies) - 1) * 0.95)))
        p95_latency = latencies[p95_idx]
    else:
        p95_latency = 0.0

    return {
        "total_cases": float(total),
        "hit_at_k": hits / total,
        "mrr": reciprocal_rank_sum / total,
        "grounded_rate": grounded / total,
        "avg_latency_ms": avg_latency,
        "p95_latency_ms": p95_latency,
    }


def compute_category_metrics(rows: List[Dict[str, object]], top_k: int) -> Dict[str, Dict[str, float]]:
    """Compute metrics grouped by case category."""
    grouped: Dict[str, List[Dict[str, object]]] = {}
    for row in rows:
        category = str(row.get("category") or "general")
        grouped.setdefault(category, []).append(row)

    category_metrics: Dict[str, Dict[str, float]] = {}
    for category, category_rows in grouped.items():
        category_metrics[category] = compute_metrics(category_rows, top_k=top_k)
    return category_metrics


def compute_difficulty_metrics(rows: List[Dict[str, object]], top_k: int) -> Dict[str, Dict[str, float]]:
    """Compute metrics grouped by case difficulty."""
    grouped: Dict[str, List[Dict[str, object]]] = {}
    for row in rows:
        difficulty = str(row.get("difficulty") or "medium")
        grouped.setdefault(difficulty, []).append(row)

    difficulty_metrics: Dict[str, Dict[str, float]] = {}
    for difficulty, difficulty_rows in grouped.items():
        difficulty_metrics[difficulty] = compute_metrics(difficulty_rows, top_k=top_k)
    return difficulty_metrics


def compute_quality_score(metrics: Dict[str, float]) -> float:
    """
    Compute a single 0-100 quality score from key retrieval metrics.
    Weighted toward hit-rate and MRR, with grounding and latency adjustments.
    """
    hit = float(metrics.get("hit_at_k", 0.0))
    mrr = float(metrics.get("mrr", 0.0))
    grounded = float(metrics.get("grounded_rate", 0.0))
    avg_latency = float(metrics.get("avg_latency_ms", 0.0))

    latency_score = 1.0
    # Soft penalty only when average latency is above 3 seconds in eval.
    if avg_latency > 3000:
        latency_score = max(0.0, 1.0 - ((avg_latency - 3000.0) / 9000.0))

    composite = (hit * 0.42) + (mrr * 0.33) + (grounded * 0.20) + (latency_score * 0.05)
    return round(max(0.0, min(1.0, composite)) * 100.0, 2)


def aggregate_reports(reports: List[Dict[str, object]], top_k: int) -> Dict[str, object]:
    """Aggregate multiple repo reports into one summary report."""
    if not reports:
        return {
            "metrics": compute_metrics([], top_k=top_k),
            "category_metrics": {},
            "difficulty_metrics": {},
            "quality_score": 0.0,
            "rows": [],
            "repos": [],
        }

    all_rows: List[Dict[str, object]] = []
    repo_summaries: List[Dict[str, object]] = []
    for report in reports:
        all_rows.extend(report.get("rows", []))
        repo_summaries.append({
            "repo_path": report.get("repo_path", ""),
            "metrics": report.get("metrics", {}),
            "quality_score": report.get("quality_score", 0.0),
            "indexed_files": report.get("indexed_files", 0),
            "indexed_chunks": report.get("indexed_chunks", 0),
        })

    metrics = compute_metrics(all_rows, top_k=top_k)
    return {
        "metrics": metrics,
        "category_metrics": compute_category_metrics(all_rows, top_k=top_k),
        "difficulty_metrics": compute_difficulty_metrics(all_rows, top_k=top_k),
        "quality_score": compute_quality_score(metrics),
        "rows": all_rows,
        "repos": repo_summaries,
    }


def evaluate_gates(
    metrics: Dict[str, float],
    min_cases: int = 0,
    min_hit_at_k: Optional[float] = None,
    min_mrr: Optional[float] = None,
    min_grounded_rate: Optional[float] = None,
) -> Tuple[bool, List[str]]:
    """Evaluate pass/fail gates from aggregate metrics."""
    checks: List[Tuple[str, bool]] = []
    total_cases = int(metrics.get("total_cases", 0))
    checks.append((f"cases >= {min_cases}", total_cases >= min_cases))

    if min_hit_at_k is not None:
        checks.append((f"hit_at_k >= {min_hit_at_k:.3f}", metrics.get("hit_at_k", 0.0) >= min_hit_at_k))
    if min_mrr is not None:
        checks.append((f"mrr >= {min_mrr:.3f}", metrics.get("mrr", 0.0) >= min_mrr))
    if min_grounded_rate is not None:
        checks.append(
            (
                f"grounded_rate >= {min_grounded_rate:.3f}",
                metrics.get("grounded_rate", 0.0) >= min_grounded_rate,
            )
        )

    failed = [rule for rule, passed in checks if not passed]
    return (len(failed) == 0, failed)


def evaluate_repo(
    repo_path: str,
    dataset_path: str,
    top_k: int = 5,
    exclude_patterns: Optional[List[str]] = None,
) -> Dict[str, object]:
    """Run retrieval evaluation for a repository and dataset."""
    cases = load_eval_cases(dataset_path)
    analyzer = RepoAnalyzer()
    repo_analysis = analyzer.analyze_local_repo(repo_path)
    if not repo_analysis:
        raise RuntimeError(f"Failed to analyze repository: {repo_path}")

    search = SemanticCodeSearch(_NoopOrchestrator())
    search.index_repository(repo_path, repo_analysis)
    active_excludes = list(exclude_patterns or _default_excludes_for_dataset(dataset_path))
    _prune_search_index(search, active_excludes)

    rows: List[Dict[str, object]] = []
    for case in cases:
        started_at = time.perf_counter()
        results = search.search_by_intent(case.question, top_k=top_k)
        latency_ms = (time.perf_counter() - started_at) * 1000.0
        retrieved_files = [chunk.file_path for chunk in results]
        rank = find_expected_rank(retrieved_files, case.expected_files)
        grounding = search.assess_grounding(case.question, results)
        rows.append({
            "id": case.case_id,
            "question": case.question,
            "expected_files": case.expected_files,
            "category": case.category,
            "difficulty": case.difficulty,
            "retrieved_files": retrieved_files,
            "rank": rank,
            "hit": bool(rank is not None and rank <= top_k),
            "grounded": bool(grounding.get("is_grounded", False)),
            "grounding_reason": grounding.get("reason", "unknown"),
            "latency_ms": latency_ms,
        })

    metrics = compute_metrics(rows, top_k=top_k)
    category_metrics = compute_category_metrics(rows, top_k=top_k)
    difficulty_metrics = compute_difficulty_metrics(rows, top_k=top_k)
    return {
        "repo_path": repo_path,
        "metrics": metrics,
        "category_metrics": category_metrics,
        "difficulty_metrics": difficulty_metrics,
        "quality_score": compute_quality_score(metrics),
        "rows": rows,
        "indexed_files": len(search.file_summaries),
        "indexed_chunks": len(search.code_chunks),
        "exclude_patterns": active_excludes,
    }


def _print_report(
    report: Dict[str, object],
    top_k: int,
    max_case_rows: int = 40,
    failures_only: bool = False,
) -> None:
    metrics = report["metrics"]
    category_metrics = report.get("category_metrics", {})
    difficulty_metrics = report.get("difficulty_metrics", {})
    rows = report["rows"]
    indexed_files = report.get("indexed_files", 0)
    indexed_chunks = report.get("indexed_chunks", 0)
    exclude_patterns = report.get("exclude_patterns", [])
    quality_score = float(report.get("quality_score", 0.0))
    repo_path = report.get("repo_path", "")
    repo_summaries = report.get("repos", [])

    print("Codebase Chat Retrieval Evaluation")
    print("=" * 33)
    if repo_path:
        print(f"Repository    : {repo_path}")
    print(f"Indexed files : {indexed_files}")
    print(f"Indexed chunks: {indexed_chunks}")
    if exclude_patterns:
        print(f"Excludes      : {', '.join(exclude_patterns)}")
    print(f"Cases         : {int(metrics['total_cases'])}")
    print(f"Hit@{top_k}       : {metrics['hit_at_k']:.3f}")
    print(f"MRR           : {metrics['mrr']:.3f}")
    print(f"Grounded rate : {metrics['grounded_rate']:.3f}")
    print(f"Avg latency   : {metrics['avg_latency_ms']:.1f} ms")
    print(f"P95 latency   : {metrics['p95_latency_ms']:.1f} ms")
    print(f"Quality score : {quality_score:.2f}/100")
    print("")

    if repo_summaries:
        print("Per-repo summary")
        print("-" * 33)
        for item in repo_summaries:
            repo_name = str(item.get("repo_path", "repo"))
            repo_metrics = item.get("metrics", {})
            print(
                f"{repo_name} | Hit@{top_k}={float(repo_metrics.get('hit_at_k', 0.0)):.3f} | "
                f"MRR={float(repo_metrics.get('mrr', 0.0)):.3f} | "
                f"Grounded={float(repo_metrics.get('grounded_rate', 0.0)):.3f} | "
                f"Quality={float(item.get('quality_score', 0.0)):.2f}"
            )
        print("")

    if category_metrics:
        print("Category metrics")
        print("-" * 33)
        for category, values in sorted(category_metrics.items()):
            print(
                f"{category:>16} | cases={int(values['total_cases']):3d} | "
                f"Hit@{top_k}={values['hit_at_k']:.3f} | "
                f"MRR={values['mrr']:.3f} | Grounded={values['grounded_rate']:.3f}"
            )
        print("")

    if difficulty_metrics:
        print("Difficulty metrics")
        print("-" * 33)
        for difficulty, values in sorted(difficulty_metrics.items()):
            print(
                f"{difficulty:>16} | cases={int(values['total_cases']):3d} | "
                f"Hit@{top_k}={values['hit_at_k']:.3f} | "
                f"MRR={values['mrr']:.3f} | Grounded={values['grounded_rate']:.3f}"
            )
        print("")

    print("Per-case results")
    print("-" * 33)

    displayed = 0
    for row in rows:
        if failures_only and row["hit"]:
            continue
        if displayed >= max_case_rows:
            break
        status = "PASS" if row["hit"] else "FAIL"
        print(
            f"[{status}] {row['id']} | category={row.get('category')} | "
            f"rank={row['rank']} | grounded={row['grounded']}"
        )
        print(f"Q: {row['question']}")
        print(f"Expected: {', '.join(row['expected_files'])}")
        retrieved = row["retrieved_files"][:top_k]
        print(f"Retrieved: {', '.join(retrieved) if retrieved else '(none)'}")
        print("")
        displayed += 1

    if len(rows) > displayed:
        print(f"... {len(rows) - displayed} more cases omitted")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate codebase chat retrieval quality.")
    parser.add_argument("--repo-path", default="", help="Path to local repository")
    parser.add_argument(
        "--repos-file",
        default="",
        help="Optional text file with one repository path per line for multi-repo evaluation",
    )
    parser.add_argument(
        "--dataset",
        default="data/eval/codebase_chat_eval.jsonl",
        help="Path to eval dataset JSONL",
    )
    parser.add_argument("--top-k", type=int, default=5, help="Top-k retrieval cutoff")
    parser.add_argument(
        "--gate-profile",
        choices=sorted(GATE_PROFILES.keys()),
        default="",
        help="Preset quality gate profile",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Substring path pattern to exclude from indexed eval corpus (repeatable)",
    )
    parser.add_argument("--max-case-rows", type=int, default=40, help="Max per-case rows to print")
    parser.add_argument("--failures-only", action="store_true", help="Print only failed cases")
    parser.add_argument("--output-json", default="", help="Optional path to save JSON report")
    parser.add_argument("--min-cases", type=int, default=0, help="Gate: minimum number of cases")
    parser.add_argument("--min-hit-at-k", type=float, default=None, help="Gate: minimum Hit@k")
    parser.add_argument("--min-mrr", type=float, default=None, help="Gate: minimum MRR")
    parser.add_argument("--min-grounded-rate", type=float, default=None, help="Gate: minimum grounded rate")
    parser.add_argument(
        "--fail-on-gate",
        action="store_true",
        help="Exit non-zero if any gate fails",
    )
    args = parser.parse_args()

    repo_paths: List[str] = []
    if args.repo_path:
        repo_paths.append(args.repo_path)
    if args.repos_file:
        repo_file = Path(args.repos_file)
        if not repo_file.exists():
            raise FileNotFoundError(f"Repos file not found: {args.repos_file}")
        for line in repo_file.read_text(encoding="utf-8").splitlines():
            path = line.strip()
            if not path or path.startswith("#"):
                continue
            repo_paths.append(path)
    if not repo_paths:
        raise ValueError("Provide at least one repository via --repo-path or --repos-file")

    repo_reports = [
        evaluate_repo(
            repo_path=repo_path,
            dataset_path=args.dataset,
            top_k=args.top_k,
            exclude_patterns=args.exclude or None,
        )
        for repo_path in repo_paths
    ]
    report = repo_reports[0] if len(repo_reports) == 1 else aggregate_reports(repo_reports, top_k=args.top_k)
    _print_report(
        report,
        top_k=args.top_k,
        max_case_rows=max(1, args.max_case_rows),
        failures_only=args.failures_only,
    )

    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Saved JSON report: {output_path}")

    profile_thresholds = GATE_PROFILES.get(args.gate_profile, {})
    min_cases = args.min_cases if args.min_cases > 0 else int(profile_thresholds.get("min_cases", 0))
    min_hit = args.min_hit_at_k if args.min_hit_at_k is not None else profile_thresholds.get("min_hit_at_k")
    min_mrr = args.min_mrr if args.min_mrr is not None else profile_thresholds.get("min_mrr")
    min_grounded = (
        args.min_grounded_rate
        if args.min_grounded_rate is not None
        else profile_thresholds.get("min_grounded_rate")
    )

    gates_requested = any(value is not None for value in (min_hit, min_mrr, min_grounded)) or min_cases > 0

    gate_passed, failed_rules = evaluate_gates(
        report["metrics"],
        min_cases=max(0, min_cases),
        min_hit_at_k=min_hit,
        min_mrr=min_mrr,
        min_grounded_rate=min_grounded,
    )

    if gates_requested:
        if args.gate_profile:
            print(f"Gate profile: {args.gate_profile}")
        if gate_passed:
            print("GATE RESULT: PASS")
        else:
            print("GATE RESULT: FAIL")
            for rule in failed_rules:
                print(f"- {rule}")

    if (args.fail_on_gate or gates_requested) and not gate_passed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
