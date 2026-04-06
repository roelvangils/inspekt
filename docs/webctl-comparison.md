# Things We (Inspekt) Could Learn or Reuse from Webctl

**Comparative Analysis Report**
**Date**: January 2026
**Author**: Claude Code Analysis

---

## Executive Summary

This report analyzes webctl's implementations across browser connection management, security practices, and architecture to identify improvements for Inspekt. The investigation reveals several key learnings:

**Top Findings:**

1. **Transport Layer Abstraction** [HIGH PRIORITY]: Webctl implements a clean transport abstraction supporting Unix sockets, TCP, and named pipes with automatic fallback [1]. Inspekt's hardcoded WebSocket-only approach limits deployment flexibility and debugging capabilities.

2. **Domain Policy Enforcement** [HIGH PRIORITY]: Webctl enforces domain restrictions at the navigation level with three policy modes (allow/deny/both) [2]. Inspekt's domain system is permission-based rather than enforcement-based, allowing execution on any domain once the browser connects.

3. **Accessibility-First Query Language** [MEDIUM PRIORITY]: Webctl's ARIA-based query DSL (`role=button name~="Submit"`) [3] provides stability across CSS refactors. Inspekt relies on CSS selectors which break more frequently.

4. **Sensitive Data Redaction** [MEDIUM PRIORITY]: Webctl implements comprehensive pattern-based redaction for passwords, API keys, credit cards, SSNs, and AWS credentials in output [4]. Inspekt has no equivalent protection.

5. **Daemon Architecture with Session Isolation** [MEDIUM PRIORITY]: Webctl's daemon model with per-session browser contexts and profile directories [5] provides better isolation than Inspekt's single shared browser connection model.

6. **Idle Timeout Management** [LOW PRIORITY]: Webctl's daemon auto-terminates after 15 minutes of inactivity [6], preventing resource leaks. Inspekt's server runs indefinitely.

**Recommendation**: Prioritize implementing transport abstraction and domain policy enforcement, as these address real security and deployment gaps in Inspekt.

---

## Section 1: Browser Connection

### 1.1 Overview of Webctl's Approach

Webctl uses a **daemon-based architecture** where a long-running server process manages browser instances via Playwright. The CLI communicates with the daemon through an IPC protocol.

**Key Implementation Details:**

| Component | File Reference | Description |
|-----------|----------------|-------------|
| Daemon Server | `src/webctl/daemon/server.py:29-148` [1] | Manages client connections, dispatches commands to handlers |
| Transport Abstraction | `src/webctl/protocol/transport.py:34-415` [7] | Abstract base classes for Unix socket, TCP, named pipe transports |
| Session Manager | `src/webctl/daemon/session_manager.py:76-128` [5] | Creates isolated browser contexts with persistent profiles |
| Event System | `src/webctl/daemon/event_emitter.py:15-69` [8] | Async pub/sub for real-time events (navigation, auth, page lifecycle) |

**Connection Lifecycle:**
```
1. CLI loads config → determines transport type
2. CLI attempts connect() → Unix socket (macOS/Linux) or TCP (Windows)
3. If daemon not running + auto_start=true → spawn daemon subprocess
4. Retry connection 50 times over 5 seconds [src/webctl/cli/app.py:94-102]
5. Send JSON-RPC request → receive streaming responses
6. Daemon tracks last_activity → auto-shutdown after idle_timeout
```

**Transport Selection Logic** (`transport.py:383-415` [7]):
```python
Windows → TCP always (127.0.0.1:port)
Linux/macOS → Unix socket primary, TCP fallback
Port = 49152 + (SHA256(session_id)[:8] % 16383)  # Deterministic
```

### 1.2 Overview of Inspekt's Current Approach

Inspekt uses a **WebSocket bridge architecture** where a userscript/extension in the browser connects to a local server.

**Key Implementation Details:**

