"""Generate a 100+ prompt benchmark pack for codebase chat retrieval."""

import argparse
import json
from pathlib import Path
from typing import Dict, List


QUESTION_TEMPLATES = [
    "Which file implements {alias}?",
    "Where is {alias} defined in this repository?",
    "Show me the source file responsible for {alias}.",
    "I need to debug {alias}; what file should I inspect first?",
    "For onboarding, where can I read the implementation of {alias}?",
    "What module contains {alias} logic?",
    "Can you point to the file that handles {alias}?",
    "In this codebase, where does {alias} happen?",
    "Find the exact file path for {alias}.",
    "Which file should I open to understand {alias}?",
]


TARGET_SPECS: List[Dict[str, object]] = [
    {
        "slug": "semantic_search",
        "category": "retrieval_core",
        "expected_files": ["analyzers/semantic_code_search.py"],
        "aliases": [
            "SemanticCodeSearch.search_by_intent",
            "SemanticCodeSearch.assess_grounding",
            "SemanticCodeSearch._extract_anchor_terms",
            "SemanticCodeSearch._route_chunks_via_repository_map",
            "SemanticCodeSearch._apply_llm_rerank",
            "SemanticCodeSearch._parse_rerank_response",
            "SemanticCodeSearch._extract_symbols",
            "SemanticCodeSearch._files_for_query_mode",
            "SemanticCodeSearch._compute_chunk_score",
            "RepositoryMap + symbol_to_files indexing",
        ],
    },
    {
        "slug": "multi_intent",
        "category": "query_understanding",
        "expected_files": ["analyzers/multi_intent_analyzer.py"],
        "aliases": [
            "MultiIntentAnalyzer.analyze_query",
            "MultiIntentAnalyzer._merge_related_segments",
            "MultiIntentAnalyzer._sanitize_intents",
            "MultiIntentAnalyzer._resolve_followup_references",
            "MultiIntentAnalyzer._extract_intents_rule_based",
            "MultiIntentAnalyzer._detect_intent_type",
            "MultiIntentAnalyzer._extract_keywords",
            "deterministic multi-intent parser",
            "intent priority assignment in MultiIntentAnalyzer",
            "generic fragment filtering in _sanitize_intents",
        ],
    },
    {
        "slug": "rag_explainer",
        "category": "answer_generation",
        "expected_files": ["analyzers/rag_explainer.py"],
        "aliases": [
            "RAGExplainer.generate_detailed_explanation",
            "RAGExplainer._location_target_not_found_message",
            "RAGExplainer._remove_unsupported_code_entities",
            "RAGExplainer._format_evidence_section",
            "RAGExplainer._is_file_existence_intent",
            "RAGExplainer._find_matching_files_in_repo_context",
            "RAGExplainer._generate_feature_overview_from_snippets",
            "RAGExplainer._build_grounded_snippets",
            "RAGExplainer._extract_observed_facts",
            "RAGExplainer._file_existence_response",
        ],
    },
    {
        "slug": "repo_manager",
        "category": "ingestion",
        "expected_files": ["analyzers/repository_manager.py"],
        "aliases": [
            "RepositoryManager.upload_from_github",
            "RepositoryManager.upload_from_folder",
            "RepositoryManager.upload_from_zip",
            "RepositoryManager.validate_repository",
            "RepositoryManager._get_directory_size",
            "RepositoryManager._validate_github_url",
            "RepositoryManager.get_supported_languages",
            "UploadResult creation in repository upload flow",
            "repo upload max_size_mb enforcement",
            "repository upload orchestration in RepositoryManager",
        ],
    },
    {
        "slug": "repo_analyzer",
        "category": "ingestion",
        "expected_files": ["analyzers/repo_analyzer.py"],
        "aliases": [
            "RepoAnalyzer.get_file_tree",
            "RepoAnalyzer._count_languages",
            "RepoAnalyzer._identify_main_files",
            "RepoAnalyzer.analyze_local_repo",
            "RepoAnalyzer.analyze_repo",
            "RepoAnalyzer._generate_summary",
            "RepoAnalyzer.clone_repo",
            "RepoAnalyzer._validate_github_url",
            "FileInfo dataclass in repo analysis",
            "RepoAnalysis dataclass construction",
        ],
    },
    {
        "slug": "chat_ui",
        "category": "chat_orchestration",
        "expected_files": ["ui/codebase_chat.py"],
        "aliases": [
            "render_codebase_chat",
            "_process_query in codebase chat",
            "voice prompt Translate button in codebase chat",
            "codebase chat language selector apply flow",
            "_grounding_failure_message",
            "_ensure_analysis_session in codebase chat",
            "_render_message chat renderer",
            "_top_k_for_query_strategy in chat",
            "_normalize_intent_for_search in chat",
            "_combine_responses in codebase chat",
        ],
    },
    {
        "slug": "unified_analysis_ui",
        "category": "analysis_flow",
        "expected_files": ["ui/unified_code_analysis.py"],
        "aliases": [
            "render_unified_code_analysis",
            "_prepare_single_file_chat_context",
            "_render_repo_starter_guide",
            "_build_default_learning_goal",
            "_prepare_auto_repo_learning_goal",
            "_run_quick_analysis",
            "_run_deep_analysis",
            "_render_results_step",
            "_render_upload_step",
            "_reset_chat_state_for_new_source",
        ],
    },
    {
        "slug": "session_manager",
        "category": "state_management",
        "expected_files": ["session_manager.py"],
        "aliases": [
            "SessionManager.set_current_repository",
            "SessionManager.get_current_repository",
            "SessionManager.set_current_intent",
            "SessionManager.set_uploaded_code",
            "SessionManager.set_learning_artifacts",
            "SessionManager.clear_current_analysis",
            "SessionManager.add_to_analysis_history",
            "SessionManager.load_progress",
            "SessionManager.save_progress",
            "SessionManager._ensure_session_initialized",
        ],
    },
    {
        "slug": "memory_store",
        "category": "persistence",
        "expected_files": ["storage/session_memory_store.py"],
        "aliases": [
            "SessionMemoryStore.create_session",
            "SessionMemoryStore.touch_session",
            "SessionMemoryStore.save_chat_message",
            "SessionMemoryStore.get_chat_messages",
            "SessionMemoryStore.save_artifact",
            "SessionMemoryStore.get_artifact",
            "SessionMemoryStore.list_artifacts",
            "SessionMemoryStore.list_sessions",
            "SessionMemoryStore.get_session",
            "SessionMemoryStore._ensure_store",
        ],
    },
    {
        "slug": "performance_metrics",
        "category": "observability",
        "expected_files": ["utils/performance_metrics.py"],
        "aliases": [
            "record_metric function",
            "_ensure_metrics_store function",
            "summarize_metric function",
            "get_metrics function",
            "chat_query_total metric tracking",
            "metric context handling in record_metric",
            "duration_seconds handling in metrics utility",
            "metric_name filtering in get_metrics",
            "performance telemetry helper module",
            "metrics summary aggregation utility",
        ],
    },
    {
        "slug": "chat_learning",
        "category": "learning_artifacts",
        "expected_files": ["generators/chat_learning_generator.py"],
        "aliases": [
            "ChatLearningGenerator.generate_flashcards",
            "ChatLearningGenerator.generate_quiz",
            "ChatLearningGenerator._extract_qa_pairs",
            "ChatLearningGenerator._extract_intent_themes",
            "ChatLearningGenerator._classify_intent",
            "ChatLearningGenerator._extract_keywords",
            "ChatLearningGenerator._difficulty",
            "ChatLearningGenerator._build_distractors",
            "ChatLearningGenerator._quiz_prompt",
            "IntentTheme dataclass in chat learning",
        ],
    },
    {
        "slug": "progress_tracker",
        "category": "learning_progress",
        "expected_files": ["learning/progress_tracker.py"],
        "aliases": [
            "ProgressTracker.record_activity",
            "ProgressTracker.get_weekly_summary",
            "ProgressTracker.get_statistics",
            "ProgressTracker.calculate_streak",
            "ProgressTracker._resolve_minutes_spent",
            "ProgressTracker.get_skill_levels",
            "ProgressTracker._bootstrap_progress",
            "ProgressTracker._update_streak",
            "ProgressStats dataclass",
            "WeeklySummary dataclass",
        ],
    },
]


