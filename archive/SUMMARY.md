# Inspekt - Project Summary

**Version**: 1.0.0 (current) → 2.0.0 (refactor target)
**Status**: Deep code review complete, refactor plan ready
**Last Updated**: 2025-10-27

---

## What is Inspekt?

Inspekt is a command-line tool that executes JavaScript in your browser from the terminal. It uses a WebSocket-based architecture to create a bidirectional communication channel between a CLI, a local server, and a Tampermonkey userscript running in the browser.

**Core Value Proposition**:
- Execute arbitrary JavaScript from terminal
- Extract data from web pages (links, articles, structure, metadata)
- Control browser with keyboard navigation (virtual focus mode)
- Monitor browser events (keyboard, DOM changes)
- Integrate browser automation into shell scripts and workflows

---

## Current State Assessment

### Architecture Overview

```
┌─────────────────┐
│   USER TERMINAL │
│   (inspekt CLI)     │
└────────┬────────┘
         │ HTTP POST /run
         ▼
┌─────────────────────────┐
│  WEBSOCKET SERVER       │
│  (aiohttp, asyncio)     │
│  - HTTP: :8765          │
│  - WS:   :8766          │
└────────┬────────────────┘
         │ WebSocket (ws://127.0.0.1:8766/ws)
         ▼
┌─────────────────────────┐
│  BROWSER RUNTIME        │
│  (Tampermonkey script)  │
│  - Connects on page load│
│  - Auto-reconnects      │
│  - Executes JS code     │
└────────┬────────────────┘
         │ Direct execution
         ▼
┌─────────────────────────┐
│  WEB PAGE / DOM         │
│  - JavaScript execution │
│  - Element interaction  │
│  - Data extraction      │
└─────────────────────────┘
```

### Codebase Metrics

| Metric | Value | Assessment |
|--------|-------|------------|
| **Total Python LOC** | ~4,807 | Medium-sized project |
| **Largest file** | cli.py (3,946 lines) | 🔴 **Critical issue** |
| **Number of CLI commands** | 33+ | Rich feature set |
| **JavaScript scripts** | 25 files (~3,700 LOC) | Well-organized |
| **Test coverage** | 0% | 🔴 **Critical issue** |
| **Type coverage** | ~5% (26 hints total) | 🔴 **Critical issue** |
| **Dependencies** | click, requests, aiohttp | Minimal, good |
| **Circular imports** | 0 | ✅ **Good** |
| **CI/CD** | None | 🟡 **Missing** |
| **Documentation** | README.md only | 🟡 **Incomplete** |

### Module Structure

```
zen_bridge/
├── zen/
│   ├── __init__.py         (110 lines)   - Package metadata
│   ├── cli.py              (3,946 lines) - 🔴 Monolithic CLI
│   ├── bridge_ws.py        (396 lines)   - WebSocket server
│   ├── client.py           (250 lines)   - HTTP client wrapper
│   ├── config.py           (213 lines)   - Config management
│   ├── scripts/            (25 JS files) - Extraction/control scripts
│   └── templates/          (empty)       - Future use
├── userscript_ws.js        (WebSocket client for browser)
├── setup.py                (Legacy packaging)
├── README.md               (User documentation)
└── tests/                  (🔴 Does not exist)
```

---

## Key Risks Identified

### 🔴 CRITICAL Risks (Must Address)

#### 1. Zero Test Coverage
**Risk**: Any refactoring or change could introduce regressions
**Impact**: High - affects all features
**Current State**: No test infrastructure exists
**Mitigation Plan**:
- Phase 0: Set up pytest, create smoke tests
- Phase 1: Add unit tests for pure functions (config, models)
- Phase 2: Add integration tests (server, client)
- Phase 3: Add E2E tests (Playwright browser tests)
- **Target**: ≥80% coverage on critical paths

#### 2. Monolithic CLI Module (3,946 lines)
**Risk**: Extremely difficult to maintain, test, and understand
**Impact**: High - central to all operations
**Current State**: Single file with 55+ functions, all CLI commands in one place
**Mitigation Plan**:
- Phase 2: Split into command groups (eval, extract, control, server, etc.)
- Target: No file >400 lines
- Enforce with code review + ruff rules

#### 3. No Type Safety
**Risk**: Runtime errors, poor IDE support, hard to refactor safely
**Impact**: High - affects developer experience and reliability
**Current State**: Only 26 type hints across entire codebase, no return types
**Mitigation Plan**:
- Phase 1: Add comprehensive type hints (100% coverage)
- Enable mypy --strict
- Use Pydantic for all data validation (config, WebSocket messages)

