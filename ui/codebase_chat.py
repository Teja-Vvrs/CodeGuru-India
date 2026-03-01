"""
Codebase Chat Interface.

Provides ChatGPT-like interface for asking questions about the codebase.
"""

import streamlit as st
import logging
import time
import html
import re
import os
from typing import List, Dict, Any, Optional
from ui.design_system import section_header, spacing
from utils.performance_metrics import record_metric

logger = logging.getLogger(__name__)

CHAT_LANGUAGE_LABELS = {
    "english": "English",
    "hindi": "हिंदी (Hindi)",
    "telugu": "తెలుగు (Telugu)",
}
CHAT_TO_VOICE_LANGUAGE = {
    "english": "en",
    "hindi": "hi",
    "telugu": "te",
}
FEATURE_OVERVIEW_PATTERNS = (
    "key feature",
    "main feature",
    "major feature",
    "what features",
    "overall functionality",
    "what this app does",
    "what this codebase does",
    "capabilities",
    "overview",
)
BROAD_CONTEXT_TERMS = (
    "codebase",
    "repo",
    "repository",
    "project",
    "application",
    "app",
    "system",
)
BROAD_OVERVIEW_CUES = (
    "about",
    "overview",
    "summary",
    "high level",
    "big picture",
    "purpose",
    "what is",
    "what does",
    "tell me",
    "explain",
)
LOCATION_PATTERNS = (
    "which file",
    "where is",
    "where are",
    "where does",
    "defined in",
    "implemented in",
    "located",
    "is there",
    "exist",
    "file exists",
)
COMPARISON_PATTERNS = (
    "compare",
    "difference",
    "different",
    "vs",
    "versus",
    "contrast",
)
DEBUG_PATTERNS = (
    "error",
    "bug",
    "issue",
    "not working",
    "failing",
    "fix",
    "exception",
    "traceback",
)
CHAT_CONTEXT_MAX_TOPICS = 14


def _audio_signature(audio_bytes: bytes) -> str:
    """Create a lightweight signature for detecting new recordings."""
    if not audio_bytes:
        return ""
    head = audio_bytes[:24]
    tail = audio_bytes[-24:] if len(audio_bytes) > 24 else b""
    return f"{len(audio_bytes)}:{head!r}:{tail!r}"


def _contains_non_ascii(text: str) -> bool:
    """Return True when text contains non-ASCII characters."""
    return any(ord(char) > 127 for char in (text or ""))


def _grounding_failure_message(output_language: str, grounding: Dict[str, Any]) -> str:
    """Localized message when retrieval evidence is insufficient."""
    if output_language == "hindi":
        return "रिपॉजिटरी में संबंधित फाइल नहीं मिली।"

    if output_language == "telugu":
        return "రిపోజిటరీలో సంబంధిత ఫైల్ దొరకలేదు."

    return "No relevant file found in repository."


def _normalize_intent_for_search(intent_text: str, output_language: str, rag_explainer) -> str:
    """
    Convert multilingual user intent into an English retrieval query.
    Final explanation language remains unchanged.
    """
    cleaned_intent = (intent_text or "").strip()
    if not cleaned_intent:
        return cleaned_intent

    if output_language == "english" and not _contains_non_ascii(cleaned_intent):
        return cleaned_intent

    orchestrator = getattr(rag_explainer, "orchestrator", None)
    if not orchestrator or not hasattr(orchestrator, "generate_completion"):
        return cleaned_intent

    prompt = f"""Rewrite this user code question into concise English for code retrieval.
Rules:
- Keep framework, library, API, and file/function names unchanged.
- Keep the meaning exactly the same.
- Output exactly one line, no bullets or explanations.

User question:
{cleaned_intent}
"""
    try:
        rewritten = orchestrator.generate_completion(
            prompt,
            max_tokens=120,
            temperature=0.0,
        )
        rewritten = str(rewritten).strip().splitlines()[0].strip(" \"'")
        if not rewritten or rewritten.lower().startswith("error"):
            return cleaned_intent
        return rewritten
    except Exception as exc:
        logger.warning(f"Intent normalization failed, using original query: {exc}")
        return cleaned_intent


def _is_feature_overview_query(text: str) -> bool:
    """Detect broad feature-overview questions."""
    query = (text or "").lower()
    if any(pattern in query for pattern in FEATURE_OVERVIEW_PATTERNS):
        return True
    return _looks_like_broad_overview_query(query)


def _looks_like_broad_overview_query(query: str) -> bool:
    """Generalized high-level query detector, not tied to exact user phrasing."""
    has_context = any(term in query for term in BROAD_CONTEXT_TERMS)
    has_overview_cue = any(term in query for term in BROAD_OVERVIEW_CUES)
    has_file_like_ref = bool(
        re.search(
            r"[A-Za-z0-9_./-]+\.(?:jsx|tsx|py|js|ts|java|go|rb|php|cs|json|yaml|yml|toml)",
            query,
        )
    )
    return bool(has_context and has_overview_cue and not has_file_like_ref)


