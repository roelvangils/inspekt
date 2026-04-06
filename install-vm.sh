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
TARBALL_URL="https://github.com/roelvangils/inspekt/archive/refs/heads/main.tar.gz"
INSTALL_DIR="${INSPEKT_DIR:-$HOME/inspekt}"

IMAGE_NAME="inspekt-browser-vm"
CONTAINER_NAME="inspekt-browser-vm"

NOVNC_PORT=6080
CONTROL_PORT=8888
VM_PORTS=(6080 6081 8767 8768 8889 9222)

# ── Helpers ──────────────────────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
RESET='\033[0m'

info()    { printf "${BLUE}▸${RESET} %s\n" "$*"; }
success() { printf "${GREEN}✔${RESET} %s\n" "$*"; }
warn()    { printf "${YELLOW}⚠${RESET} %s\n" "$*"; }
error()   { printf "${RED}✖${RESET} %s\n" "$*" >&2; }
fatal()   { error "$*"; exit 1; }

ask() {
  printf "${BOLD}%s${RESET} [Y/n] " "$1"
  read -r answer
  [[ -z "$answer" || "$answer" =~ ^[Yy] ]]
}

# ── Step 1: Check Docker ────────────────────────────────────────────────────

check_docker() {
  if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
    success "Docker is installed and running"
    return 0
  fi

  if command -v docker &>/dev/null; then
    error "Docker is installed but not running"
    echo ""
    echo "  Please start Docker and re-run this script."
    echo ""
    exit 1
  fi

  warn "Docker is not installed"
  echo ""
  echo "  Inspekt VM needs Docker to run. Pick one:"
  echo ""
  echo "    1) OrbStack  — lightweight, fast, recommended   (brew install orbstack)"
  echo "    2) Docker Desktop — official Docker app          (brew install docker)"
  echo "    3) I'll install Docker myself"
  echo ""
  printf "${BOLD}Choice [1/2/3]:${RESET} "
  read -r choice

  case "$choice" in
    1)
      install_via_brew "orbstack" "--cask orbstack"
      echo ""
      info "Starting OrbStack..."
      open -a OrbStack
      echo ""
      echo "  OrbStack needs a moment to start. Once the menubar icon appears,"
      echo "  re-run this script:"
      echo ""
      echo "    ${BOLD}./install-vm.sh${RESET}"
      echo ""
      exit 0
      ;;
    2)
      install_via_brew "Docker Desktop" "--cask docker"
      echo ""
      info "Starting Docker Desktop..."
      open -a Docker
      echo ""
      echo "  Docker Desktop needs a moment to start. Once the whale icon appears"
      echo "  in the menubar, re-run this script:"
      echo ""
      echo "    ${BOLD}./install-vm.sh${RESET}"
      echo ""
      exit 0
      ;;
    3)
      echo ""
      echo "  Install Docker, make sure it's running, then re-run this script."
      exit 0
      ;;
    *)
      fatal "Invalid choice"
      ;;
  esac
}

install_via_brew() {
  local name="$1"
  local brew_args="$2"

  if ! command -v brew &>/dev/null; then
    info "Installing Homebrew first..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

    # Add Homebrew to PATH for Apple Silicon
    if [[ -f /opt/homebrew/bin/brew ]]; then
      eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
  fi

  info "Installing ${name} via Homebrew..."
  brew install $brew_args
}

# ── Step 2: Get the source code ─────────────────────────────────────────────

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

# ── Step 3: Check ports ─────────────────────────────────────────────────────

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
    echo "  Either stop the conflicting processes or run:"
    echo "    lsof -iTCP:<port> -sTCP:LISTEN"
    echo "  to find out what's using them."
    echo ""
    fatal "Cannot start VM with ports in use"
  fi

  success "All required ports are free"
}

# ── Step 4: Clean up any existing container ──────────────────────────────────

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

# ── Step 5: Build the Docker image ──────────────────────────────────────────

build_image() {
  info "Building the Docker image (this takes 15-30 min the first time)..."
  echo ""

  docker build \
    -t "$IMAGE_NAME" \
    -f "$INSTALL_DIR/docker/browser-vm/Dockerfile" \
    "$INSTALL_DIR"

  echo ""
  success "Docker image built"
}

# ── Step 6: Start the container ─────────────────────────────────────────────

start_container() {
  info "Starting Inspekt VM..."

  docker run -d \
    --name "$CONTAINER_NAME" \
    --network host \
    --shm-size=2g \
    --security-opt no-new-privileges:true \
    --cap-drop=ALL \
    --cap-add=SETUID \
    --cap-add=SETGID \
    --cap-add=CHOWN \
    --cap-add=DAC_OVERRIDE \
    --cap-add=FOWNER \
    --cap-add=KILL \
    --cap-add=NET_ADMIN \
    --cap-add=NET_RAW \
    --cap-add=NET_BIND_SERVICE \
    -v inspekt-vm-data:/root/.config/inspekt \
    -v inspekt-vm-sitemaps:/var/cache/inspekt/sitemaps \
    "$IMAGE_NAME" \
    > /dev/null

  success "Container started"
}

# ── Step 7: Wait for services ───────────────────────────────────────────────

wait_for_ready() {
  info "Waiting for services to come up..."

  local max_wait=120
  local waited=0

  while ! curl -sf "http://127.0.0.1:${NOVNC_PORT}/" &>/dev/null; do
    sleep 2
    waited=$((waited + 2))
    if [[ $waited -ge $max_wait ]]; then
      error "Timed out after ${max_wait}s waiting for noVNC on port ${NOVNC_PORT}"
      echo ""
      echo "  Check logs with: docker logs ${CONTAINER_NAME}"
      exit 1
    fi
  done

  success "All services are up (took ~${waited}s)"
}

# ── Step 8: Open the control panel ──────────────────────────────────────────

open_panel() {
  local url="http://127.0.0.1:${NOVNC_PORT}/control.html"

  echo ""
  echo "  ┌─────────────────────────────────────────────────┐"
  echo "  │                                                 │"
  echo "  │   ${GREEN}${BOLD}Inspekt VM is running!${RESET}                      │"
  echo "  │                                                 │"
  echo "  │   Control panel: ${BOLD}${url}${RESET}  │"
  echo "  │                                                 │"
  echo "  │   Stop:    docker stop ${CONTAINER_NAME}     │"
  echo "  │   Restart: docker restart ${CONTAINER_NAME}  │"
  echo "  │   Logs:    docker logs ${CONTAINER_NAME}     │"
  echo "  │                                                 │"
  echo "  └─────────────────────────────────────────────────┘"
  echo ""

  if ask "Open the control panel in your browser?"; then
    open "$url"
  fi
}

# ── Main ─────────────────────────────────────────────────────────────────────

main() {
  echo ""
  echo "  ${BOLD}Inspekt VM Installer${RESET}"
  echo "  ───────────────────"
  echo ""

  check_docker
  get_source
  check_ports
  cleanup_existing
  build_image
  start_container
  wait_for_ready
  open_panel
}

main "$@"
