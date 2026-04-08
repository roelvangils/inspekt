# Inspekt - Practical Examples

Powerful real-world use cases and workflows.

## 🎯 Quick Wins

### Download files from a page

```bash
# List all downloadable files
inspekt download --list

# Interactive download with gum choose
inspekt download

# Download to specific directory
inspekt download --output ~/Downloads

# Quick workflow: browse to a page with resources, then:
inspekt download  # Select images, PDFs, videos, etc. interactively
```

The download command finds:
- All images (including background images from CSS)
- PDF documents
- Video and audio files
- Documents (docx, xlsx, etc.)
- Archives (zip, tar.gz, etc.)

Files are categorized and presented in an interactive menu where you can:
- Download all files of a specific type (e.g., "Download all IMAGES")
- Download individual files
- See file sizes after download

### Debug your application state
```bash
# Check your app's state
inspekt eval "window.myApp?.state" --format json

# Inspect Redux store
inspekt eval "window.__REDUX_DEVTOOLS_EXTENSION__?.store.getState()" --format json

# Check React component props
inspekt eval "$0.__reactProps$" --format json  # After selecting element in DevTools
```

### Data extraction from logged-in pages
```bash
# Extract data that requires authentication
inspekt eval "
  Array.from(document.querySelectorAll('.dashboard-item')).map(item => ({
    title: item.querySelector('.title').textContent,
    value: item.querySelector('.value').textContent,
    status: item.dataset.status
  }))
" --format json > dashboard_data.json

# Get your user info
inspekt eval "window.currentUser || window.user" --format json
```

### Quick performance checks
```bash
# Page load time
inspekt eval "(performance.timing.loadEventEnd - performance.timing.navigationStart) + 'ms'"

# Full performance report
inspekt exec zen/scripts/performance_metrics.js --format json

# Memory usage
inspekt eval "Math.round(performance.memory.usedJSHeapSize / 1048576) + 'MB'"
```

## 🔧 Built-in Scripts

### Extract all images
```bash
inspekt exec zen/scripts/extract_images.js --format json > images.json
```

### Extract table data
```bash
# Perfect for scraping tables from any page
inspekt exec zen/scripts/extract_table.js --format json > table_data.json
```

### Get SEO metadata
```bash
inspekt exec zen/scripts/extract_metadata.js --format json
```

### Performance metrics
```bash
inspekt exec zen/scripts/performance_metrics.js --format json
```

### Inject jQuery
```bash
inspekt exec zen/scripts/inject_jquery.js

# Then use jQuery
inspekt eval "$('a').length"
```

### Highlight elements
```bash
# Edit the script to change selector, then:
inspekt exec zen/scripts/highlight_selector.js
```

## 🚀 Advanced Workflows

### Monitor changes over time
```bash
# Watch element count
while true; do
  inspekt eval "document.querySelectorAll('.notification').length" --format raw
  sleep 5
done

# Monitor memory usage
watch -n 2 "inspekt eval 'Math.round(performance.memory.usedJSHeapSize / 1048576)' --format raw"
```

### Scraping workflow
```bash
# 1. Login manually in browser
# 2. Navigate to data page
# 3. Extract data
inspekt eval "
  Array.from(document.querySelectorAll('.product')).map(p => ({
    name: p.querySelector('h2').textContent,
    price: p.querySelector('.price').textContent,
    rating: p.querySelector('.rating')?.textContent,
    image: p.querySelector('img')?.src
  }))
" --format json > products.json

# 4. Process with jq
cat products.json | jq '[.[] | select(.rating != null)]' > rated_products.json
```

### Testing & Debugging
```bash
# Test a function
inspekt eval "myFunction('test input')" --format json

# Check for errors in console
inspekt eval "
  window.errors = [];
  window.addEventListener('error', e => errors.push(e.message));
  'Error monitoring started'
"

# Later check errors
inspekt eval "window.errors"

# Trigger an action
inspekt eval "document.querySelector('#submit-btn').click(); 'Clicked'"
```

