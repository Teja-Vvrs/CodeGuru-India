"""
Unit tests for error handling utilities.
"""

import pytest
from utils.error_handler import (
    CodeGuruError,
    FileValidationError,
    AnalysisError,
    AIServiceError,
    RepositoryError,
    SessionError,
    validate_file_upload,
    validate_code_content,
    validate_github_url,
    get_user_friendly_message
)


class TestFileValidation:
    """Test file upload validation."""
    
    def test_validate_file_upload_none(self):
        """Test validation with no file."""
        is_valid, error = validate_file_upload(None)
        assert not is_valid
        assert "No file uploaded" in error
    
    def test_validate_file_upload_size(self):
        """Test file size validation."""
        # Mock file object
        class MockFile:
            def __init__(self, size):
                self._size = size
                self.name = "test.py"
            
            def getvalue(self):
                return b'x' * self._size
        
        # File too large
        large_file = MockFile(11 * 1024 * 1024)  # 11MB
        is_valid, error = validate_file_upload(large_file, max_size_mb=10)
        assert not is_valid
        assert "too large" in error.lower()
        
        # File within limit
        small_file = MockFile(5 * 1024 * 1024)  # 5MB
        is_valid, error = validate_file_upload(small_file, max_size_mb=10)
        assert is_valid
        assert error is None
    
    def test_validate_file_upload_extension(self):
        """Test file extension validation."""
        class MockFile:
            def __init__(self, name):
                self.name = name
            
            def getvalue(self):
                return b'test content'
        
        # Valid extension
        py_file = MockFile("test.py")
        is_valid, error = validate_file_upload(py_file, allowed_extensions=['.py', '.js'])
        assert is_valid
        
        # Invalid extension
        txt_file = MockFile("test.txt")
        is_valid, error = validate_file_upload(txt_file, allowed_extensions=['.py', '.js'])
        assert not is_valid
        assert "Unsupported file type" in error
    
    def test_validate_file_upload_empty(self):
        """Test empty file validation."""
        class MockFile:
            name = "test.py"
            def getvalue(self):
                return b''
        
        is_valid, error = validate_file_upload(MockFile())
        assert not is_valid
        assert "empty" in error.lower()


class TestCodeValidation:
    """Test code content validation."""
    
    def test_validate_code_content_empty(self):
        """Test empty code validation."""
        is_valid, error = validate_code_content("")
        assert not is_valid
        assert "empty" in error.lower()
        
        is_valid, error = validate_code_content("   ")
        assert not is_valid
    
    def test_validate_code_content_suspicious(self):
        """Test suspicious pattern detection."""
        # Code with eval
        code_with_eval = "result = eval(user_input)"
        is_valid, warning = validate_code_content(code_with_eval)
        assert is_valid  # Still valid, just warning
        assert warning is not None
        assert "unsafe" in warning.lower()
        
        # Safe code
        safe_code = "def hello():\n    print('Hello')"
        is_valid, warning = validate_code_content(safe_code)
        assert is_valid
        assert warning is None


class TestGitHubURLValidation:
    """Test GitHub URL validation."""
    
    def test_validate_github_url_empty(self):
        """Test empty URL validation."""
        is_valid, error = validate_github_url("")
        assert not is_valid
        assert "empty" in error.lower()
    
    def test_validate_github_url_invalid_domain(self):
        """Test non-GitHub URL."""
        is_valid, error = validate_github_url("https://gitlab.com/user/repo")
        assert not is_valid
        assert "GitHub" in error
    
    def test_validate_github_url_invalid_format(self):
        """Test invalid format."""
        is_valid, error = validate_github_url("https://github.com/user")
        assert not is_valid
        assert "format" in error.lower()
    
    def test_validate_github_url_valid(self):
        """Test valid GitHub URL."""
        is_valid, error = validate_github_url("https://github.com/user/repository")
        assert is_valid
        assert error is None


class TestErrorMessages:
    """Test user-friendly error messages."""
    
    def test_get_user_friendly_message_english(self):
        """Test English error messages."""
        error = FileValidationError("Technical error", "User message")
        message = get_user_friendly_message(error, "english")
        assert "file" in message.lower()
        assert "upload" in message.lower()
    
    def test_get_user_friendly_message_hindi(self):
        """Test Hindi error messages."""
        error = AnalysisError("Technical error")
        message = get_user_friendly_message(error, "hindi")
        # Should contain Hindi text
        assert len(message) > 0
    
    def test_get_user_friendly_message_telugu(self):
        """Test Telugu error messages."""
        error = AIServiceError("Technical error")
        message = get_user_friendly_message(error, "telugu")
        # Should contain Telugu text
        assert len(message) > 0


class TestCustomExceptions:
    """Test custom exception classes."""
    
    def test_codeguru_error(self):
        """Test base CodeGuruError."""
        error = CodeGuruError(
            "Technical message",
            user_message="User-friendly message",
            details={"key": "value"}
        )
        assert error.message == "Technical message"
        assert error.user_message == "User-friendly message"
        assert error.details == {"key": "value"}
    
    def test_file_validation_error(self):
        """Test FileValidationError."""
        error = FileValidationError("File error")
        assert isinstance(error, CodeGuruError)
    
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
        error = SessionError("Session corrupted")
        assert isinstance(error, CodeGuruError)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
