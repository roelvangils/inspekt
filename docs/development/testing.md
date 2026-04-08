# Testing Guide

Comprehensive guide to testing Inspekt. This covers unit tests, integration tests, E2E tests, and test coverage strategies.

## Overview

Inspekt uses **pytest** as the testing framework with support for:

- **Unit tests** - Fast, isolated tests for individual functions
- **Integration tests** - Multi-component tests (CLI + server)
- **E2E tests** - Full browser integration tests
- **Async tests** - Tests for async/await code
- **Coverage tracking** - Code coverage reporting

## Test Structure

```
tests/
├── conftest.py              # Shared fixtures
├── test_smoke.py            # Basic smoke tests (24 tests)
│
├── unit/                    # Unit tests (fast, isolated)
│   ├── __init__.py
│   ├── test_models.py       # Pydantic models (28 tests)
│   ├── test_script_loader.py
│   ├── test_bridge_executor.py
│   ├── test_ai_integration.py
│   └── test_control_manager.py
│
├── integration/             # Integration tests (server + client)
│   ├── __init__.py
│   ├── test_bridge_loop.py
│   └── test_cli_integration.py
│
├── e2e/                     # End-to-end tests (browser)
│   ├── __init__.py
│   └── test_browser_integration.py
│
└── fixtures/                # Test data
    ├── test_page.html
    └── mock_scripts.js
```

## Running Tests

### All Tests

```bash
# Run all tests
pytest

# With verbose output
pytest -v

# With very verbose output
pytest -vv
```

### Specific Test Suites

```bash
# Unit tests only (fast)
pytest tests/unit/

# Integration tests (requires server)
pytest tests/integration/

# E2E tests (requires browser)
pytest tests/e2e/ -m e2e

# Smoke tests only
pytest tests/test_smoke.py
```

### Specific Tests

```bash
# Single test file
pytest tests/unit/test_models.py

# Single test class
pytest tests/unit/test_models.py::TestExecuteRequest

# Single test function
pytest tests/unit/test_models.py::TestExecuteRequest::test_valid_execute_request

# Tests matching pattern
pytest -k "test_execute"
```

### With Coverage

```bash
# Run with coverage
pytest --cov=inspekt

# With HTML report
pytest --cov=inspekt --cov-report=html
open htmlcov/index.html

# With terminal report showing missing lines
pytest --cov=inspekt --cov-report=term-missing

# Coverage for specific module
pytest tests/unit/test_models.py --cov=inspekt.domain.models
```

### Watch Mode

```bash
# Install pytest-watch
pip install pytest-watch

# Run tests on file changes
ptw
```

## Writing Tests

### Unit Tests

**Unit tests** should be fast, isolated, and test single functions.

#### Basic Example

```python
# tests/unit/test_my_service.py
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

    def test_invalid_input_raises_error(self):
        """Test that invalid input raises ValueError."""
        service = MyService()
        with pytest.raises(ValueError) as exc_info:
            service.process("")

        assert "input is required" in str(exc_info.value)
```

#### Pydantic Model Tests

```python
# tests/unit/test_models.py
import pytest
from pydantic import ValidationError
from inspekt.domain.models import ExecuteRequest


class TestExecuteRequest:
    """Test ExecuteRequest model."""

    def test_valid_request(self):
        """Test creating valid request."""
        req = ExecuteRequest(
            request_id="test-123",
            code="document.title"
        )
        assert req.type == "execute"
        assert req.request_id == "test-123"
        assert req.code == "document.title"

    def test_missing_required_field(self):
        """Test that missing required field raises error."""
        with pytest.raises(ValidationError) as exc_info:
            ExecuteRequest(request_id="test-123")  # Missing code

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("code",) for e in errors)

    def test_serialization(self):
        """Test model serialization."""
        req = ExecuteRequest(request_id="id", code="code")
        data = req.model_dump()

        assert data == {
            "type": "execute",
            "request_id": "id",
            "code": "code"
        }

    def test_deserialization(self):
        """Test model deserialization."""
        data = {
            "type": "execute",
            "request_id": "id",
            "code": "code"
        }
        req = ExecuteRequest(**data)

        assert req.request_id == "id"
        assert req.code == "code"
```

