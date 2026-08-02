#!/usr/bin/env bash
#
# Inspekt — one-command installer for a fresh macOS machine.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/roelvangils/inspekt/main/install.sh | bash
#
# Or clone first and run locally:
#   ./install.sh [--cli-only | --vm | --all] [--non-interactive]
#
# Modes:
#   --cli-only         CLI + dev tooling only (fast, no Docker needed)
#   --vm               Browser VM only (Docker build, ~15-30 min first time)
#   --all              CLI + VM (default when run interactively)
#   --non-interactive  Never prompt; assume defaults (implies --all unless a
#                      mode was given, skips optional installs like Rust)
#
# Prerequisites: macOS with internet access. Everything else is installed
# on demand (Homebrew, Docker/OrbStack, Python, uv, bun).

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────

REPO_URL="https://github.com/roelvangils/inspekt"
TARBALL_URL="https://github.com/roelvangils/inspekt/archive/refs/heads/main.tar.gz"
INSTALL_DIR="${INSPEKT_DIR:-$HOME/inspekt}"
SCRIPT_URL="https://raw.githubusercontent.com/roelvangils/inspekt/main/install.sh"

INSTALLER_VERSION="1.0"

IMAGE_NAME="inspekt-browser-vm"
CONTAINER_NAME="inspekt-browser-vm"

NOVNC_PORT=6080
CONTROL_PORT=8888
# Keep in sync with VM_PORTS in inspekt/app/cli/vm.py (+ CONTROL_PORT)
VM_PORTS=(6080 6081 8767 8768 8888 8889 8890 9222)

MODE=""            # cli | vm | all
INTERACTIVE=true

# ── Helpers ──────────────────────────────────────────────────────────────────

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[0;33m'
BLUE=$'\033[0;34m'
BOLD=$'\033[1m'
DIM=$'\033[2m'
RESET=$'\033[0m'

info()    { printf "${BLUE}▸${RESET} %s\n" "$*"; }
success() { printf "${GREEN}✔${RESET} %s\n" "$*"; }
warn()    { printf "${YELLOW}⚠${RESET} %s\n" "$*"; }
error()   { printf "${RED}✖${RESET} %s\n" "$*" >&2; }
fatal()   { error "$*"; exit 1; }

# Read from /dev/tty so prompts work even when piped via curl | bash
ask() {
  if [[ "$INTERACTIVE" != true ]]; then
    return 0  # non-interactive: accept the default (yes)
  fi
  printf "${BOLD}%s${RESET} [Y/n] " "$1"
  read -r answer </dev/tty
  [[ -z "$answer" || "$answer" =~ ^[Yy] ]]
}

rerun_hint() {
  if [[ -f "${BASH_SOURCE[0]:-}" && "${BASH_SOURCE[0]:-}" != "" ]]; then
    echo "    ${BOLD}$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")${RESET}"
  else
    echo "    ${BOLD}curl -fsSL ${SCRIPT_URL} | bash${RESET}"
  fi
}

# ── Argument parsing ─────────────────────────────────────────────────────────

parse_args() {
  for arg in "$@"; do
    case "$arg" in
      --cli-only)        MODE="cli" ;;
      --vm)              MODE="vm" ;;
      --all)             MODE="all" ;;
      --non-interactive) INTERACTIVE=false ;;
      -h|--help)
        sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
        exit 0
        ;;
      *) fatal "Unknown option: $arg (try --help)" ;;
    esac
  done

  # Piped through curl with no TTY? Fall back to non-interactive.
  if [[ ! -r /dev/tty ]]; then
    INTERACTIVE=false
  fi

  if [[ -z "$MODE" ]]; then
    if [[ "$INTERACTIVE" != true ]]; then
      MODE="all"
      return
    fi
    echo ""
    echo "  What would you like to install?"
    echo ""
    echo "    1) Everything — CLI + Browser VM (recommended)"
    echo "    2) CLI only   — fast, no Docker needed"
    echo "    3) Browser VM only"
    echo ""
    local choice
    printf "${BOLD}Choice [1/2/3]:${RESET} " >/dev/tty
    read -r choice </dev/tty
    case "$choice" in
      2) MODE="cli" ;;
      3) MODE="vm" ;;
      *) MODE="all" ;;
    esac
  fi
}

