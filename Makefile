.PHONY: help dev install clean test test-unit test-integration test-e2e lint format typecheck pre-commit all \
       vm-start vm-stop vm-restart vm-rebuild vm-status vm-logs vm-shell vm-services vm-health \
       vm-restart-control vm-restart-terminal vm-restart-chromium vm-restart-proxy \
       vm-bundle \
       build-man install-man clean-man

# Default target
help:
	@echo "Inspekt - Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make dev          Install package in development mode with all dependencies"
	@echo "  make install      Install package for production use"
	@echo "  make clean        Remove build artifacts and caches"
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
	@echo ""
	@echo "Combined:"
	@echo "  make all          Run format, lint, typecheck, and test"
	@echo ""
	@echo "Man pages (requires pandoc):"
	@echo "  make build-man    Regenerate man pages and copy to inspekt/man/"
	@echo "  make install-man  Install shipped man pages for the current user"
	@echo "  make clean-man    Remove generated man-page intermediates"

# Development setup
dev:
	pip install -e ".[dev]"
	@echo ""
	@echo "✓ Development environment ready!"
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
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	@echo "✓ Cleaned build artifacts"

# Testing
test:
	pytest tests/ -v --cov=inspekt --cov-report=term-missing --cov-report=html
	@echo ""
	@echo "✓ Tests complete. Coverage report: htmlcov/index.html"

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
	@echo "✓ Code formatted"

typecheck:
	mypy inspekt/ --config-file=pyproject.toml

# Pre-commit
pre-commit:
	pre-commit install
	pre-commit run --all-files
	@echo "✓ Pre-commit hooks installed and run"

# Run all checks
all: format lint typecheck test
	@echo ""
	@echo "✓ All checks passed!"

# ── Browser VM ──────────────────────────────────────────────

# Auto-detect container name (CLI creates "inspekt-browser-vm", Compose creates "inspekt-browser")
VM_CONTAINER := $(shell docker ps --format '{{.Names}}' --filter 'name=inspekt-browser' 2>/dev/null | head -1)

vm-start:
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
	@printf "Control server (8888): " && curl -sf http://localhost:8888/health > /dev/null && echo "✓" || echo "✗"
	@printf "noVNC (6080):          " && curl -sf http://localhost:6080/ > /dev/null && echo "✓" || echo "✗"
	@printf "CDP (9222):            " && curl -sf http://localhost:9222/json/version > /dev/null && echo "✓" || echo "✗"

# ── Man pages ───────────────────────────────────────────────

# Regenerate every man page from the live CLI + registry, then commit a copy
# under inspekt/man/ so the wheel can ship them without pandoc on the build host.
build-man:
	python scripts/build_man.py --output-dir build/man --commit-to-package
	@echo "✓ Man pages written to build/man/ and inspekt/man/"

# Install the shipped man pages for the current user (no sudo required).
install-man:
	inspekt man install --user

clean-man:
	rm -rf build/man inspekt/man/*.1 inspekt/man/*.7
	@echo "✓ Removed generated man pages"