def _difficulty_from_index(index: int, total: int) -> str:
    if index < max(2, total // 3):
        return "easy"
    if index < max(5, (2 * total) // 3):
        return "medium"
    return "hard"


def build_cases(cases_per_target: int) -> List[Dict[str, object]]:
    """Build benchmark cases from target specs."""
    if cases_per_target <= 0:
        raise ValueError("cases_per_target must be > 0")

    cases: List[Dict[str, object]] = []
    for spec in TARGET_SPECS:
        slug = str(spec["slug"])
        category = str(spec["category"])
        expected_files = list(spec["expected_files"])
        aliases = list(spec["aliases"])

        for idx in range(cases_per_target):
            template = QUESTION_TEMPLATES[idx % len(QUESTION_TEMPLATES)]
            alias = aliases[idx % len(aliases)]
            question = template.format(alias=alias).strip()
            case = {
                "id": f"{slug}_{idx + 1:02d}",
                "category": category,
                "difficulty": _difficulty_from_index(idx, cases_per_target),
                "question": question,
                "expected_files": expected_files,
            }
            cases.append(case)

    return cases


def write_jsonl(cases: List[Dict[str, object]], output_path: str) -> None:
    """Write cases to JSONL file."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for case in cases:
            handle.write(json.dumps(case, ensure_ascii=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate codebase chat benchmark pack.")
    parser.add_argument(
        "--output",
        default="data/eval/codebase_chat_benchmark_120.jsonl",
        help="Output JSONL path",
    )
    parser.add_argument(
        "--cases-per-target",
        type=int,
        default=10,
        help="Number of prompts generated for each target area",
    )
    args = parser.parse_args()

    cases = build_cases(args.cases_per_target)
    write_jsonl(cases, args.output)
    print(f"Generated {len(cases)} benchmark cases at {args.output}")


if __name__ == "__main__":
    main()
