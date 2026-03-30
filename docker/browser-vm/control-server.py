#!/usr/bin/env python3
"""
Simple control server for Inspekt Browser VM.
Provides API endpoints to control the VM from the web interface.
Uses Chrome DevTools Protocol (CDP) for browser navigation in kiosk mode.
"""

import asyncio
import html as html_module
import json
import os
import shlex
import subprocess
import threading
import time
import urllib.request
import urllib.error

import websockets
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote, unquote

PORT = 8888
CDP_PORT = 9222
DISPLAY = os.environ.get('DISPLAY', ':0')

# In-memory thumbnail cache: {tab_id: {'data': base64_string, 'timestamp': float}}
thumbnails = {}

# In-memory scan data cache: {tab_id: {'timestamp', 'a11y_violations', 'console_errors', 'missing_alt', ...}}
tab_scan_data = {}

# Track last inspekt command per tab: {tab_id: command_name}
last_commands = {}

# Auto-scan setting (persisted in memory only)
auto_scan_enabled = False

# Terminal visibility state (for recording workflow)
# When True, control panel should hide the terminal overlay
terminal_hidden = False

# Clipboard relay: CLI posts text here, control panel fetches it
clipboard_data = {'text': '', 'timestamp': 0}

# Screen reader simulator state
sr_state = {
    'active': False,
    'screen_reader': None,
    'verbosity': 'high',
    'script_injected': False,  # Whether the SR script has been injected into the current tab
    'tab_ws_url': None,  # WebSocket URL of the tab where SR is active
}


# Cache for the prepared SR script (data injected, CONFIG placeholder remaining)
_sr_script_cache = None


def _get_sr_base_path():
    """Get the base path for SR scripts and data, supporting dev mode."""
    # Dev mode: source repo mounted at /opt/inspekt
    dev_path = '/opt/inspekt/inspekt'
    if os.path.exists(os.path.join(dev_path, 'scripts', 'screen_reader_simulator.js')):
        return dev_path
    # Fallback: installed package
    return '/opt/inspekt/.venv/lib/python3.12/site-packages/inspekt'


def _load_sr_script():
    """Load and prepare the SR simulator script with data (cached after first call)."""
    global _sr_script_cache
    if _sr_script_cache is not None:
        return _sr_script_cache

    base = _get_sr_base_path()
    scripts_dir = os.path.join(base, 'scripts')
    data_dir = os.path.join(base, 'data', 'screen-reader-rules')

    with open(os.path.join(scripts_dir, 'screen_reader_simulator.js')) as f:
        script = f.read()
    with open(os.path.join(data_dir, 'announcements.json')) as f:
        announcements = f.read()
    with open(os.path.join(data_dir, 'verbosity-levels.json')) as f:
        verbosity = f.read()
    with open(os.path.join(data_dir, 'known-bugs.json')) as f:
        known_bugs = f.read()

    script = script.replace('__SR_ANNOUNCEMENTS__', announcements)
    script = script.replace('__SR_VERBOSITY__', verbosity)
    script = script.replace('__SR_KNOWN_BUGS__', known_bugs)

    _sr_script_cache = script
    return script


def _sr_execute(ws_url, config):
    """Execute a screen reader simulator command via CDP."""
    script = _load_sr_script()
    # Only replace the CONFIG placeholder per call (script body is cached)
    script = script.replace('__SR_CONFIG__', json.dumps(config))

    result = send_cdp_command(ws_url, 'Runtime.evaluate', {
        'expression': script,
        'returnByValue': True,
        'awaitPromise': True,
    })

    value = result.get('result', {}).get('result', {}).get('value')
    if value is None:
        error = result.get('result', {}).get('exceptionDetails', {})
        return {'ok': False, 'error': str(error) if error else 'No result returned'}
    return value


def _sr_get_keyboard_commands():
    """Load keyboard commands data for the control panel."""
    base = _get_sr_base_path()
    data_dir = os.path.join(base, 'data', 'screen-reader-rules')
    with open(os.path.join(data_dir, 'keyboard-commands.json')) as f:
        return json.load(f)


def get_cdp_tabs():
    """Get list of Chrome tabs from CDP."""
    try:
        with urllib.request.urlopen(f'http://localhost:{CDP_PORT}/json', timeout=2) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return []


def get_active_tab():
    """Get the first page-type tab (the active tab in kiosk mode)."""
    tabs = get_cdp_tabs()
    for tab in tabs:
        if tab.get('type') == 'page':
            return tab
    return None


def get_page_tabs():
    """Get all page-type tabs (excluding extensions, service workers, etc.)."""
    tabs = get_cdp_tabs()
    return [t for t in tabs if t.get('type') == 'page']


def get_tab_by_id(tab_id):
    """Get a specific tab by its ID."""
    tabs = get_cdp_tabs()
    for tab in tabs:
        if tab.get('id') == tab_id:
            return tab
    return None


def get_requested_tab(query_params):
    """Get tab by explicit ID from query params, or fall back to first page tab."""
    tab_id = query_params.get('tab', [None])[0]
    if tab_id:
        tab = get_tab_by_id(tab_id)
        if tab:
            return tab
    return get_active_tab()


def cleanup_thumbnails():
    """Remove thumbnails for tabs that no longer exist."""
    active_tab_ids = {t['id'] for t in get_page_tabs()}
    for tab_id in list(thumbnails.keys()):
        if tab_id not in active_tab_ids:
            del thumbnails[tab_id]


def cleanup_scan_data():
    """Remove scan data for tabs that no longer exist."""
    active_tab_ids = {t['id'] for t in get_page_tabs()}
    for tab_id in list(tab_scan_data.keys()):
        if tab_id not in active_tab_ids:
            del tab_scan_data[tab_id]
    for tab_id in list(last_commands.keys()):
        if tab_id not in active_tab_ids:
            del last_commands[tab_id]


def scan_tab(tab_id):
    """Run lightweight accessibility scan on a tab using CDP Runtime.evaluate."""
    tab = get_tab_by_id(tab_id)
    if not tab or not tab.get('webSocketDebuggerUrl'):
        return None

    # JavaScript to gather accessibility-focused metrics
    js_code = '''
    (() => {
        // Get console errors from Inspekt hooks if available
        const consoleBuffer = window.__INSPEKT_CONSOLE_LOGS__ || [];
        const consoleErrors = consoleBuffer.filter(l => l.level === 'error').length;

        // Count images missing alt text
        const missingAlt = document.querySelectorAll('img:not([alt]), img[alt=""]').length;

        // Quick accessibility heuristics (not full axe audit)
        let a11yIssues = 0;
        // Links without text
        a11yIssues += document.querySelectorAll('a:not([aria-label]):not([aria-labelledby])').length -
                      [...document.querySelectorAll('a:not([aria-label]):not([aria-labelledby])')].filter(a => a.textContent.trim()).length;
        // Buttons without accessible names
        a11yIssues += document.querySelectorAll('button:not([aria-label]):not([aria-labelledby])').length -
                      [...document.querySelectorAll('button:not([aria-label]):not([aria-labelledby])')].filter(b => b.textContent.trim()).length;
        // Form inputs without labels
        a11yIssues += [...document.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="button"])')].filter(i => {
            const id = i.id;
            const hasLabel = id && document.querySelector(`label[for="${id}"]`);
            const hasAriaLabel = i.getAttribute('aria-label') || i.getAttribute('aria-labelledby');
            return !hasLabel && !hasAriaLabel;
        }).length;

        return {
            a11y_violations: a11yIssues,
            console_errors: consoleErrors,
            missing_alt: missingAlt,
            title: document.title,
            url: location.href
        };
    })()
    '''

    try:
        result = send_cdp_command(
            tab['webSocketDebuggerUrl'],
            'Runtime.evaluate',
            {
                'expression': js_code,
                'returnByValue': True
            }
        )

        if result and 'result' in result and 'result' in result['result']:
            scan_result = result['result']['result'].get('value', {})
            # Cache the scan data
            tab_scan_data[tab_id] = {
                'timestamp': time.time(),
                'a11y_violations': scan_result.get('a11y_violations', 0),
                'console_errors': scan_result.get('console_errors', 0),
                'missing_alt': scan_result.get('missing_alt', 0),
                'title': scan_result.get('title', ''),
                'url': scan_result.get('url', '')
            }
            return tab_scan_data[tab_id]
    except Exception as e:
        print(f"[control-server] Tab scan failed: {e}")

    return None


def capture_tab_screenshot(tab_id):
    """Capture a screenshot of a tab using CDP and cache it."""
    tab = get_tab_by_id(tab_id)
    if not tab or not tab.get('webSocketDebuggerUrl'):
        return None

    try:
        # Capture screenshot via CDP
        result = send_cdp_command(
            tab['webSocketDebuggerUrl'],
            'Page.captureScreenshot',
            {
                'format': 'jpeg',
                'quality': 60,
                'captureBeyondViewport': False
            }
        )

        if result and 'result' in result and 'data' in result['result']:
            # Cache the screenshot
            thumbnails[tab_id] = {
                'data': result['result']['data'],
                'timestamp': time.time()
            }
            return thumbnails[tab_id]['data']
    except Exception as e:
        print(f"[control-server] Screenshot capture failed: {e}")

    return None