### Async Tests

For async functions, use `@pytest.mark.asyncio`:

```python
import pytest
from pathlib import Path
from inspekt.adapters import filesystem


@pytest.mark.asyncio
async def test_read_text_async():
    """Test async file reading."""
    test_file = Path("test.txt")

    # Create test file
    test_file.write_text("test content")

    try:
        # Test async read
        content = await filesystem.read_text_async(test_file)
        assert content == "test content"
    finally:
        # Cleanup
        test_file.unlink()


@pytest.mark.asyncio
async def test_script_loader_async():
    """Test async script loading."""
    from inspekt.services.script_loader import ScriptLoader

    loader = ScriptLoader()
    script = await loader.load_script_async("control.js")

    assert len(script) > 0
    assert "use strict" in script
```

### Fixtures

**Fixtures** provide reusable test data and setup.

#### Basic Fixtures

```python
# tests/conftest.py
import pytest
from pathlib import Path


@pytest.fixture
def project_root():
    """Return project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture
def scripts_dir(project_root):
    """Return scripts directory."""
    return project_root / "inspekt" / "scripts"


@pytest.fixture
def sample_config():
    """Return sample configuration."""
    return {
        "ai-language": "en",
        "control": {
            "auto-refocus": "only-spa",
            "verbose": True
        }
    }
```

#### Using Fixtures

```python
def test_scripts_directory_exists(scripts_dir):
    """Test that scripts directory exists."""
    assert scripts_dir.exists()
    assert scripts_dir.is_dir()


def test_load_config_with_sample(sample_config):
    """Test loading sample config."""
    from inspekt.config import validate_control_config

    validated = validate_control_config(sample_config)
    assert validated["auto-refocus"] == "only-spa"
```

#### Async Fixtures

```python
import pytest
from inspekt.bridge_ws import create_app
from aiohttp.test_utils import TestServer


@pytest.fixture
async def server():
    """Start test server."""
    app = create_app()
    server = TestServer(app)
    await server.start_server()

    yield server

    await server.close()


@pytest.mark.asyncio
async def test_health_endpoint(server):
    """Test health endpoint."""
    async with server.client.request("GET", "/health") as resp:
        assert resp.status == 200
        data = await resp.json()
        assert data["ok"] is True
```

### Mocking

**Mocking** replaces real implementations with test doubles.

#### Mock Functions

```python
import pytest
from unittest.mock import Mock, patch


def test_execute_with_mocked_client():
    """Test execution with mocked client."""
    from inspekt.services.bridge_executor import BridgeExecutor

    # Create mock client
    mock_client = Mock()
    mock_client.execute.return_value = {
        "ok": True,
        "result": "Test Result"
    }

    # Create executor with mock
    executor = BridgeExecutor()
    executor.client = mock_client

    # Test
    result = executor.execute("test code")

    assert result["ok"] is True
    assert result["result"] == "Test Result"
    mock_client.execute.assert_called_once_with("test code", timeout=10.0)
```

#### Patch Functions

```python
@patch("inspekt.adapters.filesystem.read_text_sync")
def test_script_loader_with_mock_fs(mock_read):
    """Test script loader with mocked filesystem."""
    from inspekt.services.script_loader import ScriptLoader

    # Configure mock
    mock_read.return_value = "console.log('test');"

    # Test
    loader = ScriptLoader()
    script = loader.load_script_sync("test.js")

    assert script == "console.log('test');"
    mock_read.assert_called_once()
```

#### Monkeypatch (Pytest-specific)

```python
def test_with_monkeypatch(monkeypatch):
    """Test using monkeypatch."""
    from inspekt.services import my_service

    # Patch function
    def mock_function():
        return "mocked"

    monkeypatch.setattr(my_service, "real_function", mock_function)

    # Test
    result = my_service.real_function()
    assert result == "mocked"
```

### Integration Tests

**Integration tests** test multiple components together.

#### Server + Client Test

