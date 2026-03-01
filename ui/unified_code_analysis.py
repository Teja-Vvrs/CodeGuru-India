"""
Unified Code Analysis Interface.

Consolidates single file upload and repository analysis into one streamlined workflow.
"""

import streamlit as st
import logging
import os
import shutil
import tempfile
import time
from dataclasses import asdict, is_dataclass
from typing import Optional
from ui.design_system import section_header, spacing, info_box, render_hero, render_soft_panel
from ui.learning_artifacts_dashboard import render_learning_artifacts_dashboard
from utils.performance_metrics import record_metric
from utils.error_handler import (
    display_error,
    FileValidationError,
    AnalysisError
)
from utils.security import (
    validate_and_sanitize_file,
    sanitize_user_input,
    ensure_memory_only_processing,
    SecurityAuditor
)

logger = logging.getLogger(__name__)


DEFAULT_REPO_LEARNING_GOAL = (
    "Give me a practical onboarding to this repository: explain what it does, "
    "its architecture, key execution/data flows, and the most important files "
    "to read first."
)


def _to_serializable(value):
    """Best-effort conversion for dataclasses/objects to JSON-safe structures."""
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {k: _to_serializable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_serializable(v) for v in value]
    if hasattr(value, "__dict__"):
        return _to_serializable(vars(value))
    return value


def _ensure_memory_session(source_type: str, title: str, source_ref: str, summary: str = "") -> Optional[str]:
    """Create or reuse persistent memory session for current analysis source."""
    memory_store = st.session_state.get("memory_store")
    if not memory_store:
        return None

    existing_id = st.session_state.get("current_analysis_session_id")
    if existing_id:
        existing = memory_store.get_session(existing_id)
        if existing and existing.get("source_ref") == source_ref:
            if summary:
                memory_store.touch_session(existing_id, summary=summary[:1000])
            else:
                memory_store.touch_session(existing_id)
            return existing_id

    user_id = st.session_state.get("user_id", "anonymous")
    language = st.session_state.get("selected_language", "english")
    session_id = memory_store.create_session(
        user_id=user_id,
        source_type=source_type,
        title=title,
        source_ref=source_ref,
        language=language,
        summary=summary[:1000] if summary else "",
    )
    st.session_state.current_analysis_session_id = session_id
    return session_id


def _cleanup_single_file_temp_dir() -> None:
    """Delete previously created temporary directory for single-file chat context."""
    temp_dir = st.session_state.get("single_file_temp_dir")
    if temp_dir and os.path.isdir(temp_dir):
        shutil.rmtree(temp_dir, ignore_errors=True)
    st.session_state.single_file_temp_dir = None


def _reset_chat_state_for_new_source() -> None:
    """Reset chat/search state so stale source data is never reused."""
    semantic_search = st.session_state.get("semantic_search")
    if semantic_search:
        if hasattr(semantic_search, "clear_index"):
            semantic_search.clear_index()
        else:
            semantic_search.code_chunks = []
            semantic_search.file_summaries = {}

    st.session_state.pop("chat_history", None)
    st.session_state.loaded_chat_session_id = None
    st.session_state.current_analysis_session_id = None


def _clear_single_file_state(session_manager) -> None:
    """Clear single-file upload state when switching to repository mode."""
    session_manager.set_uploaded_code(None, None)
    st.session_state.uploaded_filename = None
    st.session_state.single_file_context_signature = ""
    st.session_state.single_file_uploader_version = st.session_state.get("single_file_uploader_version", 0) + 1
    _cleanup_single_file_temp_dir()


def _prepare_single_file_chat_context(session_manager, filename: str, file_content: str) -> None:
    """
    Build a temporary one-file repository context so Codebase Chat works for local file uploads.
    """
    from analyzers.repo_analyzer import FileInfo, RepoAnalysis

    _cleanup_single_file_temp_dir()

    temp_dir = tempfile.mkdtemp(prefix="codeguru_single_")
    target_path = os.path.join(temp_dir, filename)
    target_folder = os.path.dirname(target_path)
    if target_folder:
        os.makedirs(target_folder, exist_ok=True)
    with open(target_path, "w", encoding="utf-8", errors="ignore") as handle:
        handle.write(file_content)

    file_extension = os.path.splitext(filename)[1].lower()
    total_lines = max(len(file_content.splitlines()), 1)
    total_size_bytes = len(file_content.encode("utf-8", errors="ignore"))

    file_info = FileInfo(
        path=filename,
        name=os.path.basename(filename),
        extension=file_extension,
        size_bytes=total_size_bytes,
        lines=total_lines,
    )
    language = file_extension.lstrip(".") or "code"
    repo_analysis = RepoAnalysis(
        repo_url=filename,
        total_files=1,
        total_lines=total_lines,
        total_size_bytes=total_size_bytes,
        file_tree={"root": [file_info]},
        languages={language.upper(): total_lines},
        main_files=[file_info],
        summary=f"Single-file context created for {filename}.",
    )

    session_manager.set_current_repository(temp_dir, repo_analysis)
    st.session_state.single_file_temp_dir = temp_dir


