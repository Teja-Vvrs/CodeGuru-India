"""Cache dashboard for monitoring and managing LLM cache."""
import streamlit as st
from utils.llm_cache import get_cache
from utils.performance_metrics import get_metrics, summarize_metric


def render_cache_dashboard():
    """Render cache statistics and management dashboard."""
    st.subheader("🚀 Performance & Cache Dashboard")
    
    cache = get_cache()
    stats = cache.get_stats()
    
    # Cache Statistics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Cache Hit Rate",
            f"{stats['hit_rate']:.1%}",
            help="Percentage of requests served from cache"
        )
    
    with col2:
        st.metric(
            "Total Requests",
            stats['total_requests'],
            help="Total number of LLM requests"
        )
    
    with col3:
        st.metric(
            "Cache Size",
            f"{stats['cache_size']}/{stats['max_cache_size']}",
            help="Current cache entries / Maximum capacity"
        )
    
    with col4:
        st.metric(
            "Evictions",
            stats['evictions'],
            help="Number of cache entries evicted"
        )
    
    # Detailed Statistics
    st.markdown("---")
    st.markdown("### 📊 Detailed Statistics")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Cache Performance**")
        st.write(f"- Cache Hits: {stats['hits']}")
        st.write(f"- Cache Misses: {stats['misses']}")
        st.write(f"- Hit Rate: {stats['hit_rate']:.2%}")
        st.write(f"- Miss Rate: {stats['miss_rate']:.2%}")
    
    with col2:
        st.markdown("**Cache Status**")
        st.write(f"- Current Size: {stats['cache_size']} entries")
        st.write(f"- Max Size: {stats['max_cache_size']} entries")
        st.write(f"- Evictions: {stats['evictions']}")
        fill_rate = stats['cache_size'] / stats['max_cache_size'] if stats['max_cache_size'] > 0 else 0
        st.write(f"- Fill Rate: {fill_rate:.1%}")
    
    # Performance Metrics
    st.markdown("---")
    st.markdown("### ⚡ Response Time Metrics")
    
    # LLM Completion Metrics
    llm_metrics = summarize_metric("llm_completion")
    llm_cached_metrics = summarize_metric("llm_completion_cached")
    
    if llm_metrics['count'] > 0 or llm_cached_metrics['count'] > 0:
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Uncached LLM Calls**")
            if llm_metrics['count'] > 0:
                st.write(f"- Count: {llm_metrics['count']}")
                st.write(f"- Average: {llm_metrics['avg']:.3f}s")
                st.write(f"- Min: {llm_metrics['min']:.3f}s")
                st.write(f"- Max: {llm_metrics['max']:.3f}s")
                st.write(f"- P95: {llm_metrics['p95']:.3f}s")
            else:
                st.info("No uncached calls yet")
        
        with col2:
            st.markdown("**Cached LLM Calls**")
            if llm_cached_metrics['count'] > 0:
                st.write(f"- Count: {llm_cached_metrics['count']}")
                st.write(f"- Average: {llm_cached_metrics['avg']:.3f}s")
                st.write(f"- Min: {llm_cached_metrics['min']:.3f}s")
                st.write(f"- Max: {llm_cached_metrics['max']:.3f}s")
                st.write(f"- P95: {llm_cached_metrics['p95']:.3f}s")
                
                # Calculate speedup
                if llm_metrics['avg'] > 0:
                    speedup = llm_metrics['avg'] / llm_cached_metrics['avg']
                    st.success(f"🚀 **{speedup:.1f}x faster** with cache!")
            else:
                st.info("No cached calls yet")
    
    # Code Analysis Metrics
    st.markdown("---")
    st.markdown("### 🔍 Code Analysis Metrics")
    
    analysis_metrics = summarize_metric("code_analysis")
    analysis_cached_metrics = summarize_metric("code_analysis_cached")
    
    if analysis_metrics['count'] > 0 or analysis_cached_metrics['count'] > 0:
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Uncached Analysis**")
            if analysis_metrics['count'] > 0:
                st.write(f"- Count: {analysis_metrics['count']}")
                st.write(f"- Average: {analysis_metrics['avg']:.3f}s")
                st.write(f"- P95: {analysis_metrics['p95']:.3f}s")
            else:
                st.info("No uncached analysis yet")
        
        with col2:
            st.markdown("**Cached Analysis**")
            if analysis_cached_metrics['count'] > 0:
                st.write(f"- Count: {analysis_cached_metrics['count']}")
                st.write(f"- Average: {analysis_cached_metrics['avg']:.3f}s")
                st.write(f"- P95: {analysis_cached_metrics['p95']:.3f}s")
                
                # Calculate speedup
                if analysis_metrics['avg'] > 0:
                    speedup = analysis_metrics['avg'] / analysis_cached_metrics['avg']
                    st.success(f"🚀 **{speedup:.1f}x faster** with cache!")
            else:
                st.info("No cached analysis yet")
    
    # Explanation Metrics
    explanation_metrics = summarize_metric("explanation_generated")
    explanation_cached_metrics = summarize_metric("explanation_cached")
    
    if explanation_metrics['count'] > 0 or explanation_cached_metrics['count'] > 0:
        st.markdown("---")
        st.markdown("### 💡 Explanation Metrics")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Generated Explanations**")
            if explanation_metrics['count'] > 0:
                st.write(f"- Count: {explanation_metrics['count']}")
                st.write(f"- Average: {explanation_metrics['avg']:.3f}s")
                st.write(f"- P95: {explanation_metrics['p95']:.3f}s")
            else:
                st.info("No generated explanations yet")
        
        with col2:
            st.markdown("**Cached Explanations**")
            if explanation_cached_metrics['count'] > 0:
                st.write(f"- Count: {explanation_cached_metrics['count']}")
                st.write(f"- Average: {explanation_cached_metrics['avg']:.3f}s")
                st.write(f"- P95: {explanation_cached_metrics['p95']:.3f}s")
                
                # Calculate speedup
                if explanation_metrics['avg'] > 0:
                    speedup = explanation_metrics['avg'] / explanation_cached_metrics['avg']
                    st.success(f"🚀 **{speedup:.1f}x faster** with cache!")
            else:
                st.info("No cached explanations yet")
    
    # Cache Management
    st.markdown("---")
    st.markdown("### 🛠️ Cache Management")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🗑️ Clear Cache", help="Clear all cached entries"):
            cache.clear()
            st.success("Cache cleared successfully!")
            st.rerun()
    
    with col2:
        pattern = st.text_input("Pattern to invalidate", placeholder="e.g., 'function'")
        if st.button("🔍 Invalidate Pattern", disabled=not pattern):
            count = cache.invalidate_pattern(pattern)
            st.success(f"Invalidated {count} entries matching '{pattern}'")
            st.rerun()
    
    with col3:
        if st.button("📋 View Cache Details", help="Show detailed cache information"):
            st.session_state.show_cache_details = not st.session_state.get('show_cache_details', False)
    
    # Show detailed cache info if requested
    if st.session_state.get('show_cache_details', False):
        st.markdown("---")
        st.markdown("### 📋 Cache Entries")
        
        cache_info = cache.get_cache_info()
        
        if cache_info['entries']:
            for i, entry in enumerate(cache_info['entries'], 1):
                with st.expander(f"Entry {i}: {entry['key']}"):
                    st.write(f"**Prompt Preview:** {entry['prompt_preview']}")
                    st.write(f"**Created:** {entry['created_at']}")
                    st.write(f"**Last Accessed:** {entry['last_accessed']}")
                    st.write(f"**Expires:** {entry['expires_at']}")
                    st.write(f"**Access Count:** {entry['access_count']}")
                    st.write(f"**Expired:** {'Yes' if entry['is_expired'] else 'No'}")
        else:
            st.info("No cache entries yet")
    
    # Performance Tips
    st.markdown("---")
    st.markdown("### 💡 Performance Tips")
    
    tips = [
        "✅ Cache hit rate above 30% indicates good cache utilization",
        "✅ Cached responses are typically 10-100x faster than LLM calls",
        "✅ Cache automatically evicts old entries when full",
        "✅ Identical queries with same parameters are cached",
        "⚠️ Clear cache if you notice stale responses"
    ]
    
    for tip in tips:
        st.markdown(tip)
