**inspekt** is a command-line companion for a real, running browser. It
connects to a browser extension (Chrome, Firefox, Safari) or an isolated
Chromium running inside the Inspekt VM, and exposes that session as a rich set
of subcommands: navigate, click and type, run accessibility audits, extract
content, take screenshots, record and replay flows, query the DOM, drive
plugins, and expose everything to AI agents over MCP.

Most commands operate on the *currently focused* browser tab. Use the global
**--instance** option to target a specific browser instance by its short ID,
alias, or zero-based index.
