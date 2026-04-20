.PHONY: help dev install clean test test-unit test-integration test-e2e lint format typecheck pre-commit all \
       vm-start vm-stop vm-restart vm-rebuild vm-status vm-logs vm-shell vm-services vm-health \
       vm-restart-control vm-restart-terminal vm-restart-chromium vm-restart-proxy \
       vm-bundle ensure-docker \
       build-man install-man clean-man \
       dev-cli dev-extension dev-vm dev-desktop dev-all sync-extension \
       build-cli build-vm build-extensions build-desktop build-pdf-viewer build-all \
       version doctor verify-extension-sync

VERSION := $(shell cat VERSION 2>/dev/null || echo 0.0.0)

# Default target
help:
	@echo "Inspekt $(VERSION) — Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make dev          Install package in development mode with all dependencies"
	@echo "  make install      Install package for production use"
	@echo "  make clean        Remove build artifacts and caches"
	@echo ""
	@echo "Development (one command per surface):"
	@echo "  make dev-cli       Start the bridge daemon"
	@echo "  make dev-extension Watch extensions/ for changes"
	@echo "  make dev-vm        Bundle control panel on change + hot-swap in container"
	@echo "  make dev-desktop   Start the Tauri desktop shell (apps/desktop)"
	@echo "  make dev-all       Run all four under overmind (Procfile.dev)"
	@echo "  make sync-extension  Copy extensions/chrome into running VM + restart Chromium"
	@echo ""
	@echo "Build (release artifacts):"
	@echo "  make build-cli        Python wheel (dist/)"
	@echo "  make build-vm         Docker image (self-bundles assets)"
	@echo "  make build-extensions Chrome + Firefox zips (dist/)"
	@echo "  make build-desktop    Tauri desktop app (apps/desktop/src-tauri/target)"
	@echo "  make build-pdf-viewer Tauri PDF viewer (apps/pdf-viewer/src-tauri/target)"
	@echo "  make build-all        All five above"
	@echo ""
	@echo "Versioning:"
	@echo "  make version NEW=x.y.z   Write VERSION, propagate to all manifests"
	@echo ""
	@echo "Coherence:"
	@echo "  make doctor              Print state + exit non-zero on mismatches"
	@echo "  make verify-extension-sync  Extension on host == extension in running VM"
	@echo ""
	@echo "Testing:"
	@echo "  make test         Run all tests with coverage"
	@echo "  make test-unit    Run unit tests only"
	@echo "  make test-integration  Run integration tests only"
	@echo "  make test-e2e     Run end-to-end tests (requires browser)"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint         Run linter (ruff check)"
	@echo "  make format       Format code (ruff format)"
	@echo "  make typecheck    Run type checker (mypy)"
	@echo "  make pre-commit   Install and run pre-commit hooks"
	@echo "  make all          format + lint + typecheck + test"
	@echo ""
	@echo "VM internals (rarely invoked directly):"
	@echo "  make vm-start / vm-stop / vm-restart / vm-rebuild / vm-status / vm-logs / vm-shell"
	@echo "  make vm-restart-{control,terminal,chromium,proxy}"
	@echo "  make vm-services / vm-health / vm-bundle"
	@echo ""
	@echo "Man pages (requires pandoc):"
	@echo "  make build-man    Regenerate man pages and copy to inspekt/man/"
	@echo "  make install-man  Install shipped man pages for the current user"
	@echo "  make clean-man    Remove generated man-page intermediates"

# Development setup
dev:
	pip install -e ".[dev]"
	@echo ""
	@echo "[ok] Development environment ready!"
	@echo "  Run 'make pre-commit' to install pre-commit hooks"
	@echo "  Run 'make test' to run the test suite"

install:
	pip install -e .

