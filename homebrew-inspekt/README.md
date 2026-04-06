# Homebrew Tap for Inspekt

This is the official Homebrew tap for [Inspekt](https://github.com/roelvangils/inspekt), a browser inspection, accessibility testing, and automation CLI.

## Installation

```bash
brew tap roelvangils/inspekt
brew install inspekt
```

Or install directly:

```bash
brew install roelvangils/inspekt/inspekt
```

## Post-Installation Setup

After installing, complete the setup:

### 1. Start the Bridge Server

```bash
inspekt start --daemon
```

This starts the WebSocket bridge that connects the CLI to your browser.

### 2. Install the Browser Extension

Install the Inspekt browser extension from:
- **Chrome**: [Chrome Web Store](https://chrome.google.com/webstore/detail/inspekt) *(coming soon)*
- **Firefox**: [Firefox Add-ons](https://addons.mozilla.org/firefox/addon/inspekt/) *(coming soon)*

Or install manually from the [releases page](https://github.com/roelvangils/inspekt/releases).

### 3. Verify Installation

```bash
inspekt --version
inspekt status
```

## Shell Completions

Enable tab completions for your shell:

```bash
inspekt completions install
```

This supports Bash, Zsh, and Fish.

## Updating

```bash
brew upgrade inspekt
```

## Troubleshooting

### Bridge Connection Issues

If `inspekt status` shows the server isn't running:

```bash
# Stop any existing instances
inspekt stop

# Start fresh
inspekt start --daemon

# Check status
inspekt status
```

### Extension Not Connecting

1. Ensure the extension is enabled in your browser
2. Refresh the page you're inspecting
3. Check that the bridge server is running (`inspekt status`)

## Documentation

Full documentation is available at [inspekt.dev](https://inspekt.dev).

## License

MIT License - see the [main repository](https://github.com/roelvangils/inspekt) for details.