def _build_default_learning_goal(repo_analysis) -> str:
    """Build a useful default learning goal for repository deep analysis."""
    repo_name = "repository"
    language_hint = ""

    if repo_analysis:
        repo_ref = getattr(repo_analysis, "repo_url", "") or "repository"
        repo_name = repo_ref.rstrip("/").split("/")[-1] or "repository"
        languages = list(getattr(repo_analysis, "languages", {}).keys())
        if languages:
            language_hint = f" Focus on the {', '.join(languages[:2])} parts first."

    return (
        f"For '{repo_name}', {DEFAULT_REPO_LEARNING_GOAL}"
        f"{language_hint} Keep it beginner-friendly but technically precise."
    )


def _prepare_auto_repo_learning_goal(repo_analysis) -> None:
    """Set auto-learning-goal session state for deep repository analysis."""
    st.session_state.pending_learning_goal = _build_default_learning_goal(repo_analysis)
    st.session_state.learning_goal_source = "auto"
    st.session_state.current_intent = None


def _get_analysis_learning_goal(session_manager, repo_analysis) -> str:
    """Resolve learning goal from explicit intent or auto fallback."""
    pending_goal = st.session_state.get("pending_learning_goal", "").strip()
    if pending_goal:
        return pending_goal

    intent_data = session_manager.get_current_intent()
    if intent_data and intent_data.get("intent"):
        intent = intent_data["intent"]
        original_input = getattr(intent, "original_input", "")
        if original_input:
            return original_input
        primary_intent = getattr(intent, "primary_intent", "")
        if primary_intent:
            return primary_intent.replace("_", " ")

    return _build_default_learning_goal(repo_analysis)


def _extract_repo_starter_files(selection_result, limit: int = 6):
    """Pick top files that are useful for first-pass repository onboarding."""
    if not selection_result or not getattr(selection_result, "selected_files", None):
        return []

    starter_files = []
    for item in selection_result.selected_files[:limit]:
        file_info = getattr(item, "file_info", None)
        file_path = getattr(file_info, "path", "")
        role = getattr(item, "file_role", "core_logic").replace("_", " ")
        reason = (getattr(item, "selection_reason", "") or "").split(";")[0].strip()

        if not file_path:
            continue
        if not reason:
            reason = "Important for understanding core behavior."

        starter_files.append({
            "path": file_path,
            "role": role,
            "reason": reason,
        })

    return starter_files


def _build_chat_starter_prompts(starter_files):
    """Generate practical prompts the user can ask in Codebase Chat."""
    if starter_files:
        first_file = starter_files[0]["path"]
        return [
            f"Explain the end-to-end flow starting from `{first_file}`.",
            f"What are the top 3 important modules around `{first_file}` and why?",
            "If I have only 30 minutes, what should I read first in this repo?",
        ]

    return [
        "Explain the main architecture and runtime flow of this repository.",
        "What files should I read first as a beginner, and in what order?",
        "Create a learning plan for this repo in simple terms.",
    ]


def _render_repo_starter_guide(result, session_manager):
    """Render practical first-use guidance before detailed artifacts."""
    st.markdown("### 🚀 Starter Guide")

    learning_goal = st.session_state.get("last_learning_goal") or st.session_state.get("pending_learning_goal", "")
    if learning_goal:
        st.caption(f"Learning goal used: {learning_goal}")

    repo_context = session_manager.get_current_repository() or {}
    repo_analysis = repo_context.get("repo_analysis")
    if repo_analysis:
        repo_summary = getattr(repo_analysis, "summary", "") or ""
        if repo_summary:
            with st.expander("What this repository contains", expanded=True):
                st.text(repo_summary)

    selection_result = result.get("selection_result")
    starter_files = _extract_repo_starter_files(selection_result)

    if starter_files:
        st.markdown("#### Start with These Files")
        for index, item in enumerate(starter_files, start=1):
            st.markdown(f"{index}. `{item['path']}` ({item['role']}) - {item['reason']}")

    st.markdown("#### Ask These in Codebase Chat")
    for prompt in _build_chat_starter_prompts(starter_files):
        st.code(prompt, language="text")

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("💬 Open Codebase Chat", use_container_width=True):
            st.session_state.current_page = "Codebase Chat"
            st.rerun()
    with col2:
        if st.button("🧾 Open Explanations", use_container_width=True):
            st.session_state.current_page = "Explanations"
            st.rerun()
    with col3:
        if st.button("🛤️ Open Learning Paths", use_container_width=True):
            st.session_state.current_page = "Learning Paths"
            st.rerun()


def _complexity_label(score: int) -> str:
    """Convert numeric complexity score into human-friendly level."""
    if score <= 20:
        return "Low"
    if score <= 50:
        return "Medium"
    if score <= 80:
        return "High"
    return "Very High"


def _extract_code_reading_order(structure: dict, limit: int = 6):
    """Build an ordered list of classes/functions to read first."""
    if not isinstance(structure, dict):
        return []

    items = []
    for cls in structure.get("classes", []) or []:
        items.append({
            "kind": "Class",
            "name": cls.get("name", "UnknownClass"),
            "line": int(cls.get("line_number") or 0),
        })

    for func in structure.get("functions", []) or []:
        items.append({
            "kind": "Function",
            "name": func.get("name", "unknown_function"),
            "line": int(func.get("line_number") or 0),
        })

    items = [item for item in items if item["line"] > 0]
    items.sort(key=lambda item: item["line"])
    return items[:limit]