| Component | File Reference | Description |
|-----------|----------------|-------------|
| WebSocket Server | `inspekt/bridge_ws.py:460-700` [9] | aiohttp WebSocket handler on port 8766 |
| HTTP Server | `inspekt/bridge_ws.py:2844-2856` [10] | HTTP API on port 8765 for CLI communication |
| Connection Tracking | `inspekt/bridge_ws.py:36-103` [11] | Sets tracking active connections, browser info |
| Long Polling | `inspekt/bridge_ws.py:849-896` [12] | HTTP `/result` endpoint polls for execution results |

**Connection Lifecycle:**
```
1. User installs browser extension/userscript
2. Extension connects WebSocket to ws://127.0.0.1:8766/ws
3. Server stores connection in active_connections set
4. CLI sends HTTP POST /run → server forwards to WebSocket
5. Browser executes JS → returns result via WebSocket
6. Server responds to CLI's long-polling /result request
```

### 1.3 Comparison Table: Browser Connection

| Aspect | Webctl | Inspekt | Winner |
|--------|--------|---------|--------|
| **Browser Control** | Direct via Playwright (spawns Chromium) | Indirect via extension (any browser) | Inspekt (flexibility) |
| **Transport Options** | Unix socket, TCP, Named pipe | WebSocket only | Webctl |
| **Fallback Mechanism** | Auto-fallback TCP if socket fails | None (fixed ports) | Webctl |
| **Session Isolation** | Per-session browser context + profile dir | Single shared connection | Webctl |
| **Auto-Start Daemon** | Yes, with 5s retry loop | Manual server start | Webctl |
| **Idle Management** | Auto-shutdown after 15min inactivity | Runs indefinitely | Webctl |
| **Reconnection** | Client retries 50x, deterministic port | 3s fixed delay, infinite retries | Webctl (deterministic) |
| **Connection Validation** | Transport-level connect() | `is_valid_browser_info()` check | Comparable |
| **Event Streaming** | Real-time via EventEmitter pub/sub | Polling + visibility events | Webctl |
| **Stale Detection** | Idle timeout only | Ghost (5s), Stale (45s), Idle (3600s) | Inspekt |

### 1.4 Actionable Recommendations

**[REC-CONN-1] ADOPT: Transport Layer Abstraction** (High Priority)
- Create abstract `Transport` base class in Inspekt
- Implement `WebSocketTransport` (current), `TCPTransport`, `UnixSocketTransport`
- Add `get_transport()` factory function with platform detection
- **Benefit**: Enables debugging via TCP, Unix socket for performance, future extensibility
- **Reference**: `webctl/protocol/transport.py:34-73` [7]

**[REC-CONN-2] ADOPT: Deterministic Port Generation** (Medium Priority)
- Use session ID hash for port calculation instead of fixed ports
- **Formula**: `port = 49152 + (SHA256(session_id)[:8] % 16383)`
- **Benefit**: Multiple inspekt instances can run simultaneously
- **Reference**: `webctl/protocol/transport.py:296-301` [7]

**[REC-CONN-3] ADAPT: Daemon Auto-Start** (Medium Priority)
- Inspekt CLI could auto-start `inspekt server` if not running
- Implement retry loop similar to webctl (50 attempts, 0.1s delay)
- **Benefit**: Better developer experience, no manual server management
- **Reference**: `webctl/cli/app.py:56-105` [13]

**[REC-CONN-4] ADOPT: Idle Timeout Auto-Shutdown** (Low Priority)
- Add configurable `idle_timeout` (default 15 minutes)
- Background task checks `last_activity` timestamp
- Shutdown daemon if no clients and idle exceeded
- **Benefit**: Prevents resource leaks from forgotten servers
- **Reference**: `webctl/daemon/server.py:150-160` [1]

**[REC-CONN-5] AVOID: Replacing WebSocket with Playwright**
- Inspekt's WebSocket bridge allows connecting to ANY browser
- Webctl only works with its spawned Chromium
- Inspekt's model better for testing existing sessions, authenticated states
- **Keep**: Current WebSocket architecture for browser flexibility

---

## Section 2: Security