# Clean build artifacts
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf .ruff_cache
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf coverage.xml
	rm -rf vm/dist
	rm -rf apps/*/dist
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	@echo "[ok] Cleaned build artifacts"

# Testing
test:
	pytest tests/ -v --cov=inspekt --cov-report=term-missing --cov-report=html
	@echo ""
	@echo "[ok] Tests complete. Coverage report: htmlcov/index.html"

test-unit:
	pytest tests/unit/ -v -m unit

test-integration:
	pytest tests/integration/ -v -m integration

test-e2e:
	pytest tests/e2e/ -v -m e2e

# Code quality
lint:
	ruff check inspekt/ tests/

format:
	ruff format inspekt/ tests/
	@echo "[ok] Code formatted"

typecheck:
	mypy inspekt/ --config-file=pyproject.toml

# Pre-commit
pre-commit:
	pre-commit install
	pre-commit run --all-files
	@echo "[ok] Pre-commit hooks installed and run"

# Run all checks
all: format lint typecheck test
	@echo ""
	@echo "[ok] All checks passed!"

# ── Public dev surface ──────────────────────────────────────

dev-cli:
	inspekt start

dev-extension:
	@bun scripts/watch-extensions.js

dev-vm:
	@echo "• Bundling control panel on change (Ctrl+C to stop)"
	@bun scripts/bundle-vm.mjs
	@$(MAKE) --no-print-directory vm-restart-control
	@echo "• Tip: edit vm/control-panel.html then rerun 'make dev-vm'"

dev-desktop:
	@$(MAKE) --no-print-directory vm-start
	cd apps/desktop && bun run tauri dev

dev-all: ensure-docker
	@command -v overmind >/dev/null 2>&1 || { echo "Install overmind: brew install overmind"; exit 1; }
	@command -v bun >/dev/null 2>&1 || { echo "Install bun: https://bun.sh"; exit 1; }
	@$(MAKE) --no-print-directory vm-start
	@# Stop any lingering background bridge/API daemon so the Procfile's
	@# `inspekt start --foreground` can bind cleanly. Ignore if nothing's there.
	@inspekt stop >/dev/null 2>&1 || true
	@# Remove stale overmind socket + tmux servers from a crashed previous run.
	@if ! pgrep -f "overmind start" >/dev/null 2>&1; then \
		if [ -S ./.overmind.sock ]; then \
			echo "  • Removing stale ./.overmind.sock"; \
			rm -f ./.overmind.sock; \
		fi; \
		for sock in /tmp/tmux-$$(id -u)/overmind-inspekt-*; do \
			[ -S "$$sock" ] || continue; \
			echo "  • Killing stale tmux server $$(basename $$sock)"; \
			tmux -L "$$(basename $$sock)" kill-server 2>/dev/null || true; \
		done; \
	fi
	@#    cli=blue  extension=green  vm=yellow  desktop=magenta
	OVERMIND_COLORS=4,2,3,5 overmind start -f Procfile.dev

sync-extension:
	@if [ -z "$(VM_CONTAINER)" ]; then echo "Error: No VM container running"; exit 1; fi
	docker cp extensions/chrome/. $(VM_CONTAINER):/opt/inspekt/extensions/chrome/
	@$(MAKE) --no-print-directory vm-restart-chromium
	@echo "[ok] Extension synced"

# ── Public build surface ────────────────────────────────────

build-cli:
	uv build --wheel --out-dir dist/

build-vm:
	inspekt vm restart --rebuild

build-extensions:
	@mkdir -p dist
	@cd extensions && zip -qr "../dist/inspekt-chrome-$(VERSION).zip" chrome shared
	@cd extensions && zip -qr "../dist/inspekt-firefox-$(VERSION).zip" firefox shared
	@echo "[ok] dist/inspekt-chrome-$(VERSION).zip"
	@echo "[ok] dist/inspekt-firefox-$(VERSION).zip"

build-desktop:
	cd apps/desktop && bun run tauri build

build-pdf-viewer:
	cd apps/pdf-viewer && bun run tauri build

# NOTE: build-pdf-viewer is deliberately excluded from build-all.
# The pdf-viewer app has broken imports (src/main.ts references
# src/lib/utils/platform which doesn't exist). Run it explicitly with
# `make build-pdf-viewer` once its source tree is fixed.
build-all: build-cli build-extensions build-vm build-desktop
	@echo ""
	@echo "[ok] All artifacts in dist/ and apps/desktop/src-tauri/target/"

# ── Versioning ──────────────────────────────────────────────

version:
	@if [ -z "$(NEW)" ]; then echo "Usage: make version NEW=x.y.z"; exit 1; fi
	@echo "$(NEW)" > VERSION
	@python scripts/bump_version.py

# ── Coherence / health ─────────────────────────────────────

doctor:
	@echo "── Inspekt $(VERSION) ─────────────────────────────"
	@printf "Bridge port:        " && python -c "from inspekt.config import get_bridge_port; print(get_bridge_port())" 2>/dev/null || echo "?"
	@printf "VM container:       " && [ -n "$(VM_CONTAINER)" ] && echo "$(VM_CONTAINER)" || echo "(not running)"
	@printf "VM image id:        " && docker images --format '{{.ID}}' inspekt-browser-vm 2>/dev/null | head -1 | sed 's/^/sha:/' || echo "?"
	@printf "Extension (host):   " && python -c "import json; print(json.load(open('extensions/chrome/manifest.json'))['version'])" 2>/dev/null || echo "?"
	@if [ -n "$(VM_CONTAINER)" ]; then \
		printf "Extension (in VM):  " ; \
		docker exec $(VM_CONTAINER) cat /opt/inspekt/extensions/chrome/manifest.json 2>/dev/null | python -c "import json,sys; print(json.load(sys.stdin)['version'])" 2>/dev/null || echo "(missing)" ; \
	fi
	@printf "Bundle dist:        " && [ -f vm/dist/control.html ] && echo "vm/dist/control.html ok" || echo "(run: make vm-bundle)"
	@if [ -f vm/dist/control.html ] && [ vm/control-panel.html -nt vm/dist/control.html ]; then \
		echo "[warn]  vm/control-panel.html newer than bundle — run: make vm-bundle" ; \
		exit 1 ; \
	fi

verify-extension-sync:
	@if [ -z "$(VM_CONTAINER)" ]; then echo "Error: No VM container running"; exit 1; fi
	@HOST_HASH=$$(cd extensions/chrome && find . -type f -not -path '*/\.*' | LC_ALL=C sort | xargs shasum -a 256 2>/dev/null | shasum -a 256 | cut -c1-16); \
	VM_HASH=$$(docker exec $(VM_CONTAINER) sh -c 'cd /opt/inspekt/extensions/chrome && find . -type f -not -path "*/\.*" | LC_ALL=C sort | xargs sha256sum 2>/dev/null | sha256sum' | cut -c1-16); \
	if [ "$$HOST_HASH" = "$$VM_HASH" ]; then \
		echo "[ok] extension in sync ($$HOST_HASH)" ; \
	else \
		echo "[fail] drift: host=$$HOST_HASH vm=$$VM_HASH"; echo "  run: make sync-extension"; exit 1 ; \
	fi