#### 4. Blocking I/O in Async Context
**Risk**: Event loop stalls, WebSocket server becomes unresponsive
**Impact**: High - affects real-time performance
**Current State**: `bridge_ws.py:117, 275, 340` - file I/O blocks event loop
**Example**:
```python
async def websocket_handler(request):
    # ... async context
    with open(script_path) as f:  # ❌ Blocks event loop!
        CACHED_CONTROL_SCRIPT = f.read()
```
**Mitigation Plan**:
- Phase 2: Replace with `aiofiles` for async file I/O
- Ensure all I/O in async contexts is non-blocking

### 🟡 HIGH Priority Risks

#### 5. Unvalidated WebSocket Protocol
**Risk**: Protocol drift, breaking changes, difficult debugging
**Impact**: Medium-High - affects CLI ↔ browser communication
**Current State**:
- JSON messages with string-based type checking
- No schema validation
- Version checking exists but protocol not versioned
**Mitigation Plan**:
- Phase 1: Create Pydantic models for all message types
- Document protocol in PROTOCOL.md with JSON schemas
- Implement protocol versioning

#### 6. No CI/CD Pipeline
**Risk**: Regressions not caught, inconsistent code quality
**Impact**: Medium - affects long-term maintainability
**Current State**: No .github/ directory, no automated checks
**Mitigation Plan**:
- Phase 0: Set up GitHub Actions
- Run lint, typecheck, tests on Python 3.11, 3.12, 3.13
- Require passing CI for merge

### 🟢 MEDIUM Priority Risks

#### 7. Module Organization & Dependency Management
**Risk**: Future circular dependencies, unclear boundaries
**Impact**: Low-Medium - affects scalability
**Current State**:
- ✅ No circular imports currently
- ⚠️ Flat structure, no enforced layers
**Mitigation Plan**:
- Phase 2: Define import layer architecture
- Enforce with ruff import rules
- Document in ARCHITECTURE.md

#### 8. Security Documentation Gap
**Risk**: Users may misconfigure or misunderstand threat model
**Impact**: Low-Medium - security by design (localhost-only)
**Current State**:
- ✅ Server binds to 127.0.0.1 (good!)
- ⚠️ No explicit origin validation documented
- ⚠️ Arbitrary JS execution (by design, but needs clear docs)
**Mitigation Plan**:
- Phase 3: Create SECURITY.md
- Document threat model, intentional limitations
- No remote binding without explicit opt-in

---

## Refactor Highlights (Planned)

### Phase 0: Foundation (3-5 days)
**Goal**: Set up tooling without touching application code

**Deliverables**:
- ✅ pyproject.toml (modern packaging)
- ✅ ruff, mypy, pre-commit configuration
- ✅ pytest + coverage infrastructure
- ✅ GitHub Actions CI pipeline
- ✅ CONTRIBUTING.md

**Value**: Developer productivity, code quality baseline

### Phase 1: Type Safety (5-7 days)
**Goal**: Add comprehensive typing and validation

**Deliverables**:
- ✅ Pydantic models for all WebSocket messages
- ✅ Type hints on 100% of functions
- ✅ mypy --strict passing
- ✅ PROTOCOL.md with JSON schemas
- ✅ Unit tests for config, models (≥80% coverage)

**Value**: Catch errors at development time, better IDE support

### Phase 2: Modularity (10-14 days)
**Goal**: Break up monolithic cli.py, extract services

**Deliverables**:
- ✅ cli.py split into 7+ command groups (each <400 lines)
- ✅ Service layer: ScriptLoader, BridgeExecutor, AIIntegration, ControlManager
- ✅ Adapter layer: Filesystem (async), WebSocket, HTTP
- ✅ bridge_ws.py refactored with async file I/O
- ✅ Clear import layer architecture enforced
- ✅ Integration tests (server ↔ client)

**Value**: Maintainability, testability, scalability

### Phase 3: Validation (7-10 days)
**Goal**: Comprehensive testing and documentation

**Deliverables**:
- ✅ E2E tests with Playwright (10+ browser tests)
- ✅ ≥80% test coverage on critical paths
- ✅ ARCHITECTURE.md with dependency graph
- ✅ CONTRIBUTING.md complete
- ✅ SECURITY.md
- ✅ Performance benchmarks

