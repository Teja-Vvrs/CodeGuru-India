"""
Unit tests for security utilities.
"""

import pytest
from io import BytesIO
from utils.security import (
    InputSanitizer,
    FileValidator,
    MemoryOnlyProcessor,
    HTTPSEnforcer,
    SecurityValidationResult,
    validate_and_sanitize_file,
    sanitize_user_input,
    ensure_memory_only_processing,
    get_https_config,
)


class MockFile:
    """Mock file object for testing."""
    def __init__(self, name: str, content: bytes):
        self.name = name
        self.content = content
    
    def getvalue(self):
        return self.content


class TestInputSanitizer:
    """Test input sanitization."""
    
    def test_sanitize_text_input_valid(self):
        """Test sanitizing valid text input."""
        result = InputSanitizer.sanitize_text_input("Hello, world!")
        assert result.is_valid
        assert result.sanitized_content == "Hello, world!"
        assert len(result.warnings) == 0
    
    def test_sanitize_text_input_empty(self):
        """Test sanitizing empty input."""
        result = InputSanitizer.sanitize_text_input("")
        assert not result.is_valid
        assert "empty" in result.error_message.lower()
    
    def test_sanitize_text_input_too_long(self):
        """Test sanitizing input that's too long."""
        long_text = "a" * 10001
        result = InputSanitizer.sanitize_text_input(long_text, max_length=10000)
        assert not result.is_valid
        assert "too long" in result.error_message.lower()
    
    def test_sanitize_text_input_sql_injection(self):
        """Test detecting SQL injection patterns."""
        malicious_input = "'; DROP TABLE users; --"
        result = InputSanitizer.sanitize_text_input(malicious_input)
        assert result.is_valid  # Still valid but with warnings
        assert any('sql_injection' in w.lower() for w in result.warnings)
    
    def test_sanitize_text_input_xss(self):
        """Test detecting XSS patterns."""
        malicious_input = "<script>alert('XSS')</script>"
        result = InputSanitizer.sanitize_text_input(malicious_input)
        assert result.is_valid  # Still valid but with warnings
        assert any('xss' in w.lower() for w in result.warnings)
    
    def test_sanitize_url_valid_https(self):
        """Test sanitizing valid HTTPS URL."""
        result = InputSanitizer.sanitize_url("https://github.com/user/repo")
        assert result.is_valid
        assert result.sanitized_content == "https://github.com/user/repo"
    
    def test_sanitize_url_http_rejected(self):
        """Test that HTTP URLs are rejected."""
        result = InputSanitizer.sanitize_url("http://example.com")
        assert not result.is_valid
        assert "https" in result.error_message.lower()
    
    def test_sanitize_url_javascript_rejected(self):
        """Test that javascript: URLs are rejected."""
        result = InputSanitizer.sanitize_url("javascript:alert('XSS')")
        assert not result.is_valid
        # javascript: URLs fail HTTPS check first
        assert "https" in result.error_message.lower() or "suspicious" in result.error_message.lower()
    
    def test_sanitize_code_input_valid(self):
        """Test sanitizing valid code."""
        code = "def hello():\n    print('Hello, world!')"
        result = InputSanitizer.sanitize_code_input(code)
        assert result.is_valid
        assert result.sanitized_content == code
    
    def test_sanitize_code_input_with_warnings(self):
        """Test sanitizing code with dangerous operations."""
        code = "import os\nos.system('ls')"
        result = InputSanitizer.sanitize_code_input(code)
        assert result.is_valid  # Valid but with warnings
        assert len(result.warnings) > 0
        assert any('system_calls' in w.lower() for w in result.warnings)
    
    def test_sanitize_code_input_empty(self):
        """Test sanitizing empty code."""
        result = InputSanitizer.sanitize_code_input("")
        assert not result.is_valid
        assert "empty" in result.error_message.lower()


