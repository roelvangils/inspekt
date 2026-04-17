# Services API Reference

Complete reference for all four Inspekt services that provide business logic and orchestration.

---

## Overview

Inspekt services layer implements the core business logic following a clean architecture pattern. Services use dependency injection, follow the single responsibility principle, and provide both synchronous and asynchronous interfaces where appropriate.

**Available Services:**

- [BridgeExecutor](#bridgeexecutor) - Standardized command execution with retry logic
- [AIIntegrationService](#aiintegrationservice) - Language detection and AI tool orchestration
- [ControlManager](#controlmanager) - Control mode state and notification management
- [ScriptLoader](#scriptloader) - JavaScript script loading and caching

---

## BridgeExecutor

Wraps the BridgeClient to provide standardized execution flow for browser commands.

**Location:** `inspekt/services/bridge_executor.py`

### Purpose

- Consistent error handling across all CLI commands
- Retry logic with exponential backoff
- Result formatting and validation
- Version checking
- Connection pooling (future enhancement)

### Class: `BridgeExecutor`

```python
class BridgeExecutor:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        max_retries: int = 3,
        retry_delay: float = 0.5,
    ):
        """Initialize the bridge executor."""
```

**Parameters:**

- `host` (str): Bridge server host (default: localhost)
- `port` (int): Bridge server port (default: 8765)
- `max_retries` (int): Maximum number of retry attempts on transient failures
- `retry_delay` (float): Initial delay between retries in seconds (exponential backoff)

---

### Methods

#### `is_server_running()`

Check if bridge server is running.

**Signature:**
```python
def is_server_running(self) -> bool
```

**Returns:**

- `bool`: True if server is alive, False otherwise

**Example:**

```python
executor = BridgeExecutor()
if executor.is_server_running():
    print("Server is running")
```

---

#### `ensure_server_running()`

Ensure bridge server is running, exit with error if not.

**Signature:**
```python
def ensure_server_running(self) -> None
```

**Exits:**

- `sys.exit(1)` if server is not running

**Example:**

```python
executor = BridgeExecutor()
executor.ensure_server_running()  # Will exit if server not running
```

---

#### `execute()`

Execute JavaScript code in browser with error handling and optional retries.

**Signature:**
```python
def execute(
    self,
    code: str,
    timeout: float = 10.0,
    retry_on_timeout: bool = False,
) -> dict[str, Any]
```

**Parameters:**

- `code` (str): JavaScript code to execute
- `timeout` (float): Maximum time to wait for result in seconds
- `retry_on_timeout` (bool): If True, retry on TimeoutError

**Returns:**

Dictionary with execution result:

```python
{
    "ok": bool,            # True if execution succeeded
    "result": Any,         # Present if ok=True
    "error": str,          # Present if ok=False
    "url": str,            # Present for some commands
    "title": str,          # Present for some commands
}
```

**Raises:**

- `SystemExit`: If execution fails after retries

**Example:**

```python
executor = BridgeExecutor()
result = executor.execute(
    "document.title",
    timeout=5.0,
    retry_on_timeout=True
)
print(result["result"])  # "Example Domain"
```

---

#### `execute_file()`

Execute JavaScript from a file.

**Signature:**
```python
def execute_file(
    self,
    filepath: str | Path,
    timeout: float = 10.0,
    retry_on_timeout: bool = False,
) -> dict[str, Any]
```

**Parameters:**

- `filepath` (str | Path): Path to JavaScript file
- `timeout` (float): Maximum time to wait for result in seconds
- `retry_on_timeout` (bool): If True, retry on TimeoutError

**Returns:**

- `dict[str, Any]`: Dictionary with execution result

**Raises:**

- `SystemExit`: If file read or execution fails

**Example:**

```python
executor = BridgeExecutor()
result = executor.execute_file("script.js", timeout=30.0)
```

---

#### `execute_with_script()`

Execute a helper script with template substitutions.

**Signature:**
```python
def execute_with_script(
    self,
    script_name: str,
    substitutions: dict[str, str] | None = None,
    timeout: float = 10.0,
    retry_on_timeout: bool = False,
) -> dict[str, Any]
```

**Parameters:**

- `script_name` (str): Name of script file in inspekt/scripts/
- `substitutions` (dict[str, str] | None): Dictionary of placeholder → value substitutions
- `timeout` (float): Maximum time to wait for result in seconds
- `retry_on_timeout` (bool): If True, retry on TimeoutError

**Returns:**

- `dict[str, Any]`: Dictionary with execution result

**Raises:**

- `SystemExit`: If script not found or execution fails

**Example:**

```python
executor = BridgeExecutor()
result = executor.execute_with_script(
    "cookies.js",
    substitutions={
        "ACTION_PLACEHOLDER": "get",
        "NAME_PLACEHOLDER": "session_id"
    }
)
```

---

#### `check_result_ok()`

Check if result is successful, exit with error if not.

**Signature:**
```python
def check_result_ok(self, result: dict[str, Any]) -> None
```

**Parameters:**

- `result` (dict[str, Any]): Execution result dictionary

**Exits:**

- `sys.exit(1)` if result["ok"] is False

**Example:**

```python
executor = BridgeExecutor()
result = executor.execute("document.title")
executor.check_result_ok(result)  # Will exit if result not ok
```

---

#### `get_status()`

Get bridge server status.

**Signature:**
```python
def get_status(self) -> dict[str, Any] | None
```

**Returns:**

- `dict[str, Any] | None`: Status dictionary or None if server not running

**Example:**

```python
executor = BridgeExecutor()
status = executor.get_status()
if status:
    print(f"Pending: {status['pending']}")
    print(f"Completed: {status['completed']}")
```

---

#### `check_userscript_version()`

Check if userscript version matches expected version.

**Signature:**
```python
def check_userscript_version(self, show_warning: bool = True) -> str | None
```

**Parameters:**

- `show_warning` (bool): If True, print warning when versions don't match

**Returns:**

- `str | None`: Warning message if versions don't match, None otherwise

**Example:**

```python
executor = BridgeExecutor()
warning = executor.check_userscript_version()
if warning:
    print(warning)
```

---

### Global Functions

#### `get_executor()`

Get the default executor instance (singleton pattern).

**Signature:**
```python
def get_executor(
    host: str = "127.0.0.1",
    port: int = 8765,
    max_retries: int = 3,
) -> BridgeExecutor
```

**Parameters:**

- `host` (str): Bridge server host
- `port` (int): Bridge server port
- `max_retries` (int): Maximum retry attempts

**Returns:**

- `BridgeExecutor`: Shared BridgeExecutor instance

**Example:**

```python
from inspekt.services.bridge_executor import get_executor

executor = get_executor()
result = executor.execute("document.title")
```

---

## AIIntegrationService

Handles language detection and AI tool orchestration for content analysis commands.

**Location:** `inspekt/services/ai_integration.py`

### Purpose

- Language detection from page content and configuration
- Prompt file loading and formatting
- Integration with external AI tools (mods, etc.)
- Debug mode for prompt inspection

### Class: `AIIntegrationService`

```python
class AIIntegrationService:
    def __init__(self, prompts_dir: Path | None = None):
        """Initialize the AI integration service."""
```

**Parameters:**

- `prompts_dir` (Path | None): Directory containing prompt files (default: project_root/prompts/)

---

### Methods

#### `get_target_language()`

Determine the language for AI operations.

**Signature:**
```python
def get_target_language(
    self,
    language_override: str | None = None,
    page_lang: str | None = None,
) -> str | None
```

**Priority Order:**

1. `language_override` (from --language flag)
2. config.json ai-language setting
3. If "auto", detect from page_lang
4. Default to None (let AI decide)

**Parameters:**

- `language_override` (str | None): Language code from CLI flag (e.g., "en", "nl", "fr")
- `page_lang` (str | None): Detected page language

**Returns:**

- `str | None`: Language code or None to let AI decide

**Example:**

```python
service = AIIntegrationService()
lang = service.get_target_language(
    language_override="en",
    page_lang="nl"
)
# Returns: "en" (override takes priority)
```

---

#### `extract_page_language()`

Extract page language from content string.

**Signature:**
```python
def extract_page_language(self, content: str) -> str | None
```

Looks for patterns like:
- "**Language:** xx"
- "lang": "xx"

**Parameters:**

- `content` (str): Content string (markdown or JSON)

**Returns:**

- `str | None`: Language code or None if not found

**Example:**

```python
service = AIIntegrationService()
content = "**Language:** en\n\nPage content…"
lang = service.extract_page_language(content)
# Returns: "en"
```

---

#### `check_mods_available()`

Check if the 'mods' AI tool is available.

**Signature:**
```python
def check_mods_available(self) -> bool
```

**Returns:**

- `bool`: True if mods is installed and accessible

**Example:**

```python
service = AIIntegrationService()
if not service.check_mods_available():
    print("Please install mods")
```

---

#### `ensure_mods_available()`

Ensure mods is available, exit with error if not.

**Signature:**
```python
def ensure_mods_available(self) -> None
```

**Exits:**

- `sys.exit(1)` if mods is not installed

**Example:**

```python
service = AIIntegrationService()
service.ensure_mods_available()  # Will exit if mods not found
```

---

#### `load_prompt()`

Load a prompt file from the prompts directory.

**Signature:**
```python
def load_prompt(self, prompt_name: str) -> str
```

**Parameters:**

- `prompt_name` (str): Name of prompt file (e.g., "describe.prompt", "summary.prompt")

**Returns:**

- `str`: Prompt content as string

**Raises:**

- `SystemExit`: If prompt file not found

**Example:**

```python
service = AIIntegrationService()
prompt = service.load_prompt("describe.prompt")
```

---

#### `format_prompt()`

Format a complete prompt with language instructions and content.

**Signature:**
```python
def format_prompt(
    self,
    base_prompt: str,
    content: str,
    target_lang: str | None = None,
    extra_instructions: str | None = None,
) -> str
```

**Parameters:**

- `base_prompt` (str): Base prompt template
- `content` (str): Content to analyze
- `target_lang` (str | None): Target language code (optional)
- `extra_instructions` (str | None): Additional instructions to append (optional)

**Returns:**

- `str`: Formatted prompt ready for AI tool

**Example:**

```python
service = AIIntegrationService()
prompt = service.format_prompt(
    base_prompt="Describe this page:",
    content="<page content>",
    target_lang="en",
    extra_instructions="Focus on accessibility"
)
```

---

#### `call_mods()`

Call the mods AI tool with the given prompt.

**Signature:**
```python
def call_mods(
    self,
    prompt: str,
    timeout: float = 60.0,
    additional_args: list[str] | None = None,
) -> str
```

**Parameters:**

- `prompt` (str): Complete prompt to send to mods
- `timeout` (float): Maximum time to wait for response in seconds
- `additional_args` (list[str] | None): Additional CLI arguments for mods

**Returns:**

- `str`: AI response text

**Raises:**

- `SystemExit`: If mods call fails

**Example:**

```python
service = AIIntegrationService()
response = service.call_mods(
    "Describe this page:\n\nPage content…",
    timeout=30.0
)
```

---

#### `show_debug_prompt()`

Display a formatted debug view of the prompt.

**Signature:**
```python
def show_debug_prompt(self, prompt: str) -> None
```

**Parameters:**

- `prompt` (str): The prompt to display

**Example:**

```python
service = AIIntegrationService()
service.show_debug_prompt("Full prompt here…")
```

---

#### `generate_description()`

Generate an AI-powered page description.

**Signature:**
```python
def generate_description(
    self,
    page_structure: str,
    language_override: str | None = None,
    debug: bool = False,
) -> str | None
```

**Parameters:**

- `page_structure` (str): Extracted page structure (markdown format)
- `language_override` (str | None): Optional language override
- `debug` (bool): If True, show prompt instead of calling AI

**Returns:**

- `str | None`: AI-generated description or None if debug mode

**Example:**

```python
service = AIIntegrationService()
description = service.generate_description(
    page_structure="# Main Heading\n…",
    language_override="en"
)
```

---

#### `generate_summary()`

Generate an AI-powered article summary.

**Signature:**
```python
def generate_summary(
    self,
    article: dict[str, Any],
    language_override: str | None = None,
    debug: bool = False,
) -> str | None
```

**Parameters:**

- `article` (dict[str, Any]): Extracted article data (title, content, byline, lang)
- `language_override` (str | None): Optional language override
- `debug` (bool): If True, show prompt instead of calling AI

**Returns:**

- `str | None`: AI-generated summary or None if debug mode

**Example:**

```python
service = AIIntegrationService()
summary = service.generate_summary(
    article={
        "title": "Article Title",
        "content": "Article content…",
        "lang": "en"
    }
)
```

---

### Global Functions

#### `get_ai_service()`

Get the default AI integration service instance (singleton pattern).

**Signature:**
```python
def get_ai_service(prompts_dir: Path | None = None) -> AIIntegrationService
```

**Parameters:**

- `prompts_dir` (Path | None): Optional custom prompts directory

**Returns:**

- `AIIntegrationService`: Shared AIIntegrationService instance

**Example:**

```python
from inspekt.services.ai_integration import get_ai_service

service = get_ai_service()
description = service.generate_description(page_structure)
```

---

## ControlManager

Manages control mode state and notifications.

**Location:** `inspekt/services/control_manager.py`

### Purpose

- Control mode state tracking
- Notification polling and handling
- Auto-restart logic
- Accessibility announcements coordination

### Class: `ControlNotification`

Represents a notification from the browser during control mode.

```python
class ControlNotification:
    def __init__(
        self,
        notification_type: str,
        message: str,
        data: dict[str, Any] | None = None
    ):
        """Initialize a control notification."""
```

**Attributes:**

- `type` (str): Type of notification (e.g., "refocus")
- `message` (str): Human-readable message
- `data` (dict[str, Any]): Additional notification data

**Class Methods:**

```python
@classmethod
def from_dict(cls, data: dict[str, Any]) -> ControlNotification:
    """Create notification from API response dictionary."""
```

---

### Class: `ControlManager`

Service for managing browser control mode state and notifications.

```python
class ControlManager:
    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        """Initialize the control manager."""
```

**Parameters:**

- `host` (str): Bridge server host
- `port` (int): Bridge server port

---

### Methods

#### `check_notifications()`

Check for pending notifications from the browser.

**Signature:**
```python
def check_notifications(self, timeout: float = 0.5) -> list[ControlNotification]
```

**Parameters:**

- `timeout` (float): Request timeout in seconds

**Returns:**

- `list[ControlNotification]`: List of notifications (empty if none available or on error)

**Example:**

```python
manager = ControlManager()
notifications = manager.check_notifications()
for notif in notifications:
    print(notif.message)
```

---

#### `handle_refocus_notification()`

Handle a refocus notification by announcing it.

**Signature:**
```python
def handle_refocus_notification(
    self,
    notification: ControlNotification,
    speak_enabled: bool = False,
    speak_command: str = "say",
) -> None
```

**Parameters:**

- `notification` (ControlNotification): The refocus notification
- `speak_enabled` (bool): If True, use text-to-speech
- `speak_command` (str): Command to use for TTS (default: "say" for macOS)

**Example:**

```python
manager = ControlManager()
notifications = manager.check_notifications()
for notif in notifications:
    if notif.type == "refocus":
        manager.handle_refocus_notification(notif, speak_enabled=True)
```

---

#### `announce_accessible_name()`

Announce the accessible name of a focused element via text-to-speech.

**Signature:**
```python
def announce_accessible_name(
    self,
    accessible_name: str,
    role: str | None = None,
    announce_role: bool = False,
    speak_command: str = "say",
) -> None
```

**Parameters:**

- `accessible_name` (str): The accessible name to announce
- `role` (str | None): Element role (e.g., "button", "link")
- `announce_role` (bool): If True, prepend role to announcement
- `speak_command` (str): Command to use for TTS (default: "say" for macOS)

**Example:**

```python
manager = ControlManager()
manager.announce_accessible_name(
    "Submit",
    role="button",
    announce_role=True
)
# Speaks: "button, Submit"
```

---

#### `check_needs_restart()`

Check if control mode needs to be restarted (e.g., after navigation).

**Signature:**
```python
def check_needs_restart(self, result: dict[str, Any]) -> bool
```

**Parameters:**

- `result` (dict[str, Any]): Execution result from bridge

**Returns:**

- `bool`: True if restart is needed

**Example:**

```python
manager = ControlManager()
result = executor.execute(code)
if manager.check_needs_restart(result):
    # Reinitialize control mode
    pass
```

---

#### `format_restart_message()`

Get the restart message to display.

**Signature:**
```python
def format_restart_message(self, verbose: bool = False) -> str
```

**Parameters:**

- `verbose` (bool): If True, include more details

**Returns:**

- `str`: Formatted restart message

**Example:**

```python
manager = ControlManager()
msg = manager.format_restart_message(verbose=True)
print(msg)  # "🔄 Reinitializing control mode after navigation (verbose mode)…"
```

---

#### `format_success_message()`

Get the success message after restart.

**Signature:**
```python
def format_success_message(self, verbose: bool = False) -> str
```

**Parameters:**

- `verbose` (bool): If True, include more details

**Returns:**

- `str`: Formatted success message

**Example:**

```python
manager = ControlManager()
msg = manager.format_success_message(verbose=True)
print(msg)  # "✅ Control restored successfully!"
```

---

### Global Functions

#### `get_control_manager()`

Get the default control manager instance (singleton pattern).

**Signature:**
```python
def get_control_manager(
    host: str = "127.0.0.1",
    port: int = 8765,
) -> ControlManager
```

**Parameters:**

- `host` (str): Bridge server host
- `port` (int): Bridge server port

**Returns:**

- `ControlManager`: Shared ControlManager instance

**Example:**

```python
from inspekt.services.control_manager import get_control_manager

manager = get_control_manager()
notifications = manager.check_notifications()
```

---

## ScriptLoader

Loads and caches JavaScript scripts from the inspekt/scripts/ directory.

**Location:** `inspekt/services/script_loader.py`

### Purpose

- Load JavaScript files from inspekt/scripts/ directory
- Cache scripts in memory for performance
- Handle template substitution (placeholders)
- Provide both sync and async interfaces

### Class: `ScriptLoader`

Service for loading and caching JavaScript scripts.

```python
class ScriptLoader:
    def __init__(self, scripts_dir: Path | None = None):
        """Initialize script loader."""
```

**Parameters:**

- `scripts_dir` (Path | None): Directory containing JavaScript files. If None, uses inspekt/scripts/

---

### Methods

#### `get_script_path()`

Get full path to a script file.

**Signature:**
```python
def get_script_path(self, script_name: str) -> Path
```

**Parameters:**

- `script_name` (str): Name of script (e.g., "control.js")

**Returns:**

- `Path`: Full path to script

**Raises:**

- `FileNotFoundError`: If script does not exist

**Example:**

```python
loader = ScriptLoader()
path = loader.get_script_path("control.js")
```

---

#### `load_script_sync()`

Load script synchronously (for CLI use).

**Signature:**
```python
def load_script_sync(
    self,
    script_name: str,
    use_cache: bool = True
) -> str
```

**Parameters:**

- `script_name` (str): Name of script file (e.g., "control.js")
- `use_cache` (bool): If True, use cached version if available

**Returns:**

- `str`: Script contents as string

**Raises:**

- `FileNotFoundError`: If script does not exist

**Example:**

```python
loader = ScriptLoader()
script = loader.load_script_sync("control.js")
```

---

#### `load_script_async()`

Load script asynchronously (for server use).

**Signature:**
```python
async def load_script_async(
    self,
    script_name: str,
    use_cache: bool = True
) -> str
```

**Parameters:**

- `script_name` (str): Name of script file (e.g., "control.js")
- `use_cache` (bool): If True, use cached version if available

**Returns:**

- `str`: Script contents as string

**Raises:**

- `FileNotFoundError`: If script does not exist

**Example:**

```python
loader = ScriptLoader()
script = await loader.load_script_async("control.js")
```

---

#### `substitute_placeholders()`

Substitute placeholders in script with actual values.

**Signature:**
```python
def substitute_placeholders(
    self,
    script_content: str,
    placeholders: dict[str, Any]
) -> str
```

**Parameters:**

- `script_content` (str): Original script content
- `placeholders` (dict[str, Any]): Dictionary mapping placeholder names to values

**Returns:**

- `str`: Script with placeholders replaced

**Example:**

```python
loader = ScriptLoader()
script = "const action = 'ACTION_PLACEHOLDER';"
result = loader.substitute_placeholders(
    script,
    {"ACTION_PLACEHOLDER": "start"}
)
# Returns: "const action = 'start';"
```

---

#### `load_with_substitution_sync()`

Load script and substitute placeholders (sync).

**Signature:**
```python
def load_with_substitution_sync(
    self,
    script_name: str,
    placeholders: dict[str, Any],
    use_cache: bool = False
) -> str
```

**Parameters:**

- `script_name` (str): Name of script file
- `placeholders` (dict[str, Any]): Placeholder substitutions
- `use_cache` (bool): If True, use cached base script

**Returns:**

- `str`: Script with placeholders replaced

**Note:**

Scripts with substitutions are not cached (different per request)

**Example:**

```python
loader = ScriptLoader()
script = loader.load_with_substitution_sync(
    "cookies.js",
    {"ACTION_PLACEHOLDER": "get", "NAME_PLACEHOLDER": "session_id"}
)
```

---

#### `load_with_substitution_async()`

Load script and substitute placeholders (async).

**Signature:**
```python
async def load_with_substitution_async(
    self,
    script_name: str,
    placeholders: dict[str, Any],
    use_cache: bool = False
) -> str
```

**Parameters:**

- `script_name` (str): Name of script file
- `placeholders` (dict[str, Any]): Placeholder substitutions
- `use_cache` (bool): If True, use cached base script

**Returns:**

- `str`: Script with placeholders replaced

**Example:**

```python
loader = ScriptLoader()
script = await loader.load_with_substitution_async(
    "cookies.js",
    {"ACTION_PLACEHOLDER": "get"}
)
```

---

#### `preload_script()`

Preload script into cache (sync).

**Signature:**
```python
def preload_script(self, script_name: str) -> None
```

**Parameters:**

- `script_name` (str): Name of script to preload

**Raises:**

- `FileNotFoundError`: If script does not exist

**Example:**

```python
loader = ScriptLoader()
loader.preload_script("control.js")  # Now cached
```

---

#### `preload_script_async()`

Preload script into cache (async).

**Signature:**
```python
async def preload_script_async(self, script_name: str) -> None
```

**Parameters:**

- `script_name` (str): Name of script to preload

**Raises:**

- `FileNotFoundError`: If script does not exist

**Example:**

```python
loader = ScriptLoader()
await loader.preload_script_async("control.js")
```

---

#### `clear_cache()`

Clear the script cache.

**Signature:**
```python
def clear_cache(self) -> None
```

**Example:**

```python
loader = ScriptLoader()
loader.clear_cache()
```

---

#### `get_cached_scripts()`

Get list of cached script names.

**Signature:**
```python
def get_cached_scripts(self) -> list[str]
```

**Returns:**

- `list[str]`: List of script names currently in cache

**Example:**

```python
loader = ScriptLoader()
loader.preload_script("control.js")
cached = loader.get_cached_scripts()
print(cached)  # ["control.js"]
```

---

## Integration Patterns

### Using Multiple Services Together

Services are designed to work together. Here's a common pattern:

```python
from inspekt.services.bridge_executor import get_executor
from inspekt.services.ai_integration import get_ai_service
from inspekt.services.script_loader import ScriptLoader

# Get singleton instances
executor = get_executor()
ai_service = get_ai_service()
loader = ScriptLoader()

# Load and execute script
script = loader.load_script_sync("extract_page_structure.js")
result = executor.execute(script, timeout=30.0)

# Check result
executor.check_result_ok(result)

# Generate AI description
page_structure = result["result"]
description = ai_service.generate_description(page_structure)
print(description)
```

### Error Handling Pattern

All services follow consistent error handling:

```python
from inspekt.services.bridge_executor import get_executor

executor = get_executor()

# Ensure server running (exits if not)
executor.ensure_server_running()

# Execute with retry
result = executor.execute(
    "document.title",
    timeout=10.0,
    retry_on_timeout=True
)

# Check result (exits if error)
executor.check_result_ok(result)

# Use result
print(result["result"])
```

### Dependency Injection

Services accept dependencies for testability:

```python
from pathlib import Path
from inspekt.services.script_loader import ScriptLoader

# Custom scripts directory for testing
loader = ScriptLoader(scripts_dir=Path("/custom/scripts"))
script = loader.load_script_sync("test.js")
```

---

## See Also

- [Commands Reference](commands.md)
- [Models Reference](models.md)
- [Protocol Specification](protocol.md)
- [Architecture Guide](../development/architecture.md)