**Value**: Confidence in refactor, contributor onboarding

---

## How to Run & Test (Current State)

### Installation

```bash
# Clone repository
git clone https://github.com/roelvangils/inspekt.git
cd inspekt

# Install (development mode)
pip install -e .

# Verify installation
inspekt --version
```

### Running the Bridge

**Terminal 1: Start server**
```bash
inspekt server start
# Output:
# Inspekt WebSocket Server (aiohttp)
# WebSocket: ws://127.0.0.1:8766/ws
# HTTP API: http://127.0.0.1:8765
```

**Terminal 2: Install userscript**
1. Install Tampermonkey browser extension
2. Open `userscript_ws.js` and copy contents
3. Create new userscript in Tampermonkey
4. Paste and save
5. Open any website (e.g., https://example.com)

**Terminal 2: Execute commands**
```bash
# Evaluate JavaScript
inspekt eval "document.title"

# Extract links
inspekt extract-links

# Start control mode (keyboard navigation)
inspekt control start

# Get page structure
inspekt extract-page-structure

# Screenshot element
inspekt screenshot "#logo" output.png
```

### Testing (Post-Refactor)

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run all tests
make test

# Run specific test suites
pytest tests/unit/           # Unit tests only
pytest tests/integration/    # Integration tests
pytest tests/e2e/            # End-to-end browser tests

# Check coverage
make test                    # Shows coverage report
open htmlcov/index.html      # View detailed coverage

# Lint and format
make lint                    # Check code quality
make format                  # Auto-format code
make typecheck               # Run mypy
```

---

## Success Criteria (Refactor Complete)

### Functional ✅
- [ ] All 33+ CLI commands work identically to v1.0.0
- [ ] WebSocket server stable under load (100 requests/min)
- [ ] Browser reconnect works after page navigation
- [ ] Control mode auto-reinit functional
- [ ] Installable via `pipx install inspekt`

### Quality ✅
- [ ] Test coverage ≥80% on critical modules
- [ ] E2E tests: ≥10 browser scenarios passing
- [ ] mypy --strict: 0 errors
- [ ] ruff check: 0 warnings
- [ ] No circular dependencies

### Maintainability ✅
- [ ] Largest file ≤400 lines
- [ ] Clear module boundaries (domain → adapters → services → app)
- [ ] All public APIs documented (docstrings)
- [ ] Import layers enforced (ruff rules)

### Documentation ✅
- [ ] SUMMARY.md (this file)
- [ ] ARCHITECTURE.md (high-level design)
- [ ] REFACTOR_PLAN.md (detailed plan)
- [ ] CONTRIBUTING.md (developer guide)
- [ ] PROTOCOL.md (WebSocket schema)
- [ ] SECURITY.md (threat model)

### CI/CD ✅
- [ ] GitHub Actions workflow
- [ ] Python 3.11, 3.12, 3.13 matrix
- [ ] Lint, typecheck, test, coverage in CI
- [ ] All checks passing on main branch

---

## Quick Start (For Contributors - Post-Refactor)

### First-Time Setup

```bash
# 1. Clone and enter directory
git clone https://github.com/roelvangils/inspekt.git
cd inspekt

# 2. Install dependencies (using uv, recommended)
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"

# 3. Install pre-commit hooks
pre-commit install

# 4. Run tests to verify setup
make test

# 5. Start development server
inspekt server start
```

### Development Workflow

```bash
# Before making changes
git checkout -b feature/my-feature

# Make changes to code
# ...

# Auto-format and lint
make format
make lint

# Run tests
make test

# Type check
make typecheck

# Commit (pre-commit hooks run automatically)
git commit -m "feat: add new feature"

# Push and create PR
git push origin feature/my-feature
```

### Adding a New CLI Command (Post-Refactor)

```python
# File: zen/app/cli/my_commands.py

import click
from zen.services.bridge_executor import BridgeExecutor
from zen.app.cli.base import format_output

@click.command()
@click.argument("selector")
def my_command(selector: str) -> None:
    """My new command that does something."""
    executor = BridgeExecutor()

    # Load script
    code = f"document.querySelector('{selector}').textContent"

    # Execute
    result = executor.execute(code)

    # Output
    output = format_output(result)
    click.echo(output)
```

Register in `zen/app/cli/main.py`:
```python
from zen.app.cli.my_commands import my_command

@click.group()
def cli():
    """Inspekt CLI."""
    pass

cli.add_command(my_command)
```

Test it:
```python
# File: tests/unit/test_my_commands.py

def test_my_command(mock_executor):
    """Test my_command extracts element text."""
    result = runner.invoke(cli, ["my-command", "#logo"])
    assert result.exit_code == 0
    assert "expected text" in result.output
```

---

## Open Questions & Decisions

### Before Starting Refactor

1. **Python Version Requirement**
   - Current: >=3.7
   - Proposed: >=3.11 (for modern type hints, faster asyncio)
   - **Decision Needed**: ✅ Approve version bump?

2. **Semantic Versioning**
   - Current: 1.0.0
   - Proposed: 2.0.0 (refactor may have breaking changes)
   - **Decision Needed**: ✅ Approve major version bump?

3. **Pydantic v2**
   - Use Pydantic v2 for validation?
   - **Decision Needed**: ✅ Yes (recommended, stable)

4. **External API Stability**
   - Are there external projects importing `zen` as a library?
   - If yes, we need to maintain backward compatibility
   - **Decision Needed**: ❓ Research existing usage

5. **AI Service Integration**
   - What AI service is used for `inspekt describe` and `inspekt summarize`?
   - How is it configured?
   - **Decision Needed**: ❓ Document in ARCHITECTURE.md

### During Refactor

- Code review frequency (per-phase or continuous)?
- Branching strategy (long-lived refactor branch or PR per phase)?
- Testing in production-like environments?

---

## Timeline & Effort

**Estimated Timeline** (1 full-time developer):
- Phase 0 (Foundation): 3-5 days
- Phase 1 (Type Safety): 5-7 days
- Phase 2 (Modularity): 10-14 days
- Phase 3 (Validation): 7-10 days

**Total**: 25-36 days (5-7 weeks)

**Part-time** (4 hours/day): Double timeline (~10-14 weeks)

**Multiple Contributors**: Phases can partially overlap after Phase 0 completes

---

## Next Steps

### Immediate Actions (After Review)

1. **Review Documents**
   - [ ] Read REFACTOR_PLAN.md in detail
   - [ ] Validate audit findings
   - [ ] Confirm phases and approach

2. **Approve & Sign-Off**
   - [ ] Confirm Python 3.11+ requirement
   - [ ] Confirm v2.0.0 version bump
   - [ ] Approve refactor plan

3. **Prepare**
   - [ ] Create GitHub Project for refactor
   - [ ] Create issues for each phase
   - [ ] Set up Slack/Discord for questions

4. **Kick Off Phase 0**
   - [ ] Create branch: `refactor-phase0`
   - [ ] Set up pyproject.toml
   - [ ] Configure ruff, mypy, pre-commit
   - [ ] Create CI pipeline
   - [ ] Write smoke tests

---

## Resources & References

### Key Files to Review
- `zen/cli.py` - Main CLI implementation (3,946 lines)
- `zen/bridge_ws.py` - WebSocket server (396 lines)
- `zen/client.py` - HTTP client wrapper (250 lines)
- `zen/config.py` - Configuration management (213 lines)
- `userscript_ws.js` - Browser-side WebSocket client

### Documentation (To Be Created)
- REFACTOR_PLAN.md - Detailed phase plan (✅ Created)
- SUMMARY.md - This file (✅ Created)
- ARCHITECTURE.md - High-level design (📋 Phase 0)
- PROTOCOL.md - WebSocket protocol spec (📋 Phase 1)
- CONTRIBUTING.md - Developer guide (📋 Phase 0)
- SECURITY.md - Threat model (📋 Phase 3)

### External Links
- Project Repository: https://github.com/roelvangils/inspekt
- Click Documentation: https://click.palletsprojects.com/
- Pydantic Documentation: https://docs.pydantic.dev/
- aiohttp Documentation: https://docs.aiohttp.org/
- Playwright Documentation: https://playwright.dev/python/

---

## Contact & Support

**Maintainer**: Roel van Gils
**Repository**: https://github.com/roelvangils/inspekt
**Issues**: https://github.com/roelvangils/inspekt/issues

For questions about this refactor plan, please:
1. Review REFACTOR_PLAN.md for detailed information
2. Check existing GitHub issues
3. Create a new issue with `refactor` label

---

**Document Status**: ✅ Complete - Ready for Review
**Last Updated**: 2025-10-27
**Next Review**: After Phase 0 completion
