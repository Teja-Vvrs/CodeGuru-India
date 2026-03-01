# Security Guide - CodeGuru India

## Overview

CodeGuru India implements comprehensive security measures to protect user data and prevent malicious code execution. This guide documents all security features and best practices.

## Security Features

### 1. Input Sanitization

All user inputs are sanitized to prevent injection attacks:

#### Text Input Sanitization
- **SQL Injection Protection**: Detects and warns about SQL injection patterns
- **XSS Protection**: Identifies and blocks cross-site scripting attempts
- **Command Injection Protection**: Prevents shell command injection
- **Path Traversal Protection**: Blocks directory traversal attempts

```python
from utils.security import sanitize_user_input

# Sanitize text input
is_valid, error, sanitized, warnings = sanitize_user_input(
    user_text,
    input_type='text',
    max_length=10000
)
```

#### URL Sanitization
- **HTTPS Enforcement**: Only HTTPS URLs are allowed
- **Protocol Validation**: Blocks javascript:, data:, file: protocols
- **Format Validation**: Validates GitHub URL format

```python
# Sanitize URL input
is_valid, error, sanitized_url, warnings = sanitize_user_input(
    github_url,
    input_type='url'
)
```

#### Code Sanitization
- **Dangerous Pattern Detection**: Identifies potentially dangerous operations
- **Null Byte Removal**: Removes null bytes from code
- **Length Validation**: Enforces maximum code length

```python
# Sanitize code input
is_valid, error, sanitized_code, warnings = sanitize_user_input(
    code_content,
    input_type='code',
    max_length=1000000
)
```

### 2. File Upload Validation

Comprehensive file upload security:

#### File Type Validation
- **Extension Whitelist**: Only allowed extensions (.py, .js, .java, etc.)
- **Blocked Extensions**: Executable files (.exe, .dll, .sh, etc.) are blocked
- **Magic Number Check**: Validates file signatures to prevent spoofing

#### File Content Validation
- **Size Limits**: Maximum 10MB per file
- **Empty File Detection**: Rejects empty files
- **Binary Content Detection**: Validates text files contain valid UTF-8
- **Malicious Pattern Detection**: Scans for embedded malicious content
- **Obfuscation Detection**: Uses entropy analysis to detect obfuscated code

```python
from utils.security import validate_and_sanitize_file

# Validate file upload
is_valid, error, warnings = validate_and_sanitize_file(
    uploaded_file,
    max_size_mb=10,
    allowed_extensions=['.py', '.js', '.java']
)
```

### 3. Memory-Only Processing

Code is processed in-memory only without persistent storage:

#### Enforcement
- **No Disk Persistence**: Code is never written to disk (except temporary repo clones)
- **Session State Only**: Code stored in Streamlit session state
- **Automatic Cleanup**: Session data cleared when session ends
- **Memory Monitoring**: Tracks memory usage for security auditing

```python
from utils.security import ensure_memory_only_processing

# Validate memory-only processing
if not ensure_memory_only_processing():
    st.error("Security validation failed: Code persistence detected")
```

#### Memory Management
- **Clear on Exit**: Code cleared from memory when user navigates away
- **Size Monitoring**: Alerts when memory usage exceeds thresholds
- **Audit Logging**: Memory usage logged for security review

### 4. HTTPS Configuration

Secure connection settings enforced via Streamlit configuration:

#### Server Settings
```toml
[server]
enableCORS = false
enableXsrfProtection = true
maxUploadSize = 10
enableWebsocketCompression = true
```

#### Browser Settings
```toml
[browser]
gatherUsageStats = false
```

#### Runner Settings
```toml
[runner]
enforceSerializableSessionState = true
```

### 5. Security Auditing

All security events are logged and audited:

#### Audit Events
- **File Uploads**: Logs all file upload attempts with validation results
- **Input Sanitization**: Logs warnings and blocked inputs
- **Memory Usage**: Monitors and logs memory consumption
- **Security Violations**: Logs all security policy violations

```python
from utils.security import SecurityAuditor

# Generate security report
report = SecurityAuditor.generate_security_report()
```