### 2.1 Overview of Webctl's Approach

Webctl implements multiple security layers for domain control, sensitive data handling, and session isolation.

**Key Implementation Details:**

| Component | File Reference | Description |
|-----------|----------------|-------------|
| Domain Policy | `src/webctl/security/domain_policy.py:1-136` [2] | Allow/deny/both modes with glob patterns |
| Sensitive Redaction | `src/webctl/views/redaction.py:1-62` [4] | Pattern matching for passwords, tokens, cards |
| Auth Detection | `src/webctl/daemon/detectors/auth.py:1-100` [14] | SSO, OAuth, MFA, CAPTCHA detection |
| Session Isolation | `src/webctl/daemon/session_manager.py:44-59` [5] | Per-session browser context and profile |

**Domain Policy Enforcement** (`domain_policy.py:58-83` [2]):
```python
# Three policy modes:
"allow" → Whitelist only (block all except allowed)
"deny"  → Blacklist (allow all except denied)
"both"  → Allow list checked first, then deny list

# Pattern matching supports:
- Exact: "example.com"
- Wildcard: "*.example.com", "example.*"
- Default deny: "*.malware.*", "*.phishing.*"
```

**Sensitive Data Redaction** (`redaction.py:9-56` [4]):
```python
SENSITIVE_LABELS = r"password|secret|token|api_key|..."
PATTERNS = [
    r"\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}",  # Credit cards
    r"\d{3}-\d{2}-\d{4}",                      # SSN
    r"Bearer [A-Za-z0-9-_]+\.[A-Za-z0-9-_]+", # JWT
    r"AKIA[0-9A-Z]{16}",                       # AWS keys
]
```

### 2.2 Overview of Inspekt's Current Approach

Inspekt uses localhost binding and a domain permission system, but lacks enforcement-level controls.

**Key Implementation Details:**

| Component | File Reference | Description |
|-----------|----------------|-------------|
| Localhost Binding | `inspekt/bridge_ws.py:33` [15] | Hardcoded `HOST = "127.0.0.1"` |
| Domain Service | `inspekt/services/domain_service.py:23-98` [16] | SQLite-based allowlist with yolo mode |
| Input Validation | `inspekt/domain/models.py:21-198` [17] | Pydantic schema validation |
| Config Security | `inspekt/config.py:75-213` [18] | Plain JSON config with API keys |

**Domain Permission System** (`domain_service.py` [16]):
```python
# Permission-based (not enforcement):
add_domain("example.com")     # Add to allowlist
is_domain_allowed("...")      # Check permission
enable_yolo_mode(60)          # Bypass all checks for 60 minutes

# Key difference: Inspekt PROMPTS user, webctl BLOCKS navigation
```

### 2.3 Comparison Table: Security

| Aspect | Webctl | Inspekt | Winner |
|--------|--------|---------|--------|
| **Domain Control** | Enforcement (blocks navigation) | Permission (prompts user) | Webctl |
| **Policy Modes** | Allow/Deny/Both with globs | Simple allowlist | Webctl |
| **Default Deny Patterns** | `*.malware.*`, `*.phishing.*` | None | Webctl |
| **Sensitive Redaction** | Credit cards, SSN, JWT, AWS keys | None | Webctl |
| **Auth Detection** | SSO, OAuth, MFA, CAPTCHA | None | Webctl |
| **Session Isolation** | Per-session profiles | Single shared connection | Webctl |
| **Credential Storage** | Browser's storage (via Playwright) | Plain JSON config | Comparable |
| **Localhost Binding** | Yes (127.0.0.1) | Yes (127.0.0.1) | Tie |
| **Input Validation** | Pydantic + JSON-RPC | Pydantic models | Tie |
| **Yolo/Bypass Mode** | No | Yes (time-limited) | Inspekt (flexibility) |

### 2.4 Actionable Recommendations

