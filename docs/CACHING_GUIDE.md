# LLM Response Caching Guide

## Overview

CodeGuru India implements a comprehensive caching system to optimize performance and reduce LLM API costs. The caching system operates at multiple levels:

1. **LLM Response Cache**: Caches raw LLM responses based on prompts and parameters
2. **Code Analysis Cache**: Caches complete code analysis results
3. **Explanation Cache**: Caches generated code explanations

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     User Request                             │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              Code Analyzer / Explanation Engine              │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Check Analysis/Explanation Cache                     │  │
│  │  (Session State)                                      │  │
│  └──────────────────────────────────────────────────────┘  │
│                    │                    │                    │
│              Cache Hit            Cache Miss                 │
│                    │                    │                    │
│              Return Result              ▼                    │
│                                                               │
│                    ┌─────────────────────────────────────┐  │
│                    │  LangChain Orchestrator              │  │
│                    │                                       │  │
│                    │  ┌────────────────────────────────┐ │  │
│                    │  │  Check LLM Cache               │ │  │
│                    │  │  (Session State)               │ │  │
│                    │  └────────────────────────────────┘ │  │
│                    │         │              │             │  │
│                    │   Cache Hit      Cache Miss          │  │
│                    │         │              │             │  │
│                    │   Return Result        ▼             │  │
│                    │                                       │  │
│                    │         ┌──────────────────────────┐ │  │
│                    │         │  AWS Bedrock LLM         │ │  │
│                    │         └──────────────────────────┘ │  │
│                    └─────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Features

### 1. Automatic Caching

All LLM responses are automatically cached based on:
- Prompt content
- Model parameters (temperature, max_tokens, etc.)

```python
# Automatic caching in LangChainOrchestrator
response = orchestrator.generate_completion(
    prompt="Explain this code",
    temperature=0.7
)
# Second call with same parameters uses cache
response = orchestrator.generate_completion(
    prompt="Explain this code",
    temperature=0.7
)  # Returns cached response
```

### 2. Multi-Level Caching

#### Level 1: LLM Response Cache
- Caches raw LLM responses
- Key: SHA256 hash of (prompt + parameters)
- TTL: 1 hour (configurable)
- Max size: 100 entries (configurable)

#### Level 2: Code Analysis Cache
- Caches complete code analysis results
- Key: SHA256 hash of (code + filename)
- Stored in session state
- Max size: 50 entries

#### Level 3: Explanation Cache
- Caches generated explanations
- Key: SHA256 hash of (code + context + language + difficulty)
- Stored in session state
- Max size: 30 entries

### 3. Cache Eviction

When cache reaches maximum size:
- **LRU (Least Recently Used)** eviction policy
- Oldest accessed entries are removed first
- Eviction statistics are tracked

### 4. Cache Expiration

- Default TTL: 1 hour
- Configurable per cache entry
- Expired entries are automatically removed on access

### 5. Performance Monitoring

The system tracks:
- Cache hit rate
- Cache miss rate
- Response times (cached vs uncached)
- Number of evictions
- Cache size

## Usage

### Basic Usage

Caching is enabled by default and requires no code changes:

```python
# Code analysis with automatic caching
analyzer = CodeAnalyzer(orchestrator)
result = analyzer.analyze_file(code, "test.py")
# Subsequent calls with same code use cache
```

### Disabling Cache

To disable caching for specific use cases:

```python
orchestrator = LangChainOrchestrator(
    bedrock_client=bedrock_client,
    prompt_manager=prompt_manager,
    enable_cache=False  # Disable caching
)
```

### Manual Cache Management

```python
from utils.llm_cache import get_cache

cache = get_cache()

# Get cache statistics
stats = cache.get_stats()
print(f"Hit rate: {stats['hit_rate']:.2%}")

# Clear entire cache
cache.clear()

# Invalidate entries matching pattern
count = cache.invalidate_pattern("function")
print(f"Invalidated {count} entries")

# Get detailed cache information
info = cache.get_cache_info()
for entry in info['entries']:
    print(f"Key: {entry['key']}")
    print(f"Access count: {entry['access_count']}")
```

### Cache Dashboard

Access the cache dashboard in the UI:

```python
from ui.cache_dashboard import render_cache_dashboard

# In your Streamlit app
render_cache_dashboard()
```

The dashboard shows:
- Cache hit rate and statistics
- Response time comparisons
- Cache size and evictions
- Detailed cache entries
- Cache management controls

## Performance Benefits

