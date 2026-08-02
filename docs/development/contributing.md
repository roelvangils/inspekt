# Contributing Guide

Thank you for your interest in contributing to Inspekt! This guide will help you get started with development and make your first contribution.

## Quick Start

### Prerequisites

- **Python 3.11+** (Python 3.11, 3.12, or 3.13)
- **Git** for version control
- **Modern browser** (Chrome, Firefox, Edge)
- **Tampermonkey** or **Violentmonkey** extension

### Installation

=== "Using uv (Recommended)"

    ```bash
    # Install uv (fast Python package installer)
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Clone repository
    git clone https://github.com/roelvangils/inspekt.git
    cd inspekt

    # Create virtual environment and install
    uv venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    uv pip install -e ".[dev]"

    # Install pre-commit hooks
    pre-commit install
    ```

=== "Using pip + venv"

    ```bash
    # Clone repository
    git clone https://github.com/roelvangils/inspekt.git
    cd inspekt

    # Create virtual environment
    python3 -m venv .venv
    source .venv/bin/activate

    # Install in development mode
    pip install -e ".[dev]"

    # Install pre-commit hooks (if available)
    pre-commit install
    ```

=== "Using poetry"

    ```bash
    # Clone repository
    git clone https://github.com/roelvangils/inspekt.git
    cd inspekt

    # Install dependencies
    poetry install

    # Activate shell
    poetry shell
    ```

### Verify Installation

```bash
# Check version
inspekt --version

# Check all dependencies installed
python -c "import inspekt; print(inspekt.__version__)"
```

## Development Setup

### 1. Start the Bridge Server

In one terminal:

```bash
inspekt start
```

Expected output:

```
Inspekt WebSocket Server (aiohttp)
WebSocket: ws://127.0.0.1:8766/ws
HTTP API: http://127.0.0.1:8765

✓ Loaded control.js into cache (36766 bytes)

HTTP server running on http://127.0.0.1:8765
WebSocket server running on ws://127.0.0.1:8766/ws
Ready for connections!
```

### 2. Install Userscript

