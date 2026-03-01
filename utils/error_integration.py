"""
Error handling integration for all CodeGuru India components.

This module provides comprehensive error handling wrappers and utilities
for integrating error handling across the entire application.
"""

import logging
import streamlit as st
from functools import wraps
from typing import Optional, Callable, Any, Dict
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
    display_error,
    log_error_context,
    graceful_degradation,
    ErrorRecovery,
    get_user_friendly_message
)

logger = logging.getLogger(__name__)


def safe_file_analysis(func: Callable) -> Callable:
    """
    Decorator for safe file analysis operations.
    
    Handles file validation errors and analysis failures gracefully.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except FileValidationError as e:
            language = st.session_state.get('selected_language', 'english')
            message = get_user_friendly_message(e, language)
            display_error(
                "File Validation Error",
                message,
                suggestions=[
                    "Check that your file is under 10MB",
                    "Ensure the file has a supported extension (.py, .js, .ts, etc.)",
                    "Verify the file is not corrupted"
                ]
            )
            return None
        except AnalysisError as e:
            language = st.session_state.get('selected_language', 'english')
            message = get_user_friendly_message(e, language)
            display_error(
                "Analysis Error",
                message,
                suggestions=[
                    "Try uploading a different file",
                    "Check if the code has syntax errors",
                    "Simplify the code and try again"
                ]
            )
            return None
        except Exception as e:
            logger.error(f"Unexpected error in file analysis: {e}", exc_info=True)
            display_error(
                "Unexpected Error",
                "An unexpected error occurred during file analysis",
                suggestions=[
                    "Try refreshing the page",
                    "Upload a different file",
                    "Check your internet connection"
                ]
            )
            return None
    return wrapper


def safe_repository_operation(func: Callable) -> Callable:
    """
    Decorator for safe repository operations.
    
    Handles repository cloning, validation, and analysis errors.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except RepositoryError as e:
            language = st.session_state.get('selected_language', 'english')
            message = get_user_friendly_message(e, language)
            display_error(
                "Repository Error",
                message,
                suggestions=[
                    "Verify the GitHub URL is correct",
                    "Check if the repository is public",
                    "Ensure you have internet connectivity",
                    "Try a smaller repository (under 100MB)"
                ]
            )
            return None
        except Exception as e:
            logger.error(f"Unexpected error in repository operation: {e}", exc_info=True)
            display_error(
                "Repository Operation Failed",
                "Failed to process the repository",
                suggestions=[
                    "Check the repository URL",
                    "Try a different repository",
                    "Ensure the repository is accessible"
                ]
            )
            return None
    return wrapper


def safe_ai_operation(fallback_message: str = "AI service temporarily unavailable") -> Callable:
    """
    Decorator for safe AI/LLM operations.
    
    Handles AWS Bedrock failures with fallback responses.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except AIServiceError as e:
                language = st.session_state.get('selected_language', 'english')
                message = get_user_friendly_message(e, language)
                st.warning(message)
                logger.warning(f"AI service error: {e}")
                return fallback_message
            except Exception as e:
                logger.error(f"Unexpected error in AI operation: {e}", exc_info=True)
                st.warning("AI service encountered an issue. Using fallback response.")
                return fallback_message
        return wrapper
    return decorator


def safe_diagram_generation(func: Callable) -> Callable:
    """
    Decorator for safe diagram generation.
    
    Falls back to text representation if diagram generation fails.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.warning(f"Diagram generation failed: {e}")
            st.info("Diagram generation unavailable. Showing text representation instead.")
            
            # Return a simple text fallback
            return """
```
Diagram generation is temporarily unavailable.
The code structure is displayed in text format above.
```
"""
    return wrapper


