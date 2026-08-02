#!/usr/bin/env bash
#
# DEPRECATED: install-vm.sh has been replaced by the unified installer.
# This shim forwards to `install.sh --vm` so old docs and curl one-liners
# keep working.
#
#   ./install.sh            # interactive (CLI + VM)
#   ./install.sh --vm       # what this script used to do
#   ./install.sh --cli-only # fast path, no Docker

set -euo pipefail

echo "▸ install-vm.sh is deprecated — forwarding to install.sh --vm" >&2

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]:-.}")" 2>/dev/null && pwd)"

if [[ -n "${script_dir:-}" && -f "$script_dir/install.sh" ]]; then
  exec bash "$script_dir/install.sh" --vm "$@"
fi

# Piped via curl | bash — fetch the real installer
exec bash -c "$(curl -fsSL https://raw.githubusercontent.com/roelvangils/inspekt/main/install.sh)" -- --vm "$@"