def cdp_request(endpoint, method='GET'):
    """Make a request to CDP HTTP endpoint."""
    try:
        req = urllib.request.Request(
            f'http://localhost:{CDP_PORT}{endpoint}',
            method=method
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.read().decode()
    except Exception as e:
        return None


# CDP WebSocket connection pool: {ws_url: (event_loop, websocket, lock)}
_cdp_connections = {}
_cdp_lock = threading.Lock()
_cdp_msg_id = 0


def _get_or_create_cdp_connection(ws_url):
    """Get existing pooled connection or create a new one. Caller must hold _cdp_lock."""
    if ws_url in _cdp_connections:
        loop, ws, lock = _cdp_connections[ws_url]
        # Check if connection is still open (compatible with both old and new websockets)
        try:
            is_open = ws.open
        except AttributeError:
            # websockets v14+ removed .open; check .state instead
            from websockets.protocol import State as WsState
            is_open = (ws.state == WsState.OPEN)
        if is_open:
            return loop, ws, lock
        # Connection closed, clean up
        del _cdp_connections[ws_url]

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    ws = loop.run_until_complete(
        asyncio.wait_for(websockets.connect(ws_url), timeout=3)
    )
    lock = threading.Lock()
    _cdp_connections[ws_url] = (loop, ws, lock)
    return loop, ws, lock


def send_cdp_command(ws_url, method, params=None):
    """Send a CDP command via a pooled WebSocket connection."""
    global _cdp_msg_id

    with _cdp_lock:
        loop, ws, lock = _get_or_create_cdp_connection(ws_url)

    with lock:
        asyncio.set_event_loop(loop)
        _cdp_msg_id += 1
        msg = {'id': _cdp_msg_id, 'method': method, 'params': params or {}}
        try:
            loop.run_until_complete(ws.send(json.dumps(msg)))
            response = loop.run_until_complete(
                asyncio.wait_for(ws.recv(), timeout=5)
            )
            return json.loads(response)
        except Exception:
            # Connection broken — evict from pool and retry once
            with _cdp_lock:
                _cdp_connections.pop(ws_url, None)
                try:
                    loop.run_until_complete(ws.close())
                except Exception:
                    pass
            raise


def cleanup_cdp_connections():
    """Close pooled CDP connections for tabs that no longer exist."""
    active_ws_urls = {t.get('webSocketDebuggerUrl') for t in get_page_tabs()}
    with _cdp_lock:
        for ws_url in list(_cdp_connections.keys()):
            if ws_url not in active_ws_urls:
                loop, ws, _ = _cdp_connections.pop(ws_url)
                try:
                    loop.run_until_complete(ws.close())
                except Exception:
                    pass

def get_tab_theme_color(tab):
    """Extract theme color from a tab via CDP Runtime.evaluate.

    Priority: <meta name="theme-color"> → html background-color → body background-color.
    Returns hex color string or None.
    """
    ws_url = tab.get('webSocketDebuggerUrl')
    if not ws_url:
        return None

    js_code = '''
(() => {
    // 1. Check <meta name="theme-color">
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta && meta.content) return meta.content.trim();

    // Helper: check if a color is usable (not transparent/unset)
    function isUsable(c) {
        if (!c || c === 'transparent' || c === 'initial' || c === 'inherit') return false;
        if (c === 'rgba(0, 0, 0, 0)') return false;
        return true;
    }

    // 2. Check <html> background-color
    const htmlBg = getComputedStyle(document.documentElement).backgroundColor;
    if (isUsable(htmlBg)) return htmlBg;

    // 3. Check <body> background-color
    const bodyBg = getComputedStyle(document.body).backgroundColor;
    if (isUsable(bodyBg)) return bodyBg;

    return null;
})()
'''
    try:
        result = send_cdp_command(ws_url, 'Runtime.evaluate', {
            'expression': js_code,
            'returnByValue': True
        })
        value = result.get('result', {}).get('result', {}).get('value')
        return value
    except Exception:
        return None


class ControlHandler(BaseHTTPRequestHandler):
    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _proxy_to_api(self, method='GET'):
        """Reverse proxy request to the Inspekt API server (port 80).

        Handles /internal/* and /api/* paths, forwarding the full request
        (including body for POST/PUT/DELETE) to the upstream API.
        """
        parsed = urlparse(self.path)
        path = parsed.path
        query_string = parsed.query

        # Determine upstream path
        if path.startswith('/internal/'):
            upstream_path = path[len('/internal'):]  # keep leading slash
        elif path.startswith('/api/'):
            upstream_path = path  # /api/plugins → /api/plugins
        else:
            return False  # not a proxy path

        upstream_url = f'http://localhost:80{upstream_path}'
        if query_string:
            upstream_url += f'?{query_string}'

        try:
            # Read request body for POST/PUT/DELETE
            body = None
            if method in ('POST', 'PUT', 'DELETE'):
                content_length = int(self.headers.get('Content-Length', 0))
                if content_length > 0:
                    body = self.rfile.read(content_length)

            req = urllib.request.Request(upstream_url, data=body, method=method)
            # Forward Content-Type header
            content_type = self.headers.get('Content-Type')
            if content_type:
                req.add_header('Content-Type', content_type)

            with urllib.request.urlopen(req, timeout=30) as resp:
                resp_body = resp.read()
                self.send_response(resp.status)
                self.send_header('Access-Control-Allow-Origin', '*')
                # Forward relevant response headers
                for header in ('Content-Type', 'Content-Disposition', 'Cache-Control', 'ETag'):
                    val = resp.headers.get(header)
                    if val:
                        self.send_header(header, val)
                self.end_headers()
                self.wfile.write(resp_body)
        except urllib.error.HTTPError as e:
            resp_body = e.read() if hasattr(e, 'read') else b''
            self.send_response(e.code)
            self.send_header('Content-Type', e.headers.get('Content-Type', 'text/html'))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(resp_body)
        except Exception as e:
            error_msg = html_module.escape(str(e))
            html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Proxy Error</title>
<style>body {{ font-family: system-ui; padding: 2rem; }} h1 {{ color: #e74c3c; }}</style>
</head><body><h1>Failed to reach Inspekt API</h1><p>{error_msg}</p></body></html>"""
            self.send_response(502)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(html.encode())
        return True

    def do_OPTIONS(self):
        self.send_json({})

    def do_GET(self):
        path = urlparse(self.path).path

        if path == '/':
            # Serve the control panel HTML
            try:
                with open('/usr/share/novnc/control.html', 'r') as f:
                    html = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(html.encode())
            except Exception as e:
                self.send_json({'error': str(e)}, 500)

        elif path == '/health':
            self.send_json({'ok': True, 'service': 'control-server'})

        elif path == '/api/tunnel-info':
            # Return bore tunnel server info for `inspekt tunnel` auto-discovery
            secret = ''
            try:
                with open('/tmp/.bore_secret', 'r') as f:
                    secret = f.read().strip()
            except FileNotFoundError:
                pass
            self.send_json({
                'ok': True,
                'secret': secret,
                'port': 7835,
            })

        elif path == '/dev-mode':
            # Check if running in development mode (source files mounted from host)
            is_dev = os.environ.get('INSPEKT_DEV_MODE') == '1'
            self.send_json({'ok': True, 'dev_mode': is_dev})

        elif path == '/terminal':
            # Web terminal is now handled by xterm.js in control-panel.html
            # This endpoint just returns status info
            self.send_json({
                'ok': True,
                'message': 'Terminal is available via web interface (press ` to toggle)'
            })

        elif path == '/chrome':
            try:
                # Check if Chrome is running
                result = subprocess.run(['pgrep', '-f', 'chromium'], capture_output=True)
                if result.returncode != 0:
                    # Start Chrome
                    subprocess.Popen(
                        ['/usr/bin/chromium',
                         '--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage',
                         '--no-first-run', '--start-maximized',
                         '--load-extension=/opt/inspekt/extensions/chrome',
                         'https://example.com'],
                        env={**os.environ, 'DISPLAY': DISPLAY},
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    self.send_json({'ok': True, 'message': 'Chrome started'})
                else:
                    # Chrome is running, focus it
                    subprocess.run(
                        ['xdotool', 'search', '--name', 'Chromium', 'windowactivate'],
                        env={**os.environ, 'DISPLAY': DISPLAY},
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    self.send_json({'ok': True, 'message': 'Chrome focused'})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/chrome/click':
            # Focus Chrome AND simulate clicks in the viewport
            # Note: This helps with VM-side focus but browser-side VNC canvas
            # still needs a real user click due to browser security restrictions
            try:
                env = {**os.environ, 'DISPLAY': DISPLAY}

                # Focus the Chromium window
                subprocess.run(
                    ['xdotool', 'search', '--name', 'Chromium', 'windowactivate'],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

                # Small delay for window activation
                time.sleep(0.1)

                # Click in a safe area (upper-left of content area, avoiding toolbars)
                # Using fixed coordinates that should be in the page content area
                # after Chromium's toolbar (~100px from top, ~100px from left)
                x, y = 200, 200

                # Double-click with delay - some VNC clients need this
                subprocess.run(
                    ['xdotool', 'mousemove', str(x), str(y), 'click', '1'],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                time.sleep(0.3)
                subprocess.run(
                    ['xdotool', 'click', '1'],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

                self.send_json({'ok': True, 'message': 'Chrome focused and double-clicked'})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/restart':
            try:
                # Kill and restart Chrome
                subprocess.run(['pkill', '-f', 'chromium'], capture_output=True)

                # Restart Chrome
                subprocess.Popen(
                    ['/usr/bin/chromium',
                     '--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage',
                     '--no-first-run', '--start-maximized',
                     '--load-extension=/opt/inspekt/extensions/chrome',
                     'https://example.com'],
                    env={**os.environ, 'DISPLAY': DISPLAY},
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                self.send_json({'ok': True, 'message': 'Services restarted'})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/reboot':
            try:
                # Send response first, then reboot
                self.send_json({'ok': True, 'message': 'VM rebooting...'})
                # Use supervisorctl to restart all services (soft reboot)
                subprocess.Popen(
                    ['supervisorctl', 'restart', 'all'],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/hard-reboot':
            try:
                # Send response first
                self.send_json({'ok': True, 'message': 'Hard reboot initiated...'})
                # Use supervisorctl shutdown to gracefully stop all services
                # This causes supervisord to exit → shell exits → tini exits → container stops
                # Docker will restart the container if run with --restart unless-stopped
                subprocess.Popen(
                    ['supervisorctl', 'shutdown'],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path.startswith('/inspekt/'):
            raw_command = unquote(path.split('/inspekt/')[1])

            # Structured allowlist: base_command -> {subcommand -> [flags]}
            # Simple commands (no subcommands) use an empty dict.
            # Flag '__positional__' means the subcommand accepts one positional argument
            # (e.g. `ask "what color is it?"`) — the first non-flag token is treated as that arg.
            allowed_commands = {
                'info': {},
                'axe': {},
                'links': {},
                'outline': {},
                'screenshot': {},
                'url': {},
                'describe': {'__positional__': True, '__flags__': ['--json', '--debug']},
                'ask': {'__positional__': True, '__flags__': ['--debug', '--no-cache']},
                'selection': {
                    'text': ['--raw', '--json'],
                    'html': ['--raw', '--json', '--compact'],
                    'markdown': ['--raw', '--json'],
                    'describe': ['--json', '--debug'],
                    'ask': ['--json', '--debug', '__positional__'],
                },
                'inspected': {
                    'html': ['--raw', '--json'],
                    'text': ['--raw', '--json'],
                    'markdown': ['--raw', '--json'],
                    'css': ['--raw', '--json'],
                    'describe': ['--json', '--debug'],
                    'ask': ['--json', '--debug', '__positional__'],
                },
                'extract': {
                    'article': ['--raw', '--json'],
                },
            }

            # Parse and validate each token
            tokens = shlex.split(raw_command)
            if not tokens or tokens[0] not in allowed_commands:
                self.send_json({'ok': False, 'error': 'Command not allowed'}, 400)
                return

            base_cmd = tokens[0]
            subcmds = allowed_commands[base_cmd]

            if isinstance(subcmds, dict) and subcmds.get('__positional__'):
                # Simple command that takes an optional positional argument (e.g. describe, ask)
                # Allow: `describe`, `describe --json`, `ask "question" --debug`
                allowed_flags = subcmds.get('__flags__', ['--json'])
                extra_tokens = tokens[1:]
                # Separate positional arg from flags
                positional_found = False
                for t in extra_tokens:
                    if not t.startswith('--'):
                        if positional_found:
                            self.send_json({'ok': False, 'error': 'Too many positional arguments'}, 400)
                            return
                        positional_found = True
                    elif t not in allowed_flags:
                        self.send_json({'ok': False, 'error': 'Flag not allowed'}, 400)
                        return
            elif subcmds:
                # Command requires a subcommand
                if len(tokens) < 2 or tokens[1] not in subcmds:
                    self.send_json({'ok': False, 'error': 'Subcommand not allowed'}, 400)
                    return
                allowed_flags = subcmds[tokens[1]]
                extra_tokens = tokens[2:]

                if '__positional__' in allowed_flags:
                    # This subcommand accepts a positional argument (e.g. `selection ask "question" --raw`)
                    flag_list = [f for f in allowed_flags if f != '__positional__']
                    positional_found = False
                    for t in extra_tokens:
                        if not t.startswith('--'):
                            if positional_found:
                                self.send_json({'ok': False, 'error': 'Too many positional arguments'}, 400)
                                return
                            positional_found = True
                        elif t not in flag_list:
                            self.send_json({'ok': False, 'error': 'Flag not allowed'}, 400)
                            return
                else:
                    if any(t not in allowed_flags for t in extra_tokens):
                        self.send_json({'ok': False, 'error': 'Flag not allowed'}, 400)
                        return
            else:
                # Simple command — no subcommands expected, no extra tokens allowed
                allowed_flags = []
                extra_tokens = tokens[1:]
                if any(t not in allowed_flags for t in extra_tokens):
                    self.send_json({'ok': False, 'error': 'Flag not allowed'}, 400)
                    return

            # Build safe command string from validated tokens
            safe_command = ' '.join(shlex.quote(t) for t in tokens)

            try:
                # Track last command for the active tab
                tab = get_active_tab()
                if tab:
                    last_commands[tab['id']] = base_cmd

                # AI commands (describe, ask) can take 10-30s; use longer timeout
                ai_commands = {'describe', 'ask'}
                is_ai = base_cmd in ai_commands or (len(tokens) >= 2 and tokens[1] in ai_commands)
                cmd_timeout = 60 if is_ai else 30

                result = subprocess.run(
                    ['bash', '-c', f'cd /opt/inspekt && . .venv/bin/activate && inspekt {safe_command}'],
                    capture_output=True,
                    text=True,
                    timeout=cmd_timeout
                )
                self.send_json({
                    'ok': result.returncode == 0,
                    'output': result.stdout,
                    'error': result.stderr if result.returncode != 0 else None
                })
            except subprocess.TimeoutExpired:
                self.send_json({'ok': False, 'error': 'Command timed out'}, 500)
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        # =============================================
        # Browser Navigation Endpoints (using CDP)
        # =============================================

        elif path == '/history':
            try:
                query = parse_qs(urlparse(self.path).query)
                tab = get_requested_tab(query)
                if not tab:
                    self.send_json({'ok': False, 'error': 'No active tab found'}, 500)
                    return
                result = send_cdp_command(tab['webSocketDebuggerUrl'], 'Page.getNavigationHistory')
                nav = result.get('result', {})
                current_index = nav.get('currentIndex', 0)
                entries = nav.get('entries', [])
                seen = {}
                for entry in entries:
                    seen[entry.get('url', '')] = {
                        'url': entry.get('url', ''),
                        'title': entry.get('title', ''),
                    }
                recent = list(seen.values())[-15:]
                recent.reverse()

                self.send_json({
                    'ok': True,
                    'currentIndex': current_index,
                    'entryCount': len(entries),
                    'canGoBack': current_index > 0,
                    'canGoForward': current_index < len(entries) - 1,
                    'entries': recent
                })
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/back':
            try:
                query = parse_qs(urlparse(self.path).query)
                tab = get_requested_tab(query)
                if not tab:
                    self.send_json({'ok': False, 'error': 'No active tab found'}, 500)
                    return
                result = send_cdp_command(tab['webSocketDebuggerUrl'], 'Page.getNavigationHistory')
                nav = result.get('result', {})
                current_index = nav.get('currentIndex', 0)
                entries = nav.get('entries', [])
                if current_index > 0:
                    target = entries[current_index - 1]
                    send_cdp_command(tab['webSocketDebuggerUrl'], 'Page.navigateToHistoryEntry', {'entryId': target['id']})
                    self.send_json({'ok': True, 'message': 'Navigated back', 'canGoBack': current_index - 1 > 0, 'canGoForward': True})
                else:
                    self.send_json({'ok': False, 'error': 'Already at first page'})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/forward':
            try:
                query = parse_qs(urlparse(self.path).query)
                tab = get_requested_tab(query)
                if not tab:
                    self.send_json({'ok': False, 'error': 'No active tab found'}, 500)
                    return
                result = send_cdp_command(tab['webSocketDebuggerUrl'], 'Page.getNavigationHistory')
                nav = result.get('result', {})
                current_index = nav.get('currentIndex', 0)
                entries = nav.get('entries', [])
                if current_index < len(entries) - 1:
                    target = entries[current_index + 1]
                    send_cdp_command(tab['webSocketDebuggerUrl'], 'Page.navigateToHistoryEntry', {'entryId': target['id']})
                    self.send_json({'ok': True, 'message': 'Navigated forward', 'canGoBack': True, 'canGoForward': current_index + 1 < len(entries) - 1})
                else:
                    self.send_json({'ok': False, 'error': 'Already at last page'})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/reload-page':
            try:
                query = parse_qs(urlparse(self.path).query)
                tab = get_requested_tab(query)
                if not tab:
                    self.send_json({'ok': False, 'error': 'No active tab found'}, 500)
                    return
                send_cdp_command(tab['webSocketDebuggerUrl'], 'Page.reload')
                self.send_json({'ok': True, 'message': 'Page reloaded'})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/url':
            try:
                query = parse_qs(urlparse(self.path).query)
                tab = get_requested_tab(query)
                if not tab:
                    self.send_json({'ok': False, 'error': 'No active tab found'}, 500)
                    return
                self.send_json({'ok': True, 'url': tab.get('url', ''), 'title': tab.get('title', '')})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/page-info':
            try:
                query = parse_qs(urlparse(self.path).query)
                tab = get_requested_tab(query)
                if not tab or not tab.get('webSocketDebuggerUrl'):
                    self.send_json({'ok': False, 'error': 'No active tab found'}, 500)
                    return

                js_code = r'''(() => {
    const result = {};

    // Summary
    result.summary = {
        url: location.href,
        title: document.title,
        domain: location.hostname,
        protocol: location.protocol,
        readyState: document.readyState,
        width: window.innerWidth,
        height: window.innerHeight,
        device: {
            platform: navigator.platform,
            language: navigator.language,
            screenResolution: screen.width + 'x' + screen.height,
            devicePixelRatio: window.devicePixelRatio,
            touchSupport: 'ontouchstart' in window || navigator.maxTouchPoints > 0,
            cookiesEnabled: navigator.cookieEnabled,
            onlineStatus: navigator.onLine
        },
        cookieCount: document.cookie.split(';').filter(c => c.trim()).length,
        isSecure: location.protocol === 'https:'
    };

    // Performance
    result.performance = (() => {
        const r = {};
        if (window.performance && window.performance.timing) {
            const t = performance.timing;
            const loadTime = t.loadEventEnd - t.navigationStart;
            const dcl = t.domContentLoadedEventEnd - t.navigationStart;
            const ttfb = t.responseStart - t.navigationStart;
            r.pageLoadTime = loadTime > 0 ? loadTime : null;
            r.domContentLoaded = dcl > 0 ? dcl : null;
            r.timeToFirstByte = ttfb > 0 ? ttfb : null;
        }
        if (performance.getEntriesByType) {
            const paintEntries = performance.getEntriesByType('paint');
            paintEntries.forEach(entry => {
                if (entry.name === 'first-paint') r.firstPaint = Math.round(entry.startTime);
                if (entry.name === 'first-contentful-paint') r.firstContentfulPaint = Math.round(entry.startTime);
            });
            try {
                const lcp = performance.getEntriesByType('largest-contentful-paint');
                if (lcp.length > 0) r.largestContentfulPaint = Math.round(lcp[lcp.length - 1].startTime);
            } catch (e) {}
            try {
                const ls = performance.getEntriesByType('layout-shift');
                if (ls.length > 0) r.cls = ls.reduce((sum, e) => !e.hadRecentInput ? sum + e.value : sum, 0);
            } catch (e) {}
            try {
                const fi = performance.getEntriesByType('first-input');
                if (fi.length > 0) r.fid = Math.round(fi[0].processingStart - fi[0].startTime);
                const interactions = performance.getEntriesByType('event');
                if (interactions.length > 0) {
                    const durations = interactions.map(e => e.duration).filter(d => d > 0);
                    if (durations.length > 0) r.inp = Math.round(Math.max(...durations));
                }
            } catch (e) {}
        }
        return r;
    })();

    // Meta
    result.meta = {
        specifiedLanguage: document.documentElement.lang || null,
        charset: document.characterSet || null,
        metaTags: Array.from(document.querySelectorAll('head meta')).map(meta => {
            const attrs = {};
            for (let attr of meta.attributes) attrs[attr.name] = attr.value;
            return attrs;
        }),
        openGraph: (() => {
            const og = {};
            document.querySelectorAll('meta[property^="og:"]').forEach(m => {
                og[m.getAttribute('property').replace('og:', '')] = m.getAttribute('content');
            });
            return og;
        })(),
        twitterCard: (() => {
            const tc = {};
            document.querySelectorAll('meta[name^="twitter:"]').forEach(m => {
                tc[m.getAttribute('name').replace('twitter:', '')] = m.getAttribute('content');
            });
            return tc;
        })()
    };

    // SEO
    result.seo = {
        canonical: (() => { const c = document.querySelector('link[rel="canonical"]'); return c ? c.href : null; })(),
        description: (() => { const d = document.querySelector('meta[name="description"]'); return d ? d.getAttribute('content') : null; })(),
        keywords: (() => { const k = document.querySelector('meta[name="keywords"]'); return k ? k.getAttribute('content') : null; })(),
        robots: (() => { const r = document.querySelector('meta[name="robots"]'); return r ? r.getAttribute('content') : null; })(),
        sitemap: (() => { const s = document.querySelector('link[rel="sitemap"]'); return s ? s.href : null; })(),
        favicon: (() => {
            const icon = document.querySelector('link[rel="icon"], link[rel="shortcut icon"]');
            if (icon) { const h = icon.href; if (h.endsWith('.svg')) return 'SVG'; if (h.endsWith('.png')) return 'PNG'; if (h.endsWith('.ico')) return 'ICO'; return 'Yes'; }
            return null;
        })(),
        alternateLanguages: Array.from(document.querySelectorAll('link[rel="alternate"][hreflang]')).map(l => ({ lang: l.getAttribute('hreflang'), href: l.href })),
        jsonLd: (() => {
            const types = [];
            document.querySelectorAll('script[type="application/ld+json"]').forEach(s => {
                try { const d = JSON.parse(s.textContent); const t = d['@type'] || (d['@graph'] && d['@graph'][0] && d['@graph'][0]['@type']); if (t) types.push(t); } catch (e) {}
            });
            return types;
        })(),
        microdataCount: document.querySelectorAll('[itemscope]').length
    };

    // Security
    result.security = {
        isSecure: location.protocol === 'https:',
        hasMixedContent: (() => {
            const insecure = Array.from(document.querySelectorAll('script, img, link, iframe')).some(el => {
                const src = el.src || el.href;
                return src && src.startsWith('http:');
            });
            return location.protocol === 'https:' && insecure;
        })(),
        cspMeta: (() => { const c = document.querySelector('meta[http-equiv="Content-Security-Policy"]'); return c ? c.getAttribute('content') : null; })(),
        referrerPolicy: (() => { const r = document.querySelector('meta[name="referrer"]'); return r ? r.getAttribute('content') : null; })()
    };

    // Accessibility
    result.accessibility = {
        landmarkCount: document.querySelectorAll('[role="banner"], [role="navigation"], [role="main"], [role="complementary"], [role="contentinfo"], [role="search"], [role="region"], header, nav, main, aside, footer').length,
        landmarks: (() => {
            const lm = {};
            document.querySelectorAll('[role="banner"], [role="navigation"], [role="main"], [role="complementary"], [role="contentinfo"], [role="search"], [role="region"], header:not([role]), nav:not([role]), main:not([role]), aside:not([role]), footer:not([role])').forEach(el => {
                const role = el.getAttribute('role') || el.tagName.toLowerCase();
                lm[role] = (lm[role] || 0) + 1;
            });
            return lm;
        })(),
        headingStructure: (() => {
            const s = {h1:0,h2:0,h3:0,h4:0,h5:0,h6:0};
            document.querySelectorAll('h1,h2,h3,h4,h5,h6,[role="heading"]').forEach(h => {
                if (h.hasAttribute('role')) { const l = parseInt(h.getAttribute('aria-level')||'1'); const k='h'+l; if(s[k]!==undefined)s[k]++; }
                else s[h.tagName.toLowerCase()]++;
            });
            return s;
        })(),
        imagesWithoutAlt: Array.from(document.images).filter(img => !img.hasAttribute('alt')).length,
        totalImages: document.images.length,
        formLabelsIssues: (() => {
            const inputs = document.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="button"]),select,textarea');
            let missing = 0;
            inputs.forEach(input => {
                const hasLabel = input.labels && input.labels.length > 0;
                const hasAria = input.hasAttribute('aria-label') || input.hasAttribute('aria-labelledby');
                if (!hasLabel && !hasAria) missing++;
            });
            return {total: inputs.length, missingLabels: missing};
        })(),
        linksWithoutText: Array.from(document.querySelectorAll('a')).filter(l => {
            const t=l.textContent.trim(); return !t && !l.getAttribute('aria-label') && !l.getAttribute('aria-labelledby') && !l.getAttribute('title');
        }).length,
        buttonsWithoutLabels: Array.from(document.querySelectorAll('button')).filter(b => {
            const t=b.textContent.trim(); return !t && !b.getAttribute('aria-label') && !b.getAttribute('aria-labelledby') && !b.getAttribute('title');
        }).length,
        hasSkipLink: (() => {
            return Array.from(document.querySelectorAll('a[href^="#"]')).some(l => {
                const t=l.textContent.toLowerCase(); const h=l.getAttribute('href');
                return (t.includes('skip')||t.includes('jump')) && (h==='#main'||h==='#content'||h.includes('main')||h.includes('content'));
            });
        })(),
        ariaAttributeCount: document.querySelectorAll('[aria-label],[aria-labelledby],[aria-describedby],[role],[aria-hidden],[aria-live],[aria-expanded],[aria-controls]').length,
        hasLangAttribute: document.documentElement.hasAttribute('lang')
    };

    // Resources
    result.resources = (() => {
        const currentDomain = window.location.hostname;
        const extDomains = new Set();
        const checkExt = (src) => { if(src){try{const u=new URL(src);if(u.hostname!==currentDomain&&u.hostname)extDomains.add(u.hostname);}catch(e){}} };
        Array.from(document.scripts).forEach(s => checkExt(s.src));
        Array.from(document.querySelectorAll('link[href]')).forEach(l => checkExt(l.href));
        Array.from(document.images).forEach(i => checkExt(i.src));

        const fonts = {googleFonts:[],customFonts:[],totalFontFiles:0};
        document.querySelectorAll('link[href*="fonts.googleapis.com"]').forEach(l => {
            const m=l.href.match(/family=([^&:]+)/); if(m)m[1].split('|').forEach(f => {
                const d=decodeURIComponent(f.replace(/\+/g,' ')); if(!fonts.googleFonts.includes(d))fonts.googleFonts.push(d);
            });
        });
        const customNames = new Set();
        try{Array.from(document.styleSheets).forEach(sheet=>{try{Array.from(sheet.cssRules||[]).forEach(rule=>{if(rule instanceof CSSFontFaceRule){const ff=rule.style.getPropertyValue('font-family');if(ff){const cn=ff.replace(/['"]/g,'').trim();if(cn)customNames.add(cn);}}});}catch(e){}});}catch(e){}
        fonts.customFonts = Array.from(customNames);

        let network = null;
        if(performance&&performance.getEntriesByType){try{
            const res=performance.getEntriesByType('resource');let totalSize=0;let largest=null;let largestSize=0;
            res.forEach(r=>{const sz=r.transferSize||r.encodedBodySize||0;totalSize+=sz;if(sz>largestSize){largestSize=sz;largest={name:r.name.split('/').pop()||r.name,url:r.name,size:sz};}});
            fonts.totalFontFiles=res.filter(r=>r.name.match(/\.(woff2?|ttf|otf|eot)$/i)).length;
            network={totalRequests:res.length,totalSize:totalSize,largestResource:largest};
        }catch(e){}}

        return {
            scriptCount:document.scripts.length, stylesheetCount:document.styleSheets.length,
            imageCount:document.images.length, linkCount:document.links.length,
            formCount:document.forms.length, iframeCount:document.querySelectorAll('iframe').length,
            videos:document.querySelectorAll('video').length, audio:document.querySelectorAll('audio').length,
            svgImages:document.querySelectorAll('svg, img[src$=".svg"]').length,
            thirdParty:{externalDomainCount:extDomains.size,externalDomains:Array.from(extDomains).slice(0,10)},
            fonts:fonts, network:network
        };
    })();

    // Storage
    result.storage = {
        cookieCount: document.cookie.split(';').filter(c=>c.trim()).length,
        cookieNames: document.cookie.split(';').map(c=>c.trim().split('=')[0]).filter(Boolean),
        localStorageSize: (()=>{try{return Object.keys(localStorage).reduce((a,k)=>a+k.length+localStorage[k].length,0);}catch(e){return 0;}})(),
        localStorageKeys: (()=>{try{return Object.keys(localStorage);}catch(e){return [];}})(),
        sessionStorageSize: (()=>{try{return Object.keys(sessionStorage).reduce((a,k)=>a+k.length+sessionStorage[k].length,0);}catch(e){return 0;}})(),
        sessionStorageKeys: (()=>{try{return Object.keys(sessionStorage);}catch(e){return [];}})(),
        hasServiceWorker: 'serviceWorker' in navigator
    };

    // Tech
    result.tech = (() => {
        const detected = {};
        const add = (cat, name, ver) => {
            if(!detected[cat])detected[cat]=[];
            const t = ver ? name+' '+ver : name;
            if(!detected[cat].includes(t))detected[cat].push(t);
        };
        if(window.React||document.querySelector('[data-reactroot],[data-reactid]'))add('JS Framework','React',window.React?.version);
        if(window.Vue)add('JS Framework','Vue.js',window.Vue?.version);
        if(window.angular||document.querySelector('[ng-app],[ng-version]'))add('JS Framework','Angular',document.querySelector('[ng-version]')?.getAttribute('ng-version'));
        if(window.Svelte)add('JS Framework','Svelte');
        if(window.jQuery)add('JS Library','jQuery',window.jQuery?.fn?.jquery);
        if(window._)add('JS Library','Lodash/Underscore');
        if(window.moment)add('JS Library','Moment.js');
        if(window.Alpine)add('JS Framework','Alpine.js');
        if(window.htmx)add('JS Library','htmx');
        if(document.querySelector('#__next'))add('JS Framework','Next.js');
        if(document.querySelector('#__nuxt'))add('JS Framework','Nuxt.js');
        const gen=document.querySelector('meta[name="generator"]')?.content;
        if(gen){if(gen.includes('WordPress'))add('CMS','WordPress');if(gen.includes('Drupal'))add('CMS','Drupal');if(gen.includes('Ghost'))add('CMS','Ghost');}
        if(window.Shopify||document.querySelector('link[href*="shopify"]'))add('CMS','Shopify');
        if(window.ga||window.gtag||window.google_tag_manager)add('Analytics','Google Analytics');
        if(window.dataLayer)add('Tag Manager','Google Tag Manager');
        if(window.fbq)add('Analytics','Facebook Pixel');
        if(window.hj)add('Analytics','Hotjar');
        if(window.mixpanel)add('Analytics','Mixpanel');
        if(window._paq)add('Analytics','Matomo');
        if(window.plausible)add('Analytics','Plausible');
        const allCls=Array.from(document.querySelectorAll('[class]')).slice(0,100).map(el=>el.className).join(' ');
        if(document.querySelector('link[href*="bootstrap"]')||/\bbs-|\bbtn-|\bcol-/.test(allCls))add('CSS Framework','Bootstrap');
        if(document.querySelector('link[href*="bulma"]'))add('CSS Framework','Bulma');
        if(document.querySelector('link[href*="fonts.googleapis.com"]'))add('Font Service','Google Fonts');
        if(document.querySelector('link[href*="typekit"],script[src*="typekit"]'))add('Font Service','Adobe Fonts');
        const scripts=Array.from(document.scripts).map(s=>s.src);
        if(scripts.some(s=>s.includes('cloudflare')))add('CDN','Cloudflare');
        if(scripts.some(s=>s.includes('jsdelivr')))add('CDN','jsDelivr');
        if(scripts.some(s=>s.includes('unpkg')))add('CDN','unpkg');
        if(scripts.some(s=>s.includes('cdnjs')))add('CDN','cdnjs');
        if(window.Stripe)add('Payment','Stripe');
        if(window.paypal)add('Payment','PayPal');
        return detected;
    })();

    // Layout
    result.layout = {
        viewportWidth: window.innerWidth,
        viewportHeight: window.innerHeight,
        documentWidth: document.documentElement.scrollWidth,
        documentHeight: document.documentElement.scrollHeight,
        scrollX: window.scrollX,
        scrollY: window.scrollY,
        visiblePercentage: Math.min(100, (window.innerHeight / document.documentElement.scrollHeight * 100))
    };

    return result;
})()'''

                ws_url = tab['webSocketDebuggerUrl']
                result = send_cdp_command(ws_url, 'Runtime.evaluate', {
                    'expression': js_code,
                    'returnByValue': True
                })
                value = result.get('result', {}).get('result', {}).get('value')
                if value:
                    self.send_json({'ok': True, 'data': value})
                else:
                    self.send_json({'ok': False, 'error': 'No data returned'}, 500)
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/navigate':
            query = parse_qs(urlparse(self.path).query)
            url = query.get('url', [None])[0]

            if not url:
                self.send_json({'ok': False, 'error': 'Missing url parameter'}, 400)
                return

            try:
                tab = get_requested_tab(query)
                if not tab:
                    self.send_json({'ok': False, 'error': 'No active tab found'}, 500)
                    return
                send_cdp_command(tab['webSocketDebuggerUrl'], 'Page.navigate', {'url': url})
                self.send_json({'ok': True, 'url': url, 'message': f'Navigating to {url}'})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        # =============================================
        # Tab Management Endpoints (Real Chrome Tabs)
        # =============================================

        elif path == '/tabs':
            # List all page tabs
            try:
                tabs = get_page_tabs()
                # Return simplified tab info
                tab_list = [{
                    'id': t.get('id'),
                    'title': t.get('title', 'New Tab'),
                    'url': t.get('url', ''),
                    'favicon': t.get('faviconUrl', '')
                } for t in tabs]
                self.send_json({'ok': True, 'tabs': tab_list})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/tabs/theme-colors':
            # Get theme colors for all tabs (for tab bar tinting)
            try:
                page_tabs = get_page_tabs()
                colors = {}
                for t in page_tabs:
                    tab_id = t.get('id')
                    color = get_tab_theme_color(t)
                    if color:
                        colors[tab_id] = color
                self.send_json({'ok': True, 'colors': colors})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/tabs/new':
            # Create a new tab using CDP directly
            # CDP on port 9222 only affects the VM's Chromium, not the host browser
            query = parse_qs(urlparse(self.path).query)
            url = query.get('url', ['http://inspekt/status'])[0]

            try:
                # URL-encode to handle special characters (?, &, etc.)
                encoded_url = quote(url, safe='')
                result = cdp_request(f'/json/new?{encoded_url}', method='PUT')

                if result:
                    tab_info = json.loads(result)
                    tab_id = tab_info.get('id')

                    # Activate the newly created tab
                    if tab_id:
                        cdp_request(f'/json/activate/{tab_id}', method='PUT')

                    # Focus the Chromium window so it receives keyboard input
                    subprocess.run(
                        ['xdotool', 'search', '--name', 'Chromium', 'windowactivate'],
                        env={**os.environ, 'DISPLAY': DISPLAY},
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )

                    self.send_json({
                        'ok': True,
                        'tab': {
                            'id': tab_id,
                            'url': tab_info.get('url', url),
                            'title': tab_info.get('title', 'New Tab')
                        }
                    })
                else:
                    self.send_json({'ok': False, 'error': 'Failed to create tab via CDP'}, 500)
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path.startswith('/tabs/') and path.endswith('/activate'):
            # Activate (switch to) a tab
            tab_id = path.split('/tabs/')[1].split('/activate')[0]

            try:
                result = cdp_request(f'/json/activate/{tab_id}', method='PUT')
                if result and 'activated' in result.lower():
                    self.send_json({'ok': True, 'message': 'Tab activated', 'id': tab_id})
                else:
                    self.send_json({'ok': False, 'error': 'Failed to activate tab'}, 500)
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path.startswith('/tabs/') and path.endswith('/close'):
            # Close a tab
            tab_id = path.split('/tabs/')[1].split('/close')[0]

            try:
                # Don't allow closing the last tab
                tabs = get_page_tabs()
                if len(tabs) <= 1:
                    self.send_json({'ok': False, 'error': 'Cannot close the last tab'}, 400)
                    return

                result = cdp_request(f'/json/close/{tab_id}', method='PUT')
                if result and 'closing' in result.lower():
                    # Clean up thumbnail for closed tab
                    if tab_id in thumbnails:
                        del thumbnails[tab_id]
                    self.send_json({'ok': True, 'message': 'Tab closed', 'id': tab_id})
                else:
                    self.send_json({'ok': False, 'error': 'Failed to close tab'}, 500)
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path.startswith('/tabs/') and path.endswith('/screenshot'):
            # Capture and cache a screenshot for a tab
            tab_id = path.split('/tabs/')[1].split('/screenshot')[0]

            try:
                data = capture_tab_screenshot(tab_id)
                if data:
                    self.send_json({'ok': True, 'message': 'Screenshot captured'})
                else:
                    self.send_json({'ok': False, 'error': 'Failed to capture screenshot'}, 500)
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path.startswith('/tabs/') and path.endswith('/thumbnail'):
            # Get cached thumbnail for a tab
            tab_id = path.split('/tabs/')[1].split('/thumbnail')[0]

            try:
                # Clean up old thumbnails and stale CDP connections periodically
                cleanup_thumbnails()
                cleanup_cdp_connections()

                # Return cached thumbnail if available
                if tab_id in thumbnails:
                    self.send_json({
                        'ok': True,
                        'thumbnail': thumbnails[tab_id]['data']
                    })
                else:
                    self.send_json({'ok': True, 'thumbnail': None})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path.startswith('/tabs/') and path.endswith('/scan'):
            # Run lightweight scan on a tab
            tab_id = path.split('/tabs/')[1].split('/scan')[0]

            try:
                result = scan_tab(tab_id)
                if result:
                    self.send_json({'ok': True, 'scan': result})
                else:
                    self.send_json({'ok': False, 'error': 'Failed to scan tab'}, 500)
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path.startswith('/tabs/') and path.endswith('/scan-data'):
            # Get cached scan data for a tab
            tab_id = path.split('/tabs/')[1].split('/scan-data')[0]

            try:
                # Clean up old scan data periodically
                cleanup_scan_data()

                # Return cached scan data if available, plus last command
                if tab_id in tab_scan_data:
                    data = tab_scan_data[tab_id].copy()
                    data['last_command'] = last_commands.get(tab_id)
                    self.send_json({'ok': True, **data})
                else:
                    self.send_json({
                        'ok': True,
                        'a11y_violations': None,
                        'console_errors': None,
                        'missing_alt': None,
                        'last_command': last_commands.get(tab_id)
                    })
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/tabs/scan-all':
            # Scan all tabs
            try:
                tabs = get_page_tabs()
                results = {}
                for tab in tabs:
                    tab_id = tab.get('id')
                    if tab_id:
                        result = scan_tab(tab_id)
                        results[tab_id] = result
                self.send_json({'ok': True, 'scanned': len(results), 'results': results})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/settings/auto-scan':
            # Get auto-scan setting
            self.send_json({'ok': True, 'enabled': auto_scan_enabled})

        elif path == '/ui/terminal-state':
            # Get terminal visibility state (for recording workflow)
            self.send_json({'ok': True, 'hidden': terminal_hidden})

        # DevTools management endpoints
        elif path == '/devtools/toggle':
            try:
                result = subprocess.run(
                    ['/opt/devtools-manager.sh', 'toggle'],
                    env={**os.environ, 'DISPLAY': DISPLAY},
                    capture_output=True,
                    text=True,
                    timeout=15
                )
                self.send_json({
                    'ok': result.returncode == 0,
                    'message': result.stdout.strip(),
                    'error': result.stderr.strip() if result.returncode != 0 else None
                })
            except subprocess.TimeoutExpired:
                self.send_json({'ok': False, 'error': 'DevTools toggle timed out'}, 500)
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/devtools/open':
            try:
                result = subprocess.run(
                    ['/opt/devtools-manager.sh', 'open'],
                    env={**os.environ, 'DISPLAY': DISPLAY},
                    capture_output=True,
                    text=True,
                    timeout=15
                )
                self.send_json({
                    'ok': result.returncode == 0,
                    'message': result.stdout.strip(),
                    'error': result.stderr.strip() if result.returncode != 0 else None
                })
            except subprocess.TimeoutExpired:
                self.send_json({'ok': False, 'error': 'DevTools open timed out'}, 500)
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/devtools/close':
            try:
                result = subprocess.run(
                    ['/opt/devtools-manager.sh', 'close'],
                    env={**os.environ, 'DISPLAY': DISPLAY},
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                self.send_json({
                    'ok': result.returncode == 0,
                    'message': result.stdout.strip()
                })
            except subprocess.TimeoutExpired:
                self.send_json({'ok': False, 'error': 'DevTools close timed out'}, 500)
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/devtools/status':
            try:
                result = subprocess.run(
                    ['/opt/devtools-manager.sh', 'status'],
                    env={**os.environ, 'DISPLAY': DISPLAY},
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                status = json.loads(result.stdout.strip())
                self.send_json({'ok': True, **status})
            except json.JSONDecodeError:
                self.send_json({'ok': True, 'open': False})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/devtools/tile':
            try:
                result = subprocess.run(
                    ['/opt/devtools-manager.sh', 'tile'],
                    env={**os.environ, 'DISPLAY': DISPLAY},
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                self.send_json({
                    'ok': result.returncode == 0,
                    'message': result.stdout.strip()
                })
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        # =============================================
        # Element Inspect Endpoints (host-side overlay)
        # =============================================

        elif path == '/inspect/element-at-point':
            # Lightweight, side-effect-free: returns selector + bounding rect
            # at given x,y without setting __INSPEKT_INSPECTED_ELEMENT__.
            # Used for hover preview during hover-inspect mode.
            query = parse_qs(urlparse(self.path).query)
            x = query.get('x', ['0'])[0]
            y = query.get('y', ['0'])[0]
            tab = get_requested_tab(query)
            if not tab or not tab.get('webSocketDebuggerUrl'):
                self.send_json({'ok': False, 'error': 'No active tab found'}, 500)
                return

            js_code = f'''
(() => {{
    const el = document.elementFromPoint({x}, {y});
    if (!el) return {{ ok: false }};
    const tag = el.tagName.toLowerCase();
    let selector = tag;
    if (el.id) selector += '#' + el.id;
    else if (el.className && typeof el.className === 'string' && el.className.trim())
        selector += '.' + el.className.trim().split(/\\s+/).slice(0,2).join('.');
    const r = el.getBoundingClientRect();
    return {{ ok: true, selector: selector, rect: {{ left: r.left, top: r.top, width: r.width, height: r.height }} }};
}})()
'''
            try:
                ws_url = tab['webSocketDebuggerUrl']
                result = send_cdp_command(ws_url, 'Runtime.evaluate', {
                    'expression': js_code,
                    'returnByValue': True
                })
                value = result.get('result', {}).get('result', {}).get('value', {})
                if value.get('ok'):
                    self.send_json({'ok': True, 'selector': value.get('selector', ''), 'rect': value.get('rect')})
                else:
                    self.send_json({'ok': False})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/inspect/element-details':
            # Returns detailed info about the committed inspected element.
            # Called once after locking to populate the host-side info panel.
            query = parse_qs(urlparse(self.path).query)
            tab = get_requested_tab(query)
            if not tab or not tab.get('webSocketDebuggerUrl'):
                self.send_json({'ok': False, 'error': 'No active tab found'}, 500)
                return

            js_code = '''
(() => {
    const el = window.__INSPEKT_INSPECTED_ELEMENT__;
    if (!el || !el.isConnected) return { ok: false, error: 'No inspected element' };
    const tag = el.tagName.toLowerCase();
    let selector = tag;
    if (el.id) selector += '#' + el.id;
    else if (el.className && typeof el.className === 'string' && el.className.trim())
        selector += '.' + el.className.trim().split(/\\s+/).slice(0,2).join('.');
    const r = el.getBoundingClientRect();
    const attrs = [];
    for (let i = 0; i < Math.min(el.attributes.length, 10); i++) {
        const a = el.attributes[i];
        if (a.name !== 'class' && a.name !== 'id' && a.name !== 'style') {
            const v = a.value.length > 50 ? a.value.slice(0, 50) + '...' : a.value;
            attrs.push({ name: a.name, value: v });
        }
    }
    const text = (el.textContent || '').trim().slice(0, 120);
    const cs = getComputedStyle(el);
    return {
        ok: true,
        selector: selector,
        tag: tag,
        rect: { left: r.left, top: r.top, width: r.width, height: r.height },
        attributes: attrs,
        text: text + (el.textContent && el.textContent.trim().length > 120 ? '...' : ''),
        styles: {
            fontSize: cs.fontSize,
            color: cs.color,
            backgroundColor: cs.backgroundColor,
            display: cs.display,
            position: cs.position,
            fontFamily: cs.fontFamily.split(',')[0].trim().replace(/['"]/g, '')
        }
    };
})()
'''
            try:
                ws_url = tab['webSocketDebuggerUrl']
                result = send_cdp_command(ws_url, 'Runtime.evaluate', {
                    'expression': js_code,
                    'returnByValue': True
                })
                value = result.get('result', {}).get('result', {}).get('value', {})
                if value.get('ok'):
                    self.send_json(value)
                else:
                    self.send_json({'ok': False, 'error': value.get('error', 'No inspected element')})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/inspect/set-at-point':
            # Set the element at given coordinates as the inspected element.
            # This enables all `inspekt inspected *` CLI commands without DevTools.
            query = parse_qs(urlparse(self.path).query)
            x = query.get('x', ['0'])[0]
            y = query.get('y', ['0'])[0]
            tab = get_requested_tab(query)
            if not tab or not tab.get('webSocketDebuggerUrl'):
                self.send_json({'ok': False, 'error': 'No active tab found'}, 500)
                return

            js_code = f'''
(() => {{
    const el = document.elementFromPoint({x}, {y});
    if (!el) return {{ ok: false, error: 'No element at point' }};
    window.__INSPEKT_INSPECTED_ELEMENT__ = el;
    window.__INSPEKT_NAV_STACK__ = [];
    window.__INSPEKT_SELECTION_SOURCE__ = 'context-menu';
    window.__INSPEKT_SELECTION_TIME__ = Date.now();
    const tag = el.tagName.toLowerCase();
    let selector = tag;
    if (el.id) selector += '#' + el.id;
    else if (el.className && typeof el.className === 'string' && el.className.trim())
        selector += '.' + el.className.trim().split(/\\s+/).slice(0,2).join('.');
    const r = el.getBoundingClientRect();
    return {{ ok: true, tag: tag, selector: selector, rect: {{ left: r.left, top: r.top, width: r.width, height: r.height }} }};
}})()
'''
            try:
                ws_url = tab['webSocketDebuggerUrl']
                result = send_cdp_command(ws_url, 'Runtime.evaluate', {
                    'expression': js_code,
                    'returnByValue': True
                })
                value = result.get('result', {}).get('result', {}).get('value', {})
                if value.get('ok'):
                    self.send_json({'ok': True, 'tag': value.get('tag', ''), 'selector': value.get('selector', ''), 'rect': value.get('rect')})
                else:
                    self.send_json({'ok': False, 'error': value.get('error', 'Unknown error')}, 400)
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/inspect/get-rect':
            # Return current bounding rect of the inspected element (lightweight, no side effects).
            # Used by host-side overlay polling to track scroll, resize, and font changes.
            query = parse_qs(urlparse(self.path).query)
            tab = get_requested_tab(query)
            if not tab or not tab.get('webSocketDebuggerUrl'):
                self.send_json({'ok': False, 'error': 'No active tab'}, 500)
                return

            js_code = '''
(() => {
    const el = window.__INSPEKT_INSPECTED_ELEMENT__;
    if (!el || !el.isConnected) return { ok: false };
    const r = el.getBoundingClientRect();
    const tag = el.tagName.toLowerCase();
    let selector = tag;
    if (el.id) selector += '#' + el.id;
    else if (el.className && typeof el.className === 'string' && el.className.trim())
        selector += '.' + el.className.trim().split(/\\s+/).slice(0,2).join('.');
    const siblings = Array.from(el.parentElement?.children || []);
    return { ok: true, selector: selector, rect: { left: r.left, top: r.top, width: r.width, height: r.height }, siblingIndex: siblings.indexOf(el) + 1, siblingCount: siblings.length };
})()
'''
            try:
                ws_url = tab['webSocketDebuggerUrl']
                result = send_cdp_command(ws_url, 'Runtime.evaluate', {
                    'expression': js_code,
                    'returnByValue': True
                })
                value = result.get('result', {}).get('result', {}).get('value', {})
                if value.get('ok'):
                    resp = {'ok': True, 'selector': value.get('selector', ''), 'rect': value.get('rect')}
                    if value.get('siblingIndex'):
                        resp['siblingIndex'] = value['siblingIndex']
                        resp['siblingCount'] = value['siblingCount']
                    self.send_json(resp)
                else:
                    self.send_json({'ok': False})
            except Exception:
                self.send_json({'ok': False})

        elif path == '/inspect/navigate':
            # Navigate the DOM relative to the current inspected element.
            # Directions: up (parent), down (first child), left (prev sibling), right (next sibling).
            query = parse_qs(urlparse(self.path).query)
            direction = query.get('direction', ['up'])[0]
            if direction not in ('up', 'down', 'left', 'right'):
                self.send_json({'ok': False, 'error': f'Invalid direction: {direction}'}, 400)
                return
            tab = get_requested_tab(query)
            if not tab or not tab.get('webSocketDebuggerUrl'):
                self.send_json({'ok': False, 'error': 'No active tab'}, 500)
                return

            js_code = f'''
(() => {{
    const el = window.__INSPEKT_INSPECTED_ELEMENT__;
    if (!el || !el.isConnected) return {{ ok: false, error: 'No inspected element' }};

    if (!Array.isArray(window.__INSPEKT_NAV_STACK__)) window.__INSPEKT_NAV_STACK__ = [];
    const stack = window.__INSPEKT_NAV_STACK__;

    let target = null;
    let navInfo = {{}};
    const dir = '{direction}';

    if (dir === 'up') {{
        target = el.parentElement;
        if (target && target === document.documentElement.parentElement) target = null;
        if (target) stack.push(el);
    }} else if (dir === 'down') {{
        if (stack.length > 0) {{
            const candidate = stack[stack.length - 1];
            if (candidate.isConnected && candidate.parentElement === el) {{
                target = stack.pop();
                navInfo.retraced = true;
            }} else {{
                stack.length = 0;
                target = el.firstElementChild;
            }}
        }} else {{
            target = el.firstElementChild;
        }}
    }} else if (dir === 'left') {{
        target = el.previousElementSibling;
        if (!target && el.parentElement && el.parentElement !== document.documentElement && el.parentElement !== document.body) {{
            target = el.parentElement;
            navInfo.autoClimbed = true;
        }}
        stack.length = 0;
    }} else if (dir === 'right') {{
        target = el.nextElementSibling;
        if (!target && el.parentElement && el.parentElement !== document.documentElement && el.parentElement !== document.body) {{
            target = el.parentElement;
            navInfo.autoClimbed = true;
        }}
        stack.length = 0;
    }}

    // Don't allow navigating to <html> or <body> — selecting the entire viewport is jarring
    if (target === document.documentElement || target === document.body) {{
        // Undo the stack push that "up" may have done
        if (dir === 'up' && stack.length > 0 && stack[stack.length - 1] === el) stack.pop();
        return {{ ok: false, error: 'No element in that direction' }};
    }}

    if (!target) return {{ ok: false, error: 'No element in that direction' }};

    // Scroll into view if off-screen
    target.scrollIntoView({{ block: 'nearest', inline: 'nearest' }});

    window.__INSPEKT_INSPECTED_ELEMENT__ = target;
    window.__INSPEKT_SELECTION_SOURCE__ = 'keyboard-nav';
    window.__INSPEKT_SELECTION_TIME__ = Date.now();

    const tag = target.tagName.toLowerCase();
    let selector = tag;
    if (target.id) selector += '#' + target.id;
    else if (target.className && typeof target.className === 'string' && target.className.trim())
        selector += '.' + target.className.trim().split(/\\s+/).slice(0,2).join('.');
    const r = target.getBoundingClientRect();
    const siblings = Array.from(target.parentElement?.children || []);
    return {{
        ok: true,
        selector: selector,
        rect: {{ left: r.left, top: r.top, width: r.width, height: r.height }},
        siblingIndex: siblings.indexOf(target) + 1,
        siblingCount: siblings.length,
        ...navInfo
    }};
}})()
'''
            try:
                ws_url = tab['webSocketDebuggerUrl']
                result = send_cdp_command(ws_url, 'Runtime.evaluate', {
                    'expression': js_code,
                    'returnByValue': True
                })
                value = result.get('result', {}).get('result', {}).get('value', {})
                if value.get('ok'):
                    resp = {'ok': True, 'selector': value.get('selector', ''), 'rect': value.get('rect')}
                    if value.get('siblingIndex'):
                        resp['siblingIndex'] = value['siblingIndex']
                        resp['siblingCount'] = value['siblingCount']
                    if value.get('autoClimbed'):
                        resp['autoClimbed'] = True
                    if value.get('retraced'):
                        resp['retraced'] = True
                    self.send_json(resp)
                else:
                    self.send_json({'ok': False, 'error': value.get('error', 'No element in that direction')})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        # =============================================
        # Screenshot Download Endpoints
        # =============================================

        elif path == '/screenshot/viewport':
            # Capture viewport screenshot as PNG, return base64
            try:
                tab = get_active_tab()
                if not tab or not tab.get('webSocketDebuggerUrl'):
                    self.send_json({'ok': False, 'error': 'No active tab found'}, 500)
                    return
                ws_url = tab['webSocketDebuggerUrl']
                result = send_cdp_command(ws_url, 'Page.captureScreenshot', {
                    'format': 'png',
                    'captureBeyondViewport': False
                })
                if result and 'result' in result and 'data' in result['result']:
                    self.send_json({'ok': True, 'data': result['result']['data'], 'format': 'png'})
                else:
                    self.send_json({'ok': False, 'error': 'Screenshot capture failed'}, 500)
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/screenshot/page':
            # Capture full-page screenshot by temporarily expanding the viewport
            try:
                tab = get_active_tab()
                if not tab or not tab.get('webSocketDebuggerUrl'):
                    self.send_json({'ok': False, 'error': 'No active tab found'}, 500)
                    return
                ws_url = tab['webSocketDebuggerUrl']

                # Get page dimensions and current viewport size
                dims_result = send_cdp_command(ws_url, 'Runtime.evaluate', {
                    'expression': 'JSON.stringify({scrollWidth: document.documentElement.scrollWidth, scrollHeight: document.documentElement.scrollHeight, viewportWidth: window.innerWidth, viewportHeight: window.innerHeight})',
                    'returnByValue': True
                })
                dims = json.loads(dims_result.get('result', {}).get('result', {}).get('value', '{}'))
                scroll_w = dims.get('scrollWidth', 1280)
                scroll_h = dims.get('scrollHeight', 800)
                orig_w = dims.get('viewportWidth', 1280)
                orig_h = dims.get('viewportHeight', 800)

                # Expand viewport to full page size
                send_cdp_command(ws_url, 'Emulation.setDeviceMetricsOverride', {
                    'width': scroll_w,
                    'height': scroll_h,
                    'deviceScaleFactor': 1,
                    'mobile': False
                })

                # Capture the full page
                result = send_cdp_command(ws_url, 'Page.captureScreenshot', {
                    'format': 'png',
                    'captureBeyondViewport': False
                })

                # Restore original viewport
                send_cdp_command(ws_url, 'Emulation.setDeviceMetricsOverride', {
                    'width': orig_w,
                    'height': orig_h,
                    'deviceScaleFactor': 1,
                    'mobile': False
                })
                # Clear the override to return to normal
                send_cdp_command(ws_url, 'Emulation.clearDeviceMetricsOverride', {})

                if result and 'result' in result and 'data' in result['result']:
                    self.send_json({'ok': True, 'data': result['result']['data'], 'format': 'png'})
                else:
                    self.send_json({'ok': False, 'error': 'Full page screenshot failed'}, 500)
            except Exception as e:
                # Try to restore viewport even on error
                try:
                    send_cdp_command(ws_url, 'Emulation.clearDeviceMetricsOverride', {})
                except Exception:
                    pass
                self.send_json({'ok': False, 'error': str(e)}, 500)

        # =============================================
        # File Download Endpoints
        # =============================================

        elif path == '/file-exists':
            # Check if a file exists on the VM
            query = parse_qs(urlparse(self.path).query)
            file_path = query.get('path', [None])[0]

            if not file_path:
                self.send_json({'ok': False, 'error': 'Missing path parameter'}, 400)
                return

            # Security: only allow paths under certain directories
            allowed_prefixes = ['/root/', '/tmp/', '/home/', '/opt/inspekt/']
            file_path = os.path.abspath(file_path)

            if not any(file_path.startswith(prefix) for prefix in allowed_prefixes):
                self.send_json({'ok': False, 'error': 'Path not allowed', 'exists': False}, 403)
                return

            exists = os.path.isfile(file_path)
            if exists:
                stat = os.stat(file_path)
                self.send_json({
                    'ok': True,
                    'exists': True,
                    'path': file_path,
                    'size': stat.st_size,
                    'filename': os.path.basename(file_path)
                })
            else:
                self.send_json({'ok': True, 'exists': False, 'path': file_path})

        elif path == '/download':
            # Download a file from the VM
            query = parse_qs(urlparse(self.path).query)
            file_path = query.get('path', [None])[0]

            if not file_path:
                self.send_json({'ok': False, 'error': 'Missing path parameter'}, 400)
                return

            # Normalize and validate path
            file_path = os.path.abspath(file_path)

            # Security: restrict downloads to user-accessible directories only.
            # The control server runs as root, so without this check it could
            # serve any file (e.g. /root/.config/inspekt.json with API keys).
            allowed_prefixes = ['/home/inspekt/', '/tmp/']
            if not any(file_path.startswith(p) for p in allowed_prefixes):
                self.send_json({'ok': False, 'error': 'Access denied'}, 403)
                return

            if not os.path.isfile(file_path):
                self.send_json({'ok': False, 'error': 'File not found'}, 404)
                return

            try:
                filename = os.path.basename(file_path)
                # Determine content type
                import mimetypes
                content_type, _ = mimetypes.guess_type(file_path)
                if content_type is None:
                    content_type = 'application/octet-stream'

                with open(file_path, 'rb') as f:
                    content = f.read()

                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
                self.send_header('Content-Length', str(len(content)))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(content)
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        # =============================================
        # Recordings Management Endpoints
        # =============================================

        elif path == '/recordings':
            # List all recordings with metadata
            try:
                import yaml
                recordings_dir = os.path.expanduser('~/.inspekt/recordings')
                recordings = []

                if os.path.exists(recordings_dir):
                    for filename in os.listdir(recordings_dir):
                        if filename.endswith('.yaml'):
                            filepath = os.path.join(recordings_dir, filename)
                            try:
                                with open(filepath, 'r') as f:
                                    data = yaml.safe_load(f)
                                if data and 'metadata' in data:
                                    meta = data['metadata']
                                    recordings.append({
                                        'name': filename,
                                        'path': filepath,
                                        'created_at': str(meta.get('created_at', '')),
                                        'duration_ms': meta.get('duration_ms', 0),
                                        'steps': len(data.get('steps', [])),
                                        'url': meta.get('starting_url', ''),
                                        'size': os.path.getsize(filepath)
                                    })
                            except Exception:
                                # Skip files that can't be parsed
                                pass

                # Sort by creation date (newest first)
                recordings.sort(key=lambda r: r.get('created_at', ''), reverse=True)
                self.send_json({'ok': True, 'recordings': recordings, 'count': len(recordings)})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path.startswith('/recordings/') and path.endswith('/download'):
            # Download a specific recording
            name = path.split('/recordings/')[1].split('/download')[0]
            recordings_dir = os.path.expanduser('~/.inspekt/recordings')
            filepath = os.path.join(recordings_dir, name)

            # Security check
            if not os.path.abspath(filepath).startswith(os.path.abspath(recordings_dir)):
                self.send_json({'ok': False, 'error': 'Invalid path'}, 403)
                return

            if not os.path.isfile(filepath):
                self.send_json({'ok': False, 'error': 'Recording not found'}, 404)
                return

            try:
                with open(filepath, 'rb') as f:
                    content = f.read()

                self.send_response(200)
                self.send_header('Content-Type', 'application/x-yaml')
                self.send_header('Content-Disposition', f'attachment; filename="{name}"')
                self.send_header('Content-Length', str(len(content)))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(content)
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path.startswith('/recordings/') and path.endswith('/delete'):
            # Delete a specific recording
            name = path.split('/recordings/')[1].split('/delete')[0]
            recordings_dir = os.path.expanduser('~/.inspekt/recordings')
            filepath = os.path.join(recordings_dir, name)

            # Security check
            if not os.path.abspath(filepath).startswith(os.path.abspath(recordings_dir)):
                self.send_json({'ok': False, 'error': 'Invalid path'}, 403)
                return

            if not os.path.isfile(filepath):
                self.send_json({'ok': False, 'error': 'Recording not found'}, 404)
                return

            try:
                os.remove(filepath)
                self.send_json({'ok': True, 'message': f'Deleted {name}'})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/recordings/download-all':
            # Download all recordings as a zip file
            import zipfile
            import io

            try:
                recordings_dir = os.path.expanduser('~/.inspekt/recordings')
                if not os.path.exists(recordings_dir):
                    self.send_json({'ok': False, 'error': 'No recordings directory'}, 404)
                    return

                # Create zip in memory
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for filename in os.listdir(recordings_dir):
                        if filename.endswith('.yaml'):
                            filepath = os.path.join(recordings_dir, filename)
                            zf.write(filepath, filename)

                zip_content = zip_buffer.getvalue()

                if len(zip_content) < 22:  # Empty zip file is 22 bytes
                    self.send_json({'ok': False, 'error': 'No recordings found'}, 404)
                    return

                self.send_response(200)
                self.send_header('Content-Type', 'application/zip')
                self.send_header('Content-Disposition', 'attachment; filename="inspekt-recordings.zip"')
                self.send_header('Content-Length', str(len(zip_content)))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(zip_content)
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/devtools/url':
            # Return the DevTools URL for the active page tab
            try:
                tabs = get_page_tabs()
                # Find first non-chrome:// page
                for tab in tabs:
                    url = tab.get('url', '')
                    if not url.startswith('chrome://') and not url.startswith('chrome-extension://'):
                        page_id = tab.get('id')
                        if page_id:
                            devtools_url = f'http://localhost:{CDP_PORT}/devtools/inspector.html?ws=localhost:{CDP_PORT}/devtools/page/{page_id}'
                            self.send_json({'ok': True, 'url': devtools_url, 'tab_id': page_id})
                            return
                self.send_json({'ok': False, 'error': 'No debuggable page found'}, 404)
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/devtools/connection-info':
            # Return comprehensive CDP connection info for remote debugging setup
            try:
                tabs = get_page_tabs()

                # Find the primary debuggable target (first non-chrome:// page)
                primary_target = None
                for tab in tabs:
                    url = tab.get('url', '')
                    if not url.startswith('chrome://') and not url.startswith('chrome-extension://'):
                        primary_target = tab
                        break

                # Build connection info
                info = {
                    'ok': True,
                    'cdp_port': CDP_PORT,
                    'http_endpoint': f'http://localhost:{CDP_PORT}/json',
                    'version_endpoint': f'http://localhost:{CDP_PORT}/json/version',
                    'targets': []
                }

                if primary_target:
                    page_id = primary_target.get('id')
                    info['primary_ws_url'] = f'ws://localhost:{CDP_PORT}/devtools/page/{page_id}'
                    info['devtools_url'] = f'http://localhost:{CDP_PORT}/devtools/inspector.html?ws=localhost:{CDP_PORT}/devtools/page/{page_id}'

                # Add all debuggable targets with their WebSocket URLs
                for tab in tabs:
                    url = tab.get('url', '')
                    if not url.startswith('chrome://') and not url.startswith('chrome-extension://'):
                        page_id = tab.get('id')
                        info['targets'].append({
                            'id': page_id,
                            'title': tab.get('title', 'Untitled'),
                            'url': url,
                            'ws_url': f'ws://localhost:{CDP_PORT}/devtools/page/{page_id}'
                        })

                self.send_json(info)
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/context-menu-info':
            # Return selected text and element info at given coordinates for VNC context menu.
            # Also eagerly sets __INSPEKT_INSPECTED_ELEMENT__ so inspected * commands work immediately.
            query = parse_qs(urlparse(self.path).query)
            x = query.get('x', ['0'])[0]
            y = query.get('y', ['0'])[0]
            tab = get_requested_tab(query)
            if not tab:
                self.send_json({'ok': True, 'selectedText': '', 'isImage': False})
                return

            js_code = f'''
(() => {{
    const sel = window.getSelection().toString().trim();
    const el = document.elementFromPoint({x}, {y});
    if (!el) return {{ selectedText: sel, elementTag: '', isImage: false, imageSrc: '', isLink: false, linkHref: '', isFormField: false, isHeading: false, isMedia: false, elementSelector: '', elementRect: null }};
    const tag = el.tagName.toLowerCase();
    const isImg = tag === 'img';
    const src = isImg ? el.src : '';
    const link = el.closest('a');
    const isLink = !!link;
    const linkHref = link ? link.href : '';
    const isFormField = ['input','textarea','select'].includes(tag) || el.isContentEditable;
    const isHeading = /^h[1-6]$/.test(tag);
    const isMedia = ['video','audio'].includes(tag);

    // Build a basic CSS selector for the element
    let elementSelector = tag;
    if (el.id) elementSelector += '#' + el.id;
    else if (el.className && typeof el.className === 'string' && el.className.trim())
        elementSelector += '.' + el.className.trim().split(/\\s+/).slice(0,2).join('.');

    // Eagerly set the inspected element so inspected * commands work from context menu
    window.__INSPEKT_INSPECTED_ELEMENT__ = el;
    window.__INSPEKT_NAV_STACK__ = [];
    window.__INSPEKT_SELECTION_SOURCE__ = 'context-menu';
    window.__INSPEKT_SELECTION_TIME__ = Date.now();

    // Return element rect for host-side overlay rendering
    const r = el.getBoundingClientRect();
    const elementRect = {{ left: r.left, top: r.top, width: r.width, height: r.height }};

    return {{ selectedText: sel, elementTag: tag, isImage: isImg, imageSrc: src, isLink: isLink, linkHref: linkHref, isFormField: isFormField, isHeading: isHeading, isMedia: isMedia, elementSelector: elementSelector, elementRect: elementRect }};
}})()
'''
            try:
                ws_url = tab.get('webSocketDebuggerUrl')
                if not ws_url:
                    self.send_json({'ok': True, 'selectedText': '', 'isImage': False})
                    return
                result = send_cdp_command(ws_url, 'Runtime.evaluate', {
                    'expression': js_code,
                    'returnByValue': True
                })
                value = result.get('result', {}).get('result', {}).get('value', {})
                self.send_json({
                    'ok': True,
                    'selectedText': value.get('selectedText', ''),
                    'elementTag': value.get('elementTag', ''),
                    'isImage': value.get('isImage', False),
                    'imageSrc': value.get('imageSrc', ''),
                    'isLink': value.get('isLink', False),
                    'linkHref': value.get('linkHref', ''),
                    'isFormField': value.get('isFormField', False),
                    'isHeading': value.get('isHeading', False),
                    'isMedia': value.get('isMedia', False),
                    'elementSelector': value.get('elementSelector', ''),
                    'elementRect': value.get('elementRect', None)
                })
            except Exception:
                self.send_json({'ok': True, 'selectedText': '', 'isImage': False})

        elif path == '/resolution':
            # Return current X display resolution
            try:
                result = subprocess.run(
                    ['xrandr', '--current'],
                    capture_output=True, text=True, timeout=5,
                    env={**os.environ, 'DISPLAY': DISPLAY}
                )
                current = ''
                for line in result.stdout.splitlines():
                    if '*' in line:
                        current = line.split()[0]
                        break
                if current:
                    w, h = current.split('x')
                    self.send_json({'ok': True, 'resolution': current, 'width': int(w), 'height': int(h)})
                else:
                    self.send_json({'ok': False, 'error': 'Could not parse current resolution'}, 500)
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/clipboard':
            # Return the latest clipboard text posted by CLI commands
            self.send_json({'ok': True, 'text': clipboard_data['text'], 'timestamp': clipboard_data['timestamp']})

        elif path == '/keys/send':
            # Send keystrokes via xdotool (bypasses VNC for modifier key issues)
            query = parse_qs(urlparse(self.path).query)
            keys = query.get('keys', [None])[0]
            if not keys:
                self.send_json({'ok': False, 'error': 'Missing keys parameter'}, 400)
                return
            try:
                xdotool_env = {**os.environ, 'DISPLAY': DISPLAY}
                # For modifier+key combos (e.g., shift+Tab), use a shell
                # command string with && chaining, matching the docker exec
                # approach that's proven to work reliably.
                if '+' in keys:
                    # Get the active window and send keys to it explicitly.
                    # xdotool modifier combos fail from the HTTP server's
                    # threads without explicit window targeting.
                    xdotool_env = {**os.environ, 'DISPLAY': DISPLAY}
                    wid_result = subprocess.run(
                        ['xdotool', 'getactivewindow'],
                        env=xdotool_env, capture_output=True, text=True, timeout=2,
                    )
                    wid = wid_result.stdout.strip()
                    if wid:
                        subprocess.Popen(
                            ['xdotool', 'key', '--window', wid, keys],
                            env=xdotool_env,
                        )
                    else:
                        subprocess.Popen(
                            ['xdotool', 'key', keys],
                            env=xdotool_env,
                        )
                    self.send_json({'ok': True})
                    return
                    if result.returncode != 0:
                        self.send_json({'ok': False, 'error': result.stderr or 'xdotool failed'}, 500)
                        return
                else:
                    subprocess.run(['xdotool', 'key', keys], env=xdotool_env, timeout=2, capture_output=True)
                self.send_json({'ok': True})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        # ── Screen Reader Simulator GET endpoints ─────────────────

        elif path == '/sr/state':
            self.send_json({
                'ok': True,
                'active': sr_state['active'],
                'screen_reader': sr_state['screen_reader'],
                'verbosity': sr_state['verbosity'],
            })

        elif path == '/sr/keyboard-commands':
            try:
                commands = _sr_get_keyboard_commands()
                self.send_json({'ok': True, 'commands': commands})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path.startswith('/internal/') or path.startswith('/api/'):
            # Reverse proxy to Inspekt API server (port 80)
            self._proxy_to_api('GET')

        else:
            self.send_json({'error': 'Not found'}, 404)

    def do_POST(self):
        global auto_scan_enabled, terminal_hidden, clipboard_data
        path = urlparse(self.path).path

        if path == '/clipboard':
            # CLI posts clipboard text here; control panel fetches it via GET
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_length).decode('utf-8')
                data = json.loads(body)
                clipboard_data = {'text': data.get('text', ''), 'timestamp': time.time()}
                self.send_json({'ok': True})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)
            return

        # Auto-scan settings endpoint
        if path == '/settings/auto-scan':
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_length).decode() if content_length > 0 else '{}'
                data = json.loads(body)
                auto_scan_enabled = data.get('enabled', False)
                self.send_json({'ok': True, 'enabled': auto_scan_enabled})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)
            return

        # Terminal visibility state endpoint (for recording workflow)
        if path == '/ui/terminal-state':
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_length).decode() if content_length > 0 else '{}'
                data = json.loads(body)
                terminal_hidden = data.get('hidden', False)
                self.send_json({'ok': True, 'hidden': terminal_hidden})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)
            return

        # Theme endpoint: POST /theme/dark or POST /theme/light
        if path.startswith('/theme/'):
            theme = path.split('/theme/')[1]
            if theme not in ['dark', 'light']:
                self.send_json({'ok': False, 'error': 'Invalid theme. Use dark or light.'}, 400)
                return

            try:
                # Read current theme to check if change is needed
                current_theme = 'dark'
                try:
                    with open('/tmp/inspekt_theme', 'r') as f:
                        current_theme = f.read().strip()
                except FileNotFoundError:
                    pass

                # Write theme preference
                with open('/tmp/inspekt_theme', 'w') as f:
                    f.write(theme)

                # Only restart Chrome if theme actually changed
                if current_theme != theme:
                    # Kill Chromium (supervisord will restart it with new theme)
                    subprocess.run(['pkill', '-f', 'chromium'], capture_output=True)
                    self.send_json({
                        'ok': True,
                        'theme': theme,
                        'message': f'Theme changed to {theme}, Chrome restarting...',
                        'changed': True
                    })
                else:
                    self.send_json({
                        'ok': True,
                        'theme': theme,
                        'message': f'Theme already set to {theme}',
                        'changed': False
                    })
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/resize':
            # Resize the X display to match the host viewport
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_length).decode() if content_length > 0 else '{}'
                data = json.loads(body)
                width = int(data.get('width', 0))
                height = int(data.get('height', 0))
                if width < 320 or height < 240:
                    self.send_json({'ok': False, 'error': 'Width and height must be positive integers (min 320x240)'}, 400)
                    return
                result = subprocess.run(
                    ['/opt/resize-display.sh', str(width), str(height)],
                    capture_output=True, text=True, timeout=10,
                    env={**os.environ, 'DISPLAY': DISPLAY}
                )
                try:
                    response = json.loads(result.stdout.strip())
                except (json.JSONDecodeError, ValueError):
                    response = {'ok': False, 'error': result.stderr.strip() or result.stdout.strip() or 'Unknown error'}
                self.send_json(response, 200 if response.get('ok') else 500)
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        # ── Screen Reader Simulator POST endpoints ────────────────

        elif path == '/sr/start':
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_length).decode() if content_length > 0 else '{}'
                data = json.loads(body)

                screen_reader = data.get('screenReader', 'jaws')
                verbosity = data.get('verbosity', 'high')
                sync_focus = data.get('syncFocus', False)
                sync_mouse = data.get('syncMouse', False)
                start_from_focus = data.get('startFromFocus', True)

                tab = get_active_tab()
                if not tab or not tab.get('webSocketDebuggerUrl'):
                    self.send_json({'ok': False, 'error': 'No active tab found'}, 500)
                    return

                ws_url = tab['webSocketDebuggerUrl']

                # Initialize the simulator in the browser tab
                config = {
                    'mode': 'start',
                    'screenReader': screen_reader,
                    'verbosity': verbosity,
                    'options': {
                        'startFromFocus': start_from_focus,
                        'syncFocus': sync_focus,
                    },
                }
                result = _sr_execute(ws_url, config)

                if result.get('ok') or result.get('announcement'):
                    sr_state['active'] = True
                    sr_state['screen_reader'] = screen_reader
                    sr_state['verbosity'] = verbosity
                    sr_state['sync_mouse'] = sync_mouse
                    sr_state['script_injected'] = True
                    sr_state['tab_ws_url'] = ws_url
                    self.send_json({
                        'ok': True,
                        'announcement': result.get('announcement', ''),
                        'role': result.get('role', ''),
                        'name': result.get('name', ''),
                        'rect': result.get('rect'),
                        'position': result.get('position'),
                        'language': result.get('language', 'en'),
                    })
                else:
                    self.send_json({'ok': False, 'error': result.get('error', 'Failed to start SR simulator')}, 500)
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/sr/navigate':
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_length).decode() if content_length > 0 else '{}'
                data = json.loads(body)

                action = data.get('action')
                params = data.get('params', {})

                if not action:
                    self.send_json({'ok': False, 'error': 'Missing action'}, 400)
                    return

                if not sr_state['active'] or not sr_state['tab_ws_url']:
                    self.send_json({'ok': False, 'error': 'SR simulator not active'}, 400)
                    return

                ws_url = sr_state['tab_ws_url']

                # Navigate in the simulator
                config = {
                    'mode': 'navigate',
                    'action': action,
                    'params': params,
                }
                result = _sr_execute(ws_url, config)

                # Move system mouse pointer if sync_mouse is enabled
                if sr_state.get('sync_mouse') and result.get('ok') and result.get('rect'):
                    try:
                        rect = result['rect']
                        mx = int(rect['x'] + rect['width'] / 2)
                        my = int(rect['y'] + rect['height'] / 2)
                        subprocess.run(
                            ['xdotool', 'mousemove', str(mx), str(my)],
                            env={**os.environ, 'DISPLAY': DISPLAY},
                            timeout=2, capture_output=True,
                        )
                    except Exception:
                        pass  # Mouse sync is best-effort

                self.send_json(result)

            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/sr/stop':
            try:
                if sr_state['active'] and sr_state['tab_ws_url']:
                    config = {'mode': 'stop'}
                    _sr_execute(sr_state['tab_ws_url'], config)

                sr_state['active'] = False
                sr_state['screen_reader'] = None
                sr_state['script_injected'] = False
                sr_state['tab_ws_url'] = None
                self.send_json({'ok': True})
            except Exception as e:
                # Still mark as stopped even if cleanup fails
                sr_state['active'] = False
                sr_state['screen_reader'] = None
                sr_state['script_injected'] = False
                sr_state['tab_ws_url'] = None
                self.send_json({'ok': True})

        elif path == '/sr/speak':
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_length).decode() if content_length > 0 else '{}'
                data = json.loads(body)
                text = data.get('text', '')
                lang = data.get('lang', 'en')
                rate = data.get('rate', 1.5)

                if not sr_state['active'] or not sr_state['tab_ws_url']:
                    self.send_json({'ok': False, 'error': 'SR simulator not active'}, 400)
                    return

                # Execute speechSynthesis in the browser tab
                js_speak = f'''
(() => {{
    const synth = window.speechSynthesis;
    synth.cancel();
    const utterance = new SpeechSynthesisUtterance({json.dumps(text)});
    utterance.rate = {rate};
    utterance.lang = {json.dumps(lang)};
    synth.speak(utterance);
    return {{ ok: true }};
}})()
'''
                result = send_cdp_command(sr_state['tab_ws_url'], 'Runtime.evaluate', {
                    'expression': js_speak,
                    'returnByValue': True,
                })
                self.send_json({'ok': True})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/sr/scroll':
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_length).decode() if content_length > 0 else '{}'
                data = json.loads(body)

                if not sr_state['active'] or not sr_state['tab_ws_url']:
                    self.send_json({'ok': False, 'error': 'SR simulator not active'}, 400)
                    return

                # Scroll to bring the current SR element into view
                js_scroll = '''
(() => {
    if (!window.__inspektSR || !window.__inspektSR.cursor) return { ok: false };
    const el = window.__inspektSR.cursor.getCurrentElement();
    if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        // Return updated rect after scroll settles
        return new Promise(resolve => {
            setTimeout(() => {
                const r = el.getBoundingClientRect();
                resolve({ ok: true, rect: { x: r.x, y: r.y, width: r.width, height: r.height } });
            }, 300);
        });
    }
    return { ok: false };
})()
'''
                result = send_cdp_command(sr_state['tab_ws_url'], 'Runtime.evaluate', {
                    'expression': js_scroll,
                    'returnByValue': True,
                    'awaitPromise': True,
                })
                value = result.get('result', {}).get('result', {}).get('value', {})
                self.send_json(value if value else {'ok': False})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path.startswith('/internal/') or path.startswith('/api/'):
            # Reverse proxy to Inspekt API server (port 80)
            self._proxy_to_api('POST')

        else:
            self.send_json({'error': 'Not found'}, 404)

    def do_PUT(self):
        path = urlparse(self.path).path
        if path.startswith('/internal/') or path.startswith('/api/'):
            self._proxy_to_api('PUT')
        else:
            self.send_json({'error': 'Not found'}, 404)

    def do_DELETE(self):
        path = urlparse(self.path).path
        if path.startswith('/internal/') or path.startswith('/api/'):
            self._proxy_to_api('DELETE')
        else:
            self.send_json({'error': 'Not found'}, 404)

    def log_message(self, format, *args):
        print(f"[control-server] {args[0]}")


if __name__ == '__main__':
    print(f"Starting control server on port {PORT}...")
    server = ThreadingHTTPServer(('0.0.0.0', PORT), ControlHandler)
    server.serve_forever()
