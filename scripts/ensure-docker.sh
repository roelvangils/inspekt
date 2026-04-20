#!/usr/bin/env bash
# Ensure the Docker daemon is reachable. On macOS, auto-launch OrbStack (preferred)
# or Docker Desktop if the daemon isn't responding, then poll until it is.
#
# Opt out with INSPEKT_NO_AUTOSTART_DOCKER=1 (CI, scripted runs, etc.). Also skips
# auto-launch when stdout isn't a TTY.

set -eu

if docker info >/dev/null 2>&1; then
  exit 0
fi

if [ ! -t 1 ] || [ "${INSPEKT_NO_AUTOSTART_DOCKER:-}" = "1" ]; then
  echo "Error: Docker daemon not reachable. Start Docker Desktop or OrbStack and retry." >&2
  exit 1
fi

if [ "$(uname -s)" != "Darwin" ]; then
  echo "Error: Docker daemon not reachable. Start it and retry." >&2
  exit 1
fi

launched=""
for app in OrbStack Docker; do
  if open -a "$app" >/dev/null 2>&1; then
    launched="$app"
    break
  fi
done

if [ -z "$launched" ]; then
  echo "Error: Docker daemon not reachable and no Docker app found (OrbStack or Docker Desktop)." >&2
  echo "Install one (https://orbstack.dev or https://docker.com) and retry." >&2
  exit 1
fi

echo "• Docker not running — launching $launched…"
printf "• Waiting for Docker daemon"
for _ in $(seq 1 30); do
  if docker info >/dev/null 2>&1; then
    echo
    echo "  [ok] Docker is ready"
    exit 0
  fi
  printf "."
  sleep 1
done

echo
echo "Error: Docker didn't come up within 30s. Check $launched manually." >&2
exit 1
