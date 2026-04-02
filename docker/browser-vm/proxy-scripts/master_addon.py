"""Master mitmproxy addon for InspektVM.

Dynamically loads/unloads proxy scripts based on a JSON config file.
When no scripts are active (or proxy is disabled), acts as a transparent
passthrough with zero overhead.

Config file: /tmp/mitmproxy_config.json
Scripts dir: /opt/proxy-scripts/available/

Config format:
{
  "enabled": true,
  "scripts": {
    "strip_csp": {"enabled": true, "config": {}},
    "inject_css": {"enabled": true, "config": {"url": "http://localhost:8888/proxy/custom.css"}}
  }
}
"""

import fnmatch
import importlib.util
import json
import logging
import os
import sys
import time
import traceback
from pathlib import Path

from mitmproxy import ctx, http

CONFIG_PATH = "/tmp/mitmproxy_config.json"
SCRIPTS_DIR = Path("/opt/proxy-scripts/available")
LOG_PATH = "/tmp/mitmproxy_activity.jsonl"

# Maximum number of activity log entries to keep
MAX_LOG_ENTRIES = 500

logger = logging.getLogger("inspekt.proxy")


class ScriptWrapper:
    """Wraps a loaded proxy script module, providing its addon instance."""

    def __init__(self, name: str, module_path: Path, config: dict):
        self.name = name
        self.module_path = module_path
        self.config = config
        self.addon = None
        self._load()

    def _load(self):
        """Load the script module and instantiate its addon class."""
        spec = importlib.util.spec_from_file_location(
            f"proxy_script_{self.name}", self.module_path
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Find the addon class: look for a class with request/response/responseheaders methods
        addon_class = None
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, type) and any(
                hasattr(attr, method)
                for method in ("request", "response", "responseheaders", "error")
            ):
                addon_class = attr
                break

        if addon_class is None:
            raise ValueError(
                f"Script {self.name} has no addon class with request/response methods"
            )

        # Instantiate with config if the constructor accepts it
        try:
            self.addon = addon_class(self.config)
        except TypeError:
            self.addon = addon_class()

    def reload_config(self, config: dict):
        """Update the script's config and reload if it has a configure method."""
        self.config = config
        if hasattr(self.addon, "configure"):
            self.addon.configure(config)


