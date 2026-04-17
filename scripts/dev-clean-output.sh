#!/bin/sh
# Filter for child-process stdout/stderr under overmind.
#
# - Strips leading whitespace (so `   Compiling foo` becomes `Compiling foo`,
#   lining up cleanly under overmind's `prefix |` column).
# - Drops lines that are empty or whitespace-only after the strip.
# - Line-buffered via `fflush()` so output appears in real time.
#
# Usage (in Procfile.dev):
#   some-cmd 2>&1 | scripts/dev-clean-output.sh
exec awk '{ sub(/^[ \t]+/, ""); if ($0 != "") { print; fflush() } }'
