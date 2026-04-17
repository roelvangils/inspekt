# Permanent Installation Guide

This guide explains how to install the Inspekt extension permanently in Firefox.

## Quick Answer

**For regular Firefox users:** The easiest way is to reload the temporary extension each time you restart Firefox (Method 1 below). We're working on submitting to the Firefox Add-ons store for one-click permanent installation.

**For developers:** Use Firefox Developer Edition with unsigned extensions enabled (Method 2 below).

---

## Method 1: Temporary Installation (Easiest)

**Pros:**
- No special setup required
- Works with regular Firefox
- Perfect for testing and development

**Cons:**
- Needs to be reloaded after Firefox restarts

### Steps:

1. Navigate to `about:debugging#/runtime/this-firefox`
2. Click "Load Temporary Add-on…"
3. Select `manifest.json` from the `extensions/firefox/` directory

**Note:** You'll need to repeat these steps each time you restart Firefox.

---

## Method 2: Self-Hosted Unsigned Extension (Developer Edition/Nightly)

**Pros:**
- Permanent installation
- No signing required
- Full control

**Cons:**
- Requires Firefox Developer Edition or Nightly
- Need to disable signature verification

### Steps:

#### 2.1 Install Firefox Developer Edition or Nightly

Download one of these:
- **Firefox Developer Edition**: https://www.mozilla.org/firefox/developer/
- **Firefox Nightly**: https://www.mozilla.org/firefox/nightly/

#### 2.2 Build the Extension

```bash
cd extensions/firefox
./build.sh
```

This creates `build/zen-browser-bridge-4.0.0.xpi`

#### 2.3 Disable Signature Verification

1. Open Firefox Developer Edition/Nightly
2. Navigate to `about:config`
3. Accept the risk warning
4. Search for `xpinstall.signatures.required`
5. Set it to `false` (double-click to toggle)

#### 2.4 Install the Extension

**Option A: Drag and Drop**
1. Open Firefox
2. Drag `build/zen-browser-bridge-4.0.0.xpi` into Firefox window
3. Click "Add" when prompted

**Option B: File Picker**
1. Navigate to `about:addons`
2. Click the gear icon (⚙️)
3. Select "Install Add-on From File…"
4. Choose `build/zen-browser-bridge-4.0.0.xpi`
5. Click "Add" when prompted

The extension is now permanently installed!

---

## Method 3: Web Extension Signing (Recommended for Distribution)

**Pros:**
- Works with regular Firefox
- Permanent installation
- Can be shared with others
- Most secure method

**Cons:**
- Requires Mozilla Developer account
- Takes time for review (if distributing publicly)

### Steps:

#### 3.1 Get a Mozilla Add-on Developer Account

1. Go to https://addons.mozilla.org/developers/
2. Sign in with Firefox Account (or create one)
3. Agree to the Developer Agreement

#### 3.2 Build the Extension

```bash
cd extensions/firefox
./build.sh
```

This creates `build/zen-browser-bridge-4.0.0.zip`

#### 3.3 Option A: Self-Distribution (Unlisted)

Use this if you want to host the extension yourself (not on the store):

1. Go to https://addons.mozilla.org/developers/addon/submit/upload-unlisted
2. Upload `build/zen-browser-bridge-4.0.0.zip`
3. Wait for automated validation (usually instant)
4. Download the signed .xpi file
5. Distribute the signed .xpi to users

**Advantages:**
- No review process
- Fast (usually minutes)
- Can distribute via your own website/GitHub

**How users install:**
- Users download the signed .xpi
- Drag and drop into Firefox
- Extension stays permanently installed

#### 3.4 Option B: Firefox Add-ons Store (Listed)

Use this for public distribution on the official store:

1. Go to https://addons.mozilla.org/developers/addon/submit/distribution
2. Choose "On this site" (listed)
3. Upload `build/zen-browser-bridge-4.0.0.zip`
4. Fill out listing information:
   - Name: Inspekt
   - Summary: Execute JavaScript in your browser from the command line
   - Categories: Developer Tools
   - Support email/website
5. Submit for review