class MasterAddon:
    """Master addon that delegates to dynamically loaded proxy scripts."""

    def __init__(self):
        self._config = {"enabled": False, "scripts": {}}
        self._config_mtime = 0.0
        self._scripts: dict[str, ScriptWrapper] = {}
        self._request_count = 0
        self._active_script_actions = 0
        self._load_config()
        # Always-on addons: loaded unconditionally, independent of user plugin config
        self._builtin_addons = self._load_builtin_addons()

    def _load_builtin_addons(self) -> list:
        """Load built-in addons that run regardless of plugin enabled state."""
        addons = []
        try:
            from importlib.util import spec_from_file_location, module_from_spec
            error_pages_path = SCRIPTS_DIR / "custom_error_pages.py"
            if error_pages_path.exists():
                spec = spec_from_file_location("builtin_error_pages", error_pages_path)
                mod = module_from_spec(spec)
                spec.loader.exec_module(mod)
                if hasattr(mod, "CustomErrorPages"):
                    addons.append(mod.CustomErrorPages())
                    logger.info("Built-in addon loaded: custom_error_pages")
        except Exception:
            logger.error(f"Failed to load built-in error pages: {traceback.format_exc()}")
        return addons

    def _load_config(self):
        """Read config from file, load/unload scripts as needed."""
        try:
            with open(CONFIG_PATH) as f:
                new_config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Could not read config: {e}")
            return

        self._config = new_config
        self._config_mtime = os.path.getmtime(CONFIG_PATH)

        if not new_config.get("enabled", False):
            # Proxy disabled — unload all scripts
            if self._scripts:
                logger.info("Proxy disabled, unloading all scripts")
                self._scripts.clear()
            return

        # Determine which scripts should be active
        desired = {}
        for name, script_conf in new_config.get("scripts", {}).items():
            if script_conf.get("enabled", False):
                desired[name] = script_conf.get("config", {})

        # Unload scripts that are no longer desired
        for name in list(self._scripts.keys()):
            if name not in desired:
                logger.info(f"Unloading proxy script: {name}")
                del self._scripts[name]

        # Load new scripts or update config of existing ones
        for name, script_config in desired.items():
            script_path = SCRIPTS_DIR / f"{name}.py"
            if not script_path.exists():
                logger.warning(f"Script not found: {script_path}")
                continue

            if name in self._scripts:
                # Already loaded — update config if changed
                self._scripts[name].reload_config(script_config)
            else:
                # Load new script
                try:
                    wrapper = ScriptWrapper(name, script_path, script_config)
                    self._scripts[name] = wrapper
                    logger.info(f"Loaded proxy script: {name}")
                except Exception:
                    logger.error(
                        f"Failed to load script {name}: {traceback.format_exc()}"
                    )

    def _maybe_reload_config(self):
        """Check if config file changed and reload if so."""
        try:
            mtime = os.path.getmtime(CONFIG_PATH)
            if mtime != self._config_mtime:
                self._load_config()
        except FileNotFoundError:
            pass

    def _log_activity(self, flow: http.HTTPFlow, script_name: str, action: str):
        """Append an activity entry to the log file."""
        try:
            entry = json.dumps(
                {
                    "ts": time.time(),
                    "url": flow.request.pretty_url,
                    "script": script_name,
                    "action": action,
                }
            )
            with open(LOG_PATH, "a") as f:
                f.write(entry + "\n")

            # Truncate log if it gets too large
            self._active_script_actions += 1
            if self._active_script_actions % 100 == 0:
                self._truncate_log()
        except Exception:
            pass

    def _truncate_log(self):
        """Keep only the last MAX_LOG_ENTRIES lines in the activity log."""
        try:
            with open(LOG_PATH) as f:
                lines = f.readlines()
            if len(lines) > MAX_LOG_ENTRIES:
                with open(LOG_PATH, "w") as f:
                    f.writelines(lines[-MAX_LOG_ENTRIES:])
        except Exception:
            pass

    def _domain_matches(self, name: str, flow: http.HTTPFlow) -> bool:
        """Check if a flow matches the script's domain filter (if any)."""
        scripts_conf = self._config.get("scripts", {})
        domain = scripts_conf.get(name, {}).get("domain", "")
        if not domain:
            return True  # No domain filter = match all
        return fnmatch.fnmatch(flow.request.pretty_host, domain)

    def request(self, flow: http.HTTPFlow):
        """Delegate to enabled scripts' request hooks."""
        self._request_count += 1
        self._maybe_reload_config()

        # Built-in addons (always active, e.g. custom error pages DNS pre-check)
        for addon in self._builtin_addons:
            if hasattr(addon, "request"):
                try:
                    addon.request(flow)
                    if flow.response:
                        return  # Built-in addon generated a response
                except Exception:
                    logger.error(f"Error in built-in request hook: {traceback.format_exc()}")

        if not self._config.get("enabled", False) or not self._scripts:
            return

        for name, wrapper in self._scripts.items():
            if hasattr(wrapper.addon, "request"):
                if not self._domain_matches(name, flow):
                    continue
                try:
                    wrapper.addon.request(flow)
                    if flow.response:
                        # Script generated a response (e.g., blocked the request)
                        self._log_activity(flow, name, "blocked")
                        return
                except Exception:
                    logger.error(
                        f"Error in {name}.request: {traceback.format_exc()}"
                    )

    def responseheaders(self, flow: http.HTTPFlow):
        """Delegate to enabled scripts' responseheaders hooks."""
        if not self._config.get("enabled", False) or not self._scripts:
            return

        for name, wrapper in self._scripts.items():
            if hasattr(wrapper.addon, "responseheaders"):
                if not self._domain_matches(name, flow):
                    continue
                try:
                    wrapper.addon.responseheaders(flow)
                    self._log_activity(flow, name, "modified_headers")
                except Exception:
                    logger.error(
                        f"Error in {name}.responseheaders: {traceback.format_exc()}"
                    )

    def response(self, flow: http.HTTPFlow):
        """Delegate to enabled scripts' response hooks."""
        if not self._config.get("enabled", False) or not self._scripts:
            return

        for name, wrapper in self._scripts.items():
            if hasattr(wrapper.addon, "response"):
                if not self._domain_matches(name, flow):
                    continue
                try:
                    original_content = flow.response.content
                    wrapper.addon.response(flow)
                    if flow.response.content != original_content:
                        self._log_activity(flow, name, "modified_body")
                except Exception:
                    logger.error(
                        f"Error in {name}.response: {traceback.format_exc()}"
                    )

    def error(self, flow: http.HTTPFlow):
        """Delegate to user scripts' error hooks (for logging/monitoring)."""
        if not self._config.get("enabled", False) or not self._scripts:
            return

        for name, wrapper in self._scripts.items():
            if hasattr(wrapper.addon, "error"):
                try:
                    wrapper.addon.error(flow)
                except Exception:
                    logger.error(
                        f"Error in {name}.error: {traceback.format_exc()}"
                    )

    def get_status(self) -> dict:
        """Return current proxy status (called by control server via import)."""
        return {
            "enabled": self._config.get("enabled", False),
            "request_count": self._request_count,
            "active_scripts": list(self._scripts.keys()),
            "available_scripts": [
                p.stem for p in SCRIPTS_DIR.glob("*.py") if p.stem != "__init__"
            ],
        }


addons = [MasterAddon()]
