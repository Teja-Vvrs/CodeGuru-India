"""Unit tests for LLM caching system."""
import pytest
import time
from utils.llm_cache import LLMCache
import streamlit as st


@pytest.fixture
def cache():
    """Create a fresh cache instance for each test."""
    # Clear session state
    if "llm_cache" in st.session_state:
        del st.session_state.llm_cache
    if "llm_cache_stats" in st.session_state:
        del st.session_state.llm_cache_stats
    
    return LLMCache(max_cache_size=5, default_ttl_seconds=10)


def test_cache_initialization(cache):
    """Test cache initializes correctly."""
    assert cache.max_cache_size == 5
    assert cache.default_ttl_seconds == 10
    assert "llm_cache" in st.session_state
    assert "llm_cache_stats" in st.session_state


def test_cache_miss(cache):
    """Test cache miss returns None."""
    result = cache.get("test prompt", {"temperature": 0.7})
    assert result is None
    
    stats = cache.get_stats()
    assert stats["misses"] == 1
    assert stats["hits"] == 0


def test_cache_hit(cache):
    """Test cache hit returns stored value."""
    prompt = "test prompt"
    params = {"temperature": 0.7}
    response = "test response"
    
    # Store in cache
    cache.set(prompt, response, params)
    
    # Retrieve from cache
    result = cache.get(prompt, params)
    assert result == response
    
    stats = cache.get_stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 0


def test_cache_key_generation(cache):
    """Test cache keys are unique for different inputs."""
    # Same prompt, different params
    cache.set("prompt", "response1", {"temp": 0.5})
    cache.set("prompt", "response2", {"temp": 0.9})
    
    result1 = cache.get("prompt", {"temp": 0.5})
    result2 = cache.get("prompt", {"temp": 0.9})
    
    assert result1 == "response1"
    assert result2 == "response2"


def test_cache_expiration(cache):
    """Test cache entries expire after TTL."""
    prompt = "test prompt"
    response = "test response"
    
    # Store with 1 second TTL
    cache.set(prompt, response, ttl_seconds=1)
    
    # Should be available immediately
    result = cache.get(prompt)
    assert result == response
    
    # Wait for expiration
    time.sleep(1.1)
    
    # Should be expired
    result = cache.get(prompt)
    assert result is None


def test_cache_eviction(cache):
    """Test cache evicts oldest entry when full."""
    # Fill cache to max size
    for i in range(5):
        cache.set(f"prompt{i}", f"response{i}")
    
    # Access first entry to make it recently used
    cache.get("prompt0")
    
    # Add one more entry (should evict least recently used)
    cache.set("prompt5", "response5")
    
    # Check that oldest unaccessed entry was evicted
    stats = cache.get_stats()
    assert stats["evictions"] == 1
    assert stats["cache_size"] == 5


def test_cache_clear(cache):
    """Test cache clear removes all entries."""
    # Add some entries
    for i in range(3):
        cache.set(f"prompt{i}", f"response{i}")
    
    assert cache.get_stats()["cache_size"] == 3
    
    # Clear cache
    cache.clear()
    
    assert cache.get_stats()["cache_size"] == 0


def test_cache_stats(cache):
    """Test cache statistics are tracked correctly."""
    # Generate some cache activity
    cache.set("prompt1", "response1")
    cache.get("prompt1")  # hit
    cache.get("prompt2")  # miss
    cache.get("prompt1")  # hit
    
    stats = cache.get_stats()
    assert stats["hits"] == 2
    assert stats["misses"] == 1
    assert stats["total_requests"] == 3
    assert stats["hit_rate"] == 2/3
    assert stats["miss_rate"] == 1/3


def test_cache_invalidate_pattern(cache):
    """Test pattern-based cache invalidation."""
    # Add entries with different patterns
    cache.set("explain function foo", "explanation1")
    cache.set("explain class Bar", "explanation2")
    cache.set("debug function baz", "explanation3")
    
    # Invalidate entries containing "function"
    count = cache.invalidate_pattern("function")
    
    assert count == 2
    assert cache.get_stats()["cache_size"] == 1


def test_cache_access_count(cache):
    """Test access count is tracked."""
    prompt = "test prompt"
    cache.set(prompt, "response")
    
    # Access multiple times
    for _ in range(3):
        cache.get(prompt)
    
    # Check cache info
    info = cache.get_cache_info()
    entry = info["entries"][0]
    assert entry["access_count"] == 3


def test_cache_with_no_parameters(cache):
    """Test caching works without parameters."""
    prompt = "simple prompt"
    response = "simple response"
    
    cache.set(prompt, response)
    result = cache.get(prompt)
    
    assert result == response


def test_cache_different_response_types(cache):
    """Test caching different response types."""
    # String response
    cache.set("prompt1", "string response")
    assert cache.get("prompt1") == "string response"
    
    # Dict response
    cache.set("prompt2", {"key": "value"})
    assert cache.get("prompt2") == {"key": "value"}
    
    # List response
    cache.set("prompt3", [1, 2, 3])
    assert cache.get("prompt3") == [1, 2, 3]


def test_cache_hit_rate_calculation(cache):
    """Test hit rate calculation with edge cases."""
    # No requests yet
    stats = cache.get_stats()
    assert stats["hit_rate"] == 0.0
    assert stats["miss_rate"] == 0.0
    
    # Add some activity
    cache.set("prompt", "response")
    cache.get("prompt")  # hit
    cache.get("other")   # miss
    
    stats = cache.get_stats()
    assert stats["hit_rate"] == 0.5
    assert stats["miss_rate"] == 0.5


def test_cache_info_structure(cache):
    """Test cache info returns correct structure."""
    cache.set("test prompt", "test response")
    
    info = cache.get_cache_info()
    
    assert "entries" in info
    assert "total_entries" in info
    assert "stats" in info
    assert len(info["entries"]) == 1
    
    entry = info["entries"][0]
    assert "key" in entry
    assert "prompt_preview" in entry
    assert "created_at" in entry
    assert "last_accessed" in entry
    assert "expires_at" in entry
    assert "access_count" in entry
    assert "is_expired" in entry
