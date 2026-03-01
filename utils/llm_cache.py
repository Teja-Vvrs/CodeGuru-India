"""LLM response caching system for performance optimization."""
import hashlib
import json
import time
from typing import Any, Dict, Optional
from datetime import datetime, timedelta
import streamlit as st
import logging

logger = logging.getLogger(__name__)


class LLMCache:
    """
    Caching system for LLM responses to improve performance.
    
    Implements:
    - In-memory caching using Streamlit session state
    - Cache key generation based on prompt and parameters
    - TTL (Time To Live) for cache entries
    - Cache statistics tracking
    - Cache size management
    """
    
    def __init__(
        self,
        max_cache_size: int = 100,
        default_ttl_seconds: int = 3600  # 1 hour default
    ):
        """
        Initialize LLM cache.
        
        Args:
            max_cache_size: Maximum number of cached entries
            default_ttl_seconds: Default time-to-live for cache entries
        """
        self.max_cache_size = max_cache_size
        self.default_ttl_seconds = default_ttl_seconds
        self._ensure_cache_initialized()
    
    def _ensure_cache_initialized(self) -> None:
        """Ensure cache storage exists in session state."""
        if "llm_cache" not in st.session_state:
            st.session_state.llm_cache = {}
        
        if "llm_cache_stats" not in st.session_state:
            st.session_state.llm_cache_stats = {
                "hits": 0,
                "misses": 0,
                "evictions": 0,
                "total_requests": 0
            }
    
    def _generate_cache_key(
        self,
        prompt: str,
        parameters: Optional[Dict] = None
    ) -> str:
        """
        Generate unique cache key from prompt and parameters.
        
        Args:
            prompt: Input prompt
            parameters: Optional parameters (temperature, max_tokens, etc.)
            
        Returns:
            Cache key (SHA256 hash)
        """
        # Normalize parameters for consistent hashing
        params_str = ""
        if parameters:
            # Sort keys for consistent ordering
            sorted_params = sorted(parameters.items())
            params_str = json.dumps(sorted_params, sort_keys=True)
        
        # Combine prompt and parameters
        cache_input = f"{prompt}|{params_str}"
        
        # Generate hash
        return hashlib.sha256(cache_input.encode()).hexdigest()
    
    def get(
        self,
        prompt: str,
        parameters: Optional[Dict] = None
    ) -> Optional[Any]:
        """
        Retrieve cached response if available and not expired.
        
        Args:
            prompt: Input prompt
            parameters: Optional parameters
            
        Returns:
            Cached response or None if not found/expired
        """
        self._ensure_cache_initialized()
        
        cache_key = self._generate_cache_key(prompt, parameters)
        st.session_state.llm_cache_stats["total_requests"] += 1
        
        if cache_key not in st.session_state.llm_cache:
            st.session_state.llm_cache_stats["misses"] += 1
            logger.debug(f"Cache miss for key: {cache_key[:16]}...")
            return None
        
        entry = st.session_state.llm_cache[cache_key]
        
        # Check if entry has expired
        if self._is_expired(entry):
            logger.debug(f"Cache entry expired for key: {cache_key[:16]}...")
            del st.session_state.llm_cache[cache_key]
            st.session_state.llm_cache_stats["misses"] += 1
            return None
        
        # Cache hit
        st.session_state.llm_cache_stats["hits"] += 1
        entry["last_accessed"] = time.time()
        entry["access_count"] += 1
        
        logger.info(f"Cache hit for key: {cache_key[:16]}... (accessed {entry['access_count']} times)")
        return entry["response"]
    
    def set(
        self,
        prompt: str,
        response: Any,
        parameters: Optional[Dict] = None,
        ttl_seconds: Optional[int] = None
    ) -> None:
        """
        Store response in cache.
        
        Args:
            prompt: Input prompt
            response: LLM response to cache
            parameters: Optional parameters
            ttl_seconds: Time-to-live in seconds (uses default if not specified)
        """
        self._ensure_cache_initialized()
        
        cache_key = self._generate_cache_key(prompt, parameters)
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        
        # Check cache size and evict if necessary
        if len(st.session_state.llm_cache) >= self.max_cache_size:
            self._evict_oldest()
        
        # Store entry
        st.session_state.llm_cache[cache_key] = {
            "response": response,
            "created_at": time.time(),
            "last_accessed": time.time(),
            "expires_at": time.time() + ttl,
            "access_count": 0,
            "prompt_preview": prompt[:100],  # For debugging
            "parameters": parameters
        }
        
        logger.info(f"Cached response for key: {cache_key[:16]}... (TTL: {ttl}s)")
    
    def _is_expired(self, entry: Dict) -> bool:
        """Check if cache entry has expired."""
        return time.time() > entry["expires_at"]
    
    def _evict_oldest(self) -> None:
        """Evict least recently accessed entry."""
        if not st.session_state.llm_cache:
            return
        
        # Find entry with oldest last_accessed time
        oldest_key = min(
            st.session_state.llm_cache.keys(),
            key=lambda k: st.session_state.llm_cache[k]["last_accessed"]
        )
        
        logger.info(f"Evicting cache entry: {oldest_key[:16]}...")
        del st.session_state.llm_cache[oldest_key]
        st.session_state.llm_cache_stats["evictions"] += 1
    
    def clear(self) -> None:
        """Clear all cache entries."""
        self._ensure_cache_initialized()
        count = len(st.session_state.llm_cache)
        st.session_state.llm_cache = {}
        logger.info(f"Cleared {count} cache entries")
    
    def get_stats(self) -> Dict:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        self._ensure_cache_initialized()
        
        stats = st.session_state.llm_cache_stats.copy()
        stats["cache_size"] = len(st.session_state.llm_cache)
        stats["max_cache_size"] = self.max_cache_size
        
        # Calculate hit rate
        total = stats["total_requests"]
        if total > 0:
            stats["hit_rate"] = stats["hits"] / total
            stats["miss_rate"] = stats["misses"] / total
        else:
            stats["hit_rate"] = 0.0
            stats["miss_rate"] = 0.0
        
        return stats
    
    def get_cache_info(self) -> Dict:
        """
        Get detailed cache information.
        
        Returns:
            Dictionary with cache entries info
        """
        self._ensure_cache_initialized()
        
        entries = []
        for key, entry in st.session_state.llm_cache.items():
            entries.append({
                "key": key[:16] + "...",
                "prompt_preview": entry["prompt_preview"],
                "created_at": datetime.fromtimestamp(entry["created_at"]).isoformat(),
                "last_accessed": datetime.fromtimestamp(entry["last_accessed"]).isoformat(),
                "expires_at": datetime.fromtimestamp(entry["expires_at"]).isoformat(),
                "access_count": entry["access_count"],
                "is_expired": self._is_expired(entry)
            })
        
        return {
            "entries": entries,
            "total_entries": len(entries),
            "stats": self.get_stats()
        }
    
    def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate cache entries matching a pattern in prompt.
        
        Args:
            pattern: String pattern to match in prompt preview
            
        Returns:
            Number of entries invalidated
        """
        self._ensure_cache_initialized()
        
        keys_to_delete = [
            key for key, entry in st.session_state.llm_cache.items()
            if pattern.lower() in entry["prompt_preview"].lower()
        ]
        
        for key in keys_to_delete:
            del st.session_state.llm_cache[key]
        
        logger.info(f"Invalidated {len(keys_to_delete)} cache entries matching pattern: {pattern}")
        return len(keys_to_delete)


# Global cache instance
_global_cache = None


def get_cache() -> LLMCache:
    """Get global LLM cache instance."""
    global _global_cache
    if _global_cache is None:
        _global_cache = LLMCache()
    return _global_cache