def _build_single_file_prompts(filename: str, reading_order):
    """Generate practical follow-up prompts for continued learning."""
    if reading_order:
        anchor = reading_order[0]["name"]
        return [
            f"Explain `{anchor}` step-by-step with input/output examples.",
            f"What edge cases can break `{anchor}` in `{filename}`?",
            f"If this file grows, how should we refactor `{filename}` safely?",
        ]

    return [
        f"Explain the end-to-end flow of `{filename}` in simple terms.",
        f"What are likely bugs or edge cases in `{filename}`?",
        f"How can `{filename}` be made easier to maintain?",
    ]


def render_unified_code_analysis(
    orchestrator,
    repository_manager,
    intent_interpreter,
    session_manager,
    code_analyzer,
    flashcard_manager
):
    """
    Render unified code analysis interface.
    
    Args:
        orchestrator: IntentDrivenOrchestrator instance
        repository_manager: RepositoryManager instance
        intent_interpreter: IntentInterpreter instance
        session_manager: SessionManager instance
        code_analyzer: CodeAnalyzer instance
        flashcard_manager: FlashcardManager instance
    """
    render_hero(
        "Analyze Code, Learn Faster",
        "Upload a local file or full repository. Get grounded explanations, ask follow-up questions, and generate learning artifacts from your real codebase.",
        pills=[
            "Single File + Repository",
            "Voice + Native Language",
            "Chat + Quiz + Flashcards",
        ],
    )
    section_header("Analysis Workspace", "Choose an input source and start your guided learning flow")
    
    # Initialize workflow state
    if 'analysis_mode' not in st.session_state:
        st.session_state.analysis_mode = None
    if 'workflow_step' not in st.session_state:
        st.session_state.workflow_step = 'upload'
    
    # Step 1: Upload
    if st.session_state.workflow_step == 'upload':
        _render_upload_step(
            repository_manager,
            session_manager,
            code_analyzer
        )
    
    # Step 2: Intent (only for deep mode)
    elif st.session_state.workflow_step == 'intent':
        _render_intent_step(
            intent_interpreter,
            session_manager
        )
    
    # Step 3: Analysis
    elif st.session_state.workflow_step == 'analyze':
        _render_analysis_step(
            orchestrator,
            session_manager,
            code_analyzer,
            flashcard_manager
        )
    
    # Step 4: Results
    elif st.session_state.workflow_step == 'results':
        _render_results_step(session_manager)


def _render_upload_step(repository_manager, session_manager, code_analyzer):
    """Render unified upload interface."""
    render_soft_panel(
        "Recommended Demo Flow",
        "Use repository upload for full architecture walkthroughs. Use single-file upload for quick debugging or concept explanation.",
    )
    
    # Upload method tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "📄 Single File",
        "🔗 GitHub URL",
        "📦 ZIP/Folder",
        "🎤 Voice Query"
    ])
    
    # Tab 1: Single File Upload
    with tab1:
        spacing("md")
        _render_single_file_upload(session_manager, code_analyzer)
    
    # Tab 2: GitHub URL
    with tab2:
        spacing("md")
        _render_github_upload(repository_manager, session_manager)
    
    # Tab 3: ZIP/Folder Upload
    with tab3:
        spacing("md")
        _render_zip_folder_upload(repository_manager, session_manager)
    
    # Tab 4: Voice Query
    with tab4:
        spacing("md")
        _render_voice_query(session_manager)
    
    # Show uploaded content summary
    _show_upload_summary(session_manager)