**[REC-SEC-1] ADOPT: Domain Policy Enforcement** (High Priority)
- Add `DomainPolicy` class with allow/deny/both modes
- Check policy BEFORE executing JavaScript, not just prompting
- Return error if domain blocked: `{"error": "domain_blocked", "reason": "..."}`
- **Benefit**: Prevents accidental execution on malicious sites
- **Reference**: `webctl/security/domain_policy.py:58-83` [2]

**[REC-SEC-2] ADOPT: Sensitive Data Redaction** (High Priority)
- Create `redaction.py` service with pattern matching
- Apply to: CLI output, API responses, logs
- Patterns: credit cards, SSN, JWT, API keys, AWS credentials
- **Benefit**: Prevents accidental credential leakage in terminal output
- **Reference**: `webctl/views/redaction.py:9-56` [4]

**[REC-SEC-3] ADOPT: Default Deny Patterns** (Medium Priority)
- Add default blocklist: `*.malware.*`, `*.phishing.*`, known bad domains
- Make configurable but enabled by default
- **Benefit**: Basic protection against obvious malicious domains
- **Reference**: `webctl/security/domain_policy.py:28-33` [2]

**[REC-SEC-4] ADAPT: Auth/CAPTCHA Detection** (Medium Priority)
- Detect SSO providers (Microsoft, Google, Auth0, Okta)
- Detect CAPTCHA challenges (reCAPTCHA, hCaptcha, Cloudflare)
- Emit events or warnings when detected
- **Benefit**: Better user experience during automated flows
- **Reference**: `webctl/daemon/detectors/auth.py:1-100` [14]

**[REC-SEC-5] AVOID: Removing Yolo Mode**
- Inspekt's `yolo_mode` with time limits is useful for automation
- Webctl lacks this flexibility
- **Keep**: Time-limited bypass for trusted automation scenarios

**[REC-SEC-6] CONSIDER: Encrypted Config Storage** (Low Priority)
- Neither tool encrypts credentials in config files
- Could add optional encryption for API keys
- **Trade-off**: Complexity vs. security benefit for local-only tool

---

## Section 3: Architecture

### 3.1 Overview of Webctl's Approach

Webctl uses a **modular layered architecture** with clear separation between CLI, daemon, protocol, and views.

**Project Structure:**
```
src/webctl/
├── cli/                    # User interface (Typer)
│   └── app.py             # 1,095 lines - all CLI commands
├── daemon/                 # Long-running server
│   ├── server.py          # Main daemon loop
│   ├── session_manager.py # Browser lifecycle
│   ├── event_emitter.py   # Pub/sub events
│   ├── handlers/          # Command handlers (modular)
│   └── detectors/         # Auth, cookies, view changes
├── protocol/              # IPC communication
│   ├── messages.py        # Pydantic schemas
│   ├── transport.py       # Socket/TCP/pipe abstraction
│   └── client.py          # Daemon client
├── query/                 # Element query DSL
│   ├── grammar.py         # Lark grammar
│   ├── parser.py          # AST generation
│   └── resolver.py        # Query execution
├── views/                 # Output formatters
│   ├── a11y.py           # Accessibility tree
│   ├── redaction.py      # Sensitive data filtering
│   └── filters.py        # Output filtering
├── security/             # Security policies
│   └── domain_policy.py  # Domain allow/deny
├── config.py             # Configuration management
└── exceptions.py         # Custom exceptions
```

**Key Architectural Decisions:**

| Decision | Implementation | Reference |
|----------|----------------|-----------|
| CLI Framework | Typer (type-hint based) | `cli/app.py` [19] |
| Data Validation | Pydantic v2 strict mode | `protocol/messages.py` [20] |
| Query Language | Lark parser (grammar-based) | `query/grammar.py` [3] |
| Type Checking | MyPy strict mode | `pyproject.toml:73-77` [21] |
| Linting | Ruff with extensive rules | `pyproject.toml:60-71` [21] |
| Testing | Pytest with asyncio auto mode | `tests/test_smoke.py` [22] |

### 3.2 Overview of Inspekt's Current Approach

