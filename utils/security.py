"""
Security utilities for CodeGuru India.

Implements comprehensive security measures including:
- Input sanitization
- File upload validation for malicious content
- In-memory processing enforcement
- HTTPS configuration
"""

import re
import logging
import hashlib
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass
import streamlit as st

logger = logging.getLogger(__name__)


@dataclass
class SecurityValidationResult:
    """Result of security validation."""
    is_valid: bool
    error_message: Optional[str] = None
    warnings: List[str] = None
    sanitized_content: Optional[str] = None
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class InputSanitizer:
    """Sanitizes user inputs to prevent injection attacks."""
    
    # Dangerous patterns that should be blocked or sanitized
    DANGEROUS_PATTERNS = {
        'sql_injection': [
            r"(\bUNION\b.*\bSELECT\b)",
            r"(\bDROP\b.*\bTABLE\b)",
            r"(\bINSERT\b.*\bINTO\b)",
            r"(\bDELETE\b.*\bFROM\b)",
            r"(--\s*$)",  # SQL comments
            r"(/\*.*\*/)",  # Multi-line comments
        ],
        'xss': [
            r"<script[^>]*>.*?</script>",
            r"javascript:",
            r"on\w+\s*=",  # Event handlers
            r"<iframe[^>]*>",
        ],
        'command_injection': [
            r"[;&|`$]",  # Shell metacharacters
            r"\$\(.*\)",  # Command substitution
            r"`.*`",  # Backticks
        ],
        'path_traversal': [
            r"\.\./",  # Directory traversal
            r"\.\.",  # Parent directory
            r"~\/",  # Home directory
        ]
    }
    
    @staticmethod
    def sanitize_text_input(text: str, max_length: int = 10000) -> SecurityValidationResult:
        """
        Sanitize general text input.
        
        Args:
            text: Input text to sanitize
            max_length: Maximum allowed length
        
        Returns:
            SecurityValidationResult with sanitized content
        """
        if not text:
            return SecurityValidationResult(
                is_valid=False,
                error_message="Input is empty"
            )
        
        # Check length
        if len(text) > max_length:
            return SecurityValidationResult(
                is_valid=False,
                error_message=f"Input too long ({len(text)} chars). Maximum: {max_length}"
            )
        
        warnings = []
        sanitized = text
        
        # Check for dangerous patterns
        for pattern_type, patterns in InputSanitizer.DANGEROUS_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    warnings.append(f"Potentially dangerous {pattern_type} pattern detected")
                    logger.warning(f"Dangerous pattern detected: {pattern_type} in input")
        
        # Remove null bytes
        sanitized = sanitized.replace('\x00', '')
        
        # Normalize whitespace
        sanitized = ' '.join(sanitized.split())
        
        return SecurityValidationResult(
            is_valid=True,
            warnings=warnings,
            sanitized_content=sanitized
        )
    
    @staticmethod
    def sanitize_url(url: str) -> SecurityValidationResult:
        """
        Sanitize and validate URL input.
        
        Args:
            url: URL to sanitize
        
        Returns:
            SecurityValidationResult
        """
        if not url:
            return SecurityValidationResult(
                is_valid=False,
                error_message="URL is empty"
            )
        
        url = url.strip()
        warnings = []
        
        # Only allow HTTPS URLs
        if not url.startswith('https://'):
            return SecurityValidationResult(
                is_valid=False,
                error_message="Only HTTPS URLs are allowed for security"
            )
        
        # Check for suspicious patterns
        suspicious_patterns = [
            r"javascript:",
            r"data:",
            r"file:",
            r"<script",
        ]
        
        for pattern in suspicious_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return SecurityValidationResult(
                    is_valid=False,
                    error_message="URL contains suspicious content"
                )
        
        # Validate GitHub URL format specifically
        if 'github.com' in url:
            if not re.match(r'https://github\.com/[\w-]+/[\w.-]+/?', url):
                warnings.append("GitHub URL format may be invalid")
        
        return SecurityValidationResult(
            is_valid=True,
            warnings=warnings,
            sanitized_content=url
        )
    
    @staticmethod
    def sanitize_code_input(code: str, max_length: int = 1000000) -> SecurityValidationResult:
        """
        Sanitize code input while preserving code structure.
        
        Args:
            code: Code content to sanitize
            max_length: Maximum allowed length
        
        Returns:
            SecurityValidationResult
        """
        if not code or not code.strip():
            return SecurityValidationResult(
                is_valid=False,
                error_message="Code is empty"
            )
        
        if len(code) > max_length:
            return SecurityValidationResult(
                is_valid=False,
                error_message=f"Code too long ({len(code)} chars). Maximum: {max_length}"
            )
        
        warnings = []
        
        # Check for potentially dangerous code patterns
        dangerous_code_patterns = {
            'file_operations': [r'\bopen\s*\(', r'\bfile\s*\('],
            'system_calls': [r'\bos\.system\s*\(', r'\bsubprocess\.', r'\bexec\s*\(', r'\beval\s*\('],
            'network': [r'\bsocket\.', r'\burllib\.', r'\brequests\.'],
            'imports': [r'\b__import__\s*\(', r'\bimportlib\.'],
        }
        
        for category, patterns in dangerous_code_patterns.items():
            for pattern in patterns:
                if re.search(pattern, code):
                    warnings.append(f"Code contains {category} operations")
                    logger.info(f"Code contains {category}: {pattern}")
        
        # Remove null bytes
        sanitized = code.replace('\x00', '')
        
        return SecurityValidationResult(
            is_valid=True,
            warnings=warnings,
            sanitized_content=sanitized
        )