def _render_single_file_upload(session_manager, code_analyzer):
    """Render single file upload interface."""
    st.markdown("### Quick Analysis")
    st.caption("Upload a single code file for fast analysis")

    if "single_file_uploader_version" not in st.session_state:
        st.session_state.single_file_uploader_version = 0
    
    uploaded_file = st.file_uploader(
        "Choose a code file",
        type=['py', 'js', 'jsx', 'ts', 'tsx', 'java', 'cpp', 'c', 'go', 'rb'],
        help="Supported: Python, JavaScript, TypeScript, Java, C++, C, Go, Ruby",
        key=f"single_file_uploader_{st.session_state.single_file_uploader_version}",
    )
    
    if uploaded_file:
        # Validate file upload with comprehensive security checks
        allowed_extensions = ['.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.cpp', '.c', '.go', '.rb']
        is_valid, error_msg, warnings = validate_and_sanitize_file(
            uploaded_file,
            max_size_mb=10,
            allowed_extensions=allowed_extensions
        )
        
        if not is_valid:
            display_error(
                "File Upload Error",
                error_msg,
                suggestions=[
                    "Check that your file is under 10MB",
                    "Ensure the file has a supported extension",
                    "Verify the file is not corrupted or contains malicious content",
                    "Try a different file"
                ]
            )
            return
        
        # Display security warnings if any
        if warnings:
            for warning in warnings:
                st.warning(f"⚠️ Security Notice: {warning}")
        
        file_signature = f"{uploaded_file.name}:{uploaded_file.size}"
        previous_signature = st.session_state.get("single_file_context_signature")

        if previous_signature != file_signature:
            try:
                # Store uploaded file and create chat-compatible context for this exact file.
                file_content = uploaded_file.getvalue().decode('utf-8', errors='ignore')
                
                # Sanitize code content
                is_valid_code, error_msg, sanitized_code, code_warnings = sanitize_user_input(
                    file_content,
                    input_type='code',
                    max_length=1000000  # 1MB text limit
                )
                
                if not is_valid_code:
                    st.error(error_msg)
                    return
                
                # Display code warnings
                if code_warnings:
                    with st.expander("⚠️ Code Security Warnings"):
                        for warning in code_warnings:
                            st.warning(warning)
                
                # Ensure memory-only processing
                if not ensure_memory_only_processing():
                    st.error("Security validation failed: Code persistence detected")
                    return
                
                session_manager.set_uploaded_code(sanitized_code, uploaded_file.name)
                _reset_chat_state_for_new_source()
                _prepare_single_file_chat_context(session_manager, uploaded_file.name, sanitized_code)
                st.session_state.single_file_context_signature = file_signature
                
                # Audit memory usage
                SecurityAuditor.audit_memory_usage()
            
            except Exception as e:
                logger.error(f"File processing failed: {e}")
                display_error(
                    "File Processing Error",
                    "Failed to process the uploaded file",
                    suggestions=[
                        "Check if the file is corrupted",
                        "Try re-uploading the file",
                        "Ensure the file contains valid code"
                    ]
                )
                return
        
        st.success(f"✅ Uploaded: {uploaded_file.name}")

        if st.button("⚡ Analyze File Now", use_container_width=True, type="primary"):
            st.session_state.analysis_mode = 'quick'
            st.session_state.workflow_step = 'analyze'
            st.rerun()

        st.info(
            "Need deep architecture learning with chat across multiple files? "
            "Use GitHub URL or ZIP/Folder upload above."
        )


def _render_github_upload(repository_manager, session_manager):
    """Render GitHub repository upload interface."""
    st.markdown("### GitHub Repository")
    st.caption("Analyze an entire repository from GitHub")
    
    github_url = st.text_input(
        "Repository URL",
        placeholder="https://github.com/username/repository",
        help="Enter the full GitHub repository URL"
    )
    
    if st.button("Upload Repository", type="primary"):
        if not github_url:
            st.error("Please enter a GitHub URL")
        else:
            # Sanitize and validate GitHub URL
            is_valid, error_msg, sanitized_url, warnings = sanitize_user_input(
                github_url,
                input_type='url'
            )
            
            if not is_valid:
                display_error(
                    "Invalid GitHub URL",
                    error_msg,
                    suggestions=[
                        "Ensure the URL starts with https://",
                        "Use the format: https://github.com/username/repository",
                        "Check for typos in the URL"
                    ]
                )
                return
            
            # Display warnings if any
            if warnings:
                for warning in warnings:
                    st.warning(f"⚠️ {warning}")
            
            with st.spinner("Cloning repository..."):
                result = repository_manager.upload_from_github(sanitized_url)
                
                if result.success:
                    _clear_single_file_state(session_manager)
                    _reset_chat_state_for_new_source()
                    session_manager.set_current_repository(result.repo_path, result.repo_analysis)
                    _prepare_auto_repo_learning_goal(result.repo_analysis)
                    _ensure_memory_session(
                        source_type="repository",
                        title=(result.repo_analysis.repo_url.rstrip("/").split("/")[-1]
                               if result.repo_analysis and getattr(result.repo_analysis, "repo_url", None)
                               else "repository"),
                        source_ref=result.repo_path,
                        summary=getattr(result.repo_analysis, "summary", ""),
                    )
                    
                    # Ensure memory-only processing
                    if not ensure_memory_only_processing():
                        st.warning("⚠️ Security notice: Repository data is stored in temporary directory")
                    
                    # Audit memory usage
                    SecurityAuditor.audit_memory_usage()
                    
                    st.success(f"✅ Repository uploaded successfully!")
                    st.session_state.analysis_mode = 'deep'
                    st.session_state.workflow_step = 'analyze'
                    st.rerun()
                else:
                    st.error(f"❌ Upload failed: {result.error_message}")


