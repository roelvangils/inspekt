# xterm.js vendored files

**xterm**: 6.0.0
**xterm-addon-fit**: 0.10.0
**xterm-addon-web-links**: 0.11.0
**License**: MIT
**Source**: https://github.com/xtermjs/xterm.js

Since xterm 5.4.0 the packages moved to the `@xterm/*` npm scope. The
unscoped `xterm`, `xterm-addon-fit`, and `xterm-addon-web-links` packages
are deprecated.

## Files

| File | Package | Version |
|------|---------|---------|
| `xterm.css` | @xterm/xterm | 6.0.0 |
| `xterm.min.js` | @xterm/xterm | 6.0.0 |
| `xterm-addon-fit.min.js` | @xterm/addon-fit | 0.10.0 |
| `xterm-addon-web-links.min.js` | @xterm/addon-web-links | 0.11.0 |

The UMD bundles still expose the same globals the control panel uses
(`window.Terminal`, `FitAddon.FitAddon`, `WebLinksAddon.WebLinksAddon`),
so the migration is a pure asset swap.

## Why vendored

- **Offline** — the Browser VM runs inside Docker and should not depend on external CDNs
- **Reliability** — no CDN downtime or DNS issues
- **Privacy** — no external requests from the VM

## Updating

Set the desired versions, then run:

```bash
XTERM=6.0.0
FIT=0.10.0
WEBLINKS=0.11.0

curl -sL "https://cdn.jsdelivr.net/npm/@xterm/xterm@${XTERM}/css/xterm.css" \
  -o vm/vendor/xterm.css
curl -sL "https://cdn.jsdelivr.net/npm/@xterm/xterm@${XTERM}/lib/xterm.min.js" \
  -o vm/vendor/xterm.min.js
# Addon files are published as addon-fit.min.js / addon-web-links.min.js
# in the @xterm scope — rename on download so the vendor filenames stay stable.
curl -sL "https://cdn.jsdelivr.net/npm/@xterm/addon-fit@${FIT}/lib/addon-fit.min.js" \
  -o vm/vendor/xterm-addon-fit.min.js
curl -sL "https://cdn.jsdelivr.net/npm/@xterm/addon-web-links@${WEBLINKS}/lib/addon-web-links.min.js" \
  -o vm/vendor/xterm-addon-web-links.min.js

# Verify downloads
ls -la vm/vendor/xterm*

# Update version numbers in this file, then rebuild
make vm-rebuild
```

Note: the addons have independent version numbers from xterm core.
Check compatibility at https://github.com/xtermjs/xterm.js.