### Page manipulation
```bash
# Remove annoying elements
inspekt eval "document.querySelectorAll('.ad, .popup').forEach(el => el.remove()); 'Removed'"

# Dark mode toggle
inspekt eval "
  document.body.style.filter =
    document.body.style.filter === 'invert(1) hue-rotate(180deg)'
      ? ''
      : 'invert(1) hue-rotate(180deg)';
  'Dark mode toggled'
"

# Resize all images
inspekt eval "document.querySelectorAll('img').forEach(img => img.style.maxWidth = '200px')"
```

### Form automation
```bash
# Fill form
inspekt eval "
  document.querySelector('#email').value = 'test@example.com';
  document.querySelector('#name').value = 'Test User';
  'Form filled'
"

# Submit form
inspekt eval "document.querySelector('form').submit(); 'Submitted'"

# Or click submit button
inspekt eval "document.querySelector('button[type=submit]').click()"
```

### Extract all links to CSV
```bash
inspekt eval "
  Array.from(document.links).map(a =>
    \`\${a.textContent.trim()},\${a.href}\`
  ).join('\n')
" --format raw > links.csv
```

### Screenshot alternative (data URL)
```bash
# Get image as base64
inspekt eval "
  (async () => {
    const canvas = document.createElement('canvas');
    const img = document.querySelector('img');
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    canvas.getContext('2d').drawImage(img, 0, 0);
    return canvas.toDataURL();
  })()
" --format raw > image_data.txt
```

### Local storage operations
```bash
# Get all localStorage
inspekt eval "JSON.stringify(localStorage)" --format json

# Set item
inspekt eval "localStorage.setItem('key', 'value'); 'Set'"

# Clear
inspekt eval "localStorage.clear(); 'Cleared'"

# Get specific item
inspekt eval "localStorage.getItem('token')"
```

### Cookie operations
```bash
# Get all cookies
inspekt eval "document.cookie"

# Get as structured data
inspekt eval "
  document.cookie.split(';').map(c => {
    const [key, value] = c.trim().split('=');
    return {key, value};
  })
" --format json
```

## 🎨 Interactive Development

### Live CSS experimentation
```bash
inspekt repl
```

Then in REPL:
```javascript
zen> document.body.style.backgroundColor = '#1a1a1a'
zen> document.body.style.color = '#fff'
zen> document.querySelectorAll('a').forEach(a => a.style.color = '#4a9eff')
zen> exit
```

### Test API calls
```bash
inspekt repl
```

```javascript
zen> await fetch('/api/users').then(r => r.json())
zen> await fetch('/api/data', {method: 'POST', body: JSON.stringify({test: true})}).then(r => r.json())
```

## 📊 Analysis Scripts

### Find all external resources
```bash
inspekt eval "
  ({
    scripts: Array.from(document.scripts).filter(s => s.src).map(s => s.src),
    styles: Array.from(document.styleSheets).map(s => s.href).filter(Boolean),
    images: Array.from(document.images).map(i => i.src),
    iframes: Array.from(document.querySelectorAll('iframe')).map(i => i.src)
  })
" --format json
```

### Accessibility check
```bash
inspekt eval "
  ({
    images_without_alt: Array.from(document.images).filter(img => !img.alt).length,
    links_without_text: Array.from(document.links).filter(a => !a.textContent.trim()).length,
    headings: Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6')).map(h => ({
      level: h.tagName,
      text: h.textContent.trim()
    })),
    lang: document.documentElement.lang || 'not set',
    forms_without_labels: Array.from(document.forms).reduce((count, form) =>
      count + Array.from(form.elements).filter(el =>
        el.tagName === 'INPUT' && !form.querySelector(\`label[for='\${el.id}']\`)
      ).length
    , 0)
  })
" --format json
```

