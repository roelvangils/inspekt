# inspekt validate - Validate Recording Files

The `inspekt validate` command checks recording files for errors before replay. It catches YAML syntax issues, missing files, and logical problems that would cause replay failures.

## Quick Start

```bash
# Validate most recent recording
inspekt validate

# Validate a specific file
inspekt validate my-recording.yaml

# Strict mode - treat warnings as errors
inspekt validate --strict

# JSON output for CI/tooling
inspekt validate --json
```

## Why Use Validation?

Recording files can have issues that aren't immediately obvious:

- **YAML syntax errors** - A missing quote or wrong indentation
- **Missing external files** - Uploaded files that were moved or deleted
- **Timestamp anomalies** - Steps recorded out of order due to async events
- **Invalid selectors** - Empty or malformed CSS selectors

Validation catches these **before** replay starts, saving time and providing helpful tips for fixing issues.

## Command Options

```bash
inspekt validate [OPTIONS] [RECORDING_FILE]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `RECORDING_FILE` | Path to the YAML recording file. If omitted, uses the most recent `recording_*.yaml` in the current directory. |

### Options

| Option | Description |
|--------|-------------|
| `--strict` | Treat warnings as errors (exit code 1 if any warnings) |
| `--json` | Output results as JSON for scripting/CI integration |
| `--help` | Show help message |

## Validation Levels

Inspekt validates recordings at four levels:

### Level 1: Syntax (Blocking)

Checks the file can be parsed as valid YAML.

| Check | Example Error |
|-------|---------------|
| Valid YAML | `YAML syntax error at line 57: expected block end` |
| UTF-8 encoding | `Invalid character encoding` |
| No tab characters | `Tab character found at line 12` |
| Non-empty file | `Recording file is empty` |

### Level 2: Structure (Blocking)

Verifies the recording has the required structure.

| Check | Example Error |
|-------|---------------|
| Has `steps` section | `Missing required 'steps' section` |
| Steps not empty | `Recording contains no steps` |
| Valid action types | `Unknown action 'clck' in step 3` |
| Required fields | `Step 5: 'navigate' action missing 'url'` |

### Level 3: Logic (Blocking)

Checks logical consistency of the recording.

| Check | Example Error |
|-------|---------------|
| External files exist | `Step 7: external file not found: uploads/photo.jpg` |
| Selectors not empty | `Step 3: selector is empty` |
| Timestamps positive | `Step 2: negative timestamp (-500)` |

### Level 4: Warnings (Non-blocking)

Potential issues that don't prevent replay.

| Check | Example Warning |
|-------|-----------------|
| Starts with navigate | `Recording doesn't start with 'navigate'` |
| Large time gaps | `Steps 5-6: 45 second gap` |
| Very long recording | `Recording has 127 steps` |
| Timestamp order | `Step 10: timestamp earlier than step 9` |

## Output Examples

### Success

```
✓ my-recording.yaml validated successfully
```

### Success with Warnings

```
⚠ Warning: Steps 5-6: 45 second gap
  💡 Long pauses may indicate missed interactions during recording.

⚠ Warning: Recording has 127 steps
  💡 Very long recordings may be harder to maintain.
     Consider splitting into smaller recordings.

✓ my-recording.yaml is valid with 2 warning(s)
```

### Errors

```
✗ Error: YAML syntax error: expected block end

   55 │ # Step 0005 · Press Tab (focus moves to 'Theme Color
 > 56 │             …')
   57 │ - timestamp: 14355

  💡 This often happens when a comment contains newlines or special characters.

✗ Error: Step 7: external file not found: uploads/photo.jpg
  💡 Expected: /path/to/recording_files/photo.jpg
     Re-record the upload or restore the file.

Found 2 error(s)
```

### JSON Output

```bash
inspekt validate my-recording.yaml --json
```

```json
{
  "valid": true,
  "file": "my-recording.yaml",
  "errors": [],
  "warnings": [
    {
      "message": "Steps 5-6: 45 second gap",
      "tip": "Long pauses may indicate missed interactions during recording.",
      "step": 6,
      "line": null
    }
  ]
}
```

## Configuration

Validation runs automatically before every `inspekt replay`. You can disable this globally:

```json
// config.json
{
  "replay": {
    "validate": false
  }
}
```

Or skip per-command with `--skip-validation`:

```bash
inspekt replay my-recording.yaml --skip-validation
```

## CI/CD Integration

Use `inspekt validate` in your CI pipeline to catch recording issues early:

```bash
#!/bin/bash
# validate-recordings.sh

FAILED=0
for file in tests/*.yaml; do
    echo "Validating: $file"
    if ! inspekt validate "$file" --strict; then
        FAILED=1
    fi
done

exit $FAILED
```

Or with JSON output for machine parsing:

```bash
inspekt validate recording.yaml --json | jq '.valid'
```

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Valid (no errors, and no warnings if `--strict`) |
| `1` | Invalid (errors found, or warnings with `--strict`) |

## Related Commands

- [inspekt replay](replay.md) - Replay recordings (includes automatic validation)
- [inspekt record](record.md) - Create new recordings
