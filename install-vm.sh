#!/usr/bin/env bash
#
# Inspekt VM — one-command installer for a fresh macOS machine.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/roelvangils/inspekt/main/install-vm.sh | bash
#
# Or clone first and run locally:
#   ./install-vm.sh
#
# Prerequisites: macOS with internet access. That's it.
# The script will install Docker if needed and fetch the repo via Git or tarball.

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────

REPO_URL="https://github.com/roelvangils/inspekt"
TARBALL_URL="https://github.com/roelvangils/inspekt/archive/refs/heads/feature/vm-install-script.tar.gz"
INSTALL_DIR="${INSPEKT_DIR:-$HOME/inspekt}"
SCRIPT_URL="https://raw.githubusercontent.com/roelvangils/inspekt/feature/vm-install-script/install-vm.sh"

INSTALLER_VERSION="0.8"

IMAGE_NAME="inspekt-browser-vm"
CONTAINER_NAME="inspekt-browser-vm"

NOVNC_PORT=6080
CONTROL_PORT=8888
VM_PORTS=(6080 6081 8767 8768 8888 8889 9222)

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
  printf "${BOLD}%s${RESET} [Y/n] " "$1"
  read -r answer </dev/tty
  [[ -z "$answer" || "$answer" =~ ^[Yy] ]]
}


rerun_hint() {
  # Show the right command depending on how the script was invoked
  if [[ -f "${BASH_SOURCE[0]:-}" && "${BASH_SOURCE[0]:-}" != "" ]]; then
    echo "    ${BOLD}$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")${RESET}"
  else
    echo "    ${BOLD}curl -fsSL ${SCRIPT_URL} | bash${RESET}"
  fi
}

# ── Preflight: macOS check ──────────────────────────────────────────────────

preflight() {
  if [[ "$(uname)" != "Darwin" ]]; then
    fatal "This installer is for macOS only (detected: $(uname))"
  fi

  # Check that curl exists (needed for tarball fallback and health checks)
  if ! command -v curl &>/dev/null; then
    fatal "curl is required but not found"
  fi
}

# ── Step 1: Check Docker ────────────────────────────────────────────────────

check_docker() {
  if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
    success "Docker is installed and running"
    return 0
  fi

  if command -v docker &>/dev/null; then
    warn "Docker is installed but not running"
    echo ""
    echo "  Trying to start it..."
    # Try starting whichever Docker app is installed
    open -a OrbStack 2>/dev/null || open -a Docker 2>/dev/null || true
    wait_for_docker
    return 0
  fi

  warn "Docker is not installed"
  echo ""
  echo "  Inspekt VM needs Docker to run. Pick one (both are free):"
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
      echo ""
      info "OrbStack is opening — please complete its setup wizard if prompted."
      wait_for_docker
      ;;
    2)
      install_via_brew "Docker Desktop" "--cask docker"
      open -a Docker
      echo ""
      info "Docker Desktop is opening — please complete its setup wizard if prompted."
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
  info "Waiting for Docker to be ready..."

  local max_wait=300
  local waited=0

  while ! docker info &>/dev/null 2>&1; do
    sleep 3
    waited=$((waited + 3))

    if (( waited % 30 == 0 )); then
      printf "  ${DIM}still waiting... (%ds)${RESET}\n" "$waited"
    fi

    if [[ $waited -ge $max_wait ]]; then
      echo ""
      error "Timed out after ${max_wait}s waiting for Docker"
      echo ""
      echo "  Please start Docker manually, then re-run this script:"
      rerun_hint
      echo ""
      exit 1
    fi
  done

  success "Docker is ready"
}

install_via_brew() {
  local name="$1"
  local brew_args="$2"

  if ! command -v brew &>/dev/null; then
    info "Installing Homebrew first..."
    echo ""
    # Redirect stdin from /dev/tty so Homebrew runs interactively even under curl | bash
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" </dev/tty

    # Add Homebrew to PATH for Apple Silicon
    if [[ -f /opt/homebrew/bin/brew ]]; then
      eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
    echo ""
    success "Homebrew installed (ignore the 'Next steps' above — the script handles it)"
    echo ""
  fi

  info "Installing ${name} via Homebrew..."
  brew install $brew_args
}

# ── Step 2: Detect Docker runtime ───────────────────────────────────────────

detect_docker_runtime() {
  # --network host only works natively on Linux.
  # On Docker Desktop for Mac it silently does nothing.
  # OrbStack supports it. We detect which runtime is in use.
  local docker_context
  docker_context=$(docker info --format '{{.Name}}' 2>/dev/null || echo "unknown")

  if docker info 2>/dev/null | grep -qi "orbstack"; then
    DOCKER_RUNTIME="orbstack"
    USE_HOST_NETWORK=true
  else
    DOCKER_RUNTIME="docker-desktop"
    USE_HOST_NETWORK=false
  fi

  if [[ "$USE_HOST_NETWORK" == true ]]; then
    success "Detected ${DOCKER_RUNTIME} (will use host networking)"
  else
    success "Detected ${DOCKER_RUNTIME} (will use port mappings)"
  fi
}

# ── Step 3: Get the source code ─────────────────────────────────────────────