```python
# tests/integration/test_bridge_loop.py
import pytest
import aiohttp
from aiohttp import web
from inspekt.bridge_ws import create_app


@pytest.mark.integration
@pytest.mark.asyncio
async def test_execute_request_response():
    """Test full request/response cycle."""
    # Start server
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 8765)
    await site.start()

    try:
        async with aiohttp.ClientSession() as session:
            # Mock browser WebSocket
            async with session.ws_connect("ws://127.0.0.1:8766/ws") as ws:
                # CLI sends request
                async with session.post(
                    "http://127.0.0.1:8765/run",
                    json={"code": "document.title"}
                ) as resp:
                    data = await resp.json()
                    request_id = data["request_id"]

                # Browser receives message
                msg = await ws.receive_json()
                assert msg["type"] == "execute"
                assert msg["request_id"] == request_id

                # Browser sends result
                await ws.send_json({
                    "type": "result",
                    "request_id": request_id,
                    "ok": True,
                    "result": "Test Page"
                })

                # CLI polls for result
                async with session.get(
                    f"http://127.0.0.1:8765/result?request_id={request_id}"
                ) as resp:
                    result = await resp.json()
                    assert result["ok"] is True
                    assert result["result"] == "Test Page"
    finally:
        await runner.cleanup()
```

### E2E Tests (Playwright)

**End-to-end tests** use a real browser.

```python
# tests/e2e/test_browser_integration.py
import pytest
import subprocess
from playwright.sync_api import sync_playwright


@pytest.fixture
def inspekt_server():
    """Start inspekt server in background."""
    proc = subprocess.Popen(["inspekt", "server", "start"])
    yield
    proc.terminate()


@pytest.mark.e2e
def test_eval_command(inspekt_server):
    """Test inspekt eval command with real browser."""
    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch()
        page = browser.new_page()

        # Install userscript (simplified)
        # In real test, inject userscript via extension

        # Navigate to test page
        page.goto("https://example.com")

        # Wait for WebSocket connection
        page.wait_for_timeout(1000)

        # Run CLI command
        result = subprocess.run(
            ["inspekt", "eval", "document.title"],
            capture_output=True,
            text=True
        )

        # Verify
        assert result.returncode == 0
        assert "Example Domain" in result.stdout

        browser.close()
```

## Test Coverage

### Current Coverage

**Phase 0-2 Status**:

- Overall: **11.83%**
- Domain models: **94.70%**
- Tests: 52 passing (24 smoke + 28 models)

### Target Coverage

**Phase 3 Goals**:

- Overall: **≥80%**
- Services: **≥85%**
- Adapters: **≥90%**
- Domain: **≥95%**
- CLI: **≥70%**

### Checking Coverage

```bash
# Generate coverage report
pytest --cov=inspekt --cov-report=term-missing

# HTML report
pytest --cov=inspekt --cov-report=html
open htmlcov/index.html

# Coverage for specific package
pytest --cov=inspekt.services --cov-report=term

# Fail if coverage below threshold
pytest --cov=inspekt --cov-fail-under=80
```

### Coverage Configuration

Create `.coveragerc`:

```ini
[run]
source = inspekt
omit =
    */tests/*
    */venv/*
    */__pycache__/*

[report]
exclude_lines =
    pragma: no cover
    def __repr__
    raise NotImplementedError
    if __name__ == .__main__.:
    if TYPE_CHECKING:
    @abstractmethod
```

## Test Organization

### Test Classes

Group related tests in classes:

```python
class TestScriptLoader:
    """Test ScriptLoader service."""

    def test_load_script_sync(self):
        """Test synchronous script loading."""
        ...

    def test_load_script_async(self):
        """Test asynchronous script loading."""
        ...

    def test_caching(self):
        """Test script caching."""
        ...

    def test_substitution(self):
        """Test template substitution."""
        ...
```

### Test Markers

Use markers to categorize tests:

```python
@pytest.mark.unit
def test_something():
    """Unit test."""
    ...


@pytest.mark.integration
def test_integration():
    """Integration test."""
    ...


@pytest.mark.e2e
def test_browser():
    """E2E test."""
    ...


@pytest.mark.slow
def test_slow_operation():
    """Slow test."""
    ...
```

Run specific markers:

```bash
# Only unit tests
pytest -m unit

# Only integration tests
pytest -m integration

# Skip slow tests
pytest -m "not slow"
```