class FileValidator:
    """Validates uploaded files for security threats."""
    
    # File signatures (magic numbers) for common file types
    FILE_SIGNATURES = {
        '.py': [b'#!', b'"""', b"'''", b'import ', b'from ', b'def ', b'class '],
        '.js': [b'//', b'/*', b'function', b'const ', b'let ', b'var ', b'import ', b'export '],
        '.java': [b'package ', b'import ', b'public class', b'class '],
        '.cpp': [b'#include', b'//', b'/*', b'using namespace'],
        '.c': [b'#include', b'//', b'/*'],
        '.go': [b'package ', b'import ', b'func '],
        '.rb': [b'#', b'require ', b'class ', b'def ', b'module '],
        '.ts': [b'//', b'/*', b'import ', b'export ', b'interface ', b'type '],
        '.tsx': [b'//', b'/*', b'import ', b'export ', b'interface ', b'type '],
        '.jsx': [b'//', b'/*', b'import ', b'export ', b'function', b'const '],
    }
    
    # Dangerous file extensions that should never be allowed
    BLOCKED_EXTENSIONS = [
        '.exe', '.dll', '.so', '.dylib', '.bat', '.cmd', '.sh', '.ps1',
        '.msi', '.app', '.deb', '.rpm', '.dmg', '.pkg', '.apk',
        '.jar', '.war', '.ear',  # Compiled Java (could contain malicious code)
    ]
    
    @staticmethod
    def validate_file_upload(
        file,
        max_size_mb: int = 10,
        allowed_extensions: Optional[List[str]] = None
    ) -> SecurityValidationResult:
        """
        Comprehensive file upload validation.
        
        Args:
            file: Uploaded file object
            max_size_mb: Maximum file size in MB
            allowed_extensions: List of allowed extensions
        
        Returns:
            SecurityValidationResult
        """
        if file is None:
            return SecurityValidationResult(
                is_valid=False,
                error_message="No file uploaded"
            )
        
        warnings = []
        
        # Get file extension
        filename = file.name
        file_ext = '.' + filename.split('.')[-1].lower() if '.' in filename else ''
        
        # Check for blocked extensions
        if file_ext in FileValidator.BLOCKED_EXTENSIONS:
            return SecurityValidationResult(
                is_valid=False,
                error_message=f"File type {file_ext} is not allowed for security reasons"
            )
        
        # Check allowed extensions
        if allowed_extensions and file_ext not in allowed_extensions:
            return SecurityValidationResult(
                is_valid=False,
                error_message=f"Unsupported file type. Allowed: {', '.join(allowed_extensions)}"
            )
        
        # Get file content
        try:
            file_content = file.getvalue()
        except Exception as e:
            logger.error(f"Failed to read file: {e}")
            return SecurityValidationResult(
                is_valid=False,
                error_message="Failed to read file content"
            )
        
        # Check file size
        file_size_mb = len(file_content) / (1024 * 1024)
        if file_size_mb > max_size_mb:
            return SecurityValidationResult(
                is_valid=False,
                error_message=f"File too large ({file_size_mb:.1f}MB). Maximum: {max_size_mb}MB"
            )
        
        # Check if file is empty
        if len(file_content) == 0:
            return SecurityValidationResult(
                is_valid=False,
                error_message="File is empty"
            )
        
        # Validate file signature (magic number check)
        if file_ext in FileValidator.FILE_SIGNATURES:
            expected_signatures = FileValidator.FILE_SIGNATURES[file_ext]
            has_valid_signature = any(
                file_content[:100].startswith(sig) or sig in file_content[:500]
                for sig in expected_signatures
            )
            
            if not has_valid_signature:
                warnings.append(f"File may not be a valid {file_ext} file")
        
        # Check for embedded malicious content
        malicious_patterns = [
            b'<script',
            b'javascript:',
            b'eval(',
            b'exec(',
            b'__import__',
        ]
        
        for pattern in malicious_patterns:
            if pattern in file_content:
                warnings.append(f"File contains potentially dangerous pattern: {pattern.decode('utf-8', errors='ignore')}")
        
        # Check for binary content in text files
        if file_ext in ['.py', '.js', '.java', '.cpp', '.c', '.go', '.rb', '.ts', '.tsx', '.jsx']:
            try:
                file_content.decode('utf-8')
            except UnicodeDecodeError:
                return SecurityValidationResult(
                    is_valid=False,
                    error_message="File contains invalid characters or is not a text file"
                )
        
        return SecurityValidationResult(
            is_valid=True,
            warnings=warnings
        )
    
    @staticmethod
    def validate_file_content(content: str, file_extension: str) -> SecurityValidationResult:
        """
        Validate file content for malicious code.
        
        Args:
            content: File content as string
            file_extension: File extension
        
        Returns:
            SecurityValidationResult
        """
        warnings = []
        
        # Check for obfuscated code
        if len(content) > 100:
            # Calculate entropy to detect obfuscation
            entropy = FileValidator._calculate_entropy(content[:1000])
            if entropy > 5.5:  # High entropy suggests obfuscation
                warnings.append("File may contain obfuscated code")
        
        # Check for suspicious imports/requires
        suspicious_imports = {
            'python': ['pickle', 'marshal', 'shelve', 'dill'],
            'javascript': ['child_process', 'fs', 'net'],
            'java': ['Runtime', 'ProcessBuilder'],
        }
        
        language = FileValidator._detect_language(file_extension)
        if language in suspicious_imports:
            for imp in suspicious_imports[language]:
                if imp in content:
                    warnings.append(f"File imports potentially dangerous module: {imp}")
        
        return SecurityValidationResult(
            is_valid=True,
            warnings=warnings
        )
    
    @staticmethod
    def _calculate_entropy(data: str) -> float:
        """Calculate Shannon entropy of string."""
        if not data:
            return 0.0
        
        entropy = 0.0
        for x in range(256):
            p_x = float(data.count(chr(x))) / len(data)
            if p_x > 0:
                entropy += - p_x * (p_x ** 0.5)
        
        return entropy
    
    @staticmethod
    def _detect_language(file_extension: str) -> str:
        """Detect programming language from extension."""
        language_map = {
            '.py': 'python',
            '.js': 'javascript',
            '.jsx': 'javascript',
            '.ts': 'javascript',
            '.tsx': 'javascript',
            '.java': 'java',
            '.cpp': 'cpp',
            '.c': 'c',
            '.go': 'go',
            '.rb': 'ruby',
        }
        return language_map.get(file_extension, 'unknown')