## Security Best Practices

### For Developers

1. **Always Sanitize Inputs**
   - Use `sanitize_user_input()` for all user-provided text
   - Validate file uploads with `validate_and_sanitize_file()`
   - Never trust user input

2. **Validate Before Processing**
   - Check validation results before using sanitized content
   - Display warnings to users when suspicious patterns detected
   - Log all validation failures

3. **Memory-Only Processing**
   - Store code in session state only
   - Never write user code to disk
   - Clear session data when done

4. **Error Handling**
   - Use try-except blocks around file operations
   - Provide user-friendly error messages
   - Log detailed errors for debugging

### For Deployment

1. **HTTPS Enforcement**
   - Configure reverse proxy (nginx, Apache) for HTTPS
   - Use valid SSL certificates
   - Redirect HTTP to HTTPS

2. **Environment Variables**
   - Store sensitive credentials in `.env` file
   - Never commit `.env` to version control
   - Use strong AWS credentials

3. **Access Control**
   - Implement authentication if deploying publicly
   - Use AWS IAM roles with minimal permissions
   - Rotate credentials regularly

4. **Monitoring**
   - Monitor security audit logs
   - Set up alerts for suspicious activity
   - Review memory usage patterns

## Security Checklist

### Pre-Deployment
- [ ] All inputs sanitized
- [ ] File upload validation enabled
- [ ] Memory-only processing verified
- [ ] HTTPS configured
- [ ] Security audit logging enabled
- [ ] AWS credentials secured
- [ ] Error messages don't leak sensitive info
- [ ] Session timeout configured

### Post-Deployment
- [ ] Monitor security logs
- [ ] Review audit reports
- [ ] Check for security updates
- [ ] Test security measures
- [ ] Verify HTTPS working
- [ ] Monitor memory usage
- [ ] Review access patterns

## Threat Model

### Threats Mitigated

1. **Code Injection**
   - SQL injection blocked by input sanitization
   - Command injection prevented by pattern detection
   - XSS attacks blocked by HTML sanitization

2. **Malicious File Upload**
   - Executable files blocked
   - File content validated
   - Obfuscated code detected

3. **Data Leakage**
   - Code not persisted to disk
   - Session data cleared on exit
   - No external data transmission (except AWS Bedrock)

4. **Man-in-the-Middle**
   - HTTPS enforcement
   - XSRF protection enabled
   - Secure cookie settings

### Residual Risks

1. **AWS Bedrock Security**
   - Code sent to AWS Bedrock for analysis
   - Relies on AWS security measures
   - Mitigation: Use AWS IAM policies

2. **Client-Side Security**
   - Browser security depends on user
   - Session hijacking possible if user compromised
   - Mitigation: Use secure connections, session timeouts

3. **Denial of Service**
   - Large file uploads could consume resources
   - Mitigation: File size limits, rate limiting

## Incident Response

### If Security Issue Detected

1. **Immediate Actions**
   - Stop the application
   - Review security logs
   - Identify affected users
   - Clear all session data

2. **Investigation**
   - Analyze audit logs
   - Identify attack vector
   - Assess damage
   - Document findings

3. **Remediation**
   - Patch vulnerability
   - Update security measures
   - Test fixes
   - Deploy updates

4. **Communication**
   - Notify affected users
   - Document incident
   - Update security documentation
   - Review security policies

## Security Updates

### Keeping Secure

1. **Regular Updates**
   - Update dependencies regularly
   - Monitor security advisories
   - Apply security patches promptly

2. **Security Testing**
   - Run security tests regularly
   - Perform penetration testing
   - Review code for vulnerabilities

3. **Continuous Improvement**
   - Review security logs
   - Update threat model
   - Enhance security measures
   - Train team on security

## Contact

For security issues or questions:
- Review security logs in application
- Check audit reports
- Consult security documentation

## References

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Streamlit Security](https://docs.streamlit.io/library/advanced-features/configuration)
- [AWS Security Best Practices](https://aws.amazon.com/security/best-practices/)
