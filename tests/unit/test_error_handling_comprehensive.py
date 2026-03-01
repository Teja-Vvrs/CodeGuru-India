"""
Comprehensive unit tests for error handling system.

Tests all error handling utilities, decorators, and integration functions.
"""

import pytest
import logging
from unittest.mock import Mock, patch, MagicMock
from utils.error_handler import (
    CodeGuruError,
    FileValidationError,
    AnalysisError,
    AIServiceError,
    RepositoryError,
    SessionError,
    handle_errors,
    validate_file_upload,
    validate_code_content,
    validate_github_url,
    safe_ai_call,
    ErrorRecovery,
    get_user_friendly_message
)
from utils.error_integration import (
    safe_file_analysis,
    safe_repository_operation,
    safe_ai_operation,
    safe_diagram_generation,
    safe_session_operation,
    validate_and_process_file,
    validate_and_process_github_url,
    safe_bedrock_call,
    get_localized_error_message
)


class TestErrorClasses:
    """Test custom error classes."""
    
    def test_codeguru_error_basic(self):
        """Test basic CodeGuruError creation."""
        error = CodeGuruError("Test error")
        assert str(error) == "Test error"
        assert error.user_message == "Test error"
        assert error.details == {}
    
    def test_codeguru_error_with_user_message(self):
        """Test CodeGuruError with custom user message."""
        error = CodeGuruError(
            "Technical error",
            user_message="User-friendly message",
            details={"code": 500}
        )
        assert error.message == "Technical error"
        assert error.user_message == "User-friendly message"
        assert error.details["code"] == 500
    
    def test_file_validation_error(self):
        """Test FileValidationError."""
        error = FileValidationError("Invalid file")
        assert isinstance(error, CodeGuruError)
        assert str(error) == "Invalid file"
    
    def test_analysis_error(self):
        """Test AnalysisError."""
        error = AnalysisError("Analysis failed")
        assert isinstance(error, CodeGuruError)
    
    def test_ai_service_error(self):
        """Test AIServiceError."""
        error = AIServiceError("AI service down")
        assert isinstance(error, CodeGuruError)
    
    def test_repository_error(self):
        """Test RepositoryError."""
        error = RepositoryError("Repo not found")
        assert isinstance(error, CodeGuruError)
    
    def test_session_error(self):
        """Test SessionError."""
        error = SessionError("Session expired")
        assert isinstance(error, CodeGuruError)


class TestFileValidation:
    """Test file validation functions."""
    
    def test_validate_file_upload_none(self):
        """Test validation with no file."""
        is_valid, error = validate_file_upload(None)
        assert not is_valid
        assert error == "No file uploaded"
    
    def test_validate_file_upload_too_large(self):
        """Test validation with file too large."""
        mock_file = Mock()
        mock_file.getvalue.return_value = b"x" * (11 * 1024 * 1024)  # 11MB
        mock_file.name = "test.py"
        
        is_valid, error = validate_file_upload(mock_file, max_size_mb=10)
        assert not is_valid
        assert "too large" in error.lower()
    
    def test_validate_file_upload_invalid_extension(self):
        """Test validation with invalid extension."""
        mock_file = Mock()
        mock_file.getvalue.return_value = b"print('hello')"
        mock_file.name = "test.txt"
        
        is_valid, error = validate_file_upload(
            mock_file,
            allowed_extensions=['.py', '.js']
        )
        assert not is_valid
        assert "unsupported" in error.lower()
    
    def test_validate_file_upload_empty(self):
        """Test validation with empty file."""
        mock_file = Mock()
        mock_file.getvalue.return_value = b""
        mock_file.name = "test.py"
        
        is_valid, error = validate_file_upload(mock_file)
        assert not is_valid
        assert "empty" in error.lower()
    
    def test_validate_file_upload_valid(self):
        """Test validation with valid file."""
        mock_file = Mock()
        mock_file.getvalue.return_value = b"print('hello world')"
        mock_file.name = "test.py"
        
        is_valid, error = validate_file_upload(
            mock_file,
            allowed_extensions=['.py']
        )
        assert is_valid
        assert error is None


