# Migration Guide: Zen → Inspekt

This guide helps you migrate from "Zen Browser Bridge" to "Inspekt" (v5.0.0). The rebranding includes several breaking changes that require action.

## Breaking Changes

### 1. Python Package Name Change

**Old:** `zen`
**New:** `inspekt`

**Action Required:**
```bash
# If installed from source, uninstall the old package
pip uninstall zen-bridge

# Reinstall with new package name
pip install -e .
# or
pip install inspekt
```

**Import Changes:**
```python
# Old imports
from zen.app.cli import main
from zen.services import BrowserService
import zen

# New imports
from inspekt.app.cli import main
from inspekt.services import BrowserService
import inspekt
```

### 2. Configuration File Location

**Old:** `~/.zen/config.json`
**New:** `~/.inspekt/config.json`

**Action Required:**
```bash
# Manually migrate your configuration
mkdir -p ~/.inspekt
cp ~/.zen/config.json ~/.inspekt/config.json

# Optional: Remove old config after verifying everything works
rm -rf ~/.zen
```

**Note:** The new version only checks `~/.inspekt/` for configuration files. Make sure to migrate your settings before upgrading.

### 3. Firefox Extension ID Change

**Old ID:** `zen-bridge@roelvangils.github.io`
**New ID:** `inspekt@roelvangils.github.io`

**Action Required:**
1. **Uninstall** the old "Zen Browser Bridge" extension from Firefox
2. **Download** the new "Inspekt" extension (v5.0.0+)
3. **Install** the new extension
4. **Reconfigure** any extension settings or permissions

**Important:** Automatic updates will NOT work. You must manually uninstall and reinstall.

### 4. Userscript Changes

#### Global Function Renamed

**Old:** `zenStore()`
**New:** `inspektStore()`

**Action Required:**
If you have custom scripts or DevTools commands that use `zenStore()`, update them:

```javascript
// Old
zenStore()

// New
inspektStore()
```

#### CSS Classes Renamed

If you have custom styles that target the userscript UI:

| Old Class/Attribute | New Class/Attribute |
|---------------------|---------------------|
| `zen-control-styles` | `inspekt-control-styles` |
| `zen-pulse` | `inspekt-pulse` |
| `data-zen-control-focus` | `data-inspekt-control-focus` |

### 5. Script Paths

**Old:** `zen/scripts/*.js`
**New:** `inspekt/scripts/*.js`

**Action Required:**
Update any references to built-in scripts in your code or documentation:

```python
# Old
from zen.scripts import get_script_path
script_path = "zen/scripts/accessibility.js"

# New
from inspekt.scripts import get_script_path
script_path = "inspekt/scripts/accessibility.js"
```

### 6. CLI Command Name

**Command name remains:** `inspekt` ✓

The CLI command was already renamed to `inspekt` in a previous version, so no action is needed here. However, make sure you're using `inspekt` and not `zen` in any scripts or aliases.

## Non-Breaking Changes

These changes are internal and require no action:

- Chrome extension name (user-facing only)
- Repository name (already updated to `inspekt`)
- Documentation and help text
- Internal console log messages
- Test files and assertions

## Upgrade Checklist

Use this checklist to ensure a smooth migration:

- [ ] Uninstall old Python package: `pip uninstall zen-bridge`
- [ ] Install new package: `pip install -e .` or `pip install inspekt`
- [ ] Migrate config file from `~/.zen/` to `~/.inspekt/`
- [ ] Uninstall Firefox extension "Zen Browser Bridge"
- [ ] Install new Firefox extension "Inspekt"
- [ ] Update any custom scripts using `zenStore()` to use `inspektStore()`
- [ ] Update any Python imports from `zen.*` to `inspekt.*`
- [ ] Update any script path references from `zen/scripts/` to `inspekt/scripts/`
- [ ] Update any custom CSS targeting old class names
- [ ] Test your workflows to ensure everything works

## Version Information

- **Last version as "Zen":** v4.0.0
- **First version as "Inspekt":** v5.0.0
- **Migration period:** Immediate (no backward compatibility)

## Getting Help

If you encounter issues during migration:

1. Check the [GitHub Issues](https://github.com/roelvangils/inspekt/issues)
2. Review the [updated documentation](https://roelvangils.github.io/inspekt/)
3. Report problems: [https://github.com/roelvangils/inspekt/issues/new](https://github.com/roelvangils/inspekt/issues/new)

## Rollback

If you need to rollback to the old version:

```bash
# Reinstall v4.0.0 (last "Zen" version)
git checkout v4.0.0
pip install -e .

# Restore old config
cp ~/.inspekt/config.json ~/.zen/config.json
```

Note: We recommend moving forward to the new version, as future updates will only be released under the "Inspekt" name.