def _render_zip_folder_upload(repository_manager, session_manager):
    """Render ZIP file and folder upload interface."""
    st.markdown("### ZIP File or Folder")
    st.caption("Upload a compressed repository or select a local folder")
    
    # ZIP file upload
    st.markdown("#### Upload ZIP File")
    zip_file = st.file_uploader(
        "Choose a ZIP file",
        type=['zip'],
        help="Upload a ZIP file containing your code repository"
    )
    
    if zip_file:
        if st.button("Process ZIP File", type="primary"):
            with st.spinner("Extracting and analyzing..."):
                result = repository_manager.upload_from_zip(zip_file)
                
                if result.success:
                    _clear_single_file_state(session_manager)
                    _reset_chat_state_for_new_source()
                    session_manager.set_current_repository(result.repo_path, result.repo_analysis)
                    _prepare_auto_repo_learning_goal(result.repo_analysis)
                    _ensure_memory_session(
                        source_type="repository",
                        title=(result.repo_analysis.repo_url.rstrip("/").split("/")[-1]
                               if result.repo_analysis and getattr(result.repo_analysis, "repo_url", None)
                               else "repository_zip"),
                        source_ref=result.repo_path,
                        summary=getattr(result.repo_analysis, "summary", ""),
                    )
                    st.success("✅ ZIP file processed successfully!")
                    st.session_state.analysis_mode = 'deep'
                    st.session_state.workflow_step = 'analyze'
                    st.rerun()
                else:
                    st.error(f"❌ Processing failed: {result.error_message}")
    
    spacing("lg")
    
    # Folder selection
    st.markdown("#### Select Local Folder")
    folder_path = st.text_input(
        "Folder Path",
        placeholder="/path/to/your/code/folder",
        help="Enter the full path to your local code folder"
    )
    
    if folder_path and st.button("Analyze Folder", type="primary"):
        with st.spinner("Analyzing folder..."):
            result = repository_manager.upload_from_folder(folder_path)
            
            if result.success:
                _clear_single_file_state(session_manager)
                _reset_chat_state_for_new_source()
                session_manager.set_current_repository(result.repo_path, result.repo_analysis)
                _prepare_auto_repo_learning_goal(result.repo_analysis)
                _ensure_memory_session(
                    source_type="repository",
                    title=(result.repo_analysis.repo_url.rstrip("/").split("/")[-1]
                           if result.repo_analysis and getattr(result.repo_analysis, "repo_url", None)
                           else "repository_folder"),
                    source_ref=result.repo_path,
                    summary=getattr(result.repo_analysis, "summary", ""),
                )
                st.success("✅ Folder analyzed successfully!")
                st.session_state.analysis_mode = 'deep'
                st.session_state.workflow_step = 'analyze'
                st.rerun()
            else:
                st.error(f"❌ Analysis failed: {result.error_message}")


def _render_voice_query(session_manager):
    """Render voice query interface."""
    st.markdown("### Voice Query")
    st.caption("Ask questions about code using your voice")
    
    # Initialize voice query state
    if "voice_query" not in st.session_state:
        st.session_state.voice_query = ""
    if "voice_transcript" not in st.session_state:
        st.session_state.voice_transcript = ""
    
    # Voice processor
    voice_processor = st.session_state.get("voice_processor")
    
    if voice_processor:
        languages = voice_processor.get_supported_languages()
        
        # Language selector for voice
        voice_lang = st.selectbox(
            "Select Voice Language",
            options=list(languages.keys()),
            format_func=lambda x: languages[x],
            key="voice_language"
        )
        
        info_box(f"Speak in {languages[voice_lang]} to ask questions about your code", "info")
        
        spacing("sm")
        
        # Audio recorder component
        st.markdown("**Record your question:**")
        
        try:
            # Try to use streamlit-audio-recorder if available
            from audio_recorder_streamlit import audio_recorder
            
            audio_bytes = audio_recorder(
                text="Click to record",
                recording_color="#0066CC",
                neutral_color="#E5E5E5",
                icon_size="2x"
            )
            
            if audio_bytes:
                st.success("✓ Audio recorded!")
                
                # Process audio
                if st.button("🔄 Transcribe Audio", type="primary"):
                    with st.spinner("🎙️ Transcribing..."):
                        result = voice_processor.process_audio(audio_bytes, voice_lang)
                        
                        if result:
                            st.session_state.voice_transcript = result.transcript
                            st.session_state.voice_query = result.transcript
                            
                            st.success(f"✓ Transcribed ({result.confidence:.0%} confidence)")
                            st.info(f"**Transcript:** {result.transcript}")
                        else:
                            st.error("Failed to transcribe audio")
        
        except ImportError:
            st.warning("⚠️ Audio recorder not available. Install with: pip install streamlit-audio-recorder")
            st.info("💡 Use the text box below instead")
    
    else:
        st.warning("⚠️ Voice processor not initialized")
    
    spacing("md")
    
    # Text input as fallback
    st.markdown("**Or type your question:**")
    voice_query = st.text_area(
        "Type your question",
        value=st.session_state.voice_transcript,
        placeholder="What does this function do?\nExplain the authentication logic\nHow does this code work?",
        height=120,
        key="voice_query_input",
        label_visibility="collapsed"
    )
    
    if voice_query:
        st.session_state.voice_query = voice_query
    
    repo_context = session_manager.get_current_repository()

    # Process voice query button
    if st.session_state.voice_query:
        if st.button("🚀 Ask in Codebase Chat", type="primary", use_container_width=True):
            if repo_context:
                st.session_state.chat_input = st.session_state.voice_query
                st.session_state.current_page = "Codebase Chat"
                st.rerun()
            else:
                st.error("Upload a repository first, then ask voice/text questions in Codebase Chat.")