class TestCodeValidation:
    """Test code content validation."""
    
    def test_validate_code_content_empty(self):
        """Test validation with empty code."""
        is_valid, error = validate_code_content("")
        assert not is_valid
        assert "empty" in error.lower()
    
    def test_validate_code_content_whitespace_only(self):
        """Test validation with whitespace only."""
        is_valid, error = validate_code_content("   \n\t  ")
        assert not is_valid
    
    def test_validate_code_content_with_eval(self):
        """Test validation with eval (suspicious)."""
        code = "result = eval(user_input)"
        is_valid, warning = validate_code_content(code)
        assert is_valid  # Still valid, but with warning
        assert warning is not None
        assert "eval" in warning.lower()
    
    def test_validate_code_content_with_exec(self):
        """Test validation with exec (suspicious)."""
        code = "exec(malicious_code)"
        is_valid, warning = validate_code_content(code)
        assert is_valid
        assert warning is not None
    
    def test_validate_code_content_safe(self):
        """Test validation with safe code."""
        code = "def hello():\n    print('Hello, World!')"
        is_valid, warning = validate_code_content(code)
        assert is_valid
        assert warning is None


class TestGitHubURLValidation:
    """Test GitHub URL validation."""
    
    def test_validate_github_url_empty(self):
        """Test validation with empty URL."""
        is_valid, error = validate_github_url("")
        assert not is_valid
        assert "empty" in error.lower()
    
    def test_validate_github_url_not_github(self):
        """Test validation with non-GitHub URL."""
        is_valid, error = validate_github_url("https://gitlab.com/user/repo")
        assert not is_valid
        assert "github" in error.lower()
    
    def test_validate_github_url_invalid_format(self):
        """Test validation with invalid format."""
        is_valid, error = validate_github_url("https://github.com/user")
        assert not is_valid
        assert "format" in error.lower()
    
    def test_validate_github_url_valid(self):
        """Test validation with valid URL."""
        is_valid, error = validate_github_url("https://github.com/user/repository")
        assert is_valid
        assert error is None


class TestSafeAICall:
    """Test safe AI call with retries."""
    
    def test_safe_ai_call_success(self):
        """Test successful AI call."""
        mock_func = Mock(return_value="Success response")
        result = safe_ai_call(mock_func)
        assert result == "Success response"
        assert mock_func.call_count == 1
    
    def test_safe_ai_call_retry_then_success(self):
        """Test AI call that fails once then succeeds."""
        mock_func = Mock(side_effect=[Exception("Temporary error"), "Success"])
        result = safe_ai_call(mock_func, max_retries=2)
        assert result == "Success"
        assert mock_func.call_count == 2
    
    def test_safe_ai_call_all_retries_fail(self):
        """Test AI call that fails all retries."""
        mock_func = Mock(side_effect=Exception("Persistent error"))
        result = safe_ai_call(mock_func, fallback_response="Fallback", max_retries=2)
        assert result == "Fallback"
        assert mock_func.call_count == 3  # Initial + 2 retries


class TestErrorRecovery:
    """Test error recovery utilities."""
    
    def test_retry_with_backoff_success(self):
        """Test retry with immediate success."""
        mock_func = Mock(return_value="Success")
        result = ErrorRecovery.retry_with_backoff(mock_func)
        assert result == "Success"
        assert mock_func.call_count == 1
    
    def test_retry_with_backoff_eventual_success(self):
        """Test retry with eventual success."""
        mock_func = Mock(side_effect=[
            Exception("Error 1"),
            Exception("Error 2"),
            "Success"
        ])
        result = ErrorRecovery.retry_with_backoff(mock_func, max_attempts=3)
        assert result == "Success"
        assert mock_func.call_count == 3
    
    def test_retry_with_backoff_all_fail(self):
        """Test retry with all attempts failing."""
        mock_func = Mock(side_effect=Exception("Persistent error"))
        
        with pytest.raises(Exception) as exc_info:
            ErrorRecovery.retry_with_backoff(mock_func, max_attempts=3)
        
        assert "Persistent error" in str(exc_info.value)
        assert mock_func.call_count == 3


class TestUserFriendlyMessages:
    """Test user-friendly error messages."""
    
    def test_get_user_friendly_message_english(self):
        """Test English error messages."""
        error = FileValidationError("Technical error")
        message = get_user_friendly_message(error, "english")
        assert "file" in message.lower()
        assert "upload" in message.lower()
    
    def test_get_user_friendly_message_hindi(self):
        """Test Hindi error messages."""
        error = AIServiceError("Service down")
        message = get_user_friendly_message(error, "hindi")
        assert len(message) > 0
        # Should contain Hindi characters
    
    def test_get_user_friendly_message_telugu(self):
        """Test Telugu error messages."""
        error = RepositoryError("Repo not found")
        message = get_user_friendly_message(error, "telugu")
        assert len(message) > 0
        # Should contain Telugu characters
    
    def test_get_user_friendly_message_unknown_error(self):
        """Test message for unknown error type."""
        error = ValueError("Unknown error")
        message = get_user_friendly_message(error, "english")
        assert "Unknown error" in message


