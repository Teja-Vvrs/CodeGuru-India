"""Integration tests for caching in LangChain orchestrator and analyzers."""
import pytest
import time
from unittest.mock import Mock, patch
from ai.langchain_orchestrator import LangChainOrchestrator
from ai.bedrock_client import BedrockClient
from ai.prompt_templates import PromptManager
from analyzers.code_analyzer import CodeAnalyzer
from engines.explanation_engine import ExplanationEngine
from utils.llm_cache import get_cache
import streamlit as st


@pytest.fixture
def mock_bedrock_client():
    """Create mock Bedrock client."""
    client = Mock(spec=BedrockClient)
    client.invoke_model.return_value = "Mocked LLM response"
    return client


@pytest.fixture
def prompt_manager():
    """Create prompt manager."""
    return PromptManager()


@pytest.fixture
def orchestrator(mock_bedrock_client, prompt_manager):
    """Create orchestrator with caching enabled."""
    # Clear cache before each test
    cache = get_cache()
    cache.clear()
    
    return LangChainOrchestrator(
        bedrock_client=mock_bedrock_client,
        prompt_manager=prompt_manager,
        enable_cache=True
    )


def test_orchestrator_caching_enabled(orchestrator, mock_bedrock_client):
    """Test that orchestrator uses cache when enabled."""
    prompt = "test prompt"
    
    # First call - should hit LLM
    response1 = orchestrator.generate_completion(prompt)
    assert mock_bedrock_client.invoke_model.call_count == 1
    
    # Second call with same prompt - should use cache
    response2 = orchestrator.generate_completion(prompt)
    assert mock_bedrock_client.invoke_model.call_count == 1  # No additional call
    
    # Responses should be identical
    assert response1 == response2


def test_orchestrator_cache_with_different_parameters(orchestrator, mock_bedrock_client):
    """Test cache distinguishes between different parameters."""
    prompt = "test prompt"
    
    # Call with different temperatures
    orchestrator.generate_completion(prompt, temperature=0.5)
    orchestrator.generate_completion(prompt, temperature=0.9)
    
    # Should make two LLM calls (different cache keys)
    assert mock_bedrock_client.invoke_model.call_count == 2


def test_orchestrator_cache_disabled(mock_bedrock_client, prompt_manager):
    """Test that caching can be disabled."""
    orchestrator = LangChainOrchestrator(
        bedrock_client=mock_bedrock_client,
        prompt_manager=prompt_manager,
        enable_cache=False
    )
    
    prompt = "test prompt"
    
    # Make two identical calls
    orchestrator.generate_completion(prompt)
    orchestrator.generate_completion(prompt)
    
    # Should make two LLM calls (no caching)
    assert mock_bedrock_client.invoke_model.call_count == 2


def test_code_analyzer_caching(orchestrator):
    """Test code analyzer caches analysis results."""
    analyzer = CodeAnalyzer(orchestrator)
    
    code = "def hello(): return 'world'"
    filename = "test.py"
    
    # Clear any existing cache
    if "code_analysis_cache" in st.session_state:
        st.session_state.code_analysis_cache = {}
    
    # First analysis
    start1 = time.time()
    result1 = analyzer.analyze_file(code, filename)
    duration1 = time.time() - start1
    
    # Second analysis of same code
    start2 = time.time()
    result2 = analyzer.analyze_file(code, filename)
    duration2 = time.time() - start2
    
    # Results should be identical
    assert result1.summary == result2.summary
    assert result1.complexity_score == result2.complexity_score
    
    # Second call should be faster (cached)
    assert duration2 < duration1


def test_code_analyzer_cache_invalidation(orchestrator):
    """Test code analyzer cache is invalidated for different code."""
    analyzer = CodeAnalyzer(orchestrator)
    
    # Clear cache
    if "code_analysis_cache" in st.session_state:
        st.session_state.code_analysis_cache = {}
    
    code1 = "def foo(): pass"
    code2 = "def bar(): pass"
    filename = "test.py"
    
    # Analyze different code
    result1 = analyzer.analyze_file(code1, filename)
    result2 = analyzer.analyze_file(code2, filename)
    
    # Should have different results
    assert result1.summary != result2.summary or result1.structure != result2.structure