wants_cli() { [[ "$MODE" == "cli" || "$MODE" == "all" ]]; }
wants_vm()  { [[ "$MODE" == "vm"  || "$MODE" == "all" ]]; }

# ── Preflight: macOS check ──────────────────────────────────────────────────

preflight() {
  if [[ "$(uname)" != "Darwin" ]]; then
    fatal "This installer is for macOS only (detected: $(uname))"
  fi

  if ! command -v curl &>/dev/null; then
    fatal "curl is required but not found"
  fi

  if ! xcode-select -p &>/dev/null; then
    warn "Xcode Command Line Tools not installed"
    info "Installing Command Line Tools (this may open a dialog)…"
    xcode-select --install 2>/dev/null || true
    echo ""
    echo "  If a dialog appeared, click ${BOLD}Install${RESET} and wait for it to finish."
    echo "  Then re-run this script:"
    rerun_hint
    echo ""
    exit 0
  fi
}

# ── Docker ──────────────────────────────────────────────────────────────────

check_docker() {
  if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
    success "Docker is installed and running"
    return 0
  fi

  if command -v docker &>/dev/null; then
    warn "Docker is installed but not running"
    info "Trying to start it…"
    open -a OrbStack 2>/dev/null || open -a Docker 2>/dev/null || true
    wait_for_docker
    return 0
  fi

  warn "Docker is not installed"

  # Detect if running inside a VM — nested virtualization may need enabling
  if sysctl -n machdep.cpu.features 2>/dev/null | grep -qi "VMM" \
     || system_profiler SPHardwareDataType 2>/dev/null | grep -qi "virtual"; then
    echo ""
    warn "It looks like you're running inside a virtual machine."
    echo ""
    echo "  Docker requires hardware virtualization, which typically does not work"
    echo "  inside a virtual machine."
    echo ""
    echo "  ${BOLD}Recommended:${RESET} run this installer on real hardware instead."
    echo ""
    if ! ask "  Continue anyway (probably won't work)?"; then
      exit 0
    fi
  fi

  if [[ "$INTERACTIVE" != true ]]; then
    fatal "Docker is required for the VM but not installed (non-interactive mode). Install OrbStack or Docker Desktop and re-run."
  fi

  echo ""
  echo "  The Inspekt Browser VM needs Docker. Pick one (both are free):"
  echo ""
  echo "    1) OrbStack       — lightweight and fast (recommended)"
  echo "    2) Docker Desktop — the official Docker app"
  echo "    3) I'll install Docker myself"
  echo ""
  local choice
  printf "${BOLD}Choice [1/2/3]:${RESET} " >/dev/tty
  read -r choice </dev/tty

  case "$choice" in
    1)
      install_via_brew "OrbStack" "--cask orbstack"
      open -a OrbStack
      info "OrbStack is opening — complete its setup wizard if prompted."
      wait_for_docker
      ;;
    2)
      install_via_brew "Docker Desktop" "--cask docker"
      open -a Docker
      info "Docker Desktop is opening — complete its setup wizard if prompted."
      wait_for_docker
      ;;
    3)
      echo ""
      echo "  Install Docker, make sure it's running, then re-run this script:"
      rerun_hint
      echo ""
      exit 0
      ;;
    *)
      fatal "Invalid choice. Please enter 1, 2, or 3."
      ;;
  esac
}