def _classify_query_strategy(text: str) -> str:
    """Classify query to tune retrieval breadth."""
    query = (text or "").lower()
    if any(pattern in query for pattern in FEATURE_OVERVIEW_PATTERNS):
        return "overview"
    if _looks_like_broad_overview_query(query):
        return "overview"
    if any(pattern in query for pattern in COMPARISON_PATTERNS):
        return "comparison"
    if any(pattern in query for pattern in DEBUG_PATTERNS):
        return "debug"
    if any(pattern in query for pattern in LOCATION_PATTERNS):
        return "location"
    return "specific"


def _allow_soft_grounding(grounding: Dict[str, Any], relevant_chunks: List[Any]) -> bool:
    """Allow low-score broad queries to proceed when we still have plausible evidence."""
    if not relevant_chunks:
        return False

    mode = (grounding or {}).get("query_mode", "specific")
    reason = (grounding or {}).get("reason", "ok")
    top_score = float((grounding or {}).get("top_score") or 0.0)
    anchor_terms = (grounding or {}).get("anchor_terms") or []

    if mode in {"overview", "comparison", "config"} and reason in {"low_score", "missing_anchor"}:
        return top_score >= 0.2

    if mode == "specific" and not anchor_terms and reason == "low_score":
        return top_score >= 0.25

    return False


def _top_k_for_query_strategy(strategy: str) -> int:
    """Choose retrieval depth based on query strategy."""
    mapping = {
        "overview": 36,
        "comparison": 32,
        "debug": 30,
        "location": 20,
        "specific": 20,
    }
    return mapping.get(strategy, 20)


def _topic_tokens_from_text(text: str) -> List[str]:
    """Extract reusable topic tokens from text for long-conversation memory."""
    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_./:-]{2,}", (text or ""))
    filtered = []
    stop = {
        "code", "codebase", "repo", "repository", "project", "app",
        "what", "why", "how", "where", "which", "this", "that",
        "explain", "tell", "show", "please",
    }
    for token in tokens:
        normalized = token.strip("`'\".,:;()[]{}").lower()
        if not normalized or len(normalized) <= 2:
            continue
        if normalized in stop:
            continue
        filtered.append(normalized)
    return filtered


def _is_elliptical_followup_for_context(query: str) -> bool:
    """Use topic carry-over only for short, reference-heavy follow-up prompts."""
    text = (query or "").strip().lower()
    if not text:
        return False

    followup_prefixes = (
        "and ",
        "also ",
        "then ",
        "so ",
        "what about",
        "how about",
        "why ",
        "how ",
        "where ",
    )
    followup_refs = {"this", "that", "it", "these", "those", "them", "same"}
    low_signal = {
        "what", "why", "how", "where", "which", "tell", "show", "explain",
        "about", "repo", "repository", "codebase", "project", "app",
        "flow", "overview", "summary",
    }

    tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_:-]*", text)
    has_prefix = any(text.startswith(prefix) for prefix in followup_prefixes)
    has_ref = any(token in followup_refs for token in tokens)
    has_broad_cue = any(cue in text for cue in BROAD_OVERVIEW_CUES)

    informative_tokens = [
        token for token in tokens
        if token not in followup_refs
        and token not in BROAD_CONTEXT_TERMS
        and token not in low_signal
        and len(token) > 2
    ]

    if has_broad_cue and len(informative_tokens) >= 2:
        return False
    if has_prefix and len(informative_tokens) <= 6:
        return True
    if has_ref and len(tokens) <= 10 and len(informative_tokens) <= 2:
        return True
    return len(tokens) <= 4 and len(informative_tokens) == 0


def _ensure_chat_context_store() -> Dict[str, Any]:
    """Ensure session-level chat context storage exists."""
    if "codebase_chat_context_state" not in st.session_state:
        st.session_state.codebase_chat_context_state = {}
    return st.session_state.codebase_chat_context_state


def _get_chat_context_state(session_id: str) -> Dict[str, Any]:
    """Get conversation context state for a memory session."""
    store = _ensure_chat_context_store()
    if session_id not in store:
        store[session_id] = {
            "topics": {},
            "last_user_query": "",
            "last_assistant_summary": "",
            "turns": 0,
        }
    return store[session_id]


def _active_topics(context_state: Dict[str, Any], limit: int = 5) -> List[str]:
    topics = context_state.get("topics", {})
    ranked = sorted(
        topics.items(),
        key=lambda item: (int(item[1].get("count", 0)), int(item[1].get("last_turn", 0))),
        reverse=True,
    )
    return [name for name, _ in ranked[:max(1, limit)]]