def test_explanation_engine_caching(orchestrator):
    """Test explanation engine caches explanations."""
    engine = ExplanationEngine(orchestrator)
    
    code = "x = [i**2 for i in range(10)]"
    
    # Clear cache
    if "explanation_cache" in st.session_state:
        st.session_state.explanation_cache = {}
    
    # First explanation
    start1 = time.time()
    result1 = engine.explain_code(code)
    duration1 = time.time() - start1
    
    # Second explanation of same code
    start2 = time.time()
    result2 = engine.explain_code(code)
    duration2 = time.time() - start2
    
    # Results should be identical
    assert result1.summary == result2.summary
    assert result1.detailed_explanation == result2.detailed_explanation
    
    # Second call should be faster (cached)
    assert duration2 < duration1


def test_explanation_engine_different_difficulty(orchestrator):
    """Test explanation engine caches separately for different difficulty levels."""
    engine = ExplanationEngine(orchestrator)
    
    # Clear cache
    if "explanation_cache" in st.session_state:
        st.session_state.explanation_cache = {}
    
    code = "def factorial(n): return 1 if n <= 1 else n * factorial(n-1)"
    
    # Get explanations at different difficulty levels
    result1 = engine.explain_code(code, difficulty="beginner")
    result2 = engine.explain_code(code, difficulty="advanced")
    
    # Should generate different explanations
    # (In practice, with mocked LLM they'll be the same, but cache keys are different)
    cache_info = st.session_state.get("explanation_cache", {})
    assert len(cache_info) == 2  # Two separate cache entries


def test_cache_performance_metrics(orchestrator, mock_bedrock_client):
    """Test that performance metrics are recorded."""
    # Clear metrics
    if "performance_metrics" in st.session_state:
        st.session_state.performance_metrics = []
    
    prompt = "test prompt"
    
    # Make cached and uncached calls
    orchestrator.generate_completion(prompt)  # Uncached
    orchestrator.generate_completion(prompt)  # Cached
    
    # Check metrics were recorded
    metrics = st.session_state.get("performance_metrics", [])
    assert len(metrics) >= 2
    
    # Find cached and uncached metrics
    cached_metrics = [m for m in metrics if m.get("context", {}).get("cache_hit") is True]
    uncached_metrics = [m for m in metrics if m.get("context", {}).get("cache_hit") is False]
    
    assert len(cached_metrics) >= 1
    assert len(uncached_metrics) >= 1


def test_cache_stats_tracking(orchestrator):
    """Test cache statistics are tracked correctly."""
    cache = get_cache()
    
    # Clear cache and reset stats
    cache.clear()
    if "llm_cache_stats" in st.session_state:
        st.session_state.llm_cache_stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "total_requests": 0
        }
    
    prompt1 = "prompt 1"
    prompt2 = "prompt 2"
    
    # Generate cache activity
    orchestrator.generate_completion(prompt1)  # Miss
    orchestrator.generate_completion(prompt1)  # Hit
    orchestrator.generate_completion(prompt2)  # Miss
    orchestrator.generate_completion(prompt1)  # Hit
    
    stats = cache.get_stats()
    
    assert stats["hits"] == 2
    assert stats["misses"] == 2
    assert stats["total_requests"] == 4
    assert stats["hit_rate"] == 0.5


def test_multi_layer_caching(orchestrator):
    """Test that both LLM cache and analyzer cache work together."""
    analyzer = CodeAnalyzer(orchestrator)
    
    # Clear all caches
    cache = get_cache()
    cache.clear()
    if "code_analysis_cache" in st.session_state:
        st.session_state.code_analysis_cache = {}
    
    code = "def test(): return 42"
    filename = "test.py"
    
    # First analysis - both caches miss
    analyzer.analyze_file(code, filename)
    
    # Second analysis - analyzer cache hits (doesn't call LLM)
    analyzer.analyze_file(code, filename)
    
    # Check analyzer cache
    assert len(st.session_state.get("code_analysis_cache", {})) == 1
    
    # LLM cache should also have entries
    llm_stats = cache.get_stats()
    assert llm_stats["cache_size"] > 0


def test_cache_with_framework_detection(orchestrator):
    """Test caching works with framework-specific explanations."""
    engine = ExplanationEngine(orchestrator)
    
    # Clear cache
    if "explanation_cache" in st.session_state:
        st.session_state.explanation_cache = {}
    
    react_code = "const [state, setState] = useState(0)"
    
    # First explanation
    result1 = engine.explain_code(react_code)
    
    # Second explanation (should be cached)
    result2 = engine.explain_code(react_code)
    
    # Should detect React framework
    assert any("react" in concept.lower() for concept in result1.key_concepts)
    
    # Results should be identical
    assert result1.summary == result2.summary