get_source() {
  if [[ -f "docker/browser-vm/Dockerfile" ]]; then
    # Already inside the repo (user cloned it or ran script from repo root)
    INSTALL_DIR="$(pwd)"
    success "Already in the Inspekt repo"
    return 0
  fi

  if [[ -d "$INSTALL_DIR" && -f "$INSTALL_DIR/docker/browser-vm/Dockerfile" ]]; then
    success "Inspekt repo found at $INSTALL_DIR"
    return 0
  fi

  echo ""
  info "Fetching the Inspekt source code..."

  if command -v git &>/dev/null; then
    info "Cloning via Git..."
    git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
  else
    info "Git not found — downloading tarball instead..."
    mkdir -p "$INSTALL_DIR"
    curl -fsSL "$TARBALL_URL" | tar xz -C "$INSTALL_DIR" --strip-components=1
  fi

  success "Source code ready at $INSTALL_DIR"
}

# ── Step 4: Check ports ─────────────────────────────────────────────────────

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
    echo "  Run this to see what's using them:"
    for port in "${blocked[@]}"; do
      echo "    lsof -iTCP:${port} -sTCP:LISTEN"
    done
    echo ""
    fatal "Cannot start VM with ports in use"
  fi

  success "All required ports are free"
}

# ── Step 5: Clean up any existing container ──────────────────────────────────

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

# ── Step 6: Build the Docker image ──────────────────────────────────────────

build_image() {
  echo ""
  info "Building the Docker image..."
  echo "  ${DIM}This takes 15-30 minutes the first time (subsequent builds are cached).${RESET}"
  echo ""

  if ! docker build \
    -t "$IMAGE_NAME" \
    -f "$INSTALL_DIR/docker/browser-vm/Dockerfile" \
    "$INSTALL_DIR"; then
    echo ""
    fatal "Docker build failed. Check the output above for errors."
  fi

  echo ""
  success "Docker image built"
}

# ── Step 7: Start the container ─────────────────────────────────────────────

start_container() {
  info "Starting Inspekt VM..."

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
    # Explicit port mappings for Docker Desktop on macOS
    run_args+=(
      -p "${NOVNC_PORT}:${NOVNC_PORT}"
      -p 6081:6081
      -p 8767:8767
      -p 8768:8768
      -p "${CONTROL_PORT}:${CONTROL_PORT}"
      -p 8889:8889
      -p 9222:9222
    )
  fi

  docker run "${run_args[@]}" "$IMAGE_NAME" > /dev/null

  success "Container started"
}

# ── Step 8: Wait for services ───────────────────────────────────────────────

wait_for_ready() {
  info "Waiting for services to come up..."

  local max_wait=120
  local waited=0

  while ! curl -sf "http://127.0.0.1:${NOVNC_PORT}/" &>/dev/null; do
    sleep 2
    waited=$((waited + 2))

    # Show a dot every 10 seconds so it doesn't look stuck
    if (( waited % 10 == 0 )); then
      printf "  ${DIM}still waiting... (%ds)${RESET}\n" "$waited"
    fi

    # Check if container is still running
    if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
      echo ""
      error "Container exited unexpectedly"
      echo ""
      echo "  Check logs with: docker logs ${CONTAINER_NAME}"
      exit 1
    fi

    if [[ $waited -ge $max_wait ]]; then
      echo ""
      error "Timed out after ${max_wait}s waiting for noVNC on port ${NOVNC_PORT}"
      echo ""
      echo "  Check logs with: docker logs ${CONTAINER_NAME}"
      exit 1
    fi
  done

  success "All services are up (took ~${waited}s)"
}

# ── Step 9: Open the control panel ──────────────────────────────────────────

open_panel() {
  local url="http://127.0.0.1:${NOVNC_PORT}/control.html"

  echo ""
  echo "  ┌──────────────────────────────────────────────────────┐"
  echo "  │                                                      │"
  printf "  │   ${GREEN}${BOLD}Inspekt VM is running!${RESET}                             │\n"
  echo "  │                                                      │"
  printf "  │   Control panel: ${BOLD}%s${RESET}     │\n" "$url"
  echo "  │                                                      │"
  printf "  │   Stop:    ${DIM}docker stop %s${RESET}        │\n" "$CONTAINER_NAME"
  printf "  │   Restart: ${DIM}docker restart %s${RESET}     │\n" "$CONTAINER_NAME"
  printf "  │   Logs:    ${DIM}docker logs %s${RESET}        │\n" "$CONTAINER_NAME"
  echo "  │                                                      │"
  echo "  └──────────────────────────────────────────────────────┘"
  echo ""

  if ask "Open the control panel in your browser?"; then
    open "$url"
  fi
}

# ── Main ─────────────────────────────────────────────────────────────────────

main() {
  echo ""
  echo "  ${BOLD}Inspekt VM Installer${RESET} ${DIM}(v${INSTALLER_VERSION})${RESET}"
  echo "  ────────────────────────"
  echo ""

  preflight
  check_docker
  detect_docker_runtime
  get_source
  check_ports
  cleanup_existing
  build_image
  start_container
  wait_for_ready
  open_panel
}

main "$@"