def _update_chat_context_state(
    session_id: str,
    user_query: str,
    assistant_text: str,
    code_references: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Update conversation topic memory with each completed turn."""
    state = _get_chat_context_state(session_id)
    state["turns"] = int(state.get("turns", 0)) + 1
    turn = state["turns"]

    candidates = []
    candidates.extend(_topic_tokens_from_text(user_query))
    candidates.extend(_topic_tokens_from_text(assistant_text[:800]))
    for ref in code_references or []:
        candidates.extend(_topic_tokens_from_text(str(ref.get("file", ""))))
        candidates.extend(_topic_tokens_from_text(str(ref.get("lines", ""))))

    topics = state.setdefault("topics", {})
    for token in candidates:
        entry = topics.setdefault(token, {"count": 0, "last_turn": 0})
        entry["count"] = int(entry.get("count", 0)) + 1
        entry["last_turn"] = turn

    # Keep topic memory compact.
    if len(topics) > CHAT_CONTEXT_MAX_TOPICS:
        ranked = sorted(
            topics.items(),
            key=lambda item: (int(item[1].get("count", 0)), int(item[1].get("last_turn", 0))),
            reverse=True,
        )[:CHAT_CONTEXT_MAX_TOPICS]
        state["topics"] = {name: meta for name, meta in ranked}

    state["last_user_query"] = user_query
    state["last_assistant_summary"] = (assistant_text or "")[:500]
    return state


def _build_clarification_message(
    output_language: str,
    suggested_focus: List[str],
    active_topics: List[str],
) -> str:
    """Localized clarification prompt for ambiguous user questions."""
    focus = ", ".join(suggested_focus[:4]) if suggested_focus else ""
    recent = ", ".join(active_topics[:3]) if active_topics else ""

    if output_language == "hindi":
        if recent:
            return (
                f"आपका प्रश्न थोड़ा अस्पष्ट है। क्या आप बताना चाहेंगे कि किस हिस्से पर फोकस चाहिए: {focus}? "
                f"हाल की बातचीत के आधार पर हम `{recent}` पर भी जा सकते हैं।"
            )
        return f"आपका प्रश्न थोड़ा अस्पष्ट है। कृपया फोकस बताएं: {focus}."

    if output_language == "telugu":
        if recent:
            return (
                f"మీ ప్రశ్న కొంచెం స్పష్టంగా లేదు. దయచేసి ఏ భాగం కావాలో చెప్పండి: {focus}. "
                f"ఇటీవలి చర్చ ప్రకారం `{recent}` పై కూడా కొనసాగవచ్చు."
            )
        return f"మీ ప్రశ్న కొంచెం స్పష్టంగా లేదు. దయచేసి ఫోకస్ చెప్పండి: {focus}."

    if recent:
        return (
            f"Your question is a bit ambiguous. Please pick a focus: {focus}. "
            f"From recent context, we can also continue with `{recent}`."
        )
    return f"Your question is a bit ambiguous. Please pick a focus: {focus}."


def _abspath_for_reference(repo_path: str, file_path: str) -> str:
    """Resolve reference file path to absolute path when possible."""
    if not file_path:
        return ""
    if os.path.isabs(file_path):
        return file_path
    return os.path.abspath(os.path.join(repo_path or "", file_path))


def _enrich_code_references(
    refs: List[Dict[str, Any]],
    relevant_chunks: List[Any],
    repo_path: str,
) -> List[Dict[str, Any]]:
    """Attach absolute path, score, and compact snippet to code references."""
    chunk_map = {
        (chunk.file_path, f"{chunk.start_line}-{chunk.end_line}"): chunk
        for chunk in (relevant_chunks or [])
    }
    enriched: List[Dict[str, Any]] = []
    seen = set()
    for ref in refs or []:
        file_path = str(ref.get("file", "")).strip()
        lines = str(ref.get("lines", "")).strip()
        key = (file_path, lines)
        if not file_path or key in seen:
            continue
        seen.add(key)
        chunk = chunk_map.get(key)
        snippet = str(ref.get("content", "")).strip()
        score = None
        if chunk is not None:
            snippet = (chunk.content or "").strip()[:420]
            score = float(getattr(chunk, "relevance_score", 0.0) or 0.0)

        enriched.append(
            {
                "file": file_path,
                "abs_path": _abspath_for_reference(repo_path, file_path),
                "lines": lines,
                "content": snippet,
                "score": score,
            }
        )
    enriched.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
    return enriched


def render_codebase_chat(
    session_manager,
    semantic_search,
    rag_explainer,
    multi_intent_analyzer,
    memory_store=None
):
    """
    Render chat interface for codebase queries.
    
    Args:
        session_manager: SessionManager instance
        semantic_search: SemanticCodeSearch instance
        rag_explainer: RAGExplainer instance
        multi_intent_analyzer: MultiIntentAnalyzer instance
        memory_store: MemoryStore instance
    """
    section_header(
        "💬 Codebase Chat",
        "Ask questions about your codebase - like ChatGPT for code"
    )
    
    # Check if repository is loaded
    repo_context = session_manager.get_current_repository()
    
    if not repo_context:
        st.warning("⚠️ No codebase loaded")
        st.info("Please upload a repository first using the 'Upload Code' page")
        return
    
    repo_analysis = repo_context.get('repo_analysis')
    repo_path = repo_context.get('repo_path')

    # Chat language controls
    default_language = st.session_state.get("selected_language", "english")
    if default_language not in CHAT_LANGUAGE_LABELS:
        default_language = "english"
    if "codebase_chat_language" not in st.session_state:
        st.session_state.codebase_chat_language = default_language
    if "codebase_chat_language_notice" not in st.session_state:
        st.session_state.codebase_chat_language_notice = ""

    st.markdown("### 🌐 Chat Language")
    lang_col1, lang_col2 = st.columns([4, 1])
    with lang_col1:
        current_chat_language = st.session_state.get("codebase_chat_language", default_language)
        lang_options = list(CHAT_LANGUAGE_LABELS.keys())
        selected_chat_language = st.selectbox(
            "Choose chat language",
            options=lang_options,
            index=lang_options.index(current_chat_language) if current_chat_language in lang_options else 0,
            format_func=lambda key: CHAT_LANGUAGE_LABELS[key],
            key="codebase_chat_language_selector",
            label_visibility="collapsed",
        )
    with lang_col2:
        spacing("sm")
        if st.button("Apply", use_container_width=True, key="apply_codebase_chat_language"):
            st.session_state.codebase_chat_language = selected_chat_language
            st.session_state.codebase_chat_language_notice = (
                f"Language applied: {CHAT_LANGUAGE_LABELS[selected_chat_language]}. "
                "Voice and chat responses will use this language."
            )
            st.rerun()

    if st.session_state.codebase_chat_language_notice:
        st.success(st.session_state.codebase_chat_language_notice)
        st.session_state.codebase_chat_language_notice = ""

    output_language = st.session_state.get("codebase_chat_language", default_language)

    analysis_session_id = _ensure_analysis_session(
        memory_store,
        repo_analysis,
        repo_path,
        output_language,
    )
    context_key = analysis_session_id or "__default__"
    context_state = _get_chat_context_state(context_key)
    if memory_store and analysis_session_id and not context_state.get("topics"):
        persisted_context = memory_store.get_artifact(analysis_session_id, "chat_context_state")
        if isinstance(persisted_context, dict):
            _ensure_chat_context_store()[context_key] = persisted_context
    
    # Check if semantic search is indexed
    if not hasattr(semantic_search, 'code_chunks') or not semantic_search.code_chunks:
        st.warning("⚠️ Codebase not indexed yet. Indexing now...")
        
        with st.spinner("Indexing codebase for intelligent search..."):
            try:
                semantic_search.index_repository(repo_path, repo_analysis)
                st.success("✅ Codebase indexed! You can now ask questions.")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to index codebase: {str(e)}")
                logger.error(f"Indexing failed: {e}")
                return
    
    # Show repository info
    with st.expander("📦 Current Codebase", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Files", repo_analysis.total_files)
        with col2:
            st.metric("Lines", f"{repo_analysis.total_lines:,}")
        with col3:
            st.metric("Languages", len(repo_analysis.languages))
        
        st.caption(f"**Path**: {repo_analysis.repo_url}")
        st.caption(f"**Indexed**: {len(semantic_search.code_chunks)} code chunks")
    
    spacing("md")

    # Voice prompt controls (native language input)
    voice_processor = st.session_state.get("voice_processor")
    with st.expander("🎤 Voice Prompt (Ask in Native Language)", expanded=False):
        if not voice_processor:
            st.warning("Voice processor not initialized.")
        else:
            if "codebase_voice_audio" not in st.session_state:
                st.session_state.codebase_voice_audio = b""
            if "codebase_voice_signature" not in st.session_state:
                st.session_state.codebase_voice_signature = ""
            if "codebase_voice_transcript" not in st.session_state:
                st.session_state.codebase_voice_transcript = ""

            active_voice_lang = CHAT_TO_VOICE_LANGUAGE.get(output_language, "en")
            st.caption(
                f"Voice language: {CHAT_LANGUAGE_LABELS.get(output_language, 'English')}. "
                "Recorded voice will be transcribed and inserted into chat input."
            )
            st.markdown(
                "1. Click the mic button to start recording.\n"
                "2. Click again after speaking to stop.\n"
                "3. Click `Translate` to insert the transcript into the prompt box."
            )

            try:
                from audio_recorder_streamlit import audio_recorder

                audio_bytes = audio_recorder(
                    text="🎙️ Start/Stop Recording",
                    recording_color="#0066CC",
                    neutral_color="#E5E5E5",
                    icon_size="2x",
                )
                if audio_bytes:
                    current_signature = _audio_signature(audio_bytes)
                    if current_signature != st.session_state.codebase_voice_signature:
                        st.session_state.codebase_voice_audio = audio_bytes
                        st.session_state.codebase_voice_signature = current_signature
                        st.session_state.codebase_voice_transcript = ""
                        st.success("Recording completed successfully.")

                if st.session_state.codebase_voice_audio:
                    col_translate, col_clear = st.columns(2)
                    with col_translate:
                        translate_clicked = st.button("Translate", key="translate_voice_prompt", type="primary")
                    with col_clear:
                        clear_clicked = st.button("Clear Voice", key="clear_voice_prompt", use_container_width=True)

                    if clear_clicked:
                        st.session_state.codebase_voice_audio = b""
                        st.session_state.codebase_voice_signature = ""
                        st.session_state.codebase_voice_transcript = ""
                        st.session_state["chat_input"] = ""
                        st.success("Voice recording and transcript cleared.")
                        st.rerun()

                    if translate_clicked:
                        with st.spinner("Translating your voice prompt..."):
                            result = voice_processor.process_audio(
                                st.session_state.codebase_voice_audio,
                                active_voice_lang,
                            )
                            if result and result.transcript:
                                transcript = result.transcript.strip()
                                st.session_state.codebase_voice_transcript = transcript
                                # Update prompt input before chat_input widget is created.
                                st.session_state["chat_input"] = transcript
                                st.success("Translated text inserted into prompt box.")
                            else:
                                st.error("Translation failed. Please record and try again.")

                if st.session_state.codebase_voice_transcript:
                    st.markdown("**Translated text:**")
                    st.text_area(
                        "Voice transcript",
                        value=st.session_state.codebase_voice_transcript,
                        height=90,
                        disabled=True,
                        key="voice_transcript_preview",
                        label_visibility="collapsed",
                    )
            except ImportError:
                st.warning(
                    "Voice recorder package not installed. Install with: "
                    "`pip install streamlit-audio-recorder`"
                )
    
    # Initialize chat history
    if (
        st.session_state.get("loaded_chat_session_id") != analysis_session_id
        or "chat_history" not in st.session_state
    ):
        persisted_messages = []
        if memory_store and analysis_session_id:
            persisted_messages = memory_store.get_chat_messages(analysis_session_id, limit=500)
        st.session_state.chat_history = [
            {
                "role": message.get("role"),
                "content": message.get("content", ""),
                "code_references": message.get("metadata", {}).get("code_references", []),
                "metadata": message.get("metadata", {}),
            }
            for message in persisted_messages
        ]
        st.session_state.loaded_chat_session_id = analysis_session_id

    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []
    
    if 'chat_processing' not in st.session_state:
        st.session_state.chat_processing = False

    if 'clear_chat_input' not in st.session_state:
        st.session_state.clear_chat_input = False

    # Streamlit only allows updating widget state before the widget is created.
    if st.session_state.clear_chat_input:
        st.session_state["chat_input"] = ""
        st.session_state.clear_chat_input = False
    
    # Chat container
    chat_container = st.container()
    
    # Display chat history
    with chat_container:
        if not st.session_state.chat_history:
            st.info("👋 Hi! I'm your codebase assistant. Ask me anything about the code!")
            
            # Suggested questions
            st.markdown("**Suggested questions:**")
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("🔍 How is routing implemented?", use_container_width=True):
                    _process_query(
                        "How is routing implemented in this codebase?",
                        session_manager,
                        semantic_search,
                        rag_explainer,
                        multi_intent_analyzer,
                        repo_analysis,
                        repo_path,
                        memory_store,
                        analysis_session_id,
                        output_language,
            )
                
                if st.button("🔐 Explain authentication flow", use_container_width=True):
                    _process_query(
                        "Explain the authentication flow",
                        session_manager,
                        semantic_search,
                        rag_explainer,
                        multi_intent_analyzer,
                        repo_analysis,
                        repo_path,
                        memory_store,
                        analysis_session_id,
                        output_language,
                    )
            
            with col2:
                if st.button("🏗️ What's the architecture?", use_container_width=True):
                    _process_query(
                        "What's the overall architecture of this codebase?",
                        session_manager,
                        semantic_search,
                        rag_explainer,
                        multi_intent_analyzer,
                        repo_analysis,
                        repo_path,
                        memory_store,
                        analysis_session_id,
                        output_language,
                    )
                
                if st.button("📊 How is state managed?", use_container_width=True):
                    _process_query(
                        "How is state management implemented?",
                        session_manager,
                        semantic_search,
                        rag_explainer,
                        multi_intent_analyzer,
                        repo_analysis,
                        repo_path,
                        memory_store,
                        analysis_session_id,
                        output_language,
                    )
        
        else:
            # Display chat messages
            for message in st.session_state.chat_history:
                _render_message(message)
    
    spacing("md")
    
    # Chat input
    st.markdown("---")
    
    col1, col2 = st.columns([5, 1])
    
    with col1:
        user_query = st.text_area(
            "Ask a question about the codebase",
            placeholder="e.g., How is routing implemented? What does the authentication system do? Explain the database schema...",
            height=100,
            key="chat_input",
            label_visibility="collapsed"
        )
    
    with col2:
        spacing("sm")
        send_button = st.button("📤 Send", type="primary", use_container_width=True)
        
        if st.button("🗑️ Clear Chat", use_container_width=True):
            st.session_state.chat_history = []
            st.session_state.clear_chat_input = True
            st.rerun()
    
    # Process query
    if send_button and user_query and not st.session_state.chat_processing:
        # Defer input clear to next rerun before the widget is created.
        st.session_state.clear_chat_input = True
        _process_query(
            user_query,
            session_manager,
            semantic_search,
            rag_explainer,
            multi_intent_analyzer,
            repo_analysis,
            repo_path,
            memory_store,
            analysis_session_id,
            output_language,
        )
        st.rerun()


def _process_query(
    query: str,
    session_manager,
    semantic_search,
    rag_explainer,
    multi_intent_analyzer,
    repo_analysis,
    repo_path,
    memory_store,
    analysis_session_id: str,
    output_language: str,
):
    """Process user query and generate response."""
    start_time = time.perf_counter()
    try:
        st.session_state.chat_processing = True
        previous_chat_history = list(st.session_state.chat_history)
        context_key = analysis_session_id or "__default__"
        context_state = _get_chat_context_state(context_key)
        active_context_topics = _active_topics(context_state, limit=5)
        
        # Add user message
        st.session_state.chat_history.append({
            'role': 'user',
            'content': query
        })
        if memory_store and analysis_session_id:
            memory_store.save_chat_message(
                analysis_session_id,
                role="user",
                content=query,
                language=output_language,
            )
        
        # Show processing status
        with st.spinner("🤔 Analyzing your question..."):
            # Analyze intents
            logger.info(f"Analyzing query: {query}")
            response_profile = {"depth": "standard", "format": "narrative", "include_examples": False}
            normalized_query = query
            used_chat_context = False
            if hasattr(multi_intent_analyzer, "understand_query"):
                understanding = multi_intent_analyzer.understand_query(
                    query,
                    chat_history=previous_chat_history,
                )
                intents = understanding.intents
                response_profile = understanding.response_profile or response_profile
                normalized_query = understanding.normalized_query or query
                used_chat_context = bool(understanding.used_chat_context)
                if understanding.used_chat_context:
                    logger.info(
                        "Using previous chat context to resolve follow-up query: %s",
                        understanding.normalized_query,
                    )
            else:
                intents = multi_intent_analyzer.analyze_query(query)

            clarity = {
                "is_ambiguous": False,
                "suggested_focus": [],
                "reason": "clear",
            }
            if hasattr(semantic_search, "analyze_query_clarity"):
                clarity = semantic_search.analyze_query_clarity(normalized_query)
                logger.info(f"Query clarity: {clarity}")

            if clarity.get("is_ambiguous") and not used_chat_context and not active_context_topics:
                clarification = _build_clarification_message(
                    output_language=output_language,
                    suggested_focus=clarity.get("suggested_focus", []),
                    active_topics=active_context_topics,
                )
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": clarification,
                    "code_references": [],
                    "metadata": {
                        "clarification_needed": True,
                        "clarification_reason": clarity.get("reason", "low_specificity"),
                    },
                })
                if memory_store and analysis_session_id:
                    memory_store.save_chat_message(
                        analysis_session_id,
                        role="assistant",
                        content=clarification,
                        language=output_language,
                        metadata={
                            "clarification_needed": True,
                            "clarification_reason": clarity.get("reason", "low_specificity"),
                        },
                    )
                st.session_state.chat_processing = False
                return
            logger.info(f"Found {len(intents)} intents")
        
        # Process each intent
        responses = []
        
        for i, intent in enumerate(intents, 1):
            with st.spinner(f"🔍 Searching codebase for intent {i}/{len(intents)}..."):
                # Search for relevant code
                retrieval_intent = intent.intent_text
                if hasattr(semantic_search, "analyze_query_clarity"):
                    intent_clarity = semantic_search.analyze_query_clarity(retrieval_intent)
                    if (
                        intent_clarity.get("is_ambiguous")
                        and active_context_topics
                        and _is_elliptical_followup_for_context(retrieval_intent)
                    ):
                        retrieval_intent = (
                            f"{retrieval_intent} context {' '.join(active_context_topics[:3])}"
                        )
                search_query = _normalize_intent_for_search(
                    retrieval_intent,
                    output_language,
                    rag_explainer,
                )
                strategy = _classify_query_strategy(search_query)
                if strategy == "specific":
                    strategy = _classify_query_strategy(retrieval_intent)
                top_k = _top_k_for_query_strategy(strategy)
                if response_profile.get("depth") == "deep":
                    top_k = min(top_k + 8, 48)
                elif response_profile.get("depth") == "brief":
                    top_k = max(12, top_k - 4)
                logger.info(f"Searching for: {intent.intent_text}")
                logger.info(f"Search query used for retrieval: {search_query}")
                logger.info(f"Query strategy: {strategy} (top_k={top_k})")
                relevant_chunks = semantic_search.search_by_intent(search_query, top_k=top_k)

                # Fallback to original intent if rewritten query didn't find anything.
                if not relevant_chunks and search_query != intent.intent_text:
                    relevant_chunks = semantic_search.search_by_intent(intent.intent_text, top_k=top_k)

                logger.info(f"Found {len(relevant_chunks)} relevant chunks")

                grounding = {
                    "is_grounded": bool(relevant_chunks),
                    "reason": "no_chunks" if not relevant_chunks else "ok",
                    "anchor_terms": [],
                }
                if hasattr(semantic_search, "assess_grounding"):
                    grounding = semantic_search.assess_grounding(intent.intent_text, relevant_chunks)
                    logger.info(f"Grounding assessment: {grounding}")

                grounded = bool(grounding.get("is_grounded", False))
                if not relevant_chunks or (not grounded and not _allow_soft_grounding(grounding, relevant_chunks)):
                    logger.warning(f"No relevant code found for: {intent.intent_text}")
                    responses.append({
                        'intent': intent.intent_text,
                        'explanation': _grounding_failure_message(output_language, grounding),
                        'code_references': []
                    })
                    continue
            
            with st.spinner(f"✍️ Generating detailed explanation {i}/{len(intents)}..."):
                # Generate explanation
                logger.info(f"Generating explanation for: {intent.intent_text}")
                explanation_result = rag_explainer.generate_detailed_explanation(
                    intent.intent_text,
                    relevant_chunks,
                    repo_analysis,
                    use_web_search=False,  # Set to False for now
                    output_language=output_language,
                    response_profile=response_profile,
                )
                explanation_result["code_references"] = _enrich_code_references(
                    explanation_result.get("code_references", []),
                    relevant_chunks,
                    repo_path,
                )
                logger.info(f"Explanation generated: {len(explanation_result.get('explanation', ''))} chars")
                
                responses.append(explanation_result)
        
        # Combine responses
        combined_response = _combine_responses(responses)

        updated_context_state = _update_chat_context_state(
            context_key,
            user_query=query,
            assistant_text=combined_response.get("explanation", ""),
            code_references=combined_response.get("code_references", []),
        )
        
        # Add assistant message
        st.session_state.chat_history.append({
            'role': 'assistant',
            'content': combined_response['explanation'],
            'code_references': combined_response.get('code_references', []),
            'metadata': {
                'intents_processed': len(intents),
                'active_topics': _active_topics(updated_context_state, limit=4),
                'files_analyzed': len(
                    set(
                        ref.get('file')
                        for resp in responses
                        for ref in resp.get('code_references', [])
                        if ref.get('file')
                    )
                )
            }
        })
        if memory_store and analysis_session_id:
            memory_store.save_chat_message(
                analysis_session_id,
                role="assistant",
                content=combined_response['explanation'],
                language=output_language,
                metadata={
                    "code_references": combined_response.get("code_references", []),
                    "intents_processed": len(intents),
                    "active_topics": _active_topics(updated_context_state, limit=6),
                },
            )
            memory_store.save_artifact(
                analysis_session_id,
                "chat_context_state",
                updated_context_state,
                replace=True,
            )

        record_metric(
            "chat_query_total",
            time.perf_counter() - start_time,
            {
                "intents": len(intents),
                "language": output_language,
                "query_length": len(query),
            },
        )

        progress_tracker = st.session_state.get("progress_tracker")
        if progress_tracker:
            progress_tracker.record_activity(
                "chat_query",
                {
                    "topic": query[:80],
                    "skill": "codebase_chat",
                    "minutes_spent": max(1, min(8, len(query) // 45)),
                },
            )
        
        st.session_state.chat_processing = False
    
    except Exception as e:
        logger.error(f"Query processing failed: {e}", exc_info=True)
        st.session_state.chat_history.append({
            'role': 'assistant',
            'content': f"I encountered an error while processing your question:\n\n```\n{str(e)}\n```\n\nPlease try:\n1. Rephrasing your question\n2. Being more specific\n3. Checking if the codebase is properly loaded",
            'code_references': []
        })
        if memory_store and analysis_session_id:
            memory_store.save_chat_message(
                analysis_session_id,
                role="assistant",
                content=f"I encountered an error while processing your question:\n{str(e)}",
                language=output_language,
            )
        record_metric(
            "chat_query_total",
            time.perf_counter() - start_time,
            {"error": str(e), "language": output_language},
        )
        st.session_state.chat_processing = False


def _ensure_analysis_session(memory_store, repo_analysis, repo_path: str, language: str) -> str:
    """Create or reuse an analysis session id for persistent memory."""
    if not memory_store:
        return ""
    existing = st.session_state.get("current_analysis_session_id")
    if existing:
        existing_session = memory_store.get_session(existing)
        if existing_session and existing_session.get("source_ref") == repo_path:
            return existing

    repo_title = getattr(repo_analysis, "repo_url", None) or repo_path
    repo_title = repo_title.rstrip("/").split("/")[-1] if repo_title else "repository"
    user_id = st.session_state.get("user_id", "anonymous")
    summary = getattr(repo_analysis, "summary", "")

    session_id = memory_store.create_session(
        user_id=user_id,
        source_type="repository",
        title=repo_title,
        source_ref=repo_path,
        language=language,
        summary=summary[:800] if summary else "",
    )
    st.session_state.current_analysis_session_id = session_id
    return session_id


def _combine_responses(responses: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Combine multiple intent responses into one."""
    if len(responses) == 1:
        return responses[0]
    
    # Multiple intents - combine explanations
    combined_explanation = ""
    all_code_refs = []
    
    for i, response in enumerate(responses, 1):
        if len(responses) > 1:
            combined_explanation += f"\n\n## {i}. {response['intent']}\n\n"
        
        combined_explanation += response['explanation']
        all_code_refs.extend(response.get('code_references', []))

    # Deduplicate citations and keep the highest score per file+line.
    deduped: Dict[str, Dict[str, Any]] = {}
    for ref in all_code_refs:
        file_path = str(ref.get("file", "")).strip()
        lines = str(ref.get("lines", "")).strip()
        key = f"{file_path}:{lines}"
        if not file_path:
            continue
        current_score = float(ref.get("score") or 0.0)
        existing = deduped.get(key)
        if not existing or float(existing.get("score") or 0.0) < current_score:
            deduped[key] = ref
    merged_refs = sorted(
        deduped.values(),
        key=lambda item: float(item.get("score") or 0.0),
        reverse=True,
    )
    
    return {
        'explanation': combined_explanation,
        'code_references': merged_refs
    }


def _render_message(message: Dict[str, Any]):
    """Render a chat message."""
    role = message['role']
    content = message['content']
    safe_content = html.escape(content or "")
    
    if role == 'user':
        st.markdown(
            f"""
                <div class="cg-chat-user">
                    <div class="cg-chat-label">You</div>
                    <div>{safe_content}</div>
                </div>
            """,
            unsafe_allow_html=True,
        )
    
    else:  # assistant
        st.markdown(
            """
            <div class="cg-chat-assistant">
                <div class="cg-chat-label">CodeGuru Assistant</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        
        # Render explanation
        st.markdown(content)
        
        # Show code references
        code_refs = message.get('code_references', [])
        if code_refs:
            repo_context = st.session_state.session_manager.get_current_repository() if "session_manager" in st.session_state else {}
            repo_path = repo_context.get("repo_path", "") if isinstance(repo_context, dict) else ""
            with st.expander(f"📁 Code References ({len(code_refs)} files)"):
                for idx, ref in enumerate(code_refs[:8], start=1):  # Show top references
                    file_path = ref.get("file", "")
                    lines = ref.get("lines", "")
                    abs_path = ref.get("abs_path") or _abspath_for_reference(repo_path, file_path)
                    line_value = ""
                    if lines and "-" in str(lines):
                        line_value = str(lines).split("-")[0]
                    elif lines:
                        line_value = str(lines)
                    link_target = f"file://{abs_path}"
                    if line_value.isdigit():
                        link_target = f"{link_target}#L{line_value}"
                    score = ref.get("score")
                    score_text = f" · relevance {float(score):.2f}" if score is not None else ""
                    st.markdown(
                        f"{idx}. [`{file_path}:{lines}`]({link_target}){score_text}"
                    )
                    snippet = str(ref.get("content", "") or "").strip()
                    if snippet:
                        st.code(
                            snippet[:360] + "..." if len(snippet) > 360 else snippet,
                            language="text",
                        )
        
        # Show metadata
        metadata = message.get('metadata', {})
        if metadata:
            st.caption(f"✓ Analyzed {metadata.get('files_analyzed', 0)} files | Processed {metadata.get('intents_processed', 1)} intent(s)")
            topics = metadata.get("active_topics") or []
            if topics:
                st.caption(f"Context topics: {', '.join(topics[:4])}")
        
        spacing("sm")