wait_for_docker() {
  info "Waiting for Docker to be ready…"
  local max_wait=300
  local waited=0
  while ! docker info &>/dev/null 2>&1; do
    sleep 3
    waited=$((waited + 3))
    if (( waited % 30 == 0 )); then
      printf "  ${DIM}still waiting... (%ds)${RESET}\n" "$waited"
    fi
    if [[ $waited -ge $max_wait ]]; then
      error "Timed out after ${max_wait}s waiting for Docker"
      echo "  Please start Docker manually, then re-run this script:"
      rerun_hint
      exit 1
    fi
  done
  success "Docker is ready"
}

install_via_brew() {
  local name="$1"
  local brew_args="$2"

  if ! command -v brew &>/dev/null; then
    info "Installing Homebrew first…"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" </dev/tty
    if [[ -f /opt/homebrew/bin/brew ]]; then
      eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
    success "Homebrew installed"
  fi

  info "Installing ${name} via Homebrew…"
  # shellcheck disable=SC2086
  brew install $brew_args
}

detect_docker_runtime() {
  # --network host only works natively on Linux and under OrbStack.
  # On Docker Desktop for Mac it silently does nothing.
  if docker info 2>/dev/null | grep -qi "orbstack"; then
    DOCKER_RUNTIME="orbstack"
    USE_HOST_NETWORK=true
    success "Detected OrbStack (will use host networking)"
  else
    DOCKER_RUNTIME="docker-desktop"
    USE_HOST_NETWORK=false
    success "Detected ${DOCKER_RUNTIME} (will use port mappings)"
  fi
}

# ── Development dependencies ────────────────────────────────────────────────

check_uv() {
  if command -v uv &>/dev/null; then
    success "uv is installed ($(uv --version 2>&1 | head -1))"
    return 0
  fi
  if [[ -x "$HOME/.local/bin/uv" ]]; then
    export PATH="$HOME/.local/bin:$PATH"
    success "uv is installed ($(uv --version 2>&1 | head -1))"
    return 0
  fi

  info "Installing uv (fast Python package manager)…"
  if command -v brew &>/dev/null; then
    brew install uv
  else
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
  fi
  success "uv installed"
}

check_bun() {
  if command -v bun &>/dev/null; then
    success "bun is installed ($(bun --version 2>&1))"
    return 0
  fi
  if [[ -x "$HOME/.bun/bin/bun" ]]; then
    export PATH="$HOME/.bun/bin:$PATH"
    success "bun is installed ($(bun --version 2>&1))"
    return 0
  fi

  info "Installing bun (JavaScript runtime)…"
  curl -fsSL https://bun.sh/install | bash
  export PATH="$HOME/.bun/bin:$PATH"
  success "bun installed"
}

check_rust() {
  # Rust is only needed for the optional Tauri desktop app.
  if command -v cargo &>/dev/null; then
    success "Rust is installed ($(rustc --version 2>&1))"
    return 0
  fi
  if [[ -f "$HOME/.cargo/env" ]]; then
    # shellcheck disable=SC1091
    source "$HOME/.cargo/env"
    if command -v cargo &>/dev/null; then
      success "Rust is installed ($(rustc --version 2>&1))"
      return 0
    fi
  fi

  if [[ "$INTERACTIVE" != true ]]; then
    warn "Rust not installed — skipping (only needed for the desktop app)"
    return 0
  fi

  warn "Rust is not installed (only needed for the optional desktop app)"
  if ask "  Install Rust now?"; then
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y </dev/tty
    # shellcheck disable=SC1091
    source "$HOME/.cargo/env"
    success "Rust installed ($(rustc --version 2>&1))"
  else
    warn "Skipping Rust — the desktop app won't build; everything else works"
  fi
}

# ── Python environment ──────────────────────────────────────────────────────

setup_venv() {
  # uv manages the interpreter itself, so no system Python 3.11+ is needed;
  # `uv venv --python 3.13` downloads CPython on demand.
  if [[ -x "$INSTALL_DIR/.venv/bin/inspekt" ]]; then
    info "Existing virtual environment found — updating…"
  else
    info "Setting up Python virtual environment…"
  fi
  (
    cd "$INSTALL_DIR"
    [[ -d .venv ]] || uv venv --python 3.13
    # Editable install with dev extras so tests/lint/docs work out of the box.
    # (Never bare `pip` — Homebrew Pythons are PEP 668 externally-managed.)
    uv pip install -e ".[dev]"
  )
  success "Python environment ready"
}

