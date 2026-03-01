"""Unit tests for codebase chat orchestration helpers."""

from ui.codebase_chat import (
    _build_clarification_message,
    _combine_responses,
    _is_elliptical_followup_for_context,
)


def test_build_clarification_message_english_contains_focus():
    text = _build_clarification_message(
        output_language="english",
        suggested_focus=["routing/navigation", "API/backend flow"],
        active_topics=["router", "auth"],
    )
    assert "routing/navigation" in text
    assert "API/backend flow" in text
    assert "router" in text


def test_combine_responses_dedupes_code_references_by_file_and_line():
    responses = [
        {
            "intent": "routing",
            "explanation": "Routing explanation",
            "code_references": [
                {"file": "src/router.jsx", "lines": "1-20", "score": 1.5},
                {"file": "src/main.jsx", "lines": "1-10", "score": 1.0},
            ],
        },
        {
            "intent": "routing details",
            "explanation": "More details",
            "code_references": [
                {"file": "src/router.jsx", "lines": "1-20", "score": 2.1},
            ],
        },
    ]
    combined = _combine_responses(responses)
    refs = combined["code_references"]
    assert len(refs) == 2
    assert refs[0]["file"] == "src/router.jsx"
    assert float(refs[0]["score"]) == 2.1


def test_context_carryover_used_for_short_followup_query():
    assert _is_elliptical_followup_for_context("and why we use that?") is True


def test_context_carryover_not_used_for_broad_new_overview_query():
    assert (
        _is_elliptical_followup_for_context(
            "explain the flow of this dev tinder what is this about in a clear way"
        )
        is False
    )