Inspekt uses a **4-layer hexagonal architecture** with explicit dependency rules.

**Project Structure:**
```
inspekt/
├── domain/               # Layer 0: Core models (no deps)
│   ├── models.py        # Pydantic schemas
│   └── recording.py     # Recording domain
├── adapters/            # Layer 1: External interfaces
│   └── filesystem.py    # Async file I/O
├── services/            # Layer 2: Business logic
│   ├── bridge_executor.py
│   ├── script_loader.py
│   ├── domain_service.py
│   ├── control_manager.py
│   ├── ai_integration.py
│   └── ai_providers/    # AI provider adapters
├── app/                 # Layer 3: User interfaces
│   ├── cli/            # Click-based CLI (37 modules)
│   ├── api/            # FastAPI HTTP server
│   └── mcp/            # Model Context Protocol
├── bridge_ws.py        # WebSocket/HTTP bridge server
├── client.py           # HTTP client library
└── config.py           # Configuration
```

**Dependency Rules:**
```
Layer 3 (app) → imports → Layer 2 (services)
Layer 2 (services) → imports → Layer 1 (adapters)
Layer 1 (adapters) → imports → Layer 0 (domain)
Layer 0 (domain) → imports → nothing (pure models)
```

### 3.3 Comparison Table: Architecture

| Aspect | Webctl | Inspekt | Winner |
|--------|--------|---------|--------|
| **Codebase Size** | ~1,100 lines Python | ~97,000 lines Python + ~34,000 JS | Webctl (simplicity) |
| **Architecture Pattern** | Modular layered | 4-layer hexagonal | Inspekt (clarity) |
| **CLI Framework** | Typer (type hints) | Click (decorators) | Tie |
| **HTTP Framework** | None (daemon only) | FastAPI | Inspekt (API access) |
| **Data Validation** | Pydantic v2 | Pydantic v2 | Tie |
| **Type Checking** | MyPy strict | MyPy | Webctl (stricter) |
| **Linting** | Ruff (extensive rules) | Ruff | Tie |
| **Query Language** | Custom DSL (ARIA-based) | CSS selectors + JS | Webctl (stability) |
| **Test Coverage** | Smoke tests only | Unit + Integration + E2E | Inspekt |
| **CI/CD** | GitHub Actions (lint, test, build) | GitHub Actions (lint, type, test) | Tie |
| **Documentation** | README only | PROTOCOL.md, ARCHITECTURE.md, SECURITY.md | Inspekt |
| **Entry Points** | 2 (webctl, webctld) | 1 (inspekt) | Comparable |

### 3.4 Actionable Recommendations

**[REC-ARCH-1] ADOPT: ARIA-Based Query Language** (Medium Priority)
- Create `query/` module with Lark grammar for accessibility queries
- Support: `role=button`, `name="Submit"`, `name~="partial"`, `within()`
- **Benefit**: Queries stable across CSS refactors, better accessibility
- **Reference**: `webctl/query/grammar.py`, `webctl/query/parser.py` [3]

**[REC-ARCH-2] ADOPT: MyPy Strict Mode** (Medium Priority)
- Enable `strict = true` in mypy configuration
- Add `warn_return_any = true`, `warn_unused_configs = true`
- **Benefit**: Catches more type errors at development time
- **Reference**: `webctl/pyproject.toml:73-77` [21]

**[REC-ARCH-3] ADOPT: Handler Registry Pattern** (Low Priority)
- Webctl uses `handlers/registry.py` for command dispatch
- Each handler is a separate module with consistent interface
- **Benefit**: Easier to add new commands, better testability
- **Reference**: `webctl/daemon/handlers/` [23]

**[REC-ARCH-4] ADOPT: Event Emitter Pattern** (Low Priority)
- Create pub/sub event system for real-time notifications
- Events: navigation, page lifecycle, auth detection
- **Benefit**: Decouples event producers from consumers
- **Reference**: `webctl/daemon/event_emitter.py:15-69` [8]

