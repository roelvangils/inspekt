# Security Review: Inspekt VM and Port Detection Changes

**Date**: 2025-12-16
**Reviewer**: Claude (Security Analysis)
**Scope**: Recent changes to VM infrastructure, port detection, file download functionality, and Chrome extension

---

## Executive Summary

The reviewed changes primarily implement:
1. Centralized port detection for VM vs normal environments
2. OSC 1337-based file download functionality for the VM terminal
3. Screencast (video recording) via Chrome DevTools Protocol
4. Download monitoring for recordings
5. Various CLI improvements

**Overall Risk Level**: LOW to MEDIUM

Most changes are well-designed for the sandboxed VM context. However, there are several findings that warrant attention.

---

## Detailed Findings

### 1. MEDIUM: Hardcoded API Key in Dockerfile

**File**: `docker/browser-vm/Dockerfile` (line 33)
```dockerfile
THOTH_API_KEY="f8ff6f65a4e1490f0aa3d2d5ff37cb2d40f3db4a0ea8ae115f00c78de325d115"
```

**Issue**: An API key is hardcoded in the Dockerfile. This key will be:
- Embedded in all built images
- Visible to anyone with access to the image
- Potentially exposed in Docker layer history

**Recommendation**:
- Pass the API key at runtime via environment variable: `docker run -e THOTH_API_KEY=xxx`
- Or use Docker secrets if using Docker Swarm/Compose

---

### 2. LOW: Removed Path Restrictions in Download Endpoint

**File**: `docker/browser-vm/control-server.py` (lines 734-771)

**Previous Code** (file-exists endpoint still has restrictions):
```python
allowed_prefixes = ['/root/', '/tmp/', '/home/', '/opt/inspekt/']
if not any(file_path.startswith(prefix) for prefix in allowed_prefixes):
    self.send_json({'ok': False, 'error': 'Path not allowed'}, 403)
```

**Current Code** (download endpoint):
```python
# Note: VM is sandboxed, so we allow any absolute path
# This enables downloading files from current working directory
file_path = os.path.abspath(file_path)

if not os.path.isfile(file_path):
    self.send_json({'ok': False, 'error': 'File not found'}, 404)
```

**Analysis**: The `/download` endpoint now allows downloading any file on the VM. This is intentional for VM usability (downloading files from any working directory), and the risk is mitigated by:
- The VM is a sandboxed Docker container
- The endpoint is only exposed to localhost (6080)
- The comment explicitly acknowledges the design decision

**Risk**: LOW (acceptable for sandboxed environment)

**Note**: The `/file-exists` endpoint still has path restrictions, creating an inconsistency. Consider documenting or aligning the security models.

---

### 3. INFO: VM Detection in Chrome Extension

**File**: `extensions/chrome/background.js` (lines 12-17)

```javascript
const isVMEnvironment = navigator.userAgent.includes('Linux') &&
                        (navigator.userAgent.includes('Chromium') || navigator.userAgent.includes('Chrome'));
const BRIDGE_HTTP_PORT = isVMEnvironment ? 8767 : 8765;
```

**Analysis**: This detection uses User-Agent sniffing which could theoretically be spoofed, but the impact is minimal:
- Worst case: wrong port is used, connection fails
- No security bypass possible
- This is detection logic, not authorization

**Risk**: INFORMATIONAL (no security impact)

---

### 4. LOW: Terminal Server Binds to All Interfaces

**File**: `docker/browser-vm/terminal-server.py` (line 201)

```python
async with serve(terminal_handler, "0.0.0.0", PORT):
```

**Analysis**: The WebSocket terminal server binds to `0.0.0.0:8889`. In the context of Docker with `--network host`, this exposes the terminal to the host machine.

**Mitigations**:
- Port 8889 is not listed in EXPOSE (but `--network host` bypasses EXPOSE)
- The VM is designed to be run locally, not exposed to the internet
- Users explicitly choose to run the VM

**Recommendation**: Document that the VM should never be exposed to untrusted networks. Consider binding to `127.0.0.1` only.

---

### 5. INFO: OSC 1337 Download Mechanism

