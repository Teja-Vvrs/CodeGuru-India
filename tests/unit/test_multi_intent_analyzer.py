"""Unit tests for multi-intent query decomposition and sanitization."""

from analyzers.multi_intent_analyzer import MultiIntentAnalyzer, Intent


class _DummyOrchestrator:
    def generate_completion(self, prompt, max_tokens=500):
        return ""


def test_decompose_related_followup_query_without_generic_noise():
    analyzer = MultiIntentAnalyzer(_DummyOrchestrator())

    intents = analyzer.analyze_query(
        "what is shimmer in this repo and why we use that"
    )
    texts = [intent.intent_text.lower() for intent in intents]

    assert len(texts) == 1
    assert "what is shimmer in this repo" in texts[0]
    assert "why we use shimmer" in texts[0]
    assert "tell" not in texts[0]


def test_sanitize_drops_generic_fragment_intents():
    analyzer = MultiIntentAnalyzer(_DummyOrchestrator())
    noisy_intents = [
        Intent(intent_text="why we use", intent_type="why", keywords=[], priority=1),
        Intent(intent_text="what", intent_type="what", keywords=[], priority=2),
        Intent(intent_text="what is shimmer in this repo", intent_type="what", keywords=["shimmer"], priority=3),
    ]

    cleaned = analyzer._sanitize_intents(
        noisy_intents,
        "what is shimmer in this repo and why we use that",
    )

    assert len(cleaned) == 1
    assert cleaned[0].intent_text.lower() == "what is shimmer in this repo"


def test_tell_me_prefix_does_not_create_fake_subject():
    analyzer = MultiIntentAnalyzer(_DummyOrchestrator())

    intents = analyzer.analyze_query(
        "tell me what is shimmer in this repo and why should we have to use that?"
    )

    assert len(intents) == 1
    text = intents[0].intent_text.lower()
    assert "tell" not in text
    assert "shimmer" in text
    assert "why should we have to use shimmer" in text


def test_followup_explain_clause_merges_with_primary_subject():
    analyzer = MultiIntentAnalyzer(_DummyOrchestrator())

    intents = analyzer.analyze_query(
        "which routing system used for the routing in this codebase and explain about that"
    )

    assert len(intents) == 1
    text = intents[0].intent_text.lower()
    assert "routing system" in text
    assert "explain" in text


def test_understand_query_resolves_followup_with_chat_context():
    analyzer = MultiIntentAnalyzer(_DummyOrchestrator())
    history = [
        {"role": "user", "content": "Explain authentication flow in this repository"},
        {"role": "assistant", "content": "It starts in the router and auth guard."},
    ]

    understanding = analyzer.understand_query("and why we use that?", chat_history=history)

    assert understanding.used_chat_context is True
    assert "authentication" in understanding.normalized_query.lower()
    assert understanding.intents
    assert "authentication" in understanding.intents[0].intent_text.lower()


def test_understand_query_extracts_response_profile():
    analyzer = MultiIntentAnalyzer(_DummyOrchestrator())

    understanding = analyzer.understand_query(
        "explain routing in detail step by step with examples"
    )
    profile = understanding.response_profile

    assert profile["depth"] == "deep"
    assert profile["format"] == "steps"
    assert profile["include_examples"] is True


def test_understand_query_does_not_force_previous_topic_for_broad_new_prompt():
    analyzer = MultiIntentAnalyzer(_DummyOrchestrator())
    history = [
        {"role": "user", "content": "Explain authentication flow in this repository"},
        {"role": "assistant", "content": "It starts in login and auth middleware."},
    ]

    understanding = analyzer.understand_query(
        "explain the flow of this dev tinder what is this about in a clear way",
        chat_history=history,
    )

    assert understanding.used_chat_context is False
    assert "dev tinder" in understanding.normalized_query.lower()
    assert "authentication" not in understanding.normalized_query.lower()
    assert understanding.intents