def safe_session_operation(func: Callable) -> Callable:
    """
    Decorator for safe session management operations.
    
    Handles session corruption and recovery.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except SessionError as e:
            language = st.session_state.get('selected_language', 'english')
            message = get_user_friendly_message(e, language)
            st.warning(message)
            
            # Attempt session recovery
            session_manager = args[0] if args else None
            if session_manager and ErrorRecovery.recover_session(session_manager):
                st.success("Session recovered successfully")
            else:
                st.error("Please refresh the page to start a new session")
            
            return None
        except Exception as e:
            logger.error(f"Unexpected error in session operation: {e}", exc_info=True)
            st.error("Session error occurred. Please refresh the page.")
            return None
    return wrapper


def validate_and_process_file(
    uploaded_file,
    max_size_mb: int = 10,
    allowed_extensions: Optional[list] = None
) -> tuple[bool, Optional[str], Optional[str]]:
    """
    Validate and process uploaded file with comprehensive error handling.
    
    Args:
        uploaded_file: Streamlit uploaded file object
        max_size_mb: Maximum file size in MB
        allowed_extensions: List of allowed file extensions
    
    Returns:
        (success, file_content, error_message)
    """
    try:
        # Validate file upload
        is_valid, error_msg = validate_file_upload(
            uploaded_file,
            max_size_mb=max_size_mb,
            allowed_extensions=allowed_extensions
        )
        
        if not is_valid:
            return False, None, error_msg
        
        # Read file content
        try:
            file_content = uploaded_file.getvalue().decode('utf-8', errors='ignore')
        except Exception as e:
            logger.error(f"Failed to decode file: {e}")
            return False, None, "Failed to read file content. File may be corrupted."
        
        # Validate code content
        is_valid_code, warning_msg = validate_code_content(file_content)
        
        if not is_valid_code:
            return False, None, warning_msg
        
        # Return success with optional warning
        return True, file_content, warning_msg
    
    except Exception as e:
        logger.error(f"File validation failed: {e}", exc_info=True)
        return False, None, "Failed to validate file. Please try again."


def validate_and_process_github_url(url: str) -> tuple[bool, Optional[str]]:
    """
    Validate GitHub URL with comprehensive error handling.
    
    Args:
        url: GitHub repository URL
    
    Returns:
        (is_valid, error_message)
    """
    try:
        is_valid, error_msg = validate_github_url(url)
        return is_valid, error_msg
    except Exception as e:
        logger.error(f"URL validation failed: {e}", exc_info=True)
        return False, "Failed to validate URL. Please check the format."


def safe_bedrock_call(
    bedrock_client,
    prompt: str,
    fallback_response: str = "AI service temporarily unavailable",
    max_retries: int = 2
) -> str:
    """
    Safely call AWS Bedrock with retry logic and fallback.
    
    Args:
        bedrock_client: BedrockClient instance
        prompt: Input prompt
        fallback_response: Response to return on failure
        max_retries: Maximum number of retries
    
    Returns:
        Model response or fallback
    """
    def call_bedrock():
        return bedrock_client.invoke_model(prompt)
    
    try:
        return safe_ai_call(call_bedrock, fallback_response, max_retries)
    except Exception as e:
        logger.error(f"Bedrock call failed: {e}", exc_info=True)
        return fallback_response


def handle_analysis_error(
    error: Exception,
    context: Dict[str, Any],
    language: str = "english"
) -> None:
    """
    Handle analysis errors with user-friendly messages.
    
    Args:
        error: Exception that occurred
        context: Context information for logging
        language: User's selected language
    """
    # Log error with context
    log_error_context(error, context)
    
    # Get user-friendly message
    message = get_user_friendly_message(error, language)
    
    # Display appropriate error
    if isinstance(error, FileValidationError):
        display_error(
            "File Validation Error",
            message,
            suggestions=[
                "Check file size and format",
                "Ensure file is not corrupted",
                "Try a different file"
            ]
        )
    elif isinstance(error, AnalysisError):
        display_error(
            "Analysis Error",
            message,
            suggestions=[
                "Check if code has syntax errors",
                "Try simplifying the code",
                "Upload a different file"
            ]
        )
    elif isinstance(error, AIServiceError):
        display_error(
            "AI Service Error",
            message,
            suggestions=[
                "Check your AWS credentials",
                "Verify internet connection",
                "Try again in a moment"
            ]
        )
    elif isinstance(error, RepositoryError):
        display_error(
            "Repository Error",
            message,
            suggestions=[
                "Verify the repository URL",
                "Check if repository is public",
                "Try a smaller repository"
            ]
        )
    else:
        display_error(
            "Unexpected Error",
            "An unexpected error occurred",
            suggestions=[
                "Try refreshing the page",
                "Check your internet connection",
                "Try again later"
            ]
        )


def with_graceful_degradation(
    primary_func: Callable,
    fallback_func: Callable,
    error_message: str = "Using simplified version"
) -> Any:
    """
    Execute function with graceful degradation.
    
    Args:
        primary_func: Primary function to try
        fallback_func: Fallback function if primary fails
        error_message: Message to show when falling back
    
    Returns:
        Result from primary or fallback function
    """
    return graceful_degradation(primary_func, fallback_func, error_message)


def retry_with_exponential_backoff(
    func: Callable,
    max_attempts: int = 3,
    initial_delay: float = 1.0
) -> Any:
    """
    Retry function with exponential backoff.
    
    Args:
        func: Function to retry
        max_attempts: Maximum number of attempts
        initial_delay: Initial delay in seconds
    
    Returns:
        Function result
    
    Raises:
        Last exception if all attempts fail
    """
    return ErrorRecovery.retry_with_backoff(
        func,
        max_attempts=max_attempts,
        initial_delay=initial_delay
    )


# Multi-language error messages
ERROR_MESSAGES = {
    'english': {
        'file_too_large': "File is too large. Maximum size is {max_size}MB.",
        'invalid_format': "Invalid file format. Supported formats: {formats}",
        'analysis_failed': "Code analysis failed. Please try again.",
        'ai_unavailable': "AI service is temporarily unavailable.",
        'repo_not_found': "Repository not found or inaccessible.",
        'session_expired': "Your session has expired. Please refresh the page.",
    },
    'hindi': {
        'file_too_large': "फ़ाइल बहुत बड़ी है। अधिकतम आकार {max_size}MB है।",
        'invalid_format': "अमान्य फ़ाइल प्रारूप। समर्थित प्रारूप: {formats}",
        'analysis_failed': "कोड विश्लेषण विफल रहा। कृपया पुनः प्रयास करें।",
        'ai_unavailable': "AI सेवा अस्थायी रूप से अनुपलब्ध है।",
        'repo_not_found': "रिपॉजिटरी नहीं मिली या पहुंच योग्य नहीं है।",
        'session_expired': "आपका सत्र समाप्त हो गया है। कृपया पृष्ठ को रीफ्रेश करें।",
    },
    'telugu': {
        'file_too_large': "ఫైల్ చాలా పెద్దది. గరిష్ట పరిమాణం {max_size}MB.",
        'invalid_format': "చెల్లని ఫైల్ ఫార్మాట్. మద్దతు ఉన్న ఫార్మాట్‌లు: {formats}",
        'analysis_failed': "కోడ్ విశ్లేషణ విఫలమైంది. దయచేసి మళ్లీ ప్రయత్నించండి.",
        'ai_unavailable': "AI సేవ తాత్కాలికంగా అందుబాటులో లేదు.",
        'repo_not_found': "రిపోజిటరీ కనుగొనబడలేదు లేదా యాక్సెస్ చేయలేము.",
        'session_expired': "మీ సెషన్ గడువు ముగిసింది. దయచేసి పేజీని రిఫ్రెష్ చేయండి.",
    }
}


def get_localized_error_message(
    message_key: str,
    language: str = "english",
    **kwargs
) -> str:
    """
    Get localized error message.
    
    Args:
        message_key: Key for the error message
        language: User's selected language
        **kwargs: Format parameters for the message
    
    Returns:
        Localized error message
    """
    messages = ERROR_MESSAGES.get(language, ERROR_MESSAGES['english'])
    message = messages.get(message_key, message_key)
    
    try:
        return message.format(**kwargs)
    except KeyError:
        return message
