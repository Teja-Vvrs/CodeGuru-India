# Error Handling Guide

## Overview

CodeGuru India implements comprehensive error handling across all components to ensure a robust and user-friendly experience. This guide explains the error handling system and how to use it effectively.

## Error Handling Architecture

### Error Categories

1. **Input Validation Errors**
   - File upload validation (size, format, content)
   - Repository URL validation
   - Code content validation

2. **External Service Errors**
   - AWS Bedrock API failures
   - GitHub API errors
   - Network timeouts

3. **Processing Errors**
   - Code parsing failures
   - Analysis errors
   - Diagram generation failures

4. **Session Management Errors**
   - Session corruption
   - Data persistence failures

## Custom Error Classes

### Base Error Class

```python
class CodeGuruError(Exception):
    """Base exception for CodeGuru India."""
    def __init__(self, message: str, user_message: Optional[str] = None, details: Optional[Dict] = None):
        self.message = message
        self.user_message = user_message or message
        self.details = details or {}
```

### Specialized Error Classes

- `FileValidationError`: File upload and validation failures
- `AnalysisError`: Code analysis failures
- `AIServiceError`: AWS Bedrock/LLM failures
- `RepositoryError`: Repository operations failures
- `SessionError`: Session management failures

## Error Handling Utilities

### File Validation

```python
from utils.error_handler import validate_file_upload

# Validate uploaded file
is_valid, error_msg = validate_file_upload(
    uploaded_file,
    max_size_mb=10,
    allowed_extensions=['.py', '.js', '.ts']
)

if not is_valid:
    st.error(error_msg)
```

### Code Content Validation

```python
from utils.error_handler import validate_code_content

# Validate code for suspicious patterns
is_valid, warning_msg = validate_code_content(code)

if not is_valid:
    st.error(warning_msg)
elif warning_msg:
    st.warning(warning_msg)
```

### GitHub URL Validation

```python
from utils.error_handler import validate_github_url

# Validate GitHub repository URL
is_valid, error_msg = validate_github_url(repo_url)

if not is_valid:
    st.error(error_msg)
```

## Error Handling Decorators

### Safe File Analysis

```python
from utils.error_integration import safe_file_analysis

@safe_file_analysis
def analyze_code_file(code, filename):
    # Analysis logic
    return analysis_result
```

### Safe Repository Operations

```python
from utils.error_integration import safe_repository_operation

@safe_repository_operation
def clone_repository(repo_url):
    # Clone logic
    return repo_path
```

### Safe AI Operations

```python
from utils.error_integration import safe_ai_operation

@safe_ai_operation(fallback_message="AI temporarily unavailable")
def generate_explanation(code):
    # AI call logic
    return explanation
```

### Safe Diagram Generation

```python
from utils.error_integration import safe_diagram_generation

@safe_diagram_generation
def create_flowchart(code):
    # Diagram generation logic
    return mermaid_diagram
```

## Retry Logic

### Exponential Backoff

```python
from utils.error_handler import ErrorRecovery

# Retry with exponential backoff
result = ErrorRecovery.retry_with_backoff(
    func=lambda: bedrock_client.invoke_model(prompt),
    max_attempts=3,
    initial_delay=1.0,
    backoff_factor=2.0
)
```

### Safe AI Call

```python
from utils.error_handler import safe_ai_call

# Safe AI call with retries
result = safe_ai_call(
    func=lambda: bedrock_client.invoke_model(prompt),
    fallback_response="AI service unavailable",
    max_retries=2
)
```

## Graceful Degradation

### Fallback Mechanisms

```python
from utils.error_handler import graceful_degradation

# Try primary function, fall back to simpler version
result = graceful_degradation(
    primary_func=lambda: generate_complex_diagram(code),
    fallback_func=lambda: generate_simple_text_representation(code),
    error_message="Using simplified diagram"
)
```

## User-Friendly Error Messages

### Multi-Language Support

```python
from utils.error_handler import get_user_friendly_message

# Get localized error message
language = st.session_state.get('selected_language', 'english')
error = FileValidationError("File too large")
message = get_user_friendly_message(error, language)
st.error(message)
```

### Display Error with Suggestions

```python
from utils.error_handler import display_error

display_error(
    error_type="File Upload Error",
    message="File size exceeds 10MB limit",
    suggestions=[
        "Compress the file before uploading",
        "Split large files into smaller chunks",
        "Try a different file"
    ],
    show_support=True
)
```

## Error Logging

### Log Error with Context

```python
from utils.error_handler import log_error_context

try:
    # Some operation
    pass
except Exception as e:
    log_error_context(
        error=e,
        context={
            'function': 'analyze_code',
            'filename': filename,
            'user_id': user_id
        },
        user_id=user_id
    )
```

## Session Recovery

### Recover Corrupted Session