# ── Browser VM (internal plumbing) ──────────────────────────

# Auto-detect container name (CLI creates "inspekt-browser-vm", Compose creates "inspekt-browser")
VM_CONTAINER := $(shell docker ps --format '{{.Names}}' --filter 'name=inspekt-browser' 2>/dev/null | head -1)

ensure-docker:
	@bash scripts/ensure-docker.sh

vm-start: ensure-docker
	inspekt vm start

vm-stop:
	inspekt vm stop

vm-restart:
	inspekt vm restart

vm-bundle:
	@bun scripts/bundle-vm.mjs

vm-rebuild:
	inspekt vm restart --rebuild

vm-status:
	inspekt vm status

vm-logs:
	inspekt vm logs

vm-shell:
	inspekt vm shell

# Restart individual services inside the container
vm-restart-control:
	@if [ -z "$(VM_CONTAINER)" ]; then echo "Error: No VM container running"; exit 1; fi
	docker exec $(VM_CONTAINER) supervisorctl restart control-server

vm-restart-terminal:
	@if [ -z "$(VM_CONTAINER)" ]; then echo "Error: No VM container running"; exit 1; fi
	docker exec $(VM_CONTAINER) supervisorctl restart terminal-server

vm-restart-chromium:
	@if [ -z "$(VM_CONTAINER)" ]; then echo "Error: No VM container running"; exit 1; fi
	docker exec $(VM_CONTAINER) supervisorctl restart chromium

vm-restart-proxy:
	@if [ -z "$(VM_CONTAINER)" ]; then echo "Error: No VM container running"; exit 1; fi
	docker exec $(VM_CONTAINER) supervisorctl restart mitmproxy

# List all supervised services and their status
vm-services:
	@if [ -z "$(VM_CONTAINER)" ]; then echo "Error: No VM container running"; exit 1; fi
	docker exec $(VM_CONTAINER) supervisorctl status

# Health check all endpoints (hits host ports, no container exec needed)
vm-health:
	@printf "Control server (8888): " && curl -sf http://localhost:8888/health > /dev/null && echo "[ok]" || echo "[fail]"
	@printf "noVNC (6080):          " && curl -sf http://localhost:6080/ > /dev/null && echo "[ok]" || echo "[fail]"
	@printf "CDP (9222):            " && curl -sf http://localhost:9222/json/version > /dev/null && echo "[ok]" || echo "[fail]"

# ── Man pages ───────────────────────────────────────────────

# Regenerate every man page from the live CLI + registry, then commit a copy
# under inspekt/man/ so the wheel can ship them without pandoc on the build host.
build-man:
	python scripts/build_man.py --output-dir build/man --commit-to-package
	@echo "[ok] Man pages written to build/man/ and inspekt/man/"

# Install the shipped man pages for the current user (no sudo required).
install-man:
	inspekt man install --user

clean-man:
	rm -rf build/man inspekt/man/*.1 inspekt/man/*.7
	@echo "[ok] Removed generated man pages"
