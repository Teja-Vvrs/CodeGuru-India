"""
Comprehensive error handling utilities for CodeGuru India.

Provides centralized error handling, user-friendly messages, and graceful degradation.
"""

import logging
import traceback
from typing import Optional, Dict, Any, Callable
from functools import wraps
import streamlit as st

logger = logging.getLogger(__name__)


class CodeGuruError(Exception):
    """Base exception for CodeGuru India."""
    def __init__(self, message: str, user_message: Optional[str] = None, details: Optional[Dict] = None):
        self.message = message
        self.user_message = user_message or message
        self.details = details or {}
        super().__init__(self.message)


class FileValidationError(CodeGuruError):
    """Raised when file validation fails."""
    pass


class AnalysisError(CodeGuruError):
    """Raised when code analysis fails."""
    pass


class AIServiceError(CodeGuruError):
    """Raised when AI service (Bedrock) fails."""
    pass


class RepositoryError(CodeGuruError):
    """Raised when repository operations fail."""
    pass


class SessionError(CodeGuruError):
    """Raised when session management fails."""
    pass


def handle_errors(
    fallback_message: str = "An error occurred. Please try again.",
    show_details: bool = False,
    log_error: bool = True
):
    """
    Decorator for handling errors in functions.
    
    Args:
        fallback_message: Message to show user on error
        show_details: Whether to show technical details
        log_error: Whether to log the error
    
    Usage:
        @handle_errors("Failed to analyze code")
        def analyze_code(code):
            # function code
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except CodeGuruError as e:
                if log_error:
                    logger.error(f"{func.__name__} failed: {e.message}", exc_info=True)
                
                # Show user-friendly message
                st.error(e.user_message)
                
                if show_details and e.details:
                    with st.expander("Technical Details"):
                        st.json(e.details)
                
                return None
            
            except Exception as e:
                if log_error:
                    logger.error(f"{func.__name__} failed with unexpected error: {e}", exc_info=True)
                
                st.error(fallback_message)
                
                if show_details:
                    with st.expander("Error Details"):
                        st.code(traceback.format_exc())
                
                return None
        
        return wrapper
    return decorator


def validate_file_upload(
    file,
    max_size_mb: int = 10,
    allowed_extensions: Optional[list] = None
) -> tuple[bool, Optional[str]]:
    """
    Validate uploaded file.
    
    Args:
        file: Uploaded file object
        max_size_mb: Maximum file size in MB
        allowed_extensions: List of allowed extensions
    
    Returns:
        (is_valid, error_message)
    """
    if file is None:
        return False, "No file uploaded"
    
    # Check file size
    file_size_mb = len(file.getvalue()) / (1024 * 1024)
    if file_size_mb > max_size_mb:
        return False, f"File too large ({file_size_mb:.1f}MB). Maximum size is {max_size_mb}MB"
    
    # Check extension
    if allowed_extensions:
        file_ext = '.' + file.name.split('.')[-1].lower()
        if file_ext not in allowed_extensions:
            return False, f"Unsupported file type. Allowed: {', '.join(allowed_extensions)}"
    
    # Check if file is empty
    if file_size_mb == 0:
        return False, "File is empty"
    
    return True, None


def validate_code_content(code: str) -> tuple[bool, Optional[str]]:
    """
    Validate code content for malicious patterns.
    
    Args:
        code: Code content to validate
    
    Returns:
        (is_valid, error_message)
    """
    if not code or not code.strip():
        return False, "Code content is empty"
    
    # Check for suspicious patterns (basic security)
    suspicious_patterns = [
        'eval(',
        'exec(',
        '__import__',
        'os.system',
        'subprocess.',
        'open(',  # File operations
    ]
    
    code_lower = code.lower()
    found_patterns = [p for p in suspicious_patterns if p.lower() in code_lower]
    
    if found_patterns:
        logger.warning(f"Suspicious patterns found in code: {found_patterns}")
        # Don't block, just warn
        return True, f"Warning: Code contains potentially unsafe operations: {', '.join(found_patterns)}"
    
    return True, None


def validate_github_url(url: str) -> tuple[bool, Optional[str]]:
    """
    Validate GitHub repository URL.
    
    Args:
        url: GitHub URL to validate
    
    Returns:
        (is_valid, error_message)
    """
    if not url or not url.strip():
        return False, "URL is empty"
    
    url = url.strip()
    
    # Check if it's a GitHub URL
    if not url.startswith('https://github.com/'):
        return False, "URL must be a GitHub repository (https://github.com/...)"
    
    # Check format
    parts = url.replace('https://github.com/', '').split('/')
    if len(parts) < 2:
        return False, "Invalid GitHub URL format. Expected: https://github.com/username/repository"
    
    return True, None


def safe_ai_call(
    func: Callable,
    fallback_response: str = "I'm having trouble processing this request right now.",
    max_retries: int = 2
) -> Any:
    """
    Safely call AI service with retries and fallback.
    
    Args:
        func: Function to call
        fallback_response: Response to return on failure
        max_retries: Maximum number of retries
    
    Returns:
        Function result or fallback response
    """
    for attempt in range(max_retries + 1):
        try:
            return func()
        except Exception as e:
            logger.warning(f"AI call attempt {attempt + 1} failed: {e}")
            
            if attempt < max_retries:
                continue
            else:
                logger.error(f"AI call failed after {max_retries + 1} attempts", exc_info=True)
                return fallback_response


def display_error(
    error_type: str,
    message: str,
    suggestions: Optional[list] = None,
    show_support: bool = True
):
    """
    Display user-friendly error message with suggestions.
    
    Args:
        error_type: Type of error (e.g., "File Upload Error")
        message: Error message
        suggestions: List of suggestions to fix the error
        show_support: Whether to show support information
    """
    st.error(f"**{error_type}**")
    st.write(message)
    
    if suggestions:
        st.markdown("**Try these solutions:**")
        for i, suggestion in enumerate(suggestions, 1):
            st.markdown(f"{i}. {suggestion}")
    
    if show_support:
        with st.expander("Need Help?"):
            st.markdown("""
            - Check the documentation
            - Verify your AWS credentials in .env file
            - Ensure you have a stable internet connection
            - Try refreshing the page
            """)


def log_error_context(
    error: Exception,
    context: Dict[str, Any],
    user_id: Optional[str] = None
):
    """
    Log error with context for debugging.
    
    Args:
        error: Exception that occurred
        context: Context information (file name, function, etc.)
        user_id: Optional user identifier
    """
    logger.error(
        f"Error occurred: {type(error).__name__}: {str(error)}",
        extra={
            'context': context,
            'user_id': user_id,
            'error_type': type(error).__name__
        },
        exc_info=True
    )


def graceful_degradation(
    primary_func: Callable,
    fallback_func: Callable,
    error_message: str = "Using simplified version due to technical issues"
) -> Any:
    """
    Try primary function, fall back to simpler version on failure.
    
    Args:
        primary_func: Primary function to try
        fallback_func: Fallback function if primary fails
        error_message: Message to show when falling back
    
    Returns:
        Result from primary or fallback function
    """
    try:
        return primary_func()
    except Exception as e:
        logger.warning(f"Primary function failed, using fallback: {e}")
        st.info(error_message)
        return fallback_func()


class ErrorRecovery:
    """Handles error recovery and retry logic."""
    
    @staticmethod
    def retry_with_backoff(
        func: Callable,
        max_attempts: int = 3,
        initial_delay: float = 1.0,
        backoff_factor: float = 2.0
    ) -> Any:
        """
        Retry function with exponential backoff.
        
        Args:
            func: Function to retry
            max_attempts: Maximum number of attempts
            initial_delay: Initial delay in seconds
            backoff_factor: Backoff multiplier
        
        Returns:
            Function result
        
        Raises:
            Last exception if all attempts fail
        """
        import time
        
        delay = initial_delay
        last_exception = None
        
        for attempt in range(max_attempts):
            try:
                return func()
            except Exception as e:
                last_exception = e
                logger.warning(f"Attempt {attempt + 1}/{max_attempts} failed: {e}")
                
                if attempt < max_attempts - 1:
                    time.sleep(delay)
                    delay *= backoff_factor
        
        raise last_exception
    
    @staticmethod
    def recover_session(session_manager) -> bool:
        """
        Attempt to recover corrupted session.
        
        Args:
            session_manager: SessionManager instance
        
        Returns:
            True if recovery successful
        """
        try:
            # Clear corrupted data
            if hasattr(st.session_state, 'current_analysis'):
                del st.session_state.current_analysis
            
            if hasattr(st.session_state, 'chat_history'):
                st.session_state.chat_history = []
            
            logger.info("Session recovered successfully")
            return True
        
        except Exception as e:
            logger.error(f"Session recovery failed: {e}")
            return False


def get_user_friendly_message(error: Exception, language: str = "english") -> str:
    """
    Get user-friendly error message in specified language.
    
    Args:
        error: Exception that occurred
        language: Language for message
    
    Returns:
        User-friendly error message
    """
    messages = {
        'english': {
            FileValidationError: "The file you uploaded couldn't be processed. Please check the file format and size.",
            AnalysisError: "We couldn't analyze your code. Please try again or upload a different file.",
            AIServiceError: "Our AI service is temporarily unavailable. Please try again in a moment.",
            RepositoryError: "We couldn't access the repository. Please check the URL and try again.",
            SessionError: "Your session encountered an issue. Please refresh the page.",
        },
        'hindi': {
            FileValidationError: "अपलोड की गई फ़ाइल को प्रोसेस नहीं किया जा सका। कृपया फ़ाइल प्रारूप और आकार जांचें।",
            AnalysisError: "हम आपके कोड का विश्लेषण नहीं कर सके। कृपया पुनः प्रयास करें या एक अलग फ़ाइल अपलोड करें।",
            AIServiceError: "हमारी AI सेवा अस्थायी रूप से अनुपलब्ध है। कृपया एक क्षण में पुनः प्रयास करें।",
            RepositoryError: "हम रिपॉजिटरी तक नहीं पहुंच सके। कृपया URL जांचें और पुनः प्रयास करें।",
            SessionError: "आपके सत्र में एक समस्या आई। कृपया पृष्ठ को रीफ्रेश करें।",
        },
        'telugu': {
            FileValidationError: "మీరు అప్‌లోడ్ చేసిన ফైল్ ప్రాసెస్ చేయలేకపోయాము. దయచేసి ఫైల్ ఫార్మాట్ మరియు సైజ్ తనిఖీ చేయండి.",
            AnalysisError: "మేము మీ కోడ్‌ను విశ్లేషించలేకపోయాము. దయచేసి మళ్లీ ప్రయత్నించండి లేదా వేరే ఫైల్ అప్‌లోడ్ చేయండి.",
            AIServiceError: "మా AI సేవ తాత్కాలికంగా అందుబాటులో లేదు. దయచేసి ఒక క్షణంలో మళ్లీ ప్రయత్నించండి.",
            RepositoryError: "మేము రిపోజిటరీని యాక్సెస్ చేయలేకపోయాము. దయచేసి URL తనిఖీ చేసి మళ్లీ ప్రయత్నించండి.",
            SessionError: "మీ సెషన్‌లో సమస్య ఎదురైంది. దయచేసి పేజీని రిఫ్రెష్ చేయండి.",
        }
    }
    
    error_type = type(error)
    language_messages = messages.get(language, messages['english'])
    
    return language_messages.get(error_type, str(error))