```python
from utils.error_handler import ErrorRecovery

# Attempt to recover session
if ErrorRecovery.recover_session(session_manager):
    st.success("Session recovered successfully")
else:
    st.error("Please refresh the page")
```

## Integration Examples

### Complete File Upload Flow

```python
from utils.error_integration import validate_and_process_file

# Validate and process uploaded file
success, content, error = validate_and_process_file(
    uploaded_file,
    max_size_mb=10,
    allowed_extensions=['.py', '.js', '.ts']
)

if success:
    if error:  # Warning message
        st.warning(error)
    # Process file content
    analyze_code(content)
else:
    st.error(error)
```

### Complete Repository Analysis Flow

```python
from utils.error_integration import (
    validate_and_process_github_url,
    safe_repository_operation
)

# Validate URL
is_valid, error = validate_and_process_github_url(repo_url)

if not is_valid:
    st.error(error)
else:
    # Clone and analyze
    @safe_repository_operation
    def process_repo():
        repo_path = clone_repository(repo_url)
        return analyze_repository(repo_path)
    
    result = process_repo()
```

### Complete AI Analysis Flow

```python
from utils.error_integration import safe_bedrock_call

# Safe Bedrock call with fallback
response = safe_bedrock_call(
    bedrock_client=bedrock_client,
    prompt=analysis_prompt,
    fallback_response="Analysis temporarily unavailable. Please try again.",
    max_retries=2
)

st.write(response)
```

## Best Practices

### 1. Always Validate Input

```python
# ✅ Good
is_valid, error = validate_file_upload(file)
if not is_valid:
    st.error(error)
    return

# ❌ Bad
# Directly processing without validation
```

### 2. Use Appropriate Error Classes

```python
# ✅ Good
if file_size > max_size:
    raise FileValidationError(
        f"File too large: {file_size}MB",
        user_message="Please upload a smaller file"
    )

# ❌ Bad
if file_size > max_size:
    raise Exception("File too large")
```

### 3. Provide Actionable Error Messages

```python
# ✅ Good
display_error(
    "File Upload Error",
    "File exceeds 10MB limit",
    suggestions=[
        "Compress the file",
        "Split into smaller files",
        "Try a different file"
    ]
)

# ❌ Bad
st.error("Error occurred")
```

### 4. Log Errors with Context

```python
# ✅ Good
try:
    analyze_code(code)
except Exception as e:
    log_error_context(e, {
        'function': 'analyze_code',
        'filename': filename,
        'code_length': len(code)
    })

# ❌ Bad
try:
    analyze_code(code)
except Exception as e:
    pass  # Silent failure
```

### 5. Implement Graceful Degradation

```python
# ✅ Good
result = graceful_degradation(
    primary_func=generate_ai_explanation,
    fallback_func=generate_basic_explanation,
    error_message="Using simplified explanation"
)

# ❌ Bad
try:
    result = generate_ai_explanation()
except:
    result = None  # No fallback
```

## Testing Error Handling

### Unit Tests

```python
def test_file_validation_error():
    """Test file validation with invalid file."""
    mock_file = Mock()
    mock_file.getvalue.return_value = b"x" * (11 * 1024 * 1024)
    
    is_valid, error = validate_file_upload(mock_file, max_size_mb=10)
    
    assert not is_valid
    assert "too large" in error.lower()
```

### Integration Tests

```python
def test_complete_upload_flow():
    """Test complete file upload and analysis flow."""
    # Upload file
    success, content, error = validate_and_process_file(test_file)
    assert success
    
    # Analyze code
    result = analyze_code(content)
    assert result is not None
```

## Monitoring and Debugging

### Error Metrics

Track error rates and types:
- File validation failures
- AI service failures
- Repository access failures
- Session recovery attempts

### Error Logs

All errors are logged with:
- Timestamp
- Error type
- Context information
- Stack trace (in development)
- User ID (if available)

### Debug Mode

Enable detailed error information in development:

```python
import logging

# Set log level to DEBUG
logging.basicConfig(level=logging.DEBUG)
```

## Troubleshooting

### Common Issues

1. **File Upload Fails**
   - Check file size (max 10MB)
   - Verify file extension is supported
   - Ensure file is not corrupted

2. **AI Service Unavailable**
   - Verify AWS credentials in .env
   - Check internet connection
   - Wait and retry (automatic retry implemented)

3. **Repository Clone Fails**
   - Verify GitHub URL format
   - Check if repository is public
   - Ensure repository size is under 100MB

4. **Session Errors**
   - Clear browser cache
   - Refresh the page
   - Check browser console for errors

## Support

For persistent errors:
1. Check the error logs
2. Verify configuration in .env file
3. Ensure all dependencies are installed
4. Check AWS Bedrock service status
5. Review the documentation

## Related Documentation

- [API Reference](API_REFERENCE.md)
- [User Guide](USER_GUIDE.md)
- [Testing Guide](../tests/README.md)
