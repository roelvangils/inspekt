#!/bin/sh
# Filter for child-process stdout/stderr under overmind.
#
# - Strips leading whitespace (so `   Compiling foo` lines up cleanly
#   under overmind's `prefix |` column).
# - Drops lines that are empty / whitespace-only after the strip.
# - Colors lines by content type:
#     red     errors, failures, tracebacks, panics
#     yellow  warnings, deprecated, stalled
#     green   ready / listening / finished / bundled / up to date
#   Everything else passes through uncolored; overmind still applies
#   its per-process prefix color on top.
# - Line-buffered via fflush() so output arrives in real time.
#
# Usage (in Procfile.dev):
#   some-cmd 2>&1 | scripts/dev-clean-output.sh
exec awk '
BEGIN {
  R = "\033[31m"   # red
  Y = "\033[33m"   # yellow
  G = "\033[32m"   # green
  X = "\033[0m"
}
{
  sub(/^[ \t]+/, "")
  if ($0 == "") next

  s = tolower($0)

  if (match(s, /error|failed|failure|traceback|panic|\[fatal\]|cannot find|cannot resolve|refused|denied|\bfail\b/))
    print R $0 X
  else if (match(s, /warning|\bwarn\b|deprecated|stale/))
    print Y $0 X
  else if (match(s, /\bready\b|listening|finished|bundled|compiled successfully|up to date|exited with code 0/))
    print G $0 X
  else
    print $0
  fflush()
}
'