**[REC-ARCH-5] AVOID: Reducing to Single CLI File**
- Webctl has all commands in single 1,095-line `app.py`
- Inspekt's 37 CLI modules provide better organization
- **Keep**: Current modular CLI structure

**[REC-ARCH-6] AVOID: Removing HTTP API**
- Webctl is daemon-only (IPC communication)
- Inspekt's FastAPI server enables external integrations
- **Keep**: HTTP API for flexibility

---

## Appendix A: Inspected Files

### Webctl Repository (`/Users/roelvangils/Repos/webctl`)

| File | Lines | Purpose |
|------|-------|---------|
| `src/webctl/daemon/server.py` | ~160 | Main daemon server |
| `src/webctl/daemon/session_manager.py` | ~391 | Browser session lifecycle |
| `src/webctl/daemon/event_emitter.py` | ~134 | Async event pub/sub |
| `src/webctl/daemon/handlers/navigation.py` | ~80 | Navigate command |
| `src/webctl/daemon/handlers/interact.py` | ~200 | Click/type commands |
| `src/webctl/daemon/handlers/observe.py` | ~150 | Snapshot/query commands |
| `src/webctl/daemon/detectors/auth.py` | ~100 | Auth/CAPTCHA detection |
| `src/webctl/protocol/transport.py` | ~415 | Transport abstraction |
| `src/webctl/protocol/messages.py` | ~134 | Message schemas |
| `src/webctl/protocol/client.py` | ~76 | Daemon client |
| `src/webctl/query/grammar.py` | ~50 | Lark query grammar |
| `src/webctl/query/parser.py` | ~80 | Query parser |
| `src/webctl/query/resolver.py` | ~150 | Query execution |
| `src/webctl/views/redaction.py` | ~62 | Sensitive data redaction |
| `src/webctl/views/a11y.py` | ~200 | Accessibility tree output |
| `src/webctl/security/domain_policy.py` | ~136 | Domain allow/deny |
| `src/webctl/cli/app.py` | ~1,095 | CLI commands |
| `src/webctl/config.py` | ~154 | Configuration |
| `src/webctl/exceptions.py` | ~120 | Custom exceptions |
| `pyproject.toml` | ~82 | Project metadata |
| `tests/test_smoke.py` | ~274 | Integration tests |
| `.github/workflows/ci.yml` | ~92 | CI configuration |
| `.github/workflows/publish.yml` | ~30 | PyPI publishing |

### Inspekt Repository (`/Users/roelvangils/Repos/inspekt`)

| File | Lines | Purpose |
|------|-------|---------|
| `inspekt/bridge_ws.py` | ~2,879 | WebSocket/HTTP bridge |
| `inspekt/client.py` | ~25,446 | HTTP client library |
| `inspekt/domain/models.py` | ~398 | Pydantic models |
| `inspekt/domain/recording.py` | ~12,619 | Recording domain |
| `inspekt/services/bridge_executor.py` | ~263 | Execution service |
| `inspekt/services/script_loader.py` | ~207 | Script caching |
| `inspekt/services/domain_service.py` | ~180 | Domain permissions |
| `inspekt/services/control_manager.py` | ~230 | Control mode state |
| `inspekt/services/ai_integration.py` | ~367 | AI provider integration |
| `inspekt/adapters/filesystem.py` | ~176 | Async file I/O |
| `inspekt/app/api/server.py` | ~100 | FastAPI server |
| `inspekt/app/mcp/server.py` | ~17,402 | MCP server |
| `inspekt/config.py` | ~243 | Configuration |
| `pyproject.toml` | ~194 | Project metadata |
| `tests/unit/test_models.py` | ~253 | Model tests |
| `tests/unit/test_bridge_executor.py` | ~566 | Executor tests |
| `tests/conftest.py` | ~46 | Pytest configuration |
| `.github/workflows/ci.yml` | ~145 | CI configuration |
| `PROTOCOL.md` | ~778 | Protocol specification |
| `ARCHITECTURE.md` | ~91KB | Architecture docs |
| `SECURITY.md` | ~21KB | Security policy |