1. Install [Tampermonkey](https://www.tampermonkey.net/) extension
2. Open `userscript_ws.js` in the project
3. Copy entire file contents
4. Open Tampermonkey dashboard
5. Click "Create a new script"
6. Paste contents and save
7. Open any website (e.g., https://example.com)
8. Check console: `[Inspekt] Connected via WebSocket`

### 3. Test Basic Commands

```bash
# Test evaluation
inspekt eval "document.title"

# Test data extraction
inspekt extract-links

# Test control mode
inspekt control start
inspekt control next
inspekt control click
```

## Development Workflow

### 1. Create a Branch

```bash
# Feature branch
git checkout -b feature/my-awesome-feature

# Bug fix branch
git checkout -b fix/issue-123

# Documentation
git checkout -b docs/improve-readme
```

**Branch naming**:

- `feature/description` - New features
- `fix/description` - Bug fixes
- `docs/description` - Documentation
- `refactor/description` - Code refactoring
- `test/description` - Test additions

### 2. Make Changes

Edit relevant files:

- `inspekt/app/cli/` - CLI commands
- `inspekt/services/` - Business logic
- `inspekt/adapters/` - I/O operations
- `inspekt/domain/` - Data models
- `inspekt/bridge_ws.py` - WebSocket server
- `inspekt/scripts/` - JavaScript files

### 3. Run Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=inspekt

# Run specific test file
pytest tests/unit/test_models.py

# Run with verbose output
pytest -v
```

### 4. Check Code Quality

```bash
# Format code
ruff format inspekt/

# Check linting
ruff check inspekt/

# Auto-fix issues
ruff check inspekt/ --fix

# Type checking
mypy inspekt/
```

### 5. Commit Changes

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```bash
git add .
git commit -m "feat(cli): add new extract-cookies command"
```

**Commit types**:

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `style`: Code style (no logic change)
- `refactor`: Code refactoring
- `test`: Add/modify tests
- `chore`: Maintenance
- `perf`: Performance improvement

### 6. Push and Create PR

```bash
# Push to your fork
git push origin feature/my-awesome-feature

# Create pull request on GitHub
```

## Code Style & Standards

### Python Style

We use **ruff** for linting and formatting.

**Style guidelines**:

- Line length: 100 characters
- Indentation: 4 spaces
- String quotes: Double quotes preferred
- Imports: Sorted, grouped (stdlib, third-party, local)

**Example**:

```python
"""Module docstring."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click
from pydantic import BaseModel

from inspekt.services.bridge_executor import get_executor


def my_function(arg: str, timeout: float = 10.0) -> dict[str, Any]:
    """Do something useful.

    Args:
        arg: Description
        timeout: Maximum time in seconds

    Returns:
        Dictionary with result

    Raises:
        ValueError: If arg is invalid
    """
    if not arg:
        raise ValueError("arg is required")

    return {"result": arg, "timeout": timeout}
```

### Type Hints

**All functions must have type hints**:

```python
# ✅ Good
def get_title(url: str, timeout: float = 10.0) -> str:
    """Get page title."""
    ...

# ❌ Bad
def get_title(url, timeout=10.0):
    ...
```

**Run type checker**:

```bash
mypy inspekt/ --strict
```

### Docstrings

Use Google-style docstrings:

```python
def execute_script(script_path: Path, timeout: float) -> dict[str, Any]:
    """Execute a JavaScript file in the browser.

    Args:
        script_path: Path to JavaScript file
        timeout: Maximum execution time in seconds

    Returns:
        Dictionary with execution result:
            - ok (bool): Whether execution succeeded
            - result (Any): Return value from JavaScript
            - error (str | None): Error message if failed

    Raises:
        ConnectionError: If bridge server is not running
        TimeoutError: If execution exceeds timeout
        FileNotFoundError: If script file does not exist

    Example:
        >>> result = execute_script(Path("script.js"), 10.0)
        >>> if result["ok"]:
        ...     print(result["result"])
    """
    ...
```

### JavaScript Style

For scripts in `inspekt/scripts/`:

```javascript
/**
 * Description of what this script does.
 * @returns {Object} Result object with data
 */
(function() {
    'use strict';

    try {
        // Your code here
        const data = document.querySelectorAll('.item');
        const results = Array.from(data).map(el => ({
            text: el.textContent.trim(),
            href: el.querySelector('a')?.href
        }));

        return {
            ok: true,
            results: results,
            count: results.length
        };
    } catch (error) {
        return {
            ok: false,
            error: error.message
        };
    }
})();
```

**Guidelines**:

- Use IIFE (Immediately Invoked Function Expression)
- `'use strict';` at the top
- Prefer `const` over `let`, never `var`
- Use modern ES6+ syntax
- Handle errors gracefully
- Return structured objects

## Testing

### Running Tests

```bash
# All tests
pytest

# Unit tests only
pytest tests/unit/

# Integration tests
pytest tests/integration/

# Specific test
pytest tests/unit/test_models.py::TestExecuteRequest

# With coverage report
pytest --cov=inspekt --cov-report=html
open htmlcov/index.html
```

### Writing Tests

**Unit test example**:

```python
# tests/unit/test_my_feature.py
import pytest
from inspekt.services.my_service import MyService


class TestMyService:
    """Test MyService functionality."""

    def test_initialization(self):
        """Test service can be initialized."""
        service = MyService()
        assert service is not None

    def test_process_data(self):
        """Test data processing."""
        service = MyService()
        result = service.process("input")
        assert result == "processed: input"

    def test_invalid_input(self):
        """Test handling of invalid input."""
        service = MyService()
        with pytest.raises(ValueError):
            service.process("")
```

**Async test example**:

```python
import pytest


@pytest.mark.asyncio
async def test_async_operation():
    """Test async operation."""
    from inspekt.adapters import filesystem

    content = await filesystem.read_text_async(Path("test.txt"))
    assert content is not None
```

### Test Coverage

Target: **80%+ overall**, **90%+ for services**

Check coverage:

```bash
pytest --cov=inspekt --cov-report=term-missing
```

## Commit Guidelines

We follow [Conventional Commits](https://www.conventionalcommits.org/) specification.

### Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Examples

```bash
# New feature
git commit -m "feat(cli): add extract-cookies command"

# Bug fix
git commit -m "fix(server): prevent event loop blocking in file I/O

Fixed blocking I/O operations in bridge_ws.py by using
async file operations from filesystem adapter."

# Documentation
git commit -m "docs(contributing): add testing guidelines"

# Breaking change
git commit -m "feat(config)!: require Python 3.11+

BREAKING CHANGE: Drop support for Python 3.7-3.10"
```

### Best Practices

- ✅ Use present tense: "add feature" not "added feature"
- ✅ Use imperative mood: "move cursor" not "moves cursor"
- ✅ Keep subject line under 72 characters
- ✅ Explain what and why, not how
- ❌ Don't end subject with period

## Pull Request Process

### 1. Pre-submission Checklist

Before submitting PR:

- [ ] All tests pass (`pytest`)
- [ ] Code is formatted (`ruff format inspekt/`)
- [ ] No linting errors (`ruff check inspekt/`)
- [ ] Type checking passes (`mypy inspekt/`)
- [ ] Documentation updated (if applicable)
- [ ] Commit messages follow Conventional Commits
- [ ] No breaking changes (or documented)
- [ ] Manual testing done

### 2. Create Pull Request

1. Push your branch
2. Go to GitHub repository
3. Click "New Pull Request"
4. Fill out PR template:
   - **Description**: What does this PR do?
   - **Motivation**: Why is this change needed?
   - **Testing**: How was this tested?
   - **Screenshots**: If UI changes
   - **Checklist**: Complete items

### 3. Code Review

- Address reviewer feedback promptly
- Make requested changes
- Push updates (no force-push unless necessary)
- Keep discussion professional and constructive

### 4. Merge

Once approved, maintainer will merge using:

- **Squash merge** for single feature
- **Merge commit** for multi-commit features
- **Rebase** for clean history

## Common Tasks

### Adding a New CLI Command

=== "Current Approach (v1.0.0)"

    Edit `inspekt/cli.py`:

    ```python
    @cli.command()
    @click.argument("arg")
    @click.option("--timeout", type=float, default=10.0)
    def my_command(arg: str, timeout: float) -> None:
        """My new command."""
        client = BridgeClient()

        # Load script
        script_path = Path(__file__).parent / "scripts" / "my_script.js"
        with open(script_path) as f:
            code = f.read()

        # Execute
        result = client.execute(code, timeout=timeout)
        click.echo(result.get("result"))
    ```

=== "Refactored Approach (Phase 2+)"

    Create `inspekt/app/cli/my_commands.py`:

    ```python
    import click
    from inspekt.services.bridge_executor import get_executor
    from inspekt.services.script_loader import ScriptLoader


    @click.command()
    @click.argument("arg")
    @click.option("--timeout", type=float, default=10.0)
    def my_command(arg: str, timeout: float) -> None:
        """My new command."""
        # Load script via service
        loader = ScriptLoader()
        code = loader.load_script("my_script.js")

        # Execute via service
        executor = get_executor()
        result = executor.execute(code, timeout=timeout)

        click.echo(result["result"])
    ```

    Register in `inspekt/app/cli/__init__.py`:

    ```python
    from inspekt.app.cli.my_commands import my_command

    cli.add_command(my_command)
    ```

### Adding a New JavaScript Script

1. **Create script** in `inspekt/scripts/my_script.js`:

```javascript
/**
 * Extract data from page.
 * @returns {Object} Extracted data
 */
(function() {
    'use strict';

    try {
        const items = document.querySelectorAll('.item');
        const results = Array.from(items).map(el => ({
            text: el.textContent.trim(),
            href: el.querySelector('a')?.href
        }));

        return {
            ok: true,
            results: results,
            count: results.length
        };
    } catch (error) {
        return {
            ok: false,
            error: error.message
        };
    }
})();
```

2. **Create CLI command** (see above)
3. **Test on real page**
4. **Document in README.md**

### Running Locally with Live Reload

```bash
# Terminal 1: Server (auto-restarts on changes)
python inspekt/bridge_ws.py

# Terminal 2: Make changes
vim inspekt/app/cli/my_commands.py

# Terminal 3: Test
inspekt my-command test-arg
```

## Debugging Tips

### Enable Verbose Logging

**Server side**:

```bash
inspekt start  # Already verbose
```

**Browser side** - Edit `userscript_ws.js`:

```javascript
const VERBOSE = true;  // Set to true
```

### Check Server Status

```bash
# Is server running?
inspekt status

# Health check
curl http://127.0.0.1:8765/health

# Check notifications
curl http://127.0.0.1:8765/notifications
```

### WebSocket Connection Issues

1. Check browser console for errors
2. Verify Tampermonkey script is active
3. Refresh page to reconnect
4. Check firewall (allow localhost)
5. Verify server is running

### Command Not Working

1. Test simple command: `inspekt eval "1+1"`
2. Check browser console for JavaScript errors
3. Check server logs
4. Verify userscript is loaded
5. Try on different page

## Getting Help

- **Documentation**: See [Architecture](architecture.md), [Testing](testing.md)
- **GitHub Issues**: [Open an issue](https://github.com/roelvangils/inspekt/issues)
- **Discussions**: Use GitHub Discussions for questions
- **Bug Reports**: Include reproducible example

## Resources

- [Architecture Documentation](architecture.md)
- [Testing Guide](testing.md)
- [Security Guide](security.md)

For additional technical documentation, see the project repository root files:
- `ARCHITECTURE.md` - Complete architecture documentation
- `PROTOCOL.md` - WebSocket protocol specification
- `REFACTOR_PLAN.md` - Refactoring progress and phases

## Code of Conduct

Be respectful, constructive, and inclusive. We're all here to build something useful together.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

**Thank you for contributing to Inspekt!** 🎉