**Files**:
- `inspekt/app/cli/util.py` (lines 41-76)
- `docker/browser-vm/control-panel.html` (lines 2510-2538)

**Flow**:
1. Python CLI emits: `\033]1337;download=/path/to/file\007`
2. xterm.js in control panel intercepts this sequence
3. Control panel fetches file via `/download?path=...` endpoint
4. Browser downloads the file

**Analysis**: This is a well-designed mechanism for the VM use case. The escape sequence is only interpreted by the control panel's xterm.js, not passed to other contexts.

**Security Properties**:
- Only works in the control panel terminal (INSPEKT_TERMINAL env check)
- File must exist on VM filesystem
- Download goes through authenticated browser session
- No code execution, just file transfer

**Risk**: INFORMATIONAL (good design)

---

### 6. LOW: CDP Debugger Access for Screencast

**File**: `extensions/chrome/background.js` (lines 1977-2175)

The screencast feature attaches a Chrome DevTools Protocol debugger to capture frames. This is a powerful capability that:
- Requires the extension to have `debugger` permission
- Only attaches when explicitly requested (START_SCREENCAST message)
- Properly detaches on stop or error

**Analysis**: This is necessary functionality for video recording. The implementation follows Chrome's debugger API correctly with proper cleanup.

**Risk**: LOW (necessary for feature, properly implemented)

---

### 7. INFO: Script Injection Method Change

**File**: `extensions/chrome/background.js` (lines 2238-2281)

**Previous**:
```javascript
const fn = new Function(scriptCode);
fn();
```

**New**:
```javascript
const script = document.createElement('script');
script.textContent = scriptCode;
(document.head || document.documentElement).appendChild(script);
script.remove();
```

**Analysis**: This change improves CSP compatibility. The new method:
- Creates a script element dynamically
- Works on pages with strict CSP (since extension scripts are privileged)
- Falls back to `new Function()` if script element fails

This is a security improvement for compatibility, not a security weakness.

**Risk**: INFORMATIONAL (improvement)

---

### 8. INFO: Atomic Config File Writing

**File**: `inspekt/config.py` (lines 826-869)

```python
# Atomic write: write to temp file, then rename
with tempfile.NamedTemporaryFile(mode="w", dir=config_file.parent, ...) as f:
    json.dump(config, f, indent=2)
shutil.move(str(temp_path), str(config_file))
```

**Analysis**: Good security practice. Atomic writes prevent:
- Partial file writes on crash
- Race conditions during config updates
- Data loss from interrupted writes

**Risk**: INFORMATIONAL (good practice)

---

### 9. INFO: Bounds Validation on Viewport Offsets

**File**: `inspekt/config.py` (lines 742-752, 789-794)

```python
# Validate bounds: offsets must be 0-1000px
if 0 <= width_offset <= 1000 and 0 <= height_offset <= 1000:
    return {"width": width, "height": height}
```

**Analysis**: Good input validation prevents storing corrupted or malicious values that could cause integer overflow or other issues downstream.

**Risk**: INFORMATIONAL (good practice)

---

## Recommendations Summary

| Priority | Finding | Recommendation |
|----------|---------|----------------|
| MEDIUM | Hardcoded API key | Move to runtime environment variable |
| LOW | Terminal binds to 0.0.0.0 | Document network exposure risks |
| LOW | Inconsistent path restrictions | Align /file-exists and /download security models |
| INFO | All other findings | No action required |

---

## Files Reviewed

- `docker/browser-vm/Dockerfile`
- `docker/browser-vm/control-server.py`
- `docker/browser-vm/terminal-server.py`
- `docker/browser-vm/control-panel.html`
- `extensions/chrome/background.js`
- `inspekt/config.py`
- `inspekt/client.py`
- `inspekt/app/cli/util.py`
- `inspekt/services/screencast.py`
- `inspekt/services/bridge_executor.py`
- `inspekt/app/mcp/tools.py`

---

## Conclusion

The reviewed changes are generally well-implemented with appropriate security considerations for a sandboxed VM environment. The main actionable item is removing the hardcoded API key from the Dockerfile. Other findings are either low-risk design decisions appropriate for the use case or informational notes about good practices already in place.