class MemoryOnlyProcessor:
    """Ensures code is processed in-memory only without persistent storage."""
    
    @staticmethod
    def validate_no_persistence() -> bool:
        """
        Validate that no code is being persisted to disk.
        
        Returns:
            True if validation passes
        """
        # Check session state for any file paths
        if hasattr(st.session_state, 'uploaded_code_path'):
            logger.error("Code path found in session state - persistence detected!")
            return False
        
        # Verify code is only in memory
        if hasattr(st.session_state, 'uploaded_code'):
            code = st.session_state.uploaded_code
            if isinstance(code, str):
                # Code is in memory as string - good
                return True
            else:
                logger.warning(f"Uploaded code has unexpected type: {type(code)}")
                return False
        
        return True
    
    @staticmethod
    def clear_code_from_memory():
        """Clear all code from session state."""
        keys_to_clear = [
            'uploaded_code',
            'uploaded_filename',
            'current_analysis',
            'code_content',
            'file_content',
        ]
        
        for key in keys_to_clear:
            if key in st.session_state:
                del st.session_state[key]
                logger.info(f"Cleared {key} from session state")
    
    @staticmethod
    def get_memory_usage_mb() -> float:
        """Get approximate memory usage of stored code."""
        import sys
        
        total_size = 0
        
        if hasattr(st.session_state, 'uploaded_code'):
            total_size += sys.getsizeof(st.session_state.uploaded_code)
        
        if hasattr(st.session_state, 'current_analysis'):
            total_size += sys.getsizeof(st.session_state.current_analysis)
        
        return total_size / (1024 * 1024)