**Review process:**
- Mozilla reviews the extension (can take days to weeks)
- Once approved, it appears on addons.mozilla.org
- Users can install with one click

**Advantages:**
- Maximum visibility and trust
- One-click installation for users
- Automatic updates

---

## Method 4: Use web-ext for Development

**Best for:** Active development and testing

### 4.1 Install web-ext

```bash
npm install -g web-ext
```

Or use npx (no installation needed):
```bash
npx web-ext --version
```

### 4.2 Run Extension in Temporary Profile

```bash
cd extensions/firefox
web-ext run
```

This opens a new Firefox window with the extension loaded.

### 4.3 Run with Your Firefox Profile

```bash
web-ext run --firefox-profile=/path/to/profile
```

### 4.4 Build and Sign

```bash
# Build
web-ext build

# Sign (requires API credentials)
web-ext sign --api-key=your-key --api-secret=your-secret
```

**Get API credentials:**
1. Go to https://addons.mozilla.org/developers/addon/api/key/
2. Generate API credentials
3. Use them with web-ext

---

## Comparison Table

| Method | Permanent | Regular Firefox | Setup Complexity | Best For |
|--------|-----------|----------------|------------------|----------|
| **Temporary** | ❌ No | ✅ Yes | ⭐ Easy | Testing, quick use |
| **Unsigned (Dev Edition)** | ✅ Yes | ❌ No | ⭐⭐ Medium | Development |
| **Self-Signed (Unlisted)** | ✅ Yes | ✅ Yes | ⭐⭐⭐ Medium | Self-distribution |
| **Store (Listed)** | ✅ Yes | ✅ Yes | ⭐⭐⭐⭐ Hard | Public distribution |
| **web-ext** | ❌ Temporary | ✅ Yes | ⭐⭐ Medium | Active development |

---

## Recommendations

### For Personal Use
→ **Method 2 (Unsigned)** with Firefox Developer Edition
- One-time setup, permanent installation
- No review process

### For Sharing with Friends/Team
→ **Method 3A (Self-Signed Unlisted)**
- Fast signing (minutes)
- Share the signed .xpi file
- Works on regular Firefox

### For Public Release
→ **Method 3B (Store Listed)**
- Maximum trust and visibility
- Users can find it by searching
- Automatic updates

---

## Troubleshooting

### "This add-on could not be installed because it appears to be corrupt"

**Solution:** Make sure you're using Firefox Developer Edition/Nightly with signature verification disabled, or use a signed .xpi file.

### "Install Add-on From File" is greyed out

**Solution:** This feature requires Firefox Developer Edition, Beta, Nightly, or ESR. It's disabled in regular Firefox for security.

### Extension disappears after Firefox restart (Temporary Installation)

**Solution:** This is expected behavior. Use Method 2 or 3 for permanent installation.

### Signature verification setting doesn't persist

**Solution:**
- This is only supported in Developer Edition and Nightly
- Regular Firefox doesn't allow disabling signature verification
- Use signed extensions instead

---

## Next Steps

Once you have the extension permanently installed:

1. **Start the server:**
   ```bash
   inspektserver start
   ```

2. **Test on a CSP-protected site:**
   ```bash
   # Open github.com in your browser, then:
   inspektinfo
   inspekteval "document.title"
   ```

3. **Enjoy CSP bypass on all websites!** ⚡

---

## Resources

- **Web Extension Workshop**: https://extensionworkshop.com/
- **Signing API**: https://extensionworkshop.com/documentation/publish/signing-and-distribution-overview/
- **web-ext CLI**: https://extensionworkshop.com/documentation/develop/getting-started-with-web-ext/
- **Distribution Guide**: https://extensionworkshop.com/documentation/publish/
- **Add-on Policies**: https://extensionworkshop.com/documentation/publish/add-on-policies/

---

## Future Plans

We're working on:
- ✅ Build script (done)
- 🔄 Automated signing in CI/CD
- 📦 Pre-built signed releases on GitHub
- 🏪 Submission to Firefox Add-ons Store
- 🔄 Automatic updates

Stay tuned! ⚡