def _show_upload_summary(session_manager):
    """Show summary of uploaded content."""
    # Check for uploaded file
    uploaded_code = session_manager.get_uploaded_code()
    uploaded_filename = st.session_state.get('uploaded_filename')
    
    # Check for uploaded repository
    current_repo = session_manager.get_current_repository()
    
    if uploaded_code or current_repo:
        spacing("lg")
        st.divider()
        st.markdown("### 📊 Upload Summary")
        
        if uploaded_code and uploaded_filename:
            st.info(f"**File**: {uploaded_filename}")
        
        if current_repo:
            repo_analysis = current_repo.get('repo_analysis')
            if repo_analysis:
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Files", repo_analysis.total_files)
                with col2:
                    st.metric("Lines", f"{repo_analysis.total_lines:,}")
                with col3:
                    languages = ", ".join(repo_analysis.languages.keys())
                    st.metric("Languages", len(repo_analysis.languages))
                
                with st.expander("Repository Details"):
                    st.write(f"**URL**: {repo_analysis.repo_url}")
                    st.write(f"**Size**: {repo_analysis.total_size_bytes / 1024:.1f} KB")
                    st.write(f"**Languages**: {languages}")


def _render_intent_step(intent_interpreter, session_manager):
    """Render intent input step."""
    st.markdown("## 🎯 Optional: Define Your Learning Goal")
    st.caption("Skip this if you prefer auto-analysis and continue directly.")
    
    # Back button
    if st.button("← Back to Upload"):
        st.session_state.workflow_step = 'upload'
        st.rerun()
    
    spacing("md")
    
    repo_context = session_manager.get_current_repository()
    repo_analysis = repo_context.get("repo_analysis") if repo_context else None
    suggested_goal = _build_default_learning_goal(repo_analysis)
    template_prefill = st.session_state.pop("learning_goal_template_prefill", "")
    if template_prefill:
        st.session_state.manual_learning_goal = template_prefill
    current_goal_text = st.session_state.get("manual_learning_goal", suggested_goal)

    # Intent input
    user_input = st.text_area(
        "What do you want to learn?",
        value=current_goal_text,
        key="manual_learning_goal_input",
        placeholder="Examples:\n- Understand the authentication flow\n- Learn how the payment system works\n- Prepare for interview questions about this codebase\n- Focus on the backend API architecture",
        height=150,
        help="Describe your learning goal in natural language"
    )
    st.session_state.manual_learning_goal = user_input
    
    # Quick intent templates
    st.markdown("#### Quick Templates")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🔐 Authentication Flow", use_container_width=True):
            st.session_state.learning_goal_template_prefill = "Understand the authentication and authorization flow"
            st.rerun()
    
    with col2:
        if st.button("🏗️ Architecture", use_container_width=True):
            st.session_state.learning_goal_template_prefill = "Learn the overall system architecture and design patterns"
            st.rerun()
    
    with col3:
        if st.button("💼 Interview Prep", use_container_width=True):
            st.session_state.learning_goal_template_prefill = "Prepare for technical interview questions about this codebase"
            st.rerun()
    
    spacing("md")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Continue to Analysis →", type="primary"):
            if user_input:
                with st.spinner("Interpreting your learning goal..."):
                    if repo_context:
                        intent = intent_interpreter.interpret_intent(user_input, repo_analysis)
                        session_manager.set_current_intent(intent)
                        st.session_state.pending_learning_goal = user_input
                        st.session_state.learning_goal_source = "manual"
                        st.session_state.workflow_step = 'analyze'
                        st.rerun()
                    else:
                        st.error("No repository found. Please upload code first.")
            else:
                st.error("Please provide a goal or use Skip.")
    with col2:
        if st.button("Skip and Auto-Analyze", use_container_width=True):
            if repo_context:
                _prepare_auto_repo_learning_goal(repo_analysis)
                st.session_state.workflow_step = "analyze"
                st.rerun()
            else:
                st.error("No repository found. Please upload code first.")


def _render_analysis_step(orchestrator, session_manager, code_analyzer, flashcard_manager):
    """Render analysis step."""
    st.markdown("## 🔍 Analyzing Code")
    
    analysis_mode = st.session_state.analysis_mode
    
    if analysis_mode == 'quick':
        _run_quick_analysis(session_manager, code_analyzer, flashcard_manager)
    elif analysis_mode == 'deep':
        active_goal = st.session_state.get("pending_learning_goal")
        if active_goal:
            st.caption("Using this learning goal for deep analysis:")
            st.info(active_goal)
        _run_deep_analysis(orchestrator, session_manager)
    else:
        st.error("Invalid analysis mode")


