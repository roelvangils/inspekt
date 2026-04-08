# Command Development Guide

This guide provides step-by-step instructions for adding new commands or modifying existing ones in Inspekt.

## Table of Contents

1. [Directory Structure](#directory-structure)
2. [Path Resolution Rules](#path-resolution-rules)
3. [Adding a New Command](#adding-a-new-command)
4. [Modifying an Existing Command](#modifying-an-existing-command)
5. [Testing Checklist](#testing-checklist)
6. [Common Pitfalls](#common-pitfalls)

---

## Directory Structure

```
zen_bridge/
├── zen/
│   ├── __init__.py                    # Package version
│   ├── cli.py                          # OLD monolithic CLI (deprecated, kept for reference)
│   ├── app/
│   │   ├── cli/
│   │   │   ├── __init__.py             # CLI entry point, command registration
│   │   │   ├── base.py                 # Base classes, utilities
│   │   │   ├── extraction.py           # Extraction commands (describe, do, outline, links, summarize)
│   │   │   ├── exec.py                 # Execution commands (eval, exec, repl)
│   │   │   ├── inspection.py           # Inspection commands (inspect, inspected, screenshot)
│   │   │   ├── interaction.py          # Interaction commands (click, send, wait)
│   │   │   ├── navigation.py           # Navigation commands (open, back, forward, reload)
│   │   │   ├── selection.py            # Selection commands (selected)
│   │   │   ├── server.py               # Server commands (server start/stop/status)
│   │   │   ├── cookies.py              # Cookie commands (cookies list/get/set/delete/clear)
│   │   │   ├── watch.py                # Watch commands (watch, control)
│   │   │   └── util.py                 # Utility commands (info, userscript, download)
│   │   └── bridge_ws.py                # WebSocket server
│   ├── scripts/                        # JavaScript scripts executed in browser
│   │   ├── extract_actionable_elements.js
│   │   ├── extract_page_structure.js
│   │   ├── extract_outline.js
│   │   ├── extract_links.js
│   │   ├── extract_article.js
│   │   └── ...
│   ├── services/                       # Business logic layer
│   │   ├── bridge_executor.py
│   │   ├── ai_integration.py
│   │   └── ...
│   ├── adapters/                       # I/O adapters
│   └── domain/                         # Domain models
├── prompts/                            # AI prompts (at root level!)
│   ├── describe.prompt
│   ├── do.prompt
│   └── summary.prompt
├── tests/
└── pyproject.toml                      # Entry point: inspekt = "zen.app.cli:main"
```

**Important**: Note that:
- CLI command files are in: `zen/app/cli/`
- JavaScript scripts are in: `zen/scripts/`
- AI prompts are in: `prompts/` (at project root, NOT in zen/)

---

## Path Resolution Rules

When you're in a command file at `zen/app/cli/extraction.py`, here's how to reference other files:

### JavaScript Scripts

Scripts are located at: `zen/scripts/`

From `zen/app/cli/extraction.py`:
```python
script_path = Path(__file__).parent.parent.parent / "scripts" / "my_script.js"
```

**Breakdown**:
- `Path(__file__)` = `/path/to/zen/app/cli/extraction.py`
- `.parent` = `/path/to/zen/app/cli/`
- `.parent.parent` = `/path/to/zen/app/`
- `.parent.parent.parent` = `/path/to/zen/`
- `/ "scripts"` = `/path/to/zen/scripts/`

### AI Prompts

Prompts are located at: `prompts/` (project root)

From `zen/app/cli/extraction.py`:
```python
prompt_path = Path(__file__).parent.parent.parent.parent / "prompts" / "my_prompt.prompt"
```

**Breakdown**:
- `Path(__file__)` = `/path/to/zen/app/cli/extraction.py`
- `.parent` = `/path/to/zen/app/cli/`
- `.parent.parent` = `/path/to/zen/app/`
- `.parent.parent.parent` = `/path/to/zen/`
- `.parent.parent.parent.parent` = `/path/to/` (project root)
- `/ "prompts"` = `/path/to/prompts/`

### Visual Guide

```
extraction.py (you are here)
    ↓ .parent
cli/
    ↓ .parent
app/
    ↓ .parent
zen/                    ← scripts/ lives here
    ↓ .parent
project_root/           ← prompts/ lives here
```

---

## Adding a New Command

### Step 1: Determine Command Category

Decide which module your command belongs to:
- **extraction.py** - Extract/analyze page content (links, headings, AI analysis)
- **exec.py** - Execute JavaScript code
- **inspection.py** - Inspect elements, screenshots
- **interaction.py** - Click, type, wait for elements
- **navigation.py** - Navigate pages, browser history
- **selection.py** - Text selection operations
- **server.py** - Server management
- **cookies.py** - Cookie operations
- **watch.py** - Watch events, control mode
- **util.py** - General utilities (info, download, etc.)

### Step 2: Create JavaScript Script (if needed)

If your command needs to execute JavaScript in the browser:

1. Create script at: `zen/scripts/my_new_script.js`
2. Use IIFE pattern:
   ```javascript
   (function() {
     // Your code here
     return {
       // Return structured data
     };
   })();
   ```
3. Test the script manually first:
   ```bash
   inspekt eval --file zen/scripts/my_new_script.js --format json
   ```

### Step 3: Create AI Prompt (if needed)

If your command uses AI:

1. Create prompt at: `prompts/my_command.prompt`
2. Include clear instructions for the AI
3. Specify expected output format (JSON, text, etc.)
4. Test with `--debug` flag

### Step 4: Add Command Function

Add to the appropriate module (e.g., `zen/app/cli/extraction.py`):

```python
@click.command()
@click.argument("my_arg", type=str)
@click.option("--my-option", is_flag=True, help="Description")
@click.option("--debug", is_flag=True, help="Show the full prompt instead of calling AI")
def my_command(my_arg, my_option, debug):
    """
    Short description of what this command does.

    Longer description with more details about the command's purpose,
    what it analyzes, and what output it produces.

    Examples:
        inspekt my-command "example input"
        inspekt my-command "input" --my-option
    """
    client = BridgeClient()

    # 1. Check if server is alive
    if not client.is_alive():
        click.echo("Error: Bridge server is not running. Start it with: inspekt server start", err=True)
        sys.exit(1)

    # 2. Check for external dependencies (if needed)
    if needs_mods:
        try:
            subprocess.run(["mods", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            click.echo("Error: 'mods' command not found. Please install mods first.", err=True)
            click.echo("Visit: https://github.com/charmbracelet/mods", err=True)
            sys.exit(1)

    # 3. Load JavaScript script (if needed)
    script_path = Path(__file__).parent.parent.parent / "scripts" / "my_script.js"

    if not script_path.exists():
        click.echo(f"Error: Script not found: {script_path}", err=True)
        sys.exit(1)

    try:
        with builtin_open(script_path) as f:
            script = f.read()

        # 4. Execute script
        click.echo("Processing...", err=True)
        result = client.execute(script, timeout=30.0)

        if not result.get("ok"):
            click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)

        # 5. Process result
        data = result.get("result", {})

        # 6. Load AI prompt (if needed)
        prompt_path = Path(__file__).parent.parent.parent.parent / "prompts" / "my_prompt.prompt"

        if not prompt_path.exists():
            click.echo(f"Error: Prompt file not found: {prompt_path}", err=True)
            sys.exit(1)

        with builtin_open(prompt_path) as f:
            prompt = f.read().strip()

        # 7. Combine prompt with data
        full_input = f"{prompt}\n\n---\n\nDATA:\n{json.dumps(data, indent=2)}"

        # 8. Debug mode support
        if debug:
            click.echo("=" * 80)
            click.echo("DEBUG: Full prompt that would be sent to AI")
            click.echo("=" * 80)
            click.echo()
            click.echo(full_input)
            click.echo()
            click.echo("=" * 80)
            return

        # 9. Call AI (if needed)
        try:
            result = subprocess.run(
                ["mods"], input=full_input, text=True, capture_output=True, check=True
            )
            click.echo(result.stdout)
        except subprocess.CalledProcessError as e:
            click.echo(f"Error calling mods: {e}", err=True)
            if e.stderr:
                click.echo(e.stderr, err=True)
            sys.exit(1)

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
```

### Step 5: Register Command

Add to `zen/app/cli/__init__.py`:

```python
# In the appropriate section (e.g., Content extraction commands)
cli.add_command(extraction_module.my_command, name="my-command")
```

### Step 6: Update Documentation

Update the module docstring in the command file:

```python
"""
Content extraction and AI-powered analysis commands.

This module provides commands for extracting and analyzing page content:
- describe: AI-powered page description for screen reader users
- do: AI-powered action matching for natural language navigation
- my_command: Description of new command  # ADD THIS
- outline: Display heading structure as nested outline
...
"""
```

### Step 7: Reinstall Package

```bash
pip install -e . --force-reinstall --no-deps
pyenv rehash  # If using pyenv
```

### Step 8: Test (See Testing Checklist)

---

## Modifying an Existing Command

### Step 1: Locate Command

1. Check `zen/app/cli/__init__.py` to find which module contains the command
2. Open the appropriate module (e.g., `zen/app/cli/extraction.py`)

### Step 2: Understand Dependencies

Check if the command uses:
- JavaScript scripts? → `zen/scripts/`
- AI prompts? → `prompts/`
- Services? → `zen/services/`

### Step 3: Make Changes

When modifying paths, remember:
- Scripts: `.parent.parent.parent / "scripts"`
- Prompts: `.parent.parent.parent.parent / "prompts"`

### Step 4: Test (See Testing Checklist)

---

## Testing Checklist

**CRITICAL**: Always complete ALL steps below before considering a command done.

### 1. Help Text

```bash
# Test that command appears in main help
inspekt --help | grep my-command

# Test command-specific help
inspekt my-command --help
```

**Expected**: Clean, readable help text with examples.

### 2. Path Resolution

```bash
# Test with --debug flag (if applicable) to verify files load
inspekt my-command "test" --debug 2>&1 | head -20

# Check error messages for path issues
# Should NOT see "Script not found" or "Prompt file not found"
```

**Expected**: Files load successfully, no path errors.

### 3. Script Execution

If command uses JavaScript:

```bash
# Test the script directly first
inspekt eval --file zen/scripts/my_script.js --format json

# Then test through the command
inspekt my-command "test input" --debug
```

**Expected**: JavaScript executes without errors, returns expected data structure.

### 4. Full Functionality

```bash
# Test with real input (may require server + browser)
inspekt server start --daemon
# Open browser with userscript active
inspekt my-command "real input"
```

**Expected**: Command executes successfully end-to-end.

### 5. Error Handling

Test error cases:
```bash
# Server not running
inspekt server stop
inspekt my-command "test"  # Should show clear error

# Invalid input
inspekt my-command ""  # Should handle gracefully
inspekt my-command "ñ∂ƒ©˙∆"  # Should handle special characters
```

**Expected**: Clear error messages, no crashes.

### 6. Edge Cases

- Empty results
- Large datasets
- Special characters in input
- Network timeouts (if applicable)

### 7. Integration with Existing Commands

```bash
# Verify you didn't break other commands
inspekt describe --help
inspekt outline --help
inspekt links --help
inspekt summarize --help

# Test a few existing commands
inspekt outline --help
inspekt info --help
```

**Expected**: All commands still work.

### 8. Documentation

- [ ] Module docstring updated
- [ ] Command docstring includes examples
- [ ] README.md updated (if user-facing feature)
- [ ] This guide updated (if new patterns introduced)

---

## Common Pitfalls

### 1. Wrong Path Levels

**Problem**: `Error: Script not found: /path/to/zen/app/scripts/my_script.js`

**Cause**: Used `.parent.parent` instead of `.parent.parent.parent`

**Solution**:
- Scripts: 3 parents → `zen/scripts/`
- Prompts: 4 parents → `prompts/`

### 2. Forgot to Reinstall

**Problem**: Command not found after adding it.

**Solution**:
```bash
pip install -e . --force-reinstall --no-deps
pyenv rehash
```

### 3. Only Tested --help

**Problem**: Help works but command fails with "Script not found"

**Solution**: Always test with `--debug` flag or real input, not just `--help`

### 4. Changed Entry Point but Not Paths

**Problem**: After changing from `zen.cli` to `zen.app.cli`, all commands broke

**Solution**: When changing infrastructure, update ALL path references

### 5. Forgot builtin_open

**Problem**: NameError: name 'open' is not defined (Click shadows built-in)

**Solution**: Use `builtin_open()` from `zen.app.cli.base`
```python
from zen.app.cli.base import builtin_open

with builtin_open(script_path) as f:
    script = f.read()
```

### 6. No Error Handling

**Problem**: Command crashes with Python traceback instead of user-friendly error

**Solution**: Wrap in try/except:
```python
try:
    # Your code
except (ConnectionError, TimeoutError, RuntimeError) as e:
    click.echo(f"Error: {e}", err=True)
    sys.exit(1)
```

### 7. Missing Debug Flag

**Problem**: Can't test AI commands without mods or can't see what's being sent

**Solution**: Always add `--debug` flag for AI commands:
```python
@click.option("--debug", is_flag=True, help="Show the full prompt instead of calling AI")
```

### 8. Not Using err=True

**Problem**: Progress messages mixed with actual output

**Solution**: Use `err=True` for progress/status messages:
```python
click.echo("Processing...", err=True)  # Goes to stderr
click.echo(actual_output)              # Goes to stdout
```

---

## Quick Reference

### File Locations

| Item | Location | From `zen/app/cli/*.py` |
|------|----------|-------------------------|
| JavaScript scripts | `zen/scripts/` | `.parent.parent.parent / "scripts"` |
| AI prompts | `prompts/` | `.parent.parent.parent.parent / "prompts"` |
| Command modules | `zen/app/cli/` | Same directory |
| Services | `zen/services/` | `.parent.parent / "services"` |

### Command Template Locations

- Extraction/AI commands: `zen/app/cli/extraction.py`
- Execution commands: `zen/app/cli/exec.py`
- Interaction commands: `zen/app/cli/interaction.py`

### Testing Commands

```bash
# Full test cycle
inspekt my-command --help                   # 1. Help text
inspekt my-command "test" --debug 2>&1      # 2. Path resolution
inspekt eval --file zen/scripts/test.js     # 3. Script execution
inspekt my-command "real input"             # 4. Full functionality
inspekt my-command ""                       # 5. Error handling
```

---

## When You Break Things

If you break existing commands:

1. **Identify the scope**: Did you change infrastructure (entry points, paths)?
2. **Check all commands**: Test multiple existing commands
3. **Look for patterns**: Same type of error across multiple commands?
4. **Fix systematically**: Update all instances of the pattern
5. **Test everything**: Use the full testing checklist
6. **Document what broke**: Update this guide with the pitfall

---

## Example: Complete Workflow

Let's add a hypothetical `inspekt analyze` command:

```bash
# 1. Create JavaScript script
cat > zen/scripts/analyze_page.js << 'EOF'
(function() {
  return {
    title: document.title,
    links: document.links.length
  };
})();
EOF

# 2. Test script directly
inspekt eval --file zen/scripts/analyze_page.js --format json

# 3. Create AI prompt
cat > prompts/analyze.prompt << 'EOF'
Analyze this page data and provide insights.
Return JSON with "insights" array.
EOF

# 4. Add command to zen/app/cli/extraction.py
# (Add the @click.command() function)

# 5. Register in zen/app/cli/__init__.py
# cli.add_command(extraction_module.analyze, name="analyze")

# 6. Reinstall
pip install -e . --force-reinstall --no-deps
pyenv rehash

# 7. Test help
inspekt analyze --help

# 8. Test with debug
inspekt analyze "test" --debug

# 9. Test full functionality
inspekt analyze "test"

# 10. Test error handling
inspekt server stop
inspekt analyze "test"  # Should show server error
```

---

## Questions or Issues?

If you find gaps in this guide or discover new pitfalls:

1. Document them immediately
2. Update this guide
3. Consider adding automated tests to prevent regression

---

**Remember**: The best code is tested code. Complete the testing checklist every time.