link_cli() {
  # Make `inspekt` available on PATH without requiring venv activation.
  local target="$INSTALL_DIR/.venv/bin/inspekt"
  local linkdir="$HOME/.local/bin"

  if command -v inspekt &>/dev/null && [[ "$(command -v inspekt)" != "$linkdir/inspekt" ]]; then
    success "inspekt already on PATH ($(command -v inspekt))"
    return 0
  fi

  mkdir -p "$linkdir"
  ln -sf "$target" "$linkdir/inspekt"
  success "Linked inspekt into $linkdir"

  if ! echo ":$PATH:" | grep -q ":$linkdir:"; then
    warn "$linkdir is not on your PATH"
    echo "  Add this to your shell profile (~/.zshrc):"
    echo "    ${BOLD}export PATH=\"\$HOME/.local/bin:\$PATH\"${RESET}"
  fi
}

# ── Source code ─────────────────────────────────────────────────────────────

get_source() {
  if [[ -f "vm/Dockerfile" && -f "pyproject.toml" ]]; then
    INSTALL_DIR="$(pwd)"
    success "Already in the Inspekt repo"
    return 0
  fi

  if [[ -d "$INSTALL_DIR" && -f "$INSTALL_DIR/vm/Dockerfile" ]]; then
    success "Inspekt repo found at $INSTALL_DIR"
    return 0
  fi

  info "Fetching the Inspekt source code…"
  if command -v git &>/dev/null; then
    git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
  else
    info "Git not found — downloading tarball instead…"
    mkdir -p "$INSTALL_DIR"
    curl -fsSL "$TARBALL_URL" | tar xz -C "$INSTALL_DIR" --strip-components=1
  fi
  success "Source code ready at $INSTALL_DIR"
}

# ── VM: ports, container, build, run ────────────────────────────────────────