class TestErrorIntegration:
    """Test error integration utilities."""
    
    def test_validate_and_process_file_success(self):
        """Test successful file validation and processing."""
        mock_file = Mock()
        mock_file.getvalue.return_value = b"print('hello')"
        mock_file.name = "test.py"
        
        success, content, error = validate_and_process_file(
            mock_file,
            allowed_extensions=['.py']
        )
        
        assert success
        assert content == "print('hello')"
        assert error is None or "warning" in error.lower()
    
    def test_validate_and_process_file_invalid(self):
        """Test file validation failure."""
        mock_file = Mock()
        mock_file.getvalue.return_value = b"x" * (11 * 1024 * 1024)
        mock_file.name = "test.py"
        
        success, content, error = validate_and_process_file(
            mock_file,
            max_size_mb=10
        )
        
        assert not success
        assert content is None
        assert error is not None
    
    def test_validate_and_process_github_url_valid(self):
        """Test valid GitHub URL processing."""
        is_valid, error = validate_and_process_github_url(
            "https://github.com/user/repo"
        )
        assert is_valid
        assert error is None
    
    def test_validate_and_process_github_url_invalid(self):
        """Test invalid GitHub URL processing."""
        is_valid, error = validate_and_process_github_url(
            "https://gitlab.com/user/repo"
        )
        assert not is_valid
        assert error is not None


class TestLocalizedMessages:
    """Test localized error messages."""
    
    def test_get_localized_message_english(self):
        """Test English localized message."""
        message = get_localized_error_message(
            'file_too_large',
            'english',
            max_size=10
        )
        assert "10MB" in message
    
    def test_get_localized_message_hindi(self):
        """Test Hindi localized message."""
        message = get_localized_error_message(
            'invalid_format',
            'hindi',
            formats='.py, .js'
        )
        assert len(message) > 0
    
    def test_get_localized_message_telugu(self):
        """Test Telugu localized message."""
        message = get_localized_error_message(
            'analysis_failed',
            'telugu'
        )
        assert len(message) > 0
    
    def test_get_localized_message_unknown_key(self):
        """Test unknown message key."""
        message = get_localized_error_message(
            'unknown_key',
            'english'
        )
        assert message == 'unknown_key'


class TestDecorators:
    """Test error handling decorators."""
    
    @patch('streamlit.error')
    @patch('streamlit.warning')
    def test_safe_file_analysis_decorator(self, mock_warning, mock_error):
        """Test safe file analysis decorator."""
        @safe_file_analysis
        def analyze_file():
            raise FileValidationError("Invalid file")
        
        result = analyze_file()
        assert result is None
        # Should have displayed error
    
    @patch('streamlit.error')
    def test_safe_repository_operation_decorator(self, mock_error):
        """Test safe repository operation decorator."""
        @safe_repository_operation
        def clone_repo():
            raise RepositoryError("Clone failed")
        
        result = clone_repo()
        assert result is None
    
    @patch('streamlit.warning')
    def test_safe_ai_operation_decorator(self, mock_warning):
        """Test safe AI operation decorator."""
        @safe_ai_operation(fallback_message="Fallback")
        def call_ai():
            raise AIServiceError("AI down")
        
        result = call_ai()
        assert result == "Fallback"
    
    def test_safe_diagram_generation_decorator(self):
        """Test safe diagram generation decorator."""
        @safe_diagram_generation
        def generate_diagram():
            raise Exception("Generation failed")
        
        result = generate_diagram()
        assert result is not None
        assert "unavailable" in result.lower()


class TestBedrockIntegration:
    """Test Bedrock client error handling integration."""
    
    def test_safe_bedrock_call_success(self):
        """Test successful Bedrock call."""
        mock_client = Mock()
        mock_client.invoke_model.return_value = "AI response"
        
        result = safe_bedrock_call(mock_client, "Test prompt")
        assert result == "AI response"
    
    def test_safe_bedrock_call_failure(self):
        """Test Bedrock call with failure."""
        mock_client = Mock()
        mock_client.invoke_model.side_effect = Exception("API error")
        
        result = safe_bedrock_call(
            mock_client,
            "Test prompt",
            fallback_response="Fallback"
        )
        assert result == "Fallback"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