def _run_quick_analysis(session_manager, code_analyzer, flashcard_manager):
    """Run quick single-file analysis."""
    code = session_manager.get_uploaded_code()
    filename = st.session_state.get('uploaded_filename', 'code.py')
    
    if not code:
        st.error("No file found. Please upload a file first.")
        return
    
    with st.spinner("Analyzing code..."):
        start_time = time.perf_counter()
        try:
            analysis_session_id = _ensure_memory_session(
                source_type="code",
                title=filename,
                source_ref=filename,
                summary=f"Quick analysis for {filename}",
            )

            # Analyze file
            analysis = code_analyzer.analyze_file(code, filename)
            
            # Generate flashcards
            flashcards = flashcard_manager.generate_flashcards(
                analysis,
                language=st.session_state.get("selected_language", "english"),
            )
            flashcards_serialized = _to_serializable(flashcards)
            
            # Store results in session state
            st.session_state.current_analysis = {
                'mode': 'quick',
                'analysis': analysis,
                'flashcards': flashcards_serialized,
                'filename': filename
            }

            memory_store = st.session_state.get("memory_store")
            if memory_store and analysis_session_id:
                memory_store.touch_session(
                    analysis_session_id,
                    summary=f"Quick analysis complete for {filename}",
                )
                memory_store.save_artifact(
                    analysis_session_id,
                    "quick_analysis",
                    {
                        "filename": filename,
                        "analysis": _to_serializable(analysis),
                    },
                    replace=True,
                )
                memory_store.save_artifact(
                    analysis_session_id,
                    "quick_flashcards",
                    flashcards_serialized,
                    replace=True,
                )

            record_metric(
                "quick_analysis_total",
                time.perf_counter() - start_time,
                {"mode": "quick", "filename": filename},
            )

            progress_tracker = st.session_state.get("progress_tracker")
            if progress_tracker:
                progress_tracker.record_activity(
                    "analysis_completed",
                    {
                        "topic": filename,
                        "skill": "quick_analysis",
                        "minutes_spent": 10,
                    },
                )
            
            st.success("✅ Analysis complete!")
            st.session_state.workflow_step = 'results'
            st.rerun()
        
        except Exception as e:
            record_metric(
                "quick_analysis_total",
                time.perf_counter() - start_time,
                {"mode": "quick", "filename": filename, "error": str(e)},
            )
            logger.error(f"Quick analysis failed: {e}")
            st.error(f"Analysis failed: {str(e)}")


def _run_deep_analysis(orchestrator, session_manager):
    """Run deep intent-driven analysis."""
    repo_context = session_manager.get_current_repository()

    if not repo_context:
        st.error("Missing repository. Please upload repository and try again.")
        return
    
    with st.spinner("Running deep analysis..."):
        start_time = time.perf_counter()
        try:
            repo_path = repo_context.get('repo_path')
            repo_analysis = repo_context.get('repo_analysis')
            user_input = _get_analysis_learning_goal(session_manager, repo_analysis)
            analysis_session_id = _ensure_memory_session(
                source_type="repository",
                title=(getattr(repo_analysis, "repo_url", repo_path).rstrip("/").split("/")[-1]
                       if repo_analysis
                       else "repository"),
                source_ref=repo_path,
                summary=getattr(repo_analysis, "summary", ""),
            )
            
            # Index repository for semantic search
            if 'semantic_search' in st.session_state:
                with st.spinner("Indexing codebase for intelligent search..."):
                    index_start = time.perf_counter()
                    st.session_state.semantic_search.index_repository(repo_path, repo_analysis)
                    record_metric(
                        "repository_indexing",
                        time.perf_counter() - index_start,
                        {"repo_path": repo_path},
                    )
                    st.success("✓ Codebase indexed - you can now use Codebase Chat!")
            
            # Run complete workflow
            result = orchestrator.analyze_repository_with_intent(
                repo_path,
                user_input
            )
            
            if 'error' in result:
                st.error(f"Analysis failed: {result['error']}")
            else:
                # Store results in session state
                st.session_state.current_analysis = {
                    'mode': 'deep',
                    'result': result
                }
                st.session_state.last_learning_goal = user_input

                memory_store = st.session_state.get("memory_store")
                if memory_store and analysis_session_id and result.get("status") == "success":
                    memory_store.touch_session(
                        analysis_session_id,
                        summary=result.get("concept_summary", {}).get("summary", "Deep analysis completed"),
                    )
                    memory_store.save_artifact(
                        analysis_session_id,
                        "deep_analysis",
                        _to_serializable(result),
                        replace=True,
                    )
                
                st.session_state.pending_learning_goal = ""
                record_metric(
                    "deep_analysis_total",
                    time.perf_counter() - start_time,
                    {"mode": "deep", "repo_path": repo_path},
                )

                progress_tracker = st.session_state.get("progress_tracker")
                if progress_tracker:
                    progress_tracker.record_activity(
                        "analysis_completed",
                        {
                            "topic": user_input,
                            "skill": "deep_analysis",
                            "minutes_spent": 20,
                        },
                    )
                st.success("✅ Deep analysis complete!")
                st.session_state.workflow_step = 'results'
                st.rerun()
        
        except Exception as e:
            record_metric(
                "deep_analysis_total",
                time.perf_counter() - start_time,
                {"mode": "deep", "error": str(e)},
            )
            logger.error(f"Deep analysis failed: {e}")
            st.error(f"Analysis failed: {str(e)}")


def _render_results_step(session_manager):
    """Render analysis results."""
    analysis = st.session_state.get('current_analysis')
    
    if not analysis:
        st.error("No analysis results found")
        return
    
    mode = analysis.get('mode')
    
    # Header with restart button
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown("## 📊 Analysis Results")
    with col2:
        if st.button("🔄 New Analysis", use_container_width=True):
            session_manager.clear_current_analysis()
            _clear_single_file_state(session_manager)
            _reset_chat_state_for_new_source()
            st.session_state.workflow_step = 'upload'
            st.session_state.analysis_mode = None
            st.session_state.current_analysis = None
            st.session_state.pending_learning_goal = ""
            st.session_state.last_learning_goal = ""
            st.session_state.learning_goal_source = ""
            st.rerun()
    
    spacing("md")
    
    if mode == 'quick':
        _render_quick_results(analysis)
    elif mode == 'deep':
        _render_deep_results(analysis, session_manager)