---

## Appendix B: Assumptions

1. **Read-only access**: Analysis based on file contents at time of exploration; no runtime testing performed.

2. **Version currency**: Webctl v0.1.2, Inspekt v1.0.0 analyzed. Findings may not apply to future versions.

3. **Named pipe implementation**: Webctl's Windows named pipe transport (`transport.py:109-162`) appears to be a stub; TCP fallback is used in practice.

4. **Inspekt domain enforcement**: Assumed domain service prompts user rather than blocks, based on code structure. Runtime behavior may differ.

5. **Test coverage metrics**: Inspekt claims 97%+ coverage in documentation; not independently verified.

6. **CI/CD equivalence**: Both projects use GitHub Actions with similar patterns; detailed workflow comparison not performed.

---

## References

[1] `webctl/src/webctl/daemon/server.py:29-160`
[2] `webctl/src/webctl/security/domain_policy.py:1-136`
[3] `webctl/src/webctl/query/grammar.py`, `parser.py`, `resolver.py`
[4] `webctl/src/webctl/views/redaction.py:1-62`
[5] `webctl/src/webctl/daemon/session_manager.py:44-128`
[6] `webctl/src/webctl/daemon/server.py:150-160`
[7] `webctl/src/webctl/protocol/transport.py:34-415`
[8] `webctl/src/webctl/daemon/event_emitter.py:15-69`
[9] `inspekt/inspekt/bridge_ws.py:460-700`
[10] `inspekt/inspekt/bridge_ws.py:2844-2856`
[11] `inspekt/inspekt/bridge_ws.py:36-103`
[12] `inspekt/inspekt/bridge_ws.py:849-896`
[13] `webctl/src/webctl/cli/app.py:56-105`
[14] `webctl/src/webctl/daemon/detectors/auth.py:1-100`
[15] `inspekt/inspekt/bridge_ws.py:33`
[16] `inspekt/inspekt/services/domain_service.py:23-98`
[17] `inspekt/inspekt/domain/models.py:21-198`
[18] `inspekt/inspekt/config.py:75-213`
[19] `webctl/src/webctl/cli/app.py`
[20] `webctl/src/webctl/protocol/messages.py`
[21] `webctl/pyproject.toml:60-77`
[22] `webctl/tests/test_smoke.py`
[23] `webctl/src/webctl/daemon/handlers/`

---

## Summary of Recommendations

### High Priority
| ID | Recommendation | Effort | Impact |
|----|----------------|--------|--------|
| REC-CONN-1 | Transport layer abstraction | High | High |
| REC-SEC-1 | Domain policy enforcement | Medium | High |
| REC-SEC-2 | Sensitive data redaction | Low | High |

### Medium Priority
| ID | Recommendation | Effort | Impact |
|----|----------------|--------|--------|
| REC-CONN-2 | Deterministic port generation | Low | Medium |
| REC-CONN-3 | Daemon auto-start | Medium | Medium |
| REC-SEC-3 | Default deny patterns | Low | Medium |
| REC-SEC-4 | Auth/CAPTCHA detection | Medium | Medium |
| REC-ARCH-1 | ARIA-based query language | High | Medium |
| REC-ARCH-2 | MyPy strict mode | Low | Medium |

### Low Priority
| ID | Recommendation | Effort | Impact |
|----|----------------|--------|--------|
| REC-CONN-4 | Idle timeout auto-shutdown | Low | Low |
| REC-ARCH-3 | Handler registry pattern | Medium | Low |
| REC-ARCH-4 | Event emitter pattern | Medium | Low |

### Avoid/Keep Current
| ID | Recommendation | Reason |
|----|----------------|--------|
| REC-CONN-5 | Keep WebSocket architecture | Browser flexibility |
| REC-SEC-5 | Keep Yolo mode | Automation flexibility |
| REC-ARCH-5 | Keep modular CLI | Better organization |
| REC-ARCH-6 | Keep HTTP API | External integrations |
