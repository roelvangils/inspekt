# xterm.js vendored files

**xterm**: 5.3.0
**xterm-addon-fit**: 0.8.0
**xterm-addon-web-links**: 0.9.0
**License**: MIT
**Source**: https://github.com/xtermjs/xterm.js

## Files

| File | Package | Version |
|------|---------|---------|
| `xterm.css` | xterm | 5.3.0 |
| `xterm.min.js` | xterm | 5.3.0 |
| `xterm-addon-fit.min.js` | xterm-addon-fit | 0.8.0 |
| `xterm-addon-web-links.min.js` | xterm-addon-web-links | 0.9.0 |

## Why vendored

- **Offline** — the Browser VM runs inside Docker and should not depend on external CDNs
- **Reliability** — no CDN downtime or DNS issues
- **Privacy** — no external requests from the VM

## Updating

Set the desired versions, then run:

```bash
XTERM=5.3.0
FIT=0.8.0
WEBLINKS=0.9.0

curl -sL "https://cdn.jsdelivr.net/npm/xterm@${XTERM}/css/xterm.css" \
  -o vm/vendor/xterm.css
curl -sL "https://cdn.jsdelivr.net/npm/xterm@${XTERM}/lib/xterm.min.js" \
  -o vm/vendor/xterm.min.js
curl -sL "https://cdn.jsdelivr.net/npm/xterm-addon-fit@${FIT}/lib/xterm-addon-fit.min.js" \
  -o vm/vendor/xterm-addon-fit.min.js
curl -sL "https://cdn.jsdelivr.net/npm/xterm-addon-web-links@${WEBLINKS}/lib/xterm-addon-web-links.min.js" \
  -o vm/vendor/xterm-addon-web-links.min.js

# Verify downloads
ls -la vm/vendor/xterm*

# Update version numbers in this file, then rebuild
make vm-rebuild
```

Note: the addons have independent version numbers from xterm core.
Check compatibility at https://github.com/xtermjs/xterm.js.