def _render_quick_results(analysis):
    """Render quick analysis results."""
    analysis_data = analysis.get('analysis', {})
    if not isinstance(analysis_data, dict):
        analysis_data = _to_serializable(analysis_data)
    flashcards = analysis.get('flashcards', [])
    filename = analysis.get('filename', 'code file')
    
    # Tabs for different views
    tab1, tab2 = st.tabs(["🚀 Starter Guide", "🎴 Flashcards"])
    
    with tab1:
        st.markdown(f"### {filename} - Practical Walkthrough")

        summary_text = analysis_data.get("summary") or analysis_data.get("explanation")
        if summary_text:
            st.markdown("#### What This File Does")
            st.markdown(summary_text)
        else:
            st.info("Summary is not available for this file.")

        complexity = int(analysis_data.get("complexity_score") or 0)
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Complexity Score", complexity)
        with col2:
            st.metric("Complexity Level", _complexity_label(complexity))

        structure = analysis_data.get("structure", {})
        reading_order = _extract_code_reading_order(structure)
        if reading_order:
            st.markdown("#### Read in This Order")
            for index, item in enumerate(reading_order, start=1):
                st.markdown(
                    f"{index}. {item['kind']} `{item['name']}` (line {item['line']})"
                )

        patterns = analysis_data.get("patterns", []) or []
        if patterns:
            st.markdown("#### Key Patterns in This File")
            for pattern in patterns[:4]:
                name = pattern.get("name", "Pattern")
                desc = pattern.get("description", "")
                st.markdown(f"- **{name}**: {desc}")

        issues = analysis_data.get("issues", []) or []
        if issues:
            st.markdown("#### Review These Potential Issues")
            for issue in issues[:5]:
                severity = (issue.get("severity", "warning") or "warning").upper()
                line_num = issue.get("line_number", "?")
                description = issue.get("description", "Potential issue detected.")
                suggestion = issue.get("suggestion", "Review this section.")
                st.markdown(
                    f"- `{severity}` line {line_num}: {description} | Fix: {suggestion}"
                )

        st.markdown("#### Ask Next")
        for prompt in _build_single_file_prompts(filename, reading_order):
            st.code(prompt, language="text")
    
    with tab2:
        st.markdown("### Flashcards")
        
        if flashcards and len(flashcards) > 0:
            st.info(f"Generated {len(flashcards)} flashcards for review")
            
            for i, card in enumerate(flashcards, 1):
                with st.expander(f"Card {i}: {card.get('front', 'Question')}"):
                    st.markdown(f"**Question:** {card.get('front', 'N/A')}")
                    st.markdown(f"**Answer:** {card.get('back', 'N/A')}")
                    
                    if 'code_evidence' in card:
                        st.code(card['code_evidence'], language='python')
        else:
            st.info("No flashcards generated. Flashcards are created for more complex code.")
            st.caption("Try a larger file for stronger practice material.")


def _render_deep_results(analysis, session_manager):
    """Render deep analysis results."""
    result = analysis.get('result', {})
    
    # Check result status
    status = result.get('status', 'unknown')
    
    if status == 'error':
        st.error(f"Analysis failed: {result.get('error', 'Unknown error')}")
        return
    
    elif status == 'clarification_needed':
        st.warning("The learning goal needs clarification.")
        questions = result.get('questions', [])
        for question in questions:
            st.write(f"- {question}")
        if st.button("Use Smart Default Goal Instead", type="primary"):
            repo_context = session_manager.get_current_repository() or {}
            repo_analysis = repo_context.get("repo_analysis")
            _prepare_auto_repo_learning_goal(repo_analysis)
            st.session_state.workflow_step = "analyze"
            st.rerun()
        return
    
    elif status == 'no_files_found':
        st.warning("No relevant files found for your learning goal")
        suggestions = result.get('suggestions', [])
        if suggestions:
            st.write("**Suggestions:**")
            for suggestion in suggestions:
                st.write(f"- {suggestion}")
        return
    
    elif status == 'success':
        # Show summary
        intent = result.get('intent')
        selection_result = result.get('selection_result')
        
        if intent and selection_result:
            st.success("✅ Analysis complete!")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Files Analyzed", len(selection_result.selected_files))
            with col2:
                flashcards = result.get('flashcards', [])
                st.metric("Flashcards", len(flashcards))
            with col3:
                quiz = result.get('quiz', {})
                questions = quiz.get('questions', [])
                st.metric("Quiz Questions", len(questions))
            
            spacing("md")

        tab1, tab2 = st.tabs(["🚀 Starter Guide", "📚 Learning Materials"])
        with tab1:
            _render_repo_starter_guide(result, session_manager)
        with tab2:
            render_learning_artifacts_dashboard(session_manager)
    
    else:
        st.error(f"Unknown analysis status: {status}")
