"""Main entry point for CodeGuru India application."""
import streamlit as st
from session_manager import SessionManager
from config import load_config
from ai.bedrock_client import BedrockClient
from ai.prompt_templates import PromptManager
from ai.langchain_orchestrator import LangChainOrchestrator
from analyzers.code_analyzer import CodeAnalyzer

# Module-level cache for session-specific services
# This avoids storing non-serializable objects in st.session_state
_session_services_cache = {}


@st.cache_resource
def get_backend_services():
    """
    Initialize and cache backend services.
    
    Uses @st.cache_resource to avoid serialization issues and improve performance.
    These objects are cached globally and reused across sessions.
    """
    try:
        # Load configuration
        aws_config, app_config = load_config()
        
        # Initialize AI services
        bedrock_client = BedrockClient(aws_config)
        prompt_manager = PromptManager()
        orchestrator = LangChainOrchestrator(bedrock_client, prompt_manager)
        
        from ai.voice_processor import VoiceProcessor
        voice_processor = VoiceProcessor(aws_config)
        
        # Initialize analyzers and engines
        code_analyzer = CodeAnalyzer(orchestrator)
        
        from engines.explanation_engine import ExplanationEngine
        from engines.quiz_engine import QuizEngine
        from generators.diagram_generator import DiagramGenerator
        from learning.path_manager import LearningPathManager
        from analyzers.repo_analyzer import RepoAnalyzer
        
        explanation_engine = ExplanationEngine(orchestrator)
        quiz_engine = QuizEngine(orchestrator)
        diagram_generator = DiagramGenerator()
        path_manager = LearningPathManager()
        repo_analyzer = RepoAnalyzer(code_analyzer)
        
        # Initialize intent-driven analysis components
        from analyzers.intent_interpreter import IntentInterpreter
        from analyzers.file_selector import FileSelector
        from analyzers.multi_file_analyzer import MultiFileAnalyzer
        from analyzers.repository_manager import RepositoryManager
        
        # Initialize new AI-powered components
        from analyzers.semantic_code_search import SemanticCodeSearch
        from analyzers.multi_intent_analyzer import MultiIntentAnalyzer
        from analyzers.rag_explainer import RAGExplainer
        from storage.memory_store import MemoryStore
        from storage.session_memory_store import SessionMemoryStore
        from generators.chat_learning_generator import ChatLearningGenerator
        
        intent_interpreter = IntentInterpreter(orchestrator)
        file_selector = FileSelector(orchestrator)
        multi_file_analyzer = MultiFileAnalyzer(code_analyzer, orchestrator)
        repository_manager = RepositoryManager(repo_analyzer, max_size_mb=100)
        
        # Note: These need session_manager which is session-specific, so we'll initialize them separately
        semantic_search = SemanticCodeSearch(orchestrator)
        multi_intent_analyzer = MultiIntentAnalyzer(orchestrator)
        rag_explainer = RAGExplainer(orchestrator, web_search_available=False)
        
        if app_config.memory_backend == "sqlite":
            memory_store = MemoryStore()
            memory_backend = "sqlite"
        else:
            memory_store = SessionMemoryStore()
            memory_backend = "session"
        
        chat_learning_generator = ChatLearningGenerator(orchestrator)
        
        return {
            'bedrock_client': bedrock_client,
            'prompt_manager': prompt_manager,
            'orchestrator': orchestrator,
            'voice_processor': voice_processor,
            'code_analyzer': code_analyzer,
            'explanation_engine': explanation_engine,
            'quiz_engine': quiz_engine,
            'diagram_generator': diagram_generator,
            'path_manager': path_manager,
            'repo_analyzer': repo_analyzer,
            'intent_interpreter': intent_interpreter,
            'file_selector': file_selector,
            'multi_file_analyzer': multi_file_analyzer,
            'repository_manager': repository_manager,
            'semantic_search': semantic_search,
            'multi_intent_analyzer': multi_intent_analyzer,
            'rag_explainer': rag_explainer,
            'memory_store': memory_store,
            'memory_backend': memory_backend,
            'chat_learning_generator': chat_learning_generator,
            'app_config': app_config,
        }
    except Exception as e:
        return {'error': str(e)}


def get_service(service_name: str):
    """
    Helper function to get a cached service by name.
    
    Args:
        service_name: Name of the service to retrieve
        
    Returns:
        The requested service or None if not found
    """
    services = get_backend_services()
    return services.get(service_name)


