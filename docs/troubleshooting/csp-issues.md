# Troubleshooting CSP Issues

This guide helps you understand and troubleshoot Content Security Policy (CSP) issues with Inspekt.

---

## What is CSP?

**Content Security Policy (CSP)** is a security feature that websites use to control what resources (scripts, styles, connections) can be loaded and executed on their pages.

CSP is implemented through HTTP headers or `<meta>` tags and acts as a protective barrier against:
- Cross-site scripting (XSS) attacks
- Data injection attacks
- Unauthorized script execution
- Unwanted network connections

---

## Why Inspekt May Not Work

Inspekt requires two things that CSP can block:

### 1. JavaScript Execution

When you run commands like `inspekt eval "document.title"`, Zen injects JavaScript into the page. Strict CSP policies may block this.

### 2. WebSocket Connection

The userscript connects to `ws://localhost:8766` to communicate with the Zen CLI. CSP's `connect-src` directive can block connections to localhost.

---

## Detecting CSP Issues

### In Browser Console

Open your browser's DevTools (F12) and look for errors like:

```
Refused to connect to 'ws://localhost:8766' because it violates the
following Content Security Policy directive: "connect-src 'self'"
```

### Inspekt Warning

Starting with version 3.5, Inspekt automatically detects CSP and shows a warning:

```
⚠️ Inspekt: CSP Detected

This website has Content Security Policy (CSP) restrictions that block Inspekt.

What this means:
• WebSocket connections to localhost are blocked
• Zen commands will not work on this page

Why this happens:
• High-security sites (GitHub, banking, government) use CSP
• CSP prevents unauthorized scripts and connections
• This is a security feature, not a bug
```

### Manual Check

Check if a site has CSP using curl:

```bash
curl -I https://example.com | grep -i content-security
```

Example output:
```
Content-Security-Policy: default-src 'self'; connect-src 'self' https://api.example.com
```

This policy blocks WebSocket connections to localhost.

---

## Affected Websites

### High-Security Sites (Usually Blocked)

Sites with strict CSP that typically block Inspekt:

- **Code Hosting**: GitHub, GitLab, Bitbucket
- **Google Services**: Gmail, Drive, Docs, Cloud Console
- **Financial**: Banking websites, payment processors
- **Government**: Government portals, public services
- **Enterprise**: Corporate intranals, cloud platforms (AWS, Azure)
- **Security-Focused**: Password managers, VPN services

### Sites That Usually Work

- News websites (most)
- Blogs and personal sites
- Documentation sites
- E-commerce (many)
- Social media (some)
- Local development servers

---

## Workarounds

### ✅ Test on Different Sites

The simplest solution is to use Inspekt on sites without strict CSP:

```bash
# Works on most sites
inspekt eval "document.title"

# Try different domains
inspekt eval "window.location.href"
```

### ✅ Verify Server is Running

Sometimes the issue isn't CSP:

```bash
# Check if server is running
inspekt status

# Restart if needed
inspekt restart
```

### ✅ Check Browser Console

Always check the browser console for specific error messages:

1. Open DevTools (F12)
2. Go to Console tab
3. Look for Inspekt messages or CSP violations
4. Share error messages when reporting issues

### ❌ What Won't Work

These approaches **do not work** and are not recommended:

1. **Disabling CSP in browser** - Removes all security, very dangerous
2. **Modifying HTTP headers** - Requires browser extension with elevated privileges
3. **Proxying through another domain** - CSP still blocks injected scripts

---

## Future Solutions

We're exploring ways to make Inspekt work with CSP:

### Browser Extension (Future)

A full browser extension (not just a userscript) could:
- Use `chrome.tabs.executeScript()` API with CSP bypass
- Maintain WebSocket connections with elevated privileges
- Require installation from Chrome/Firefox store

**Trade-offs:**
- More installation steps
- Store review process
- More restrictive permissions needed

### CSP-Compatible Mode (Future)

A limited mode that works within CSP constraints:
- Read-only operations
- No arbitrary script execution
- Limited to predefined commands

**Trade-offs:**
- Reduced functionality
- No custom JavaScript evaluation
- Limited use cases

---

## Reporting CSP Issues

If you encounter CSP issues on sites where you'd expect Zen to work:

1. **Check the browser console** for specific CSP errors
2. **Note the website URL** and any error messages
3. **Test on a different site** to verify Zen works elsewhere
4. **Report the issue** at: https://github.com/roelvangils/inspekt/issues

Include:
- Website URL (if public)
- CSP policy (from curl or browser)
- Error messages from console
- Inspekt version (`inspekt --version`)

---

## Technical Details

### CSP Directives That Affect Zen

| Directive | Impact | Example Blocking Policy |
|-----------|--------|------------------------|
| `connect-src` | Blocks WebSocket | `connect-src 'self'` |
| `script-src` | Blocks injected scripts | `script-src 'self'` |
| `default-src` | Fallback for other directives | `default-src 'none'` |

### What Inspekt Needs

For Inspekt to work, the CSP must allow:

```
Content-Security-Policy:
  connect-src 'self' ws://localhost:8766 ws://127.0.0.1:8766;
  script-src 'self' 'unsafe-eval';
```

Most high-security sites will **never** allow this, by design.

### Detection Methods

Inspekt uses multiple methods to detect CSP:

1. **Meta tag detection**: Checks for `<meta http-equiv="Content-Security-Policy">`
2. **Connection failure patterns**: Multiple failed WebSocket attempts
3. **Error message analysis**: Catches CSP-related error messages

---

## Examples

### GitHub (Strict CSP)

```bash
$ curl -I https://github.com | grep -i content-security
Content-Security-Policy: default-src 'none'; connect-src 'self' *.github.com
```

**Result**: ❌ Inspekt blocked (localhost not in connect-src)

### Personal Blog (No CSP)

```bash
$ curl -I https://example-blog.com | grep -i content-security
# No CSP header
```

**Result**: ✅ Inspekt works

### E-commerce Site (Moderate CSP)

```bash
$ curl -I https://shop.example.com | grep -i content-security
Content-Security-Policy: default-src 'self'; connect-src 'self' https:
```

**Result**: ❌ Inspekt blocked (https: only, no ws://)

---

## Best Practices

1. **Test before relying on Zen** - Verify it works on your target sites
2. **Use for development** - Works great on localhost and dev environments
3. **Report unexpected blocks** - Help us improve CSP detection
4. **Stay informed** - Watch for updates on CSP compatibility

---

## FAQ

### Why don't you just bypass CSP?

CSP is a critical security feature. Bypassing it would:
- Require dangerous browser modifications
- Compromise site security
- Violate browser security policies
- Put users at risk

Inspekt respects web security standards.

### Will this ever be fixed?

"Fixed" implies CSP is a bug - it's not. CSP is working as designed.

We're exploring alternatives like browser extensions, but these require different installation and permission models.

### Can I whitelist localhost in CSP?

Only site owners can modify their CSP policy. If you control the website, you can add:

```
Content-Security-Policy: connect-src 'self' ws://localhost:8766
```

But this only works for your own sites.

### Does this affect all userscripts?

CSP affects any tool that:
- Injects scripts into pages
- Makes external connections
- Executes dynamic code

This is a common limitation of browser automation tools on high-security sites.

---

## Summary

- **CSP is a security feature**, not a bug
- **High-security sites block Zen by design**
- **Inspekt detects and warns about CSP** (v3.5+)
- **Use Zen on sites without strict CSP**
- **Report unexpected issues** to help improve detection

For most use cases (development, testing, personal sites), Inspekt works great. For high-security production sites, CSP restrictions are intentional and appropriate.
