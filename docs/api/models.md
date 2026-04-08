# Models API Reference

Complete reference for all Pydantic models used in Inspekt protocol and configuration.

---

## Overview

Inspekt uses Pydantic v2 for data validation and serialization. All models provide:

- Automatic validation
- Type safety
- JSON serialization/deserialization
- Clear error messages
- Documentation via field descriptions

**Model Categories:**

- [WebSocket Message Models](#websocket-message-models) - Protocol messages
- [HTTP API Models](#http-api-models) - REST API request/response
- [Configuration Models](#configuration-models) - Settings and config
- [Helper Functions](#helper-functions) - Utilities for message parsing

**Location:** `inspekt/domain/models.py`

---

## WebSocket Message Models

### ExecuteRequest

Request to execute JavaScript code in the browser.

**Direction:** Server → Browser

```python
class ExecuteRequest(BaseModel):
    type: Literal["execute"] = "execute"
    request_id: str = Field(..., description="UUID v4 identifying this request")
    code: str = Field(..., description="JavaScript code to evaluate")
    
    model_config = {"extra": "forbid"}
```

**Fields:**

- `type` (Literal["execute"]): Message type (always "execute")
- `request_id` (str): UUID v4 identifying this request
- `code` (str): JavaScript code to evaluate

**Validation:**

- Extra fields forbidden
- All fields required

**Example JSON:**

```json
{
  "type": "execute",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "code": "document.title"
}
```

**Python Usage:**

```python
from inspekt.domain.models import ExecuteRequest

request = ExecuteRequest(
    request_id="550e8400-e29b-41d4-a716-446655440000",
    code="document.title"
)
```

---

### ExecuteResult

Result of JavaScript code execution.

**Direction:** Browser → Server

```python
class ExecuteResult(BaseModel):
    type: Literal["result"] = "result"
    request_id: str = Field(..., description="UUID matching the execute request")
    ok: bool = Field(..., description="True if execution succeeded")
    result: Optional[Any] = Field(None, description="Return value from JavaScript")
    error: Optional[str] = Field(None, description="Error message if ok=False")
    url: Optional[str] = Field(None, description="Current page URL")
    title: Optional[str] = Field(None, description="Current page title")
    
    model_config = {"extra": "allow"}
```

**Fields:**

- `type` (Literal["result"]): Message type (always "result")
- `request_id` (str): UUID matching the execute request
- `ok` (bool): True if execution succeeded
- `result` (Optional[Any]): Return value from JavaScript (if ok=True)
- `error` (Optional[str]): Error message (if ok=False)
- `url` (Optional[str]): Current page URL
- `title` (Optional[str]): Current page title

**Validation:**

- Extra fields allowed (browser may send additional data)
- `request_id`, `ok` required
- `result` and `error` optional

**Example JSON (Success):**

```json
{
  "type": "result",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "ok": true,
  "result": "Example Domain",
  "url": "https://example.com",
  "title": "Example Domain"
}
```

**Example JSON (Error):**

```json
{
  "type": "result",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "ok": false,
  "error": "ReferenceError: foo is not defined"
}
```

**Python Usage:**

```python
from inspekt.domain.models import ExecuteResult

# Success
result = ExecuteResult(
    request_id="550e8400-e29b-41d4-a716-446655440000",
    ok=True,
    result="Example Domain",
    url="https://example.com",
    title="Example Domain"
)

# Error
error_result = ExecuteResult(
    request_id="550e8400-e29b-41d4-a716-446655440000",
    ok=False,
    error="ReferenceError: foo is not defined"
)
```

---

### ReinitControlRequest

Request to reinitialize control mode after page reload.

**Direction:** Browser → Server

```python
class ReinitControlRequest(BaseModel):
    type: Literal["reinit_control"] = "reinit_control"
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Control mode configuration"
    )
    
    model_config = {"extra": "forbid"}
```

**Fields:**

- `type` (Literal["reinit_control"]): Message type
- `config` (dict[str, Any]): Control mode configuration (default: empty dict)

**Validation:**

- Extra fields forbidden
- `config` defaults to empty dict if not provided

**Example JSON:**

```json
{
  "type": "reinit_control",
  "config": {
    "auto-refocus": "only-spa",
    "speak-name": false
  }
}
```

**Python Usage:**

```python
from inspekt.domain.models import ReinitControlRequest

request = ReinitControlRequest(
    config={"auto-refocus": "only-spa", "speak-name": False}
)
```

---

### RefocusNotification

Notification of refocus operation result.

**Direction:** Browser → Server

```python
class RefocusNotification(BaseModel):
    type: Literal["refocus_notification"] = "refocus_notification"
    success: bool = Field(..., description="Whether refocus succeeded")
    message: str = Field(..., description="Human-readable status message")
    
    model_config = {"extra": "forbid"}
```

**Fields:**

- `type` (Literal["refocus_notification"]): Message type
- `success` (bool): Whether refocus succeeded
- `message` (str): Human-readable status message

**Validation:**

- Extra fields forbidden
- All fields required

**Example JSON:**

```json
{
  "type": "refocus_notification",
  "success": true,
  "message": "Refocused to first interactive element"
}
```

**Python Usage:**

```python
from inspekt.domain.models import RefocusNotification

notification = RefocusNotification(
    success=True,
    message="Refocused to first interactive element"
)
```

---

### PingMessage

Keepalive ping message.

**Direction:** Browser → Server

```python
class PingMessage(BaseModel):
    type: Literal["ping"] = "ping"
    
    model_config = {"extra": "forbid"}
```

**Fields:**

- `type` (Literal["ping"]): Message type (always "ping")

**Example JSON:**

```json
{
  "type": "ping"
}
```

**Python Usage:**

```python
from inspekt.domain.models import PingMessage

ping = PingMessage()
```

---

### PongMessage

Keepalive pong response.

**Direction:** Server → Browser

```python
class PongMessage(BaseModel):
    type: Literal["pong"] = "pong"
    
    model_config = {"extra": "forbid"}
```

**Fields:**

- `type` (Literal["pong"]): Message type (always "pong")

**Example JSON:**

```json
{
  "type": "pong"
}
```

**Python Usage:**

```python
from inspekt.domain.models import PongMessage

pong = PongMessage()
```

---

### Message Union Types

```python
# Incoming messages (Browser → Server)
IncomingMessage = (
    ExecuteResult | ReinitControlRequest | RefocusNotification | PingMessage
)

# Outgoing messages (Server → Browser)
OutgoingMessage = ExecuteRequest | PongMessage
```

---

## HTTP API Models

### RunRequest

HTTP POST /run request body.

```python
class RunRequest(BaseModel):
    code: str = Field(..., min_length=1, description="JavaScript code to execute")
    
    model_config = {"extra": "forbid"}
```

**Fields:**

- `code` (str): JavaScript code to execute (min length: 1)

**Validation:**

- Extra fields forbidden
- `code` required and non-empty

**Example JSON:**

```json
{
  "code": "document.title"
}
```

**Python Usage:**

```python
from inspekt.domain.models import RunRequest

request = RunRequest(code="document.title")
```

---

### RunResponse

HTTP POST /run response.

```python
class RunResponse(BaseModel):
    ok: bool
    request_id: Optional[str] = None
    error: Optional[str] = None
    
    model_config = {"extra": "forbid"}
```

**Fields:**

- `ok` (bool): Whether request was accepted
- `request_id` (Optional[str]): Request ID if accepted
- `error` (Optional[str]): Error message if not accepted

**Example JSON (Success):**

```json
{
  "ok": true,
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Example JSON (Error):**

```json
{
  "ok": false,
  "error": "No browser connected"
}
```

---

### ResultResponse

HTTP GET /result response.

```python
class ResultResponse(BaseModel):
    ok: bool
    status: Optional[Literal["pending"]] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    url: Optional[str] = None
    title: Optional[str] = None
    
    model_config = {"extra": "allow"}
```

**Fields:**

- `ok` (bool): Whether result is available
- `status` (Optional[Literal["pending"]]): "pending" if still waiting
- `result` (Optional[Any]): Execution result
- `error` (Optional[str]): Error message if failed
- `url` (Optional[str]): Current page URL
- `title` (Optional[str]): Current page title

**Example JSON (Pending):**

```json
{
  "ok": false,
  "status": "pending"
}
```

**Example JSON (Complete):**

```json
{
  "ok": true,
  "result": "Example Domain",
  "url": "https://example.com",
  "title": "Example Domain"
}
```

---

### HealthResponse

HTTP GET /health response.

```python
class HealthResponse(BaseModel):
    ok: bool
    timestamp: float
    connected_browsers: int
    pending: int
    completed: int
    
    model_config = {"extra": "forbid"}
```

**Fields:**

- `ok` (bool): Server health status
- `timestamp` (float): Unix timestamp
- `connected_browsers` (int): Number of connected browsers
- `pending` (int): Number of pending requests
- `completed` (int): Number of completed requests

**Example JSON:**

```json
{
  "ok": true,
  "timestamp": 1698765432.123,
  "connected_browsers": 1,
  "pending": 0,
  "completed": 142
}
```

---

### Notification

Notification item.

```python
class Notification(BaseModel):
    type: str
    success: bool
    message: str
    timestamp: float
    
    model_config = {"extra": "allow"}
```

**Fields:**

- `type` (str): Notification type
- `success` (bool): Whether operation succeeded
- `message` (str): Human-readable message
- `timestamp` (float): Unix timestamp

**Example JSON:**

```json
{
  "type": "refocus",
  "success": true,
  "message": "Refocused to first interactive element",
  "timestamp": 1698765432.123
}
```

---

### NotificationsResponse

HTTP GET /notifications response.

```python
class NotificationsResponse(BaseModel):
    ok: bool
    notifications: list[Notification]
    
    model_config = {"extra": "forbid"}
```

**Fields:**

- `ok` (bool): Request success
- `notifications` (list[Notification]): List of notifications

**Example JSON:**

```json
{
  "ok": true,
  "notifications": [
    {
      "type": "refocus",
      "success": true,
      "message": "Refocused to first interactive element",
      "timestamp": 1698765432.123
    }
  ]
}
```

---

### ReinitControlHTTPRequest

HTTP POST /reinit-control request body.

```python
class ReinitControlHTTPRequest(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)
    
    model_config = {"extra": "forbid"}
```

**Fields:**

- `config` (dict[str, Any]): Control configuration (default: empty dict)

**Example JSON:**

```json
{
  "config": {
    "auto-refocus": "always",
    "speak-name": true
  }
}
```

---

## Configuration Models

### ControlConfig

Control mode configuration.

```python
class ControlConfig(BaseModel):
    auto_refocus: Literal["always", "only-spa", "never"] = Field(
        default="only-spa",
        alias="auto-refocus",
        description="When to automatically refocus after page changes",
    )
    
    focus_outline: Literal["custom", "original", "none"] = Field(
        default="custom",
        alias="focus-outline",
        description="Focus outline style",
    )
    
    speak_name: bool = Field(
        default=False,
        alias="speak-name",
        description="Speak element name via TTS",
    )
    
    speak_all: bool = Field(
        default=True,
        alias="speak-all",
        description="Speak all terminal output via TTS",
    )
    
    announce_role: bool = Field(
        default=False,
        alias="announce-role",
        description="Announce element role (button, link, etc.)",
    )
    
    announce_on_page_load: bool = Field(
        default=False,
        alias="announce-on-page-load",
        description="Announce page title on load",
    )
    
    navigation_wrap: bool = Field(
        default=True,
        alias="navigation-wrap",
        description="Wrap navigation at end of page",
    )
    
    scroll_on_focus: bool = Field(
        default=True,
        alias="scroll-on-focus",
        description="Scroll element into view on focus",
    )
    
    click_delay: int = Field(
        default=0,
        ge=0,
        alias="click-delay",
        description="Delay before click in milliseconds",
    )
    
    focus_color: str = Field(
        default="#0066ff",
        alias="focus-color",
        description="CSS color for focus outline",
    )
    
    focus_size: int = Field(
        default=3,
        ge=1,
        alias="focus-size",
        description="Focus outline size in pixels",
    )
    
    focus_animation: bool = Field(
        default=True,
        alias="focus-animation",
        description="Enable focus animation",
    )
    
    focus_glow: bool = Field(
        default=True,
        alias="focus-glow",
        description="Enable focus glow effect",
    )
    
    sound_on_focus: Literal["none", "beep", "click", "subtle"] = Field(
        default="none",
        alias="sound-on-focus",
        description="Sound to play on focus change",
    )
    
    selector_strategy: Literal["id-first", "aria-first", "css-first"] = Field(
        default="id-first",
        alias="selector-strategy",
        description="Strategy for element selection",
    )
    
    refocus_timeout: int = Field(
        default=2000,
        ge=100,
        alias="refocus-timeout",
        description="Timeout for refocus operations in milliseconds",
    )
    
    verbose: bool = Field(
        default=True,
        description="Show verbose terminal announcements",
    )
    
    verbose_logging: bool = Field(
        default=False,
        alias="verbose-logging",
        description="Enable verbose browser console logging",
    )
    
    model_config = {"extra": "forbid", "populate_by_name": True}
```

**All Fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `auto_refocus` | `"always"\|"only-spa"\|"never"` | `"only-spa"` | When to automatically refocus after page changes |
| `focus_outline` | `"custom"\|"original"\|"none"` | `"custom"` | Focus outline style |
| `speak_name` | `bool` | `False` | Speak element name via TTS |
| `speak_all` | `bool` | `True` | Speak all terminal output via TTS |
| `announce_role` | `bool` | `False` | Announce element role |
| `announce_on_page_load` | `bool` | `False` | Announce page title on load |
| `navigation_wrap` | `bool` | `True` | Wrap navigation at end of page |
| `scroll_on_focus` | `bool` | `True` | Scroll element into view on focus |
| `click_delay` | `int` | `0` | Delay before click in milliseconds (≥ 0) |
| `focus_color` | `str` | `"#0066ff"` | CSS color for focus outline |
| `focus_size` | `int` | `3` | Focus outline size in pixels (≥ 1) |
| `focus_animation` | `bool` | `True` | Enable focus animation |
| `focus_glow` | `bool` | `True` | Enable focus glow effect |
| `sound_on_focus` | `"none"\|"beep"\|"click"\|"subtle"` | `"none"` | Sound to play on focus change |
| `selector_strategy` | `"id-first"\|"aria-first"\|"css-first"` | `"id-first"` | Strategy for element selection |
| `refocus_timeout` | `int` | `2000` | Timeout for refocus operations in ms (≥ 100) |
| `verbose` | `bool` | `True` | Show verbose terminal announcements |
| `verbose_logging` | `bool` | `False` | Enable verbose browser console logging |

**Validation:**

- `focus_color`: Must be non-empty string (basic validation)
- `click_delay`: Must be ≥ 0
- `focus_size`: Must be ≥ 1
- `refocus_timeout`: Must be ≥ 100
- Supports both snake_case and kebab-case field names (via aliases)

**Example JSON:**

```json
{
  "auto-refocus": "always",
  "focus-outline": "custom",
  "speak-name": true,
  "speak-all": true,
  "announce-role": true,
  "navigation-wrap": true,
  "scroll-on-focus": true,
  "click-delay": 100,
  "focus-color": "#ff0000",
  "focus-size": 4,
  "focus-animation": true,
  "focus-glow": true,
  "sound-on-focus": "beep",
  "selector-strategy": "aria-first",
  "refocus-timeout": 3000,
  "verbose": true,
  "verbose-logging": false
}
```

**Python Usage:**

```python
from inspekt.domain.models import ControlConfig

# With defaults
config = ControlConfig()

# With custom values
config = ControlConfig(
    auto_refocus="always",
    speak_name=True,
    focus_color="#ff0000"
)

# From JSON (supports kebab-case)
import json
config_dict = json.loads('{"auto-refocus": "always", "speak-name": true}')
config = ControlConfig(**config_dict)
```

---

### InspektConfig

Complete Inspekt configuration.

```python
class InspektConfig(BaseModel):
    ai_language: str = Field(
        default="auto",
        alias="ai-language",
        description="Language for AI operations (auto, en, nl, fr, etc.)",
    )
    
    control: ControlConfig = Field(
        default_factory=ControlConfig,
        description="Control mode configuration",
    )
    
    model_config = {"extra": "allow", "populate_by_name": True}
```

**Fields:**

- `ai_language` (str): Language for AI operations (default: "auto")
- `control` (ControlConfig): Control mode configuration (default: ControlConfig())

**Validation:**

- `ai_language`: Must be non-empty string
- Extra fields allowed for future extensions
- Supports both snake_case and kebab-case

**Example JSON:**

```json
{
  "ai-language": "en",
  "control": {
    "auto-refocus": "always",
    "speak-name": true
  }
}
```

**Python Usage:**

```python
from inspekt.domain.models import InspektConfig, ControlConfig

# With defaults
config = InspektConfig()

# With custom values
config = InspektConfig(
    ai_language="en",
    control=ControlConfig(auto_refocus="always")
)

# From JSON file
import json
with open("config.json") as f:
    config_dict = json.load(f)
config = InspektConfig(**config_dict)
```

---

## Helper Functions

### parse_incoming_message()

Parse incoming WebSocket message based on type field.

**Signature:**
```python
def parse_incoming_message(data: dict[str, Any]) -> IncomingMessage
```

**Parameters:**

- `data` (dict[str, Any]): Raw message dictionary from WebSocket

**Returns:**

- `IncomingMessage`: Validated Pydantic model instance (ExecuteResult | ReinitControlRequest | RefocusNotification | PingMessage)

**Raises:**

- `ValueError`: If message type is unknown or validation fails

**Example:**

```python
from inspekt.domain.models import parse_incoming_message

raw_message = {
    "type": "result",
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "ok": True,
    "result": "Example Domain"
}

message = parse_incoming_message(raw_message)
# Returns: ExecuteResult instance

if message.type == "result":
    print(message.result)  # "Example Domain"
```

---

### create_execute_request()

Create an execute request message.

**Signature:**
```python
def create_execute_request(request_id: str, code: str) -> ExecuteRequest
```

**Parameters:**

- `request_id` (str): UUID for this request
- `code` (str): JavaScript code to execute

**Returns:**

- `ExecuteRequest`: Validated ExecuteRequest model

**Example:**

```python
from inspekt.domain.models import create_execute_request
import uuid

request = create_execute_request(
    request_id=str(uuid.uuid4()),
    code="document.title"
)
```

---

### create_pong_message()

Create a pong response message.

**Signature:**
```python
def create_pong_message() -> PongMessage
```

**Returns:**

- `PongMessage`: PongMessage instance

**Example:**

```python
from inspekt.domain.models import create_pong_message

pong = create_pong_message()
```

---

## Usage Examples

### Complete Request/Response Flow

```python
import uuid
from inspekt.domain.models import (
    create_execute_request,
    parse_incoming_message,
    ExecuteResult
)

# Create request
request_id = str(uuid.uuid4())
request = create_execute_request(
    request_id=request_id,
    code="document.title"
)

# Serialize to JSON
request_json = request.model_dump_json()

# Send to browser via WebSocket...
# Receive response...

# Parse response
response_data = {
    "type": "result",
    "request_id": request_id,
    "ok": True,
    "result": "Example Domain",
    "url": "https://example.com",
    "title": "Example Domain"
}

result = parse_incoming_message(response_data)

# Type-safe access
if isinstance(result, ExecuteResult):
    if result.ok:
        print(f"Success: {result.result}")
        print(f"URL: {result.url}")
    else:
        print(f"Error: {result.error}")
```

### Configuration Loading

```python
import json
from pathlib import Path
from inspekt.domain.models import InspektConfig

# Load from file
config_path = Path.home() / ".config" / "inspekt" / "config.json"
if config_path.exists():
    with open(config_path) as f:
        config_dict = json.load(f)
    config = InspektConfig(**config_dict)
else:
    # Use defaults
    config = InspektConfig()

# Access configuration
print(f"AI Language: {config.ai_language}")
print(f"Auto Refocus: {config.control.auto_refocus}")
print(f"Speak Name: {config.control.speak_name}")
```

### Validation Error Handling

```python
from pydantic import ValidationError
from inspekt.domain.models import ControlConfig

try:
    config = ControlConfig(
        click_delay=-1,  # Invalid: must be >= 0
        focus_size=0,    # Invalid: must be >= 1
    )
except ValidationError as e:
    print(e)
    # Shows detailed validation errors
```

---

## See Also

- [Commands Reference](commands.md)
- [Services Reference](services.md)
- [Protocol Specification](protocol.md)
- [Configuration Guide](../getting-started/configuration.md)