def get_session_specific_services():
    """
    Get or create session-specific services that depend on session_manager.
    
    These services are created per-session and stored in a way that avoids
    serialization issues.
    
    Returns:
        Dictionary of session-specific services
    """
    # Use a simple flag to track if we've initialized session services
    if 'session_services_initialized' not in st.session_state:
        from learning.progress_tracker import ProgressTracker
        from learning.flashcard_manager import FlashcardManager
        from learning.traceability_manager import TraceabilityManager
        from generators.learning_artifact_generator import LearningArtifactGenerator
        from analyzers.intent_driven_orchestrator import IntentDrivenOrchestrator
        
        services = get_backend_services()
        
        # Create session-specific instances
        progress_tracker = ProgressTracker(st.session_state.session_manager)
        flashcard_manager = FlashcardManager(st.session_state.session_manager)
        traceability_manager = TraceabilityManager(st.session_state.session_manager)
        
        learning_artifact_generator = LearningArtifactGenerator(
            flashcard_manager,
            services['quiz_engine'],
            services['orchestrator']
        )
        
        intent_driven_orchestrator = IntentDrivenOrchestrator(
            services['repository_manager'],
            services['intent_interpreter'],
            services['file_selector'],
            services['multi_file_analyzer'],
            learning_artifact_generator,
            traceability_manager,
            st.session_state.session_manager
        )
        
        # Store in a module-level cache keyed by session
        # This avoids storing in st.session_state
        session_id = id(st.session_state.session_manager)
        _session_services_cache[session_id] = {
            'progress_tracker': progress_tracker,
            'flashcard_manager': flashcard_manager,
            'traceability_manager': traceability_manager,
            'learning_artifact_generator': learning_artifact_generator,
            'intent_driven_orchestrator': intent_driven_orchestrator,
        }
        
        st.session_state.session_services_initialized = True
        st.session_state._session_id = session_id
    
    # Retrieve from cache
    session_id = st.session_state.get('_session_id')
    return _session_services_cache.get(session_id, {})


def main():
    """Initialize and run the Streamlit application."""
    setup_page_config()
    initialize_session_state()
    initialize_backend_services()
    
    # Import sidebar and route to selected page.
    from ui.sidebar import render_sidebar
    
    selected_page = render_sidebar()
    route_to_page(selected_page)