### Parametrized Tests

Test multiple inputs:

```python
@pytest.mark.parametrize("input,expected", [
    ("hello", "HELLO"),
    ("world", "WORLD"),
    ("", ""),
    ("123", "123"),
])
def test_uppercase(input, expected):
    """Test uppercase conversion."""
    assert input.upper() == expected


@pytest.mark.parametrize("code,result_type", [
    ("1 + 1", int),
    ("'hello'", str),
    ("[1, 2, 3]", list),
    ("{'a': 1}", dict),
])
def test_eval_types(code, result_type):
    """Test eval returns correct types."""
    from inspekt.services.bridge_executor import get_executor

    executor = get_executor()
    result = executor.execute(code)

    assert isinstance(result["result"], result_type)
```

## Best Practices

### Test Naming

Use descriptive names:

```python
# ✅ Good
def test_execute_returns_error_when_server_not_running():
    """Test that execute raises error when server is not running."""
    ...

# ❌ Bad
def test_execute():
    """Test execute."""
    ...
```

### AAA Pattern

Arrange, Act, Assert:

```python
def test_script_loader_caching():
    """Test that scripts are cached after first load."""
    # Arrange
    from inspekt.services.script_loader import ScriptLoader
    loader = ScriptLoader()

    # Act
    script1 = loader.load_script_sync("control.js")
    script2 = loader.load_script_sync("control.js")

    # Assert
    assert script1 == script2
    assert "control.js" in loader.get_cached_scripts()
```

### One Assertion Per Test

```python
# ✅ Good - Each test has clear purpose
def test_execute_request_has_type():
    """Test ExecuteRequest has type field."""
    req = ExecuteRequest(request_id="id", code="code")
    assert req.type == "execute"


def test_execute_request_has_request_id():
    """Test ExecuteRequest has request_id field."""
    req = ExecuteRequest(request_id="id", code="code")
    assert req.request_id == "id"


# ❌ Bad - Multiple unrelated assertions
def test_execute_request():
    """Test ExecuteRequest."""
    req = ExecuteRequest(request_id="id", code="code")
    assert req.type == "execute"
    assert req.request_id == "id"
    assert req.code == "code"
```

### Test Independence

Each test should be independent:

```python
# ✅ Good - Independent tests
def test_load_script():
    """Test loading script."""
    loader = ScriptLoader()  # New instance
    script = loader.load_script_sync("test.js")
    assert script is not None


def test_cache_script():
    """Test caching script."""
    loader = ScriptLoader()  # New instance
    loader.load_script_sync("test.js")
    assert "test.js" in loader.get_cached_scripts()


# ❌ Bad - Tests depend on each other
loader = ScriptLoader()  # Shared state

def test_load_script():
    """Test loading script."""
    loader.load_script_sync("test.js")

def test_cache_script():
    """Test caching script."""
    # Depends on test_load_script running first
    assert "test.js" in loader.get_cached_scripts()
```

## Continuous Integration

### GitHub Actions

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12", "3.13"]

    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: |
          pip install -e ".[dev]"

      - name: Run tests
        run: |
          pytest --cov=inspekt --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## Debugging Tests

### Print Debugging

```python
def test_with_debug():
    """Test with debug output."""
    result = some_function()

    # Print for debugging
    print(f"Result: {result}")
    print(f"Type: {type(result)}")

    assert result is not None
```

Run with `-s` to see prints:

```bash
pytest tests/test_file.py -s
```

### PDB Debugging

```python
def test_with_pdb():
    """Test with debugger."""
    result = some_function()

    # Drop into debugger
    import pdb; pdb.set_trace()

    assert result is not None
```

Run to trigger debugger:

```bash
pytest tests/test_file.py
```

### Pytest Debugging

```bash
# Drop into debugger on failure
pytest --pdb

# Drop into debugger at start
pytest --trace
```

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [pytest-cov](https://pytest-cov.readthedocs.io/)
- [Playwright for Python](https://playwright.dev/python/)

## Next Steps

- [Architecture Guide](architecture.md) - System design
- [Contributing Guide](contributing.md) - Development workflow
- [Security Guide](security.md) - Security model
