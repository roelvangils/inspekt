# Publishing to Chrome Web Store - Developer Guide

This guide provides **step-by-step instructions** for publishing the Inspekt extension to the Chrome Web Store. This is for developers who want to distribute the extension officially.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Preparing for Submission](#preparing-for-submission)
3. [Creating Assets](#creating-assets)
4. [Chrome Web Store Submission](#chrome-web-store-submission)
5. [Filling Out the Listing](#filling-out-the-listing)
6. [Privacy & Permissions](#privacy--permissions)
7. [Review Process](#review-process)
8. [Post-Publication](#post-publication)
9. [Updates & Maintenance](#updates--maintenance)

## Prerequisites

### 1. Chrome Web Store Developer Account

You need a Chrome Web Store developer account:

1. **Go to**: [Chrome Web Store Developer Dashboard](https://chrome.google.com/webstore/devconsole)
2. **Sign in** with a Google account
3. **Pay the one-time registration fee**: $5 USD
4. **Complete verification** (may take a few hours)

### 2. Development Environment

Ensure you have:
- ✅ Latest version of Chrome installed
- ✅ Extension tested in developer mode
- ✅ All assets and materials ready (see below)

## Preparing for Submission

### 1. Final Testing

Before submission, thoroughly test the extension:

```bash
# Test on various websites
# CSP-protected sites:
- github.com
- gmail.com
- twitter.com

# Regular sites:
- example.com
- your-test-site.com

# Test all features:
- WebSocket connection
- JavaScript execution
- DevTools integration (inspektStore)
- Status panel
- Auto-reconnect
```

### 2. Code Review

Review the code for:
- ✅ No hardcoded credentials or API keys
- ✅ Proper error handling
- ✅ No console.log spam (keep only essential logs)
- ✅ Clean, well-commented code
- ✅ No external dependencies (unless necessary)
- ✅ Manifest V3 compliance

### 3. Build Package

Create the ZIP file for submission:

```bash
cd extensions/chrome

# Create ZIP (exclude development files)
zip -r zen-browser-bridge-chrome-4.0.0.zip . \
  -x "*.git*" \
  -x "*.DS_Store" \
  -x "*.md" \
  -x "build.sh" \
  -x "node_modules/*" \
  -x "test/*" \
  -x ".vscode/*"

# Verify the ZIP contains only necessary files
unzip -l zen-browser-bridge-chrome-4.0.0.zip
```

**Required files in ZIP**:
- `manifest.json`
- `background.js`
- `content.js`
- `popup/popup.html`
- `popup/popup.css`
- `popup/popup.js`
- `icons/icon-16.png`
- `icons/icon-48.png`
- `icons/icon-128.png`

## Creating Assets

### 1. Extension Icons (Required)

Already created in `icons/` directory:
- ✅ `icon-16.png` - 16x16px (toolbar)
- ✅ `icon-48.png` - 48x48px (extension management)
- ✅ `icon-128.png` - 128x128px (Chrome Web Store)

**If you need to recreate them**:
```bash
# Using ImageMagick or similar tool
# Start with a high-res version of your icon (512x512 or larger)
convert icon-512.png -resize 16x16 icon-16.png
convert icon-512.png -resize 48x48 icon-48.png
convert icon-512.png -resize 128x128 icon-128.png
```

### 2. Store Listing Graphics (Required)

Create these promotional images for the Chrome Web Store:

**Small Promo Tile** (440x280px):
- Use case: Small promotional tile on the store
- **Create with**: Design tool (Figma, Canva, Photoshop)
- **Content**: Extension icon + "Inspekt" text + tagline

**Large Promo Tile** (920x680px):
- Use case: Featured on the Chrome Web Store homepage (if selected)
- **Create with**: Design tool
- **Content**: More detailed promotional graphic

**Marquee Promo Tile** (1400x560px) - Optional:
- Use case: Very large featured placement
- **Content**: Full promotional banner

**Example Content for Promo Tiles**:
```
Title: Inspekt
Tagline: Control Your Browser from the Command Line
Features:
- Works on ALL websites (GitHub, Gmail, Banking)
- Bypass CSP restrictions safely
- AI-powered web automation
- DevTools integration
```

### 3. Screenshots (Required - at least 1, max 5)

Take 1280x800px or 640x400px screenshots showing:

**Screenshot 1**: Extension popup/status panel
- Show connected state
- Highlight key features

**Screenshot 2**: Terminal + Browser side-by-side
- Terminal running `zen` commands
- Browser showing results

**Screenshot 3**: GitHub/Gmail working
- Demonstrate CSP bypass on popular site
- Show command execution

**Screenshot 4**: DevTools integration
- Show `inspektStore($0)` in console
- Demonstrate inspected element storage

**Screenshot 5**: Various commands
- Show different Zen commands in action

**How to take screenshots**:
```bash
# macOS
Cmd + Shift + 4 (select area)

# Linux
Use screenshot tool to capture 1280x800px

# Windows
Use Snipping Tool or Snip & Sketch

# Resize if needed
convert screenshot.png -resize 1280x800 screenshot-final.png
```

### 4. Promotional Video (Optional, but Recommended)

Create a 30-60 second demo video showing:
- Installation process
- Starting the Zen server
- Running commands
- Extension working on GitHub/Gmail

**Upload to**:
- YouTube (unlisted or public)
- Provide link in Chrome Web Store listing

## Chrome Web Store Submission

### 1. Navigate to Developer Dashboard

1. Go to: [Chrome Web Store Developer Dashboard](https://chrome.google.com/webstore/devconsole)
2. Click **"New Item"** button

### 2. Upload ZIP

1. Click **"Choose file"** or drag and drop your ZIP
2. Upload `zen-browser-bridge-chrome-4.0.0.zip`
3. Wait for upload and validation
4. Fix any validation errors if they appear

### 3. Fill Out Store Listing

After upload, you'll be taken to the listing page.

## Filling Out the Listing

### Product Details

**Name**: (Required)
```
Inspekt
```

**Summary**: (Required, max 132 characters)
```
Secure CLI browser automation. Explicit per-domain permissions. AI-powered. 100% local. For developers.
```

**Description**: (Required, max 16,000 characters)

```markdown
# Inspekt - Command Line Browser Automation

Control your browser from the terminal with AI-powered automation. Execute JavaScript, automate tasks, and interact with any website using natural language commands.

## 🚀 Key Features

🔒 **Secure & User-Controlled** - Explicit opt-in required for each domain. You choose which websites Zen can access.

✨ **Works on ALL Websites** - Uses proper extension APIs to work on GitHub, Gmail, banking sites, and more (with your permission)

🤖 **AI-Powered Automation** - Use natural language commands like "click login button" or "fill out the form"

⚡ **DevTools Integration** - Store inspected elements with `inspektStore($0)` and manipulate them from CLI

🔒 **100% Local** - All communication stays between your browser and local CLI. No cloud, no tracking, complete privacy.

🛠️ **Developer-Friendly** - Perfect for web scraping, testing, automation, and rapid prototyping

## 🔐 Security First

**You're in control:** Zen Bridge requires your explicit permission before accessing any website.

1. Visit a new website → Permission modal appears
2. Review what access means → Allow or deny
3. Permission saved → Manage anytime from extension popup
4. Full transparency → See all allowed domains

Only websites YOU explicitly allow can be controlled from the CLI. Revoke access anytime.

## 📝 Quick Start

1. **Install the Extension** - Click "Add to Chrome"
2. **Install Zen CLI**:
   ```bash
   pip install zen-bridge
   ```
3. **Start the Server**:
   ```bash
   inspektserver start
   ```
4. **Run Commands**:
   ```bash
   inspekteval "document.title"
   inspektdo "click login button"
   inspektdescribe
   ```

## 🎯 Use Cases

- **Web Automation**: Automate repetitive browser tasks
- **Testing**: Test web applications from the command line
- **Data Extraction**: Extract data from websites programmatically
- **Debugging**: Execute JavaScript directly from your terminal
- **Prototyping**: Quickly test ideas without writing full scripts

## 🔐 Privacy & Security

- ✅ **Open Source** - Full transparency, review our code on GitHub
- ✅ **Local Only** - No data sent to external servers
- ✅ **No Tracking** - Zero analytics or data collection
- ✅ **Your Data Stays Yours** - All processing happens locally

## 💡 Example Commands

```bash
# Get page information
inspektinfo

# Extract all links
inspektlinks

# Natural language interaction
inspektdo "scroll to bottom"
inspektdo "click the blue button"

# AI-powered page description
inspektdescribe

# Execute custom JavaScript
inspekteval "document.querySelector('h1').textContent"

# Store element from DevTools
# 1. Inspect element (Right-click → Inspect)
# 2. In console: inspektStore($0)
# 3. In terminal: inspektinspected
```

## 🌟 Why Extension Over Userscript?

Many websites (GitHub, Gmail, banking sites) use Content Security Policy (CSP) that blocks userscripts. This extension uses Chrome's built-in APIs with proper permissions to bypass CSP safely and legally.

## 📚 Documentation

- Full Documentation: https://roelvangils.github.io/zen-bridge/
- GitHub Repository: https://github.com/roelvangils/zen-bridge
- Issue Tracker: https://github.com/roelvangils/zen-bridge/issues

## 🤝 Support

Need help? Found a bug?
- Documentation: https://roelvangils.github.io/zen-bridge/
- GitHub Issues: https://github.com/roelvangils/zen-bridge/issues

## ⚖️ License

Open source under MIT License. See repository for details.

---

**Note**: This extension requires the Zen Bridge CLI to be installed separately. The extension provides the browser-side component that communicates with your local CLI.
```

**Category**: (Required)
```
Developer Tools
```

**Language**: (Required)
```
English (United States)
```

### Privacy Practices

**Single Purpose Description**: (Required)
```
This extension enables command-line control of Chrome for browser automation, testing, and web interaction by establishing a local WebSocket connection between the browser and a CLI tool.
```

**Permission Justifications**: (Required)

You need to justify each permission in manifest.json:

**activeTab**:
```
Required to execute JavaScript in the currently active tab for browser automation and command execution.
```

**scripting**:
```
Required to inject and execute code with proper CSP bypass capabilities, enabling the extension to work on all websites including those with strict Content Security Policies. Users must explicitly allow each domain before the extension can access it.
```

**storage**:
```
Required to store user's domain permissions. The extension requires users to explicitly allow each domain before it can be controlled from the CLI. This list of allowed domains is stored locally using chrome.storage.sync.
```

**host_permissions (<all_urls>)**:
```
Required to inject the content script that displays the permission modal on all websites. The content script only establishes a connection AFTER the user explicitly allows the domain. Users maintain full control over which domains the extension can access.
```

**Data Usage**: (Required)

Check the appropriate boxes:

**Does this extension collect user data?**
```
No
```

If you check "Yes", you'll need to explain what data and why. Since Zen Bridge doesn't collect any data, select **No**.

**Data Usage Certification**:
```
✅ I certify that this extension complies with Chrome Web Store policies
✅ I certify that the disclosure practices are accurate
```

### Pricing & Distribution

**Pricing**:
```
Free
```

**Distribution**:
```
Public (visible to everyone on Chrome Web Store)
```

**Regions**:
```
All regions
```

### Store Listing Assets

Upload the assets you created:

1. **Icon** - 128x128px (auto-pulled from manifest, verify it looks good)
2. **Screenshots** - Upload 1-5 screenshots (1280x800px)
3. **Small promo tile** - 440x280px
4. **Large promo tile** - 920x680px (optional)
5. **Marquee** - 1400x560px (optional)
6. **Video** - YouTube link (optional)

## Privacy & Permissions

### Privacy Policy (Required)

You need a privacy policy URL. Create a page on your documentation site or GitHub:

**Example**: `https://roelvangils.github.io/zen-bridge/privacy-policy/`

**Privacy Policy Content**:

```markdown
# Privacy Policy - Inspekt

**Last Updated**: [Date]

## Data Collection

Inspekt does NOT collect, store, or transmit any user data. The extension operates entirely locally on your machine.

## How It Works

1. The extension establishes a WebSocket connection to `localhost:8766`
2. All communication stays between your browser and local CLI
3. No data is sent to external servers
4. No analytics or tracking

## Permissions

The extension requires these permissions:

- **activeTab**: To execute commands in the active browser tab
- **scripting**: To inject code with CSP bypass (core functionality)
- **<all_urls>**: To work on all websites

These permissions are used solely for the extension's core functionality and no data is collected or transmitted.

## Third-Party Services

This extension does NOT use any third-party services, analytics, or tracking.

## Changes to This Policy

We may update this privacy policy. Changes will be posted at this URL with an updated date.

## Contact

Questions? Open an issue: https://github.com/roelvangils/zen-bridge/issues
```

### Terms of Service (Optional)

Not required but recommended. You can link to your repository's LICENSE file:

```
https://github.com/roelvangils/zen-bridge/blob/main/LICENSE
```

## Review Process

### Submit for Review

1. Click **"Submit for Review"** button
2. Review all information one final time
3. Confirm submission

### What Happens Next

**Timeline**:
- Initial review: Usually 1-3 business days
- May take longer for first submission or complex extensions

**Possible Outcomes**:

1. **Approved** ✅
   - Extension goes live on Chrome Web Store
   - You'll receive an email notification

2. **Rejected** ❌
   - You'll receive specific feedback on what needs to be changed
   - Common reasons:
     - Missing or inadequate privacy policy
     - Insufficient permission justifications
     - Policy violations
     - Code quality issues
   - Fix the issues and resubmit

3. **More Information Needed** ⚠️
   - Reviewer has questions
   - Provide detailed responses promptly

### Common Rejection Reasons (and How to Avoid)

**1. Insufficient Permission Justification**
- ✅ **Fix**: Clearly explain why each permission is necessary
- Be specific about how the permission enables core functionality

**2. Missing or Inadequate Privacy Policy**
- ✅ **Fix**: Host a complete privacy policy that addresses data collection, permissions, and third-party services

**3. Misleading Functionality**
- ✅ **Fix**: Ensure description matches actual functionality
- Don't overpromise features

**4. Single Purpose Violation**
- ✅ **Fix**: Extension should do one thing well
- Zen Bridge's single purpose: CLI browser control

**5. Code Quality Issues**
- ✅ **Fix**: Remove console.log spam, ensure error handling, clean up code

## Post-Publication

### After Approval

1. **Verify the Listing**:
   - Visit your extension's Chrome Web Store page
   - Test installation from the store
   - Verify all links and assets display correctly

2. **Update Documentation**:
   ```markdown
   # In your main README and docs:
   - Add Chrome Web Store badge
   - Add installation link
   - Update "Coming Soon" to "Available Now"
   ```

3. **Announce Launch**:
   - GitHub release
   - Documentation update
   - Social media (if applicable)
   - Community forums

### Chrome Web Store Badge

Add to README.md:

```markdown
[![Chrome Web Store](https://img.shields.io/chrome-web-store/v/YOUR_EXTENSION_ID.svg)](https://chrome.google.com/webstore/detail/YOUR_EXTENSION_ID)
[![Chrome Web Store Users](https://img.shields.io/chrome-web-store/users/YOUR_EXTENSION_ID.svg)](https://chrome.google.com/webstore/detail/YOUR_EXTENSION_ID)
[![Chrome Web Store Rating](https://img.shields.io/chrome-web-store/rating/YOUR_EXTENSION_ID.svg)](https://chrome.google.com/webstore/detail/YOUR_EXTENSION_ID)
```

### Monitor Metrics

In Developer Dashboard, monitor:
- **Installations**: Track user adoption
- **Reviews**: Respond to user feedback
- **Crashes**: Fix any reported issues
- **Ratings**: Maintain quality

## Updates & Maintenance

### Publishing Updates

1. **Update version** in `manifest.json`:
   ```json
   {
     "version": "4.1.0"  // Increment version
   }
   ```

2. **Create new ZIP**:
   ```bash
   zip -r zen-browser-bridge-chrome-4.1.0.zip . -x [exclusions]
   ```

3. **Upload to Developer Dashboard**:
   - Go to your extension page
   - Click **"Upload Updated Package"**
   - Upload new ZIP
   - Add changelog/release notes
   - Submit for review

**Review Time for Updates**:
- Usually faster than initial submission (few hours to 1 day)
- Unless significant changes to permissions or functionality

### Versioning Strategy

Follow **Semantic Versioning** (SemVer):
```
MAJOR.MINOR.PATCH

4.0.0 -> 4.0.1 (bug fix)
4.0.1 -> 4.1.0 (new feature)
4.1.0 -> 5.0.0 (breaking change)
```

### Responding to Reviews

**Best Practices**:
- Respond to all reviews (good and bad)
- Be professional and helpful
- Offer to help with issues
- Direct users to GitHub for bug reports

**Example Response**:
```
Thank you for the feedback! Sorry you're experiencing issues.
This sounds like a bug. Could you please open an issue on our
GitHub with more details? https://github.com/roelvangils/zen-bridge/issues

We'll get this fixed in the next update!
```

## Checklist for Submission

Use this checklist before submitting:

### Code
- [ ] Extension tested on Chrome (latest version)
- [ ] Tested on CSP-protected sites (GitHub, Gmail)
- [ ] All features working correctly
- [ ] No console errors
- [ ] Clean, commented code
- [ ] Version number updated in manifest.json

### Package
- [ ] ZIP created with correct files
- [ ] No development files included
- [ ] File size reasonable (<10MB)

### Assets
- [ ] Icon 16x16px
- [ ] Icon 48x48px
- [ ] Icon 128x128px
- [ ] At least 1 screenshot (1280x800px)
- [ ] Small promo tile (440x280px)
- [ ] Large promo tile (920x680px) - optional

### Listing
- [ ] Name clear and descriptive
- [ ] Summary under 132 characters
- [ ] Description comprehensive and accurate
- [ ] Category selected (Developer Tools)
- [ ] Language selected

### Legal
- [ ] Privacy policy published and URL added
- [ ] All permissions justified
- [ ] Data usage questions answered
- [ ] Single purpose clearly defined
- [ ] Terms of service (optional)

### Developer Account
- [ ] Registration fee paid ($5)
- [ ] Account verified
- [ ] Email confirmed

## Resources

### Official Chrome Documentation
- [Chrome Web Store Developer Dashboard](https://chrome.google.com/webstore/devconsole)
- [Chrome Extension Development Guide](https://developer.chrome.com/docs/extensions/mv3/)
- [Chrome Web Store Program Policies](https://developer.chrome.com/docs/webstore/program-policies/)
- [Best Practices for Extensions](https://developer.chrome.com/docs/extensions/mv3/quality_guidelines/)

### Zen Bridge Resources
- [Main Documentation](https://roelvangils.github.io/zen-bridge/)
- [GitHub Repository](https://github.com/roelvangils/zen-bridge)
- [Issue Tracker](https://github.com/roelvangils/zen-bridge/issues)

## Getting Help

**Questions about submission?**
- Open an issue: https://github.com/roelvangils/zen-bridge/issues
- Tag with `chrome-web-store` label

**Chrome Web Store Support**:
- [Support Forum](https://support.google.com/chrome_webstore/)
- [Chrome Extension Support](https://groups.google.com/a/chromium.org/g/chromium-extensions)

## Conclusion

Publishing to the Chrome Web Store makes Inspekt accessible to millions of Chrome users. Follow this guide carefully to ensure a smooth submission process.

**Good luck with your submission! 🚀**

---

**Last Updated**: 2024-11-11
**Extension Version**: 4.0.0
**Manifest Version**: 3
