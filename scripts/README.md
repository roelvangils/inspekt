# scripts/

Active build and dev helpers, all referenced from `Makefile`,
`Procfile.dev`, GitHub workflows, or per-app `CLAUDE.md` docs.
**Adding a new script?** Reference it from one of those entry points
or it doesn't belong here — move it to `archive/scripts/` instead.

| Script | Called by | Purpose |
|---|---|---|
| `build_man.py` | `make build-man` | Generate Click man pages → `inspekt/man/` |
| `build_popover_css.py` | `make build-css` (axe popover docs) | Bundle modular popover CSS into `run_axe.js` / `run_ibm.js` |
| `bump_version.py` | `make bump-version` | Bump version across `pyproject.toml`, `__init__.py`, package.json |
| `bundle-vm.mjs` | `make vm-bundle`, Procfile.dev `vm` watcher | Bundle `vm/control-panel.html` + CSS/JS into `vm/dist/` |
| `dev-clean-output.sh` | Procfile.dev (all four panes) | Strip ANSI cruft from process output for overmind display |
| `ensure-docker.sh` | `make ensure-docker` | Verify Docker is running before VM commands |
| `import_aria_at_data.py` | `.github/workflows/sync-sr-data.yml` | Sync ARIA-AT screen reader expected-output dataset |
| `watch-extensions.js` | `make dev-extension`, Procfile.dev `extension` | Hot-reload Chrome/Firefox extensions on file change |

Build artifacts live alongside source (e.g. `vm/dist/`,
`inspekt/man/`); these scripts are *generators*, never the artifact.

For one-shot migrations or scripts that only ran once, see
[`archive/scripts/`](../archive/scripts/).
