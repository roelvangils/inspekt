# Documentation Guide

MkDocs documentation for Inspekt has been set up with Material theme.

## Quick Start

### Install Documentation Dependencies

```bash
pip install -e ".[dev]"
```

This installs:
- mkdocs>=1.5.0
- mkdocs-material>=9.4.0
- pymdown-extensions>=10.3
- mkdocs-minify-plugin>=0.7.0

### Build and Serve Locally

```bash
# Serve with live reload (default: http://127.0.0.1:8000)
mkdocs serve

# Serve on different port
mkdocs serve -a localhost:8080

# Build static site
mkdocs build

# Build and view
mkdocs build && open site/index.html
```

### Deploy to GitHub Pages

```bash
# Deploy to gh-pages branch
mkdocs gh-deploy

# Deploy with commit message
mkdocs gh-deploy -m "Update documentation"
```

## Documentation Structure

```
docs/
├── index.md                    # Home page
├── getting-started/
│   ├── installation.md         # Installation guide
│   ├── quick-start.md          # Quick start tutorial
│   └── configuration.md        # Configuration options
├── guide/
│   ├── overview.md             # User guide overview
│   ├── basic-commands.md       # Basic commands
│   ├── javascript-execution.md # JavaScript execution
│   ├── element-interaction.md  # Element interaction
│   ├── data-extraction.md      # Data extraction
│   ├── ai-features.md          # AI features
│   ├── control-mode.md         # Control mode
│   └── advanced.md             # Advanced usage
├── api/
│   ├── commands.md             # CLI commands reference
│   ├── services.md             # Services API
│   ├── models.md               # Models API
│   └── protocol.md             # Protocol specification
├── development/
│   ├── architecture.md         # Architecture overview
│   ├── contributing.md         # Contributing guide
│   ├── testing.md              # Testing guide
│   └── security.md             # Security considerations
└── about/
    ├── changelog.md            # Changelog
    └── license.md              # License information
```

## Configuration

The `mkdocs.yml` configuration includes:

- **Material Theme**: Modern, responsive design with dark/light mode
- **Navigation**: Tabs, sections, and instant loading
- **Search**: Full-text search with highlighting
- **Code**: Syntax highlighting with copy buttons
- **Extensions**: Admonitions, tabs, diagrams (Mermaid), and more

## Writing Documentation

### Markdown Features

All standard Markdown is supported, plus:

#### Admonitions

```markdown
!!! note "Optional Title"
    This is a note admonition.

!!! warning
    This is a warning.

!!! tip
    This is a tip.
```

#### Code Blocks

```markdown
\`\`\`python
def example():
    return "Hello"
\`\`\`

\`\`\`bash
inspekt exec "document.title"
\`\`\`
```

#### Tabs

```markdown
=== "Tab 1"
    Content for tab 1

=== "Tab 2"
    Content for tab 2
```

#### Mermaid Diagrams

```markdown
\`\`\`mermaid
graph LR
    A[CLI] --> B[Server]
    B --> C[Browser]
\`\`\`
```

### Navigation

Edit the `nav` section in `mkdocs.yml` to modify site navigation:

```yaml
nav:
  - Home: index.md
  - Getting Started:
      - Installation: getting-started/installation.md
  # ... more sections
```

## GitHub Pages Setup

### One-Time Setup

1. Enable GitHub Pages in repository settings
2. Set source to `gh-pages` branch
3. Run `mkdocs gh-deploy`

### Continuous Deployment

Add to `.github/workflows/docs.yml`:

```yaml
name: Deploy Documentation

on:
  push:
    branches: [main]
    paths:
      - 'docs/**'
      - 'mkdocs.yml'

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: 3.x
      - run: pip install mkdocs-material pymdown-extensions mkdocs-minify-plugin
      - run: mkdocs gh-deploy --force
```

## Useful Commands

```bash
# Check for broken links
mkdocs build --strict

# Generate search index
mkdocs build

# Clean build directory
rm -rf site/

# Validate configuration
mkdocs build --clean --strict
```

## Tips

1. **Preview changes**: Always run `mkdocs serve` to preview locally
2. **Test navigation**: Verify all internal links work
3. **Mobile check**: Material theme is responsive - test on mobile
4. **Search index**: Rebuild to update search after content changes
5. **Version control**: Commit docs/ and mkdocs.yml, ignore site/

## Troubleshooting

### Port Already in Use

```bash
# Use different port
mkdocs serve -a localhost:8001
```

### Build Errors

```bash
# Verbose output
mkdocs build --verbose

# Strict mode (fails on warnings)
mkdocs build --strict
```

### Missing Dependencies

```bash
# Reinstall docs dependencies
pip install -e ".[dev]" --force-reinstall
```

## Resources

- [MkDocs Documentation](https://www.mkdocs.org/)
- [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/)
- [PyMdown Extensions](https://facelessuser.github.io/pymdown-extensions/)
- [Markdown Guide](https://www.markdownguide.org/)

## Next Steps

1. Install dependencies: `pip install -e ".[dev]"`
2. Start local server: `mkdocs serve`
3. View docs at: http://127.0.0.1:8000
4. Edit markdown files in `docs/`
5. Deploy when ready: `mkdocs gh-deploy`

Happy documenting!