### Typical Performance Improvements

| Operation | Uncached | Cached | Speedup |
|-----------|----------|--------|---------|
| LLM Completion | 2-5s | 0.01-0.05s | 50-200x |
| Code Analysis | 3-8s | 0.02-0.1s | 30-150x |
| Explanation | 4-10s | 0.02-0.1s | 40-200x |

### Cost Savings

- Reduces AWS Bedrock API calls by 30-70% (typical)
- Saves on token usage costs
- Improves user experience with faster responses

## Configuration

### Cache Size Limits

```python
# In utils/llm_cache.py
cache = LLMCache(
    max_cache_size=100,      # Maximum entries
    default_ttl_seconds=3600  # 1 hour TTL
)
```

### Cache TTL

```python
# Set custom TTL for specific entries
cache.set(
    prompt="test",
    response="result",
    ttl_seconds=7200  # 2 hours
)
```

## Best Practices

### 1. Cache Warming

For frequently used operations, warm the cache on startup:

```python
# Warm cache with common queries
common_queries = [
    "Explain list comprehension",
    "What is async/await",
    "Explain React hooks"
]

for query in common_queries:
    orchestrator.generate_completion(query)
```

### 2. Cache Invalidation

Invalidate cache when:
- User changes language preference
- Code is modified
- Model parameters change significantly

```python
# Invalidate specific patterns
cache.invalidate_pattern("react")

# Or clear entire cache
cache.clear()
```

### 3. Monitoring

Regularly monitor cache performance:

```python
stats = cache.get_stats()

# Alert if hit rate is too low
if stats['hit_rate'] < 0.2:
    logger.warning("Low cache hit rate: {:.2%}".format(stats['hit_rate']))

# Alert if cache is frequently full
if stats['evictions'] > 100:
    logger.warning("High eviction rate: {}".format(stats['evictions']))
```

### 4. Testing

Always test with cache disabled for accurate benchmarks:

```python
# Disable cache for testing
orchestrator = LangChainOrchestrator(
    bedrock_client=bedrock_client,
    prompt_manager=prompt_manager,
    enable_cache=False
)
```

## Troubleshooting

### Issue: Low Cache Hit Rate

**Symptoms**: Hit rate below 20%

**Causes**:
- Queries are too diverse
- Parameters vary too much
- Cache size too small

**Solutions**:
- Increase cache size
- Normalize query parameters
- Review query patterns

### Issue: Stale Responses

**Symptoms**: Cached responses are outdated

**Causes**:
- TTL too long
- Cache not invalidated after updates

**Solutions**:
- Reduce TTL
- Implement cache invalidation on updates
- Clear cache manually

### Issue: High Memory Usage

**Symptoms**: Session state growing too large

**Causes**:
- Cache size too large
- Large responses being cached

**Solutions**:
- Reduce max_cache_size
- Implement response size limits
- Clear cache more frequently

## API Reference

### LLMCache

```python
class LLMCache:
    def __init__(
        self,
        max_cache_size: int = 100,
        default_ttl_seconds: int = 3600
    )
    
    def get(
        self,
        prompt: str,
        parameters: Optional[Dict] = None
    ) -> Optional[Any]
    
    def set(
        self,
        prompt: str,
        response: Any,
        parameters: Optional[Dict] = None,
        ttl_seconds: Optional[int] = None
    ) -> None
    
    def clear(self) -> None
    
    def get_stats(self) -> Dict
    
    def get_cache_info(self) -> Dict
    
    def invalidate_pattern(self, pattern: str) -> int
```

### Performance Metrics

```python
from utils.performance_metrics import (
    record_metric,
    get_metrics,
    summarize_metric
)

# Record a metric
record_metric("operation_name", duration_seconds, context)

# Get all metrics
metrics = get_metrics("operation_name")

# Get summary statistics
summary = summarize_metric("operation_name")
# Returns: {count, min, max, avg, p95}
```

## Future Enhancements

Planned improvements:
- [ ] Persistent cache (Redis/DynamoDB)
- [ ] Distributed caching for multi-instance deployments
- [ ] Smart cache warming based on usage patterns
- [ ] Cache compression for large responses
- [ ] Cache analytics and recommendations
- [ ] A/B testing framework for cache strategies

## Related Documentation

- [Performance Optimization Guide](PERFORMANCE_GUIDE.md)
- [AWS Bedrock Integration](AWS_BEDROCK_GUIDE.md)
- [Testing Guide](../tests/README.md)