class TestFileValidator:
    """Test file validation."""
    
    def test_validate_file_upload_valid_python(self):
        """Test validating valid Python file."""
        file = MockFile("test.py", b"def hello():\n    pass")
        result = FileValidator.validate_file_upload(file, allowed_extensions=['.py'])
        assert result.is_valid
    
    def test_validate_file_upload_no_file(self):
        """Test validating when no file is provided."""
        result = FileValidator.validate_file_upload(None)
        assert not result.is_valid
        assert "no file" in result.error_message.lower()
    
    def test_validate_file_upload_blocked_extension(self):
        """Test that blocked extensions are rejected."""
        file = MockFile("malware.exe", b"MZ\x90\x00")
        result = FileValidator.validate_file_upload(file)
        assert not result.is_valid
        assert "not allowed" in result.error_message.lower()
    
    def test_validate_file_upload_wrong_extension(self):
        """Test that wrong extensions are rejected."""
        file = MockFile("test.txt", b"Hello")
        result = FileValidator.validate_file_upload(file, allowed_extensions=['.py', '.js'])
        assert not result.is_valid
        assert "unsupported" in result.error_message.lower()
    
    def test_validate_file_upload_too_large(self):
        """Test that large files are rejected."""
        large_content = b"a" * (11 * 1024 * 1024)  # 11 MB
        file = MockFile("large.py", large_content)
        result = FileValidator.validate_file_upload(file, max_size_mb=10)
        assert not result.is_valid
        assert "too large" in result.error_message.lower()
    
    def test_validate_file_upload_empty(self):
        """Test that empty files are rejected."""
        file = MockFile("empty.py", b"")
        result = FileValidator.validate_file_upload(file)
        assert not result.is_valid
        assert "empty" in result.error_message.lower()
    
    def test_validate_file_upload_invalid_signature(self):
        """Test detecting invalid file signatures."""
        # Binary content in a .py file
        file = MockFile("fake.py", b"\x00\x01\x02\x03\x04")
        result = FileValidator.validate_file_upload(file, allowed_extensions=['.py'])
        # Should have warnings about invalid signature
        assert len(result.warnings) > 0 or not result.is_valid
    
    def test_validate_file_content_obfuscated(self):
        """Test detecting obfuscated code."""
        # High entropy content (random-looking)
        obfuscated = "x" * 50 + "y" * 50 + "z" * 50 + "1234567890" * 10
        result = FileValidator.validate_file_content(obfuscated, '.py')
        # May have warnings about obfuscation
        assert result.is_valid
    
    def test_validate_file_content_suspicious_imports(self):
        """Test detecting suspicious imports."""
        code = "import pickle\nimport marshal"
        result = FileValidator.validate_file_content(code, '.py')
        assert result.is_valid
        assert len(result.warnings) > 0
        assert any('dangerous module' in w.lower() for w in result.warnings)


class TestMemoryOnlyProcessor:
    """Test memory-only processing enforcement."""
    
    def test_get_memory_usage(self):
        """Test getting memory usage."""
        usage = MemoryOnlyProcessor.get_memory_usage_mb()
        assert isinstance(usage, float)
        assert usage >= 0
    
    def test_clear_code_from_memory(self):
        """Test clearing code from memory."""
        # This test would need Streamlit session state mocking
        # For now, just ensure it doesn't crash
        MemoryOnlyProcessor.clear_code_from_memory()


class TestHTTPSEnforcer:
    """Test HTTPS enforcement."""
    
    def test_get_streamlit_https_config(self):
        """Test getting HTTPS configuration."""
        config = HTTPSEnforcer.get_streamlit_https_config()
        assert isinstance(config, dict)
        assert 'server' in config
        assert 'enableXsrfProtection' in config['server']
        assert config['server']['enableXsrfProtection'] is True
    
    def test_validate_secure_connection(self):
        """Test validating secure connection."""
        is_secure, message = HTTPSEnforcer.validate_secure_connection()
        assert isinstance(is_secure, bool)
        assert isinstance(message, str)


class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_validate_and_sanitize_file(self):
        """Test file validation convenience function."""
        file = MockFile("test.py", b"def hello(): pass")
        is_valid, error, warnings = validate_and_sanitize_file(
            file,
            max_size_mb=10,
            allowed_extensions=['.py']
        )
        assert is_valid
        assert error is None
    
    def test_sanitize_user_input_text(self):
        """Test text input sanitization convenience function."""
        is_valid, error, sanitized, warnings = sanitize_user_input("Hello, world!")
        assert is_valid
        assert error is None
        assert sanitized == "Hello, world!"
    
    def test_sanitize_user_input_url(self):
        """Test URL input sanitization convenience function."""
        is_valid, error, sanitized, warnings = sanitize_user_input(
            "https://github.com/user/repo",
            input_type='url'
        )
        assert is_valid
        assert error is None
    
    def test_sanitize_user_input_code(self):
        """Test code input sanitization convenience function."""
        code = "def hello(): pass"
        is_valid, error, sanitized, warnings = sanitize_user_input(
            code,
            input_type='code'
        )
        assert is_valid
        assert error is None
    
    def test_get_https_config(self):
        """Test getting HTTPS config convenience function."""
        config = get_https_config()
        assert isinstance(config, dict)
        assert 'server' in config


class TestSecurityValidationResult:
    """Test SecurityValidationResult dataclass."""
    
    def test_create_valid_result(self):
        """Test creating valid result."""
        result = SecurityValidationResult(is_valid=True)
        assert result.is_valid
        assert result.error_message is None
        assert result.warnings == []
    
    def test_create_invalid_result(self):
        """Test creating invalid result."""
        result = SecurityValidationResult(
            is_valid=False,
            error_message="Test error"
        )
        assert not result.is_valid
        assert result.error_message == "Test error"
    
    def test_create_result_with_warnings(self):
        """Test creating result with warnings."""
        result = SecurityValidationResult(
            is_valid=True,
            warnings=["Warning 1", "Warning 2"]
        )
        assert result.is_valid
        assert len(result.warnings) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