check_ports() {
  local blocked=()
  for port in "${VM_PORTS[@]}"; do
    if lsof -iTCP:"$port" -sTCP:LISTEN &>/dev/null 2>&1; then
      blocked+=("$port")
    fi
  done

  if [[ ${#blocked[@]} -gt 0 ]]; then
    error "These ports are already in use: ${blocked[*]}"
    echo ""
    echo "  The VM needs them. See what's using them:"
    for port in "${blocked[@]}"; do
      echo "    lsof -iTCP:${port} -sTCP:LISTEN"
    done
    echo ""
    fatal "Free the ports above, then re-run this script"
  fi
  success "All required ports are free"
}

cleanup_existing() {
  if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    warn "Found existing container '${CONTAINER_NAME}'"
    if ask "  Remove it and start fresh?"; then
      docker rm -f "$CONTAINER_NAME" &>/dev/null
      success "Removed old container"
    else
      fatal "Cannot proceed with existing container"
    fi
  fi
}

build_image() {
  echo ""
  info "Building the Docker image…"
  echo "  ${DIM}This takes 15-30 minutes the first time (subsequent builds are cached).${RESET}"
  echo ""

  if ! docker build -t "$IMAGE_NAME" -f "$INSTALL_DIR/vm/Dockerfile" "$INSTALL_DIR"; then
    fatal "Docker build failed. Check the output above for errors."
  fi
  success "Docker image built"
}

start_container() {
  info "Starting Inspekt VM…"

  local run_args=(
    -d
    --name "$CONTAINER_NAME"
    --shm-size=2g
    --security-opt no-new-privileges:true
    --cap-drop=ALL
    --cap-add=SETUID
    --cap-add=SETGID
    --cap-add=CHOWN
    --cap-add=DAC_OVERRIDE
    --cap-add=FOWNER
    --cap-add=KILL
    --cap-add=NET_ADMIN
    --cap-add=NET_RAW
    --cap-add=NET_BIND_SERVICE
    -v inspekt-vm-data:/root/.config/inspekt
    -v inspekt-vm-sitemaps:/var/cache/inspekt/sitemaps
  )

  if [[ "$USE_HOST_NETWORK" == true ]]; then
    run_args+=(--network host)
  else
    for port in "${VM_PORTS[@]}"; do
      run_args+=(-p "${port}:${port}")
    done
  fi

  docker run "${run_args[@]}" "$IMAGE_NAME" > /dev/null
  success "Container started"
}

wait_for_ready() {
  info "Waiting for services to come up…"
  local max_wait=120
  local waited=0

  while ! curl -sf "http://127.0.0.1:${NOVNC_PORT}/" &>/dev/null; do
    sleep 2
    waited=$((waited + 2))
    if (( waited % 10 == 0 )); then
      printf "  ${DIM}still waiting... (%ds)${RESET}\n" "$waited"
    fi
    if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
      error "Container exited unexpectedly"
      echo "  Check logs with: docker logs ${CONTAINER_NAME}"
      exit 1
    fi
    if [[ $waited -ge $max_wait ]]; then
      error "Timed out after ${max_wait}s waiting for noVNC on port ${NOVNC_PORT}"
      echo "  Check logs with: docker logs ${CONTAINER_NAME}"
      exit 1
    fi
  done
  success "All services are up (took ~${waited}s)"
}

# ── Verification & summary ──────────────────────────────────────────────────

verify_cli() {
  local bin="$INSTALL_DIR/.venv/bin/inspekt"
  if ! "$bin" --version &>/dev/null; then
    fatal "CLI verification failed: $bin --version did not run"
  fi
  success "CLI verified ($("$bin" --version 2>&1))"
}

summary() {
  echo ""
  echo "  ${GREEN}${BOLD}Inspekt is installed!${RESET}"
  echo ""
  if wants_cli; then
    echo "  ${BOLD}CLI${RESET}"
    echo "    Activate:   ${DIM}source $INSTALL_DIR/.venv/bin/activate${RESET}"
    echo "    Or run:     ${DIM}inspekt --help${RESET}  (linked in ~/.local/bin)"
    echo "    Bridge:     ${DIM}inspekt start${RESET}   then load the browser extension:"
    echo "                ${DIM}chrome://extensions → Developer mode → Load unpacked → $INSTALL_DIR/extensions/chrome${RESET}"
    echo ""
  fi
  if wants_vm; then
    local url="http://127.0.0.1:${NOVNC_PORT}/control.html"
    echo "  ${BOLD}Browser VM${RESET}"
    echo "    Control panel: ${BOLD}${url}${RESET}"
    echo "    Stop:          ${DIM}docker stop ${CONTAINER_NAME}${RESET}"
    echo "    Restart:       ${DIM}docker restart ${CONTAINER_NAME}${RESET}"
    echo "    Logs:          ${DIM}docker logs ${CONTAINER_NAME}${RESET}"
    echo ""
    if ask "Open the control panel in your browser?"; then
      open "$url"
    fi
  fi
}

# ── Main ─────────────────────────────────────────────────────────────────────

main() {
  parse_args "$@"

  echo ""
  echo "  ${BOLD}Inspekt Installer${RESET} ${DIM}(v${INSTALLER_VERSION}, mode: ${MODE})${RESET}"
  echo "  ─────────────────────"
  echo ""

  preflight
  get_source

  if wants_cli || wants_vm; then
    check_uv
  fi

  if wants_cli; then
    check_bun
    check_rust
    setup_venv
    verify_cli
    link_cli
  fi

  if wants_vm; then
    check_docker
    detect_docker_runtime
    check_ports
    cleanup_existing
    build_image
    start_container
    wait_for_ready
  fi

  summary
}

main "$@"