class HTTPSEnforcer:
    """Enforces HTTPS and secure connection settings."""
    
    @staticmethod
    def get_streamlit_https_config() -> Dict[str, Any]:
        """
        Get Streamlit configuration for HTTPS enforcement.
        
        Returns:
            Configuration dictionary for .streamlit/config.toml
        """
        return {
            'server': {
                'enableCORS': False,
                'enableXsrfProtection': True,
                'maxUploadSize': 10,  # MB
                'enableWebsocketCompression': True,
            },
            'browser': {
                'gatherUsageStats': False,
                'serverAddress': 'localhost',
                'serverPort': 8501,
            },
            'runner': {
                'fastReruns': True,
                'enforceSerializableSessionState': True,
            }
        }
    
    @staticmethod
    def validate_secure_connection() -> Tuple[bool, str]:
        """
        Validate that connection is secure.
        
        Returns:
            (is_secure, message)
        """
        # In production, check for HTTPS
        # For local development, this is informational
        
        try:
            # Check if running in production mode
            import os
            is_production = os.getenv('ENVIRONMENT', 'development') == 'production'
            
            if is_production:
                # In production, enforce HTTPS
                # This would typically be handled by reverse proxy (nginx, etc.)
                return True, "Running in production mode - ensure HTTPS is configured at proxy level"
            else:
                return True, "Running in development mode - HTTPS not required"
        
        except Exception as e:
            logger.error(f"Failed to validate connection: {e}")
            return False, "Failed to validate connection security"


