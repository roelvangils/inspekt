#!/usr/bin/env python3
"""
Simple control server for Inspekt Browser VM.
Provides API endpoints to control the VM from the web interface.
Uses Chrome DevTools Protocol (CDP) for browser navigation in kiosk mode.
"""

import subprocess
import json
import os
import shlex
import time
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote

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
    import time

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
    import time

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


def send_cdp_command(ws_url, method, params=None):
    """Send a CDP command via WebSocket."""
    import asyncio
    import websockets

    async def _send():
        async with websockets.connect(ws_url) as ws:
            msg = {'id': 1, 'method': method, 'params': params or {}}
            await ws.send(json.dumps(msg))
            response = await asyncio.wait_for(ws.recv(), timeout=5)
            return json.loads(response)

    return asyncio.run(_send())

class ControlHandler(BaseHTTPRequestHandler):
    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_OPTIONS(self):
        self.send_json({})

    def do_GET(self):
        path = urlparse(self.path).path

        if path == '/':
            # Serve the control panel HTML
            try:
                with open('/opt/xpra-html5/control.html', 'r') as f:
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
            command = path.split('/inspekt/')[1]
            allowed_commands = ['info', 'axe', 'links', 'outline', 'screenshot', 'url']

            if command not in allowed_commands:
                self.send_json({'ok': False, 'error': 'Command not allowed'}, 400)
                return

            try:
                # Track last command for the active tab
                tab = get_active_tab()
                if tab:
                    last_commands[tab['id']] = command

                result = subprocess.run(
                    ['bash', '-c', f'cd /opt/inspekt && . .venv/bin/activate && inspekt {command}'],
                    capture_output=True,
                    text=True,
                    timeout=30
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

        elif path == '/back':
            try:
                tab = get_active_tab()
                if not tab:
                    self.send_json({'ok': False, 'error': 'No active tab found'}, 500)
                    return
                send_cdp_command(tab['webSocketDebuggerUrl'], 'Page.goBack')
                self.send_json({'ok': True, 'message': 'Navigated back'})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/forward':
            try:
                tab = get_active_tab()
                if not tab:
                    self.send_json({'ok': False, 'error': 'No active tab found'}, 500)
                    return
                send_cdp_command(tab['webSocketDebuggerUrl'], 'Page.goForward')
                self.send_json({'ok': True, 'message': 'Navigated forward'})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/reload-page':
            try:
                tab = get_active_tab()
                if not tab:
                    self.send_json({'ok': False, 'error': 'No active tab found'}, 500)
                    return
                send_cdp_command(tab['webSocketDebuggerUrl'], 'Page.reload')
                self.send_json({'ok': True, 'message': 'Page reloaded'})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/url':
            try:
                tab = get_active_tab()
                if not tab:
                    self.send_json({'ok': False, 'error': 'No active tab found'}, 500)
                    return
                self.send_json({'ok': True, 'url': tab.get('url', '')})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/navigate':
            query = parse_qs(urlparse(self.path).query)
            url = query.get('url', [None])[0]

            if not url:
                self.send_json({'ok': False, 'error': 'Missing url parameter'}, 400)
                return

            try:
                tab = get_active_tab()
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

        elif path == '/tabs/new':
            # Create a new tab using CDP directly
            # CDP on port 9222 only affects the VM's Chromium, not the host browser
            query = parse_qs(urlparse(self.path).query)
            url = query.get('url', ['about:blank'])[0]

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
                # Clean up old thumbnails periodically
                cleanup_thumbnails()

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
            # Note: VM is sandboxed, so we allow any absolute path
            # This enables downloading files from current working directory
            file_path = os.path.abspath(file_path)

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

        else:
            self.send_json({'error': 'Not found'}, 404)

    def do_POST(self):
        global auto_scan_enabled, terminal_hidden
        path = urlparse(self.path).path

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

        else:
            self.send_json({'error': 'Not found'}, 404)

    def log_message(self, format, *args):
        print(f"[control-server] {args[0]}")


if __name__ == '__main__':
    print(f"Starting control server on port {PORT}...")
    server = HTTPServer(('0.0.0.0', PORT), ControlHandler)
    server.serve_forever()
