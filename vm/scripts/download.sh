#!/bin/bash
# Download file from VM to host browser
#
# Usage: download <file>
#
# This command triggers the host browser to download the specified file
# from the VM using a custom escape sequence that the control panel intercepts.
#
# Security restrictions:
# - Files must be in /root/Downloads (symlinks are resolved)
# - Maximum file size: 5MB

DOWNLOAD_DIR="/root/Downloads"
MAX_SIZE_BYTES=$((5 * 1024 * 1024))  # 5MB in bytes
MAX_SIZE_HUMAN="5MB"

if [ -z "$1" ]; then
    echo "Usage: download <file>"
    echo "       download <file1> <file2> ..."
    echo ""
    echo "Files must be in: $DOWNLOAD_DIR"
    echo "Maximum file size: $MAX_SIZE_HUMAN"
    echo ""
    echo "Example:"
    echo "  cd $DOWNLOAD_DIR"
    echo "  download myfile.txt"
    exit 1
fi

# Ensure download directory exists
mkdir -p "$DOWNLOAD_DIR"

for arg in "$@"; do
    # Resolve to absolute path (handle both relative and absolute paths)
    if [[ "$arg" = /* ]]; then
        # Already absolute path
        FILE="$arg"
    else
        # Relative path - prepend current directory
        FILE="$(pwd)/$arg"
    fi

    # Check file exists before resolving (to give better error message)
    if [ ! -e "$FILE" ]; then
        echo "Error: File not found: $FILE"
        continue
    fi

    # SECURITY: Resolve symlinks to get the REAL path
    # This prevents symlink attacks where a link in /root/Downloads points elsewhere
    REAL_FILE=$(realpath "$FILE" 2>/dev/null)

    if [ -z "$REAL_FILE" ]; then
        echo "Error: Cannot resolve path: $FILE"
        continue
    fi

    # Security check: resolved file must be in /root/Downloads
    if [[ "$REAL_FILE" != "$DOWNLOAD_DIR"/* ]]; then
        echo "Error: Access denied. Files must be in $DOWNLOAD_DIR"
        echo "       Path: $FILE"
        if [ "$FILE" != "$REAL_FILE" ]; then
            echo "       Resolves to: $REAL_FILE (symlinks not allowed)"
        fi
        echo ""
        echo "Tip: Copy your file first:"
        echo "  cp \"$arg\" $DOWNLOAD_DIR/"
        echo "  cd $DOWNLOAD_DIR && download $(basename "$arg")"
        continue
    fi

    if [ ! -f "$REAL_FILE" ]; then
        echo "Error: Not a regular file: $REAL_FILE"
        continue
    fi

    # Check file size
    FILE_SIZE=$(stat -c%s "$REAL_FILE" 2>/dev/null || stat -f%z "$REAL_FILE" 2>/dev/null)

    if [ -z "$FILE_SIZE" ]; then
        echo "Error: Cannot determine file size: $REAL_FILE"
        continue
    fi

    if [ "$FILE_SIZE" -gt "$MAX_SIZE_BYTES" ]; then
        # Convert to human readable
        FILE_SIZE_MB=$(echo "scale=2; $FILE_SIZE / 1024 / 1024" | bc)
        echo "Error: File too large (${FILE_SIZE_MB}MB). Maximum size is $MAX_SIZE_HUMAN"
        echo "       File: $(basename "$REAL_FILE")"
        continue
    fi

    # Output special escape sequence that JavaScript will intercept
    # Format: OSC 1337 ; download=<path> BEL
    # This is similar to iTerm2's proprietary escape sequences
    printf '\033]1337;download=%s\007' "$REAL_FILE"

    # Show user feedback (this appears after the escape sequence is stripped)
    echo "↓ $(basename "$REAL_FILE")"
done