def setup_page_config():
    """Configure Streamlit page settings."""
    st.set_page_config(
        page_title="CodeGuru India - AI-Powered Code Learning",
        page_icon="🎓",
        layout="wide",
        initial_sidebar_state="expanded",
        menu_items={
            'Get Help': None,
            'Report a bug': None,
            'About': "CodeGuru India - Learn code faster with AI-powered explanations"
        }
    )
    
    # Load custom CSS
    from ui.design_system import load_design_system
    load_design_system()
    # Keep sidebar toggle clearly visible across custom themes.
    st.markdown(
        """
        <style>
        [data-testid="collapsedControl"] {
            display: flex !important;
            visibility: visible !important;
            opacity: 1 !important;
            z-index: 999999 !important;
            border-radius: 9px !important;
            border: 1px solid #b9cccd !important;
            background: rgba(255,255,255,0.95) !important;
            box-shadow: 0 4px 12px rgba(15, 37, 55, 0.12) !important;
        }
        [data-testid="collapsedControl"]:hover {
            border-color: #0f766e !important;
            background: #ffffff !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def initialize_session_state():
    """Initialize session state variables."""
    if "session_manager" not in st.session_state:
        st.session_state.session_manager = SessionManager()
    
    if "current_page" not in st.session_state:
        st.session_state.current_page = "Home"

    if "current_analysis_session_id" not in st.session_state:
        st.session_state.current_analysis_session_id = None


def initialize_backend_services():
    """Initialize AI and analysis services using cached resources."""
    if "backend_initialized" not in st.session_state:
        # Get cached backend services (this validates they can be created)
        services = get_backend_services()
        
        if 'error' in services:
            st.session_state.backend_initialized = False
            st.session_state.backend_error = services['error']
            return
        
        try:
            # Don't store any service objects in session_state
            # They will be accessed via get_backend_services() or get_service()
            # Only store simple flags and data
            st.session_state.memory_backend = services['memory_backend']
            st.session_state.backend_initialized = True
            
        except Exception as e:
            st.session_state.backend_initialized = False
            st.session_state.backend_error = str(e)


def route_to_page(page: str):
    """Route to the selected page component."""
    from ui.explanation_view import render_explanation_view
    from ui.learning_path import render_learning_path
    from ui.progress_dashboard import render_progress_dashboard
    
    if page == "Home":
        from ui.design_system import (
            info_box,
            render_feature_card,
            render_hero,
            render_soft_panel,
            render_stats,
            section_header,
            spacing,
        )

        render_hero(
            "CodeGuru India",
            "AI-powered code learning for real repositories. Understand complex codebases in your native language, ask by voice, and master through guided practice.",
            pills=[
                "Repository + Local File Analysis",
                "English • हिंदी • తెలుగు",
                "Voice to Code Chat",
                "Intent-driven Quizzes & Flashcards",
            ],
        )

        section_header(
            "What You Can Demo",
            "A minimal workflow designed for judges: upload -> explain -> ask -> practice -> track",
        )

        col1, col2, col3 = st.columns(3)
        with col1:
            render_feature_card(
                "Deep Code Understanding",
                "Analyze full repositories or single files and surface the architecture, key modules, and core behavior quickly.",
                chip="Analysis",
            )
            spacing("sm")
            render_feature_card(
                "Learning Materials That Teach",
                "Generate challenging flashcards and quizzes from actual conversation intent and repository evidence.",
                chip="Learning",
            )
        with col2:
            render_feature_card(
                "Codebase Chat That Stays Grounded",
                "Ask any technical question and get answers tied to retrieved snippets, not generic textbook guesses.",
                chip="Chat",
            )
            spacing("sm")
            render_feature_card(
                "Voice-Native Interaction",
                "Speak in your preferred language, translate into query input, and continue the same chat context smoothly.",
                chip="Voice",
            )
        with col3:
            render_feature_card(
                "Guided Paths + Progress",
                "Follow practical learning paths and track your coverage, confidence, and activity over time.",
                chip="Progress",
            )
            spacing("sm")
            render_feature_card(
                "Hackathon-Ready UX",
                "Clean, focused interface that highlights outcomes fast without clutter or demo-breaking complexity.",
                chip="Presentation",
            )

        spacing("lg")
        render_stats([
            ("10+", "Code Languages"),
            ("3", "UI Languages"),
            ("5+", "Learning Surfaces"),
            ("< 1 min", "First Insight Time"),
        ])

        spacing("md")
        if st.session_state.get("backend_initialized", False):
            info_box("AI services connected. Full Bedrock-powered experience is active.", "success")
        else:
            info_box("Running in fallback mode. Configure AWS credentials in `.env` for full AI behavior.", "warning")

        col_primary, col_secondary = st.columns([2, 1])
        with col_primary:
            if st.button("Start New Analysis", type="primary", use_container_width=True):
                st.session_state.current_page = "Upload Code"
                st.rerun()
        with col_secondary:
            if st.button("Open Codebase Chat", type="secondary", use_container_width=True):
                st.session_state.current_page = "Codebase Chat"
                st.rerun()

        render_soft_panel(
            "Judge Pitch Tip",
            "Demo one repository in Hindi/Telugu voice mode, ask architecture + feature questions, then show generated quiz and progress in one continuous flow.",
        )
    
    elif page == "Upload Code":
        # Use unified code analysis interface
        from ui.unified_code_analysis import render_unified_code_analysis
        
        # Get services from cache
        services = get_backend_services()
        session_services = get_session_specific_services()
        
        render_unified_code_analysis(
            session_services['intent_driven_orchestrator'],
            services['repository_manager'],
            services['intent_interpreter'],
            st.session_state.session_manager,
            services['code_analyzer'],
            session_services['flashcard_manager'],
        )
    
    elif page == "Codebase Chat":
        from ui.codebase_chat import render_codebase_chat
        
        # Get services from cache
        services = get_backend_services()
        
        render_codebase_chat(
            st.session_state.session_manager,
            services['semantic_search'],
            services['rag_explainer'],
            services['multi_intent_analyzer'],
            services.get("memory_store"),
        )
    
    elif page == "Learning Memory":
        from ui.learning_memory import render_learning_memory
        
        # Get services from cache
        services = get_backend_services()
        
        render_learning_memory(
            st.session_state.session_manager,
            services.get("memory_store"),
            services.get("chat_learning_generator"),
        )
    
    elif page == "Explanations":
        render_explanation_view()
    
    elif page == "Learning Paths":
        render_learning_path()
    
    elif page == "Progress":
        render_progress_dashboard()
    
    else:
        st.session_state.current_page = "Home"
        st.rerun()


if __name__ == "__main__":
    main()