### Find performance issues
```bash
inspekt eval "
  ({
    large_images: Array.from(document.images)
      .filter(img => img.naturalWidth * img.naturalHeight > 1000000)
      .map(img => ({src: img.src, size: \`\${img.naturalWidth}x\${img.naturalHeight}\`})),

    inline_styles: document.querySelectorAll('[style]').length,

    dom_depth: Math.max(...Array.from(document.querySelectorAll('*')).map(el => {
      let depth = 0;
      let node = el;
      while (node.parentElement) {
        depth++;
        node = node.parentElement;
      }
      return depth;
    })),

    total_elements: document.querySelectorAll('*').length
  })
" --format json
```

## 🔄 Shell Integration

### Use in bash scripts
```bash
#!/bin/bash

# Get page title
TITLE=$(inspekt eval "document.title" --format raw)
echo "Current page: $TITLE"

# Check if element exists
HAS_LOGIN=$(inspekt eval "document.querySelector('.login-btn') ? 'yes' : 'no'" --format raw)

if [ "$HAS_LOGIN" = "yes" ]; then
  echo "Login button found"
  inspekt eval "document.querySelector('.login-btn').click()"
fi
```

### Process with other CLI tools
```bash
# Extract links and filter with grep
inspekt eval "Array.from(document.links).map(a => a.href).join('\n')" --format raw | grep "github"

# Count unique domains
inspekt eval "Array.from(document.links).map(a => new URL(a.href).hostname).join('\n')" --format raw | sort -u | wc -l

# Extract emails
inspekt eval "document.body.textContent" --format raw | grep -oE '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
```

## 💡 Creative Uses

### Auto-scroll for lazy loading
```bash
inspekt eval "
  let scrolls = 0;
  const interval = setInterval(() => {
    window.scrollBy(0, 500);
    scrolls++;
    if (scrolls >= 10) clearInterval(interval);
  }, 500);
  'Auto-scrolling...'
"
```

### Export browser bookmarks
```bash
# If you can access bookmark manager page
inspekt eval "
  Array.from(document.querySelectorAll('a')).map(a => ({
    title: a.textContent.trim(),
    url: a.href
  }))
" --format json > bookmarks.json
```

### Monitor build status
```bash
# Check CI/CD dashboard
while true; do
  STATUS=$(inspekt eval "document.querySelector('.build-status').textContent" --format raw)
  echo "$(date): $STATUS"
  if [[ $STATUS == *"success"* ]]; then
    osascript -e 'display notification "Build succeeded!" with title "CI Status"'
    break
  fi
  sleep 30
done
```

## 🎓 Learning & Teaching

### Experiment with DOM
```bash
# Create elements
inspekt eval "
  const div = document.createElement('div');
  div.textContent = 'Hello from CLI!';
  div.style.cssText = 'position:fixed;top:10px;right:10px;background:#ff6b6b;color:white;padding:20px;border-radius:8px;z-index:99999;';
  document.body.appendChild(div);
  'Created notification'
"
```

### Test selectors
```bash
# Try different selectors
inspekt eval "document.querySelectorAll('.my-selector').length"
inspekt eval "document.querySelector('#id')?.textContent"
inspekt eval "document.evaluate('//div[@class=\"test\"]', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue"
```

## 📝 Tips & Tricks

### Timeout for slow operations
```bash
inspekt eval "await slowFunction()" --timeout 30
```

### Multiple commands
```bash
# Use semicolons or IIFE
inspekt eval "const x = 5; const y = 10; x + y"
```

### Return values
```bash
# Last expression is returned
inspekt eval "document.title; document.URL; 'Done'"  # Returns 'Done'

# Explicit return
inspekt eval "(function() { return {a: 1, b: 2}; })()"
```

### Debugging
```bash
# Add console.log and return value
inspekt eval "console.log('Debug:', window.myVar); window.myVar"

# Use debugger (check browser DevTools)
inspekt eval "debugger; myFunction()"
```
