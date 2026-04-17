#!/bin/bash
# Generate Homebrew resource blocks for Inspekt dependencies
#
# Prerequisites:
#   pip install homebrew-pypi-poet
#
# Usage:
#   ./generate-resources.sh
#
# This script generates the resource blocks needed for the Homebrew formula.
# Run this after:
#   1. Click 8.2.0+ is released and pyproject.toml is updated
#   2. A new release is tagged
#
# The output should be pasted into Formula/inspekt.rb, replacing the
# placeholder resource blocks.

set -e

echo "=== Homebrew Resource Generator for Inspekt ==="
echo

# Check if poet is installed
if ! command -v poet &> /dev/null; then
    echo "Error: homebrew-pypi-poet is not installed"
    echo "Install it with: pip install homebrew-pypi-poet"
    exit 1
fi

# Check if we're in the right directory
if [ ! -f "../pyproject.toml" ]; then
    echo "Error: Run this script from the homebrew-inspekt directory"
    exit 1
fi

echo "Generating resource blocks…"
echo "Note: This requires inspekt to be installable from PyPI or locally"
echo

# Try to generate resources
# If inspekt isn't on PyPI yet, install locally first:
#   pip install -e ..
#   poet inspekt

echo "Run the following commands manually:"
echo
echo "  # Install locally if not on PyPI"
echo "  pip install -e .."
echo
echo "  # Generate resources"
echo "  poet inspekt"
echo
echo "Then paste the output into Formula/inspekt.rb"