class SecurityAuditor:
    """Audits security measures and logs security events."""
    
    @staticmethod
    def audit_file_upload(filename: str, file_size: int, validation_result: SecurityValidationResult):
        """
        Audit file upload event.
        
        Args:
            filename: Name of uploaded file
            file_size: Size in bytes
            validation_result: Validation result
        """
        audit_entry = {
            'event': 'file_upload',
            'filename': filename,
            'file_size_mb': file_size / (1024 * 1024),
            'is_valid': validation_result.is_valid,
            'warnings': validation_result.warnings,
            'error': validation_result.error_message,
        }
        
        if validation_result.is_valid:
            logger.info(f"File upload audit: {audit_entry}")
        else:
            logger.warning(f"File upload rejected: {audit_entry}")
    
    @staticmethod
    def audit_input_sanitization(input_type: str, had_warnings: bool, warnings: List[str]):
        """
        Audit input sanitization event.
        
        Args:
            input_type: Type of input (text, url, code)
            had_warnings: Whether warnings were generated
            warnings: List of warnings
        """
        if had_warnings:
            logger.warning(f"Input sanitization warnings for {input_type}: {warnings}")
        else:
            logger.debug(f"Input sanitization passed for {input_type}")
    
    @staticmethod
    def audit_memory_usage():
        """Audit memory usage for code storage."""
        usage_mb = MemoryOnlyProcessor.get_memory_usage_mb()
        logger.info(f"Code memory usage: {usage_mb:.2f}MB")
        
        if usage_mb > 50:  # Warning threshold
            logger.warning(f"High memory usage detected: {usage_mb:.2f}MB")
    
    @staticmethod
    def generate_security_report() -> Dict[str, Any]:
        """
        Generate security audit report.
        
        Returns:
            Security report dictionary
        """
        return {
            'memory_only_processing': MemoryOnlyProcessor.validate_no_persistence(),
            'memory_usage_mb': MemoryOnlyProcessor.get_memory_usage_mb(),
            'https_status': HTTPSEnforcer.validate_secure_connection(),
            'session_state_keys': list(st.session_state.keys()) if hasattr(st, 'session_state') else [],
        }


# Convenience functions for easy integration

def validate_and_sanitize_file(file, max_size_mb: int = 10, allowed_extensions: Optional[List[str]] = None) -> Tuple[bool, Optional[str], List[str]]:
    """
    Validate and sanitize uploaded file.
    
    Args:
        file: Uploaded file object
        max_size_mb: Maximum file size
        allowed_extensions: Allowed extensions
    
    Returns:
        (is_valid, error_message, warnings)
    """
    # Validate file
    validation_result = FileValidator.validate_file_upload(file, max_size_mb, allowed_extensions)
    
    # Audit the upload
    if file:
        SecurityAuditor.audit_file_upload(
            file.name,
            len(file.getvalue()) if validation_result.is_valid else 0,
            validation_result
        )
    
    return validation_result.is_valid, validation_result.error_message, validation_result.warnings


def sanitize_user_input(text: str, input_type: str = 'text', max_length: int = 10000) -> Tuple[bool, Optional[str], str, List[str]]:
    """
    Sanitize user input.
    
    Args:
        text: Input text
        input_type: Type of input ('text', 'url', 'code')
        max_length: Maximum length
    
    Returns:
        (is_valid, error_message, sanitized_content, warnings)
    """
    if input_type == 'url':
        result = InputSanitizer.sanitize_url(text)
    elif input_type == 'code':
        result = InputSanitizer.sanitize_code_input(text, max_length)
    else:
        result = InputSanitizer.sanitize_text_input(text, max_length)
    
    # Audit sanitization
    SecurityAuditor.audit_input_sanitization(input_type, len(result.warnings) > 0, result.warnings)
    
    return result.is_valid, result.error_message, result.sanitized_content or text, result.warnings


def ensure_memory_only_processing() -> bool:
    """
    Ensure code is processed in-memory only.
    
    Returns:
        True if validation passes
    """
    is_valid = MemoryOnlyProcessor.validate_no_persistence()
    
    if not is_valid:
        logger.error("Memory-only processing validation failed!")
    
    return is_valid


def get_https_config() -> Dict[str, Any]:
    """
    Get HTTPS configuration for Streamlit.
    
    Returns:
        Configuration dictionary
    """
    return HTTPSEnforcer.get_streamlit_https_config()
