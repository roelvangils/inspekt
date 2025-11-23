# Bundled Third-Party Libraries

This directory contains third-party JavaScript libraries bundled with Inspekt for offline usage and reliability.

## axe-core.min.js

**Version**: 4.11.0
**Source**: https://github.com/dequelabs/axe-core
**License**: MPL-2.0 (Mozilla Public License 2.0)
**Downloaded from**: https://cdn.jsdelivr.net/npm/axe-core@4.11.0/axe.min.js
**Size**: ~560 KB (minified)

### Purpose

The axe-core library is used by the `inspekt axe` command to run accessibility audits. We bundle it locally instead of loading from CDN to ensure:

- **Offline functionality** - Works without internet connection
- **Reliability** - No CDN downtime or network issues
- **CSP compatibility** - Works on sites with strict Content Security Policies
- **Version stability** - Consistent results across environments
- **Privacy** - No external requests during audits

### Updating

To update to a newer version of axe-core:

```bash
# Download latest version
curl -sL https://cdn.jsdelivr.net/npm/axe-core@latest/axe.min.js -o inspekt/scripts/vendor/axe-core.min.js

# Verify download
head -c 200 inspekt/scripts/vendor/axe-core.min.js

# Test
inspekt axe --level 21aa
```

### License Compliance

axe-core is licensed under the Mozilla Public License 2.0 (MPL-2.0), which allows:
- ✅ Commercial use
- ✅ Distribution
- ✅ Modification
- ✅ Private use

The MPL-2.0 requires:
- ✅ Disclosure of source (met via this README and axe-core repository link)
- ✅ License and copyright notice (included in axe-core.min.js header)
- ✅ Same license for modifications (we don't modify the library)

Full license: https://www.mozilla.org/en-US/MPL/2.0/

### Copyright

```
Copyright (c) 2015 - 2025 Deque Systems, Inc.
```

See the header of axe-core.min.js for full copyright and license information.
