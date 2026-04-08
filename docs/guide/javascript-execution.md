# JavaScript Execution

Master JavaScript execution in Inspekt. Learn inline code execution, file execution, stdin piping, timeout handling, error handling, output formatting, and advanced patterns.

## Execution Methods

Inspekt offers three ways to execute JavaScript code in your browser.

### 1. Inline Code Execution

Execute code directly from the command line:

```bash
inspekt eval "document.title"
```

**Best for:**
- Quick one-liners
- Testing expressions
- Shell scripts with short code snippets

### 2. File Execution

Execute code from JavaScript files:

```bash
inspekt eval --file script.js
# or
inspekt exec script.js
```

**Best for:**
- Complex scripts
- Reusable code
- Version-controlled automation

### 3. stdin Piping

Pipe code from stdin:

```bash
cat script.js | inspekt eval
echo "document.title" | inspekt eval
```

**Best for:**
- Generated code
- Dynamic scripts
- Shell pipelines

---

## Inline Code Execution

### Simple Expressions

```bash
# Get page title
inspekt eval "document.title"

# Get URL
inspekt eval "window.location.href"

# Count elements
inspekt eval "document.querySelectorAll('a').length"

# Check if element exists
inspekt eval "document.querySelector('.modal') !== null"
```

### Complex Expressions

```bash
# Array operations
inspekt eval "Array.from(document.links).map(a => a.href)"

# Object literals (wrap in parentheses)
inspekt eval "({title: document.title, url: location.href})"

# Filter and map
inspekt eval "Array.from(document.querySelectorAll('img')).filter(img => img.alt).map(img => img.src)"

# Reduce
inspekt eval "Array.from(document.links).reduce((acc, link) => acc + link.textContent.length, 0)"
```

### Multi-line Code

Use newlines and proper JavaScript syntax:

```bash
inspekt eval "
  const products = document.querySelectorAll('.product');
  const data = Array.from(products).map(p => ({
    name: p.querySelector('.name').textContent,
    price: p.querySelector('.price').textContent
  }));
  return data;
"
```

!!! tip "Multi-line Tips"
    - Separate statements with semicolons
    - Use `return` for the final value
    - Proper indentation makes code readable

### Handling Quotes

Shell quoting can be tricky. Here are the rules:

```bash
# Double quotes - escape inner double quotes
inspekt eval "document.querySelector(\"h1\").textContent"

# Single quotes in double quotes - no escaping needed
inspekt eval "document.querySelector('h1').textContent"

# Backticks for template literals - use single quotes outside
inspekt eval 'document.querySelector("h1").textContent = `Hello ${name}`'

# Heredoc for complex quoting
inspekt eval <<'EOF'
const selector = 'div[data-value="complex"]';
const element = document.querySelector(selector);
return element?.textContent;
EOF
```

---

## File Execution

### Basic File Execution

**script.js:**
```javascript
// Extract all links
const links = Array.from(document.querySelectorAll('a'));
return links.map(link => ({
  text: link.textContent.trim(),
  href: link.href,
  external: link.hostname !== location.hostname
}));
```

**Execute:**
```bash
inspekt exec script.js
# or
inspekt eval --file script.js
```

### File with Modules

Modern JavaScript syntax is supported:

**extract-data.js:**
```javascript
// Extract product data with validation
const products = Array.from(document.querySelectorAll('.product'));

function extractProduct(element) {
  const name = element.querySelector('.product-name')?.textContent?.trim();
  const price = element.querySelector('.product-price')?.textContent?.trim();
  const image = element.querySelector('.product-image')?.src;

  // Validate required fields
  if (!name || !price) return null;

  return { name, price, image };
}

const data = products.map(extractProduct).filter(Boolean);

return {
  count: data.length,
  products: data,
  extracted: new Date().toISOString()
};
```

### Built-in Scripts

Inspekt includes several ready-to-use scripts in the `inspekt/scripts/` directory:

```bash
# Extract all images
inspekt exec inspekt/scripts/extract_images.js

# Extract table data
inspekt exec inspekt/scripts/extract_table.js

# Get SEO metadata
inspekt exec inspekt/scripts/extract_metadata.js

# Performance metrics
inspekt exec inspekt/scripts/performance_metrics.js

# Inject jQuery
inspekt exec inspekt/scripts/inject_jquery.js

# Highlight elements
inspekt exec inspekt/scripts/highlight_selector.js
```

### Creating Your Own Scripts

**1. Create a script directory:**
```bash
mkdir -p ~/inspekt-scripts
```

**2. Write your script:**
```javascript
// ~/inspekt-scripts/extract-prices.js
const prices = Array.from(document.querySelectorAll('.price'));
return prices.map(p => ({
  text: p.textContent,
  value: parseFloat(p.textContent.replace(/[^0-9.]/g, ''))
}));
```

**3. Execute:**
```bash
inspekt exec ~/inspekt-scripts/extract-prices.js --format json
```

---

## stdin Piping

### Pipe from Files

```bash
cat script.js | inspekt eval
```

### Pipe from echo

```bash
echo "document.title" | inspekt eval
```

### Generate Code Dynamically

```bash
# Generate selector from variable
SELECTOR=".product"
echo "document.querySelectorAll('$SELECTOR').length" | inspekt eval

# Generate complex code
cat <<EOF | inspekt eval
const selector = '$SELECTOR';
const elements = document.querySelectorAll(selector);
return Array.from(elements).length;
EOF
```

### Pipe Chains

```bash
# Extract, filter, execute
grep -v "^//" script.js | inspekt eval

# Combine multiple commands
echo "document.links.length" | inspekt eval | awk '{print "Found " $1 " links"}'
```

---

## Timeout Handling

### Default Timeout

Commands timeout after **10 seconds** by default:

```bash
inspekt eval "document.title"  # 10 second timeout
```

### Custom Timeout

Adjust for slow operations:

```bash
# 30 second timeout
inspekt eval "await fetch('/api/data').then(r => r.json())" --timeout 30

# 5 second timeout (strict)
inspekt eval "document.title" --timeout 5

# 60 second timeout (very slow operations)
inspekt eval "await heavyComputation()" --timeout 60
```

### Timeout Examples

**Long-running API call:**
```bash
inspekt eval "
  const response = await fetch('/api/large-dataset');
  const data = await response.json();
  return data.items.length;
" --timeout 30
```

**Wait for lazy-loaded content:**
```bash
inspekt eval "
  // Scroll to load content
  for (let i = 0; i < 10; i++) {
    window.scrollTo(0, document.body.scrollHeight);
    await new Promise(resolve => setTimeout(resolve, 1000));
  }
  return document.querySelectorAll('.lazy-item').length;
" --timeout 30
```

### Timeout Errors

When a timeout occurs:

```
Error: Request timed out after 10 seconds
```

**Solutions:**
1. Increase timeout with `--timeout`
2. Optimize your JavaScript code
3. Break into smaller operations
4. Check for infinite loops

---

## Error Handling

### JavaScript Errors

Runtime errors are caught and displayed:

```bash
inspekt eval "document.querySelector('.missing').click()"
```

**Output:**
```
TypeError: Cannot read property 'click' of null
  at <eval>:1:42
```

### Syntax Errors

Invalid JavaScript is caught:

```bash
inspekt eval "document..title"
```

**Output:**
```
SyntaxError: Unexpected token '.'
```

### Handling Errors in Your Code

Use try-catch for graceful error handling:

```bash
inspekt eval "
  try {
    const element = document.querySelector('.maybe-exists');
    return element.textContent;
  } catch (error) {
    return null;
  }
"
```

### Defensive Coding

Use optional chaining and nullish coalescing:

```bash
# Optional chaining
inspekt eval "document.querySelector('.modal')?.textContent"

# Nullish coalescing
inspekt eval "document.querySelector('.price')?.textContent ?? 'N/A'"

# Combined
inspekt eval "document.querySelector('.product')?.querySelector('.price')?.textContent ?? 'No price'"
```

### Validation

Validate before operating:

```bash
inspekt eval "
  const element = document.querySelector('.submit-btn');
  if (!element) {
    return { error: 'Button not found' };
  }
  element.click();
  return { success: true };
"
```

---

## Output Formatting

### Format Options

Control output format with the `--format` flag:

| Format | Description | Use Case |
|--------|-------------|----------|
| `auto` | Smart formatting (default) | General use |
| `json` | Valid JSON | Scripting, piping to `jq` |
| `raw` | Plain text | Shell variables |

### Auto Format (Default)

Intelligently formats output:

```bash
inspekt eval "document.title"
# Output: Example Domain (plain text)

inspekt eval "({title: document.title, url: location.href})"
# Output: Pretty-printed JSON
```

### JSON Format

Always outputs valid JSON:

```bash
inspekt eval "document.title" --format json
# Output: "Example Domain"

inspekt eval "({title: document.title, links: document.links.length})" --format json
# Output: {"title":"Example Domain","links":15}
```

**Perfect for `jq`:**
```bash
inspekt eval "({title: document.title, url: location.href})" --format json | jq '.title'
# Output: "Example Domain"
```

### Raw Format

No formatting - just the value:

```bash
inspekt eval "document.title" --format raw
# Output: Example Domain

inspekt eval "document.links.length" --format raw
# Output: 15
```

**Perfect for shell variables:**
```bash
TITLE=$(inspekt eval "document.title" --format raw)
COUNT=$(inspekt eval "document.links.length" --format raw)
echo "$COUNT links on $TITLE"
```

### Metadata Flags

Add context to output:

```bash
# Add URL
inspekt eval "document.title" --url

# Add title
inspekt eval "document.links.length" --title

# Add both
inspekt eval "document.links.length" --url --title
```

**Output:**
```
URL: https://example.com
Title: Example Domain

15
```

---

## Advanced Patterns

### Async/Await

Full support for promises and async/await:

```bash
# Fetch API
inspekt eval "await fetch('/api/data').then(r => r.json())"

# Multiple awaits
inspekt eval "
  const response = await fetch('/api/users');
  const users = await response.json();
  return users.length;
"

# Promise.all
inspekt eval "
  const promises = Array.from({length: 5}, (_, i) =>
    fetch(\`/api/item/\${i}\`).then(r => r.json())
  );
  return await Promise.all(promises);
"
```

### Working with Arrays

```bash
# Map
inspekt eval "Array.from(document.querySelectorAll('a')).map(a => a.href)"

# Filter
inspekt eval "Array.from(document.links).filter(a => a.hostname === location.hostname)"

# Reduce
inspekt eval "Array.from(document.images).reduce((sum, img) => sum + img.naturalWidth, 0)"

# Find
inspekt eval "Array.from(document.links).find(a => a.textContent.includes('Contact'))"

# Some/Every
inspekt eval "Array.from(document.images).every(img => img.alt)"
```

### Working with Objects

```bash
# Object.keys
inspekt eval "Object.keys(window)"

# Object.entries
inspekt eval "Object.entries(localStorage).map(([k,v]) => ({key: k, value: v}))"

# Destructuring
inspekt eval "
  const {title, URL: url} = document;
  return {title, url};
"
```

### DOM Traversal

```bash
# Parent
inspekt eval "document.querySelector('.child').parentElement.tagName"

# Children
inspekt eval "Array.from(document.body.children).map(el => el.tagName)"

# Siblings
inspekt eval "document.querySelector('h1').nextElementSibling?.tagName"

# Closest
inspekt eval "document.querySelector('.nested').closest('.container')?.className"
```

### Performance Optimization

**Cache selectors:**
```bash
inspekt eval "
  const products = document.querySelectorAll('.product');
  return Array.from(products).map(p => {
    // Reuse 'p' instead of querying again
    return {
      name: p.querySelector('.name').textContent,
      price: p.querySelector('.price').textContent
    };
  });
"
```

**Use document fragments:**
```bash
inspekt eval "
  const fragment = document.createDocumentFragment();
  for (let i = 0; i < 100; i++) {
    const div = document.createElement('div');
    div.textContent = i;
    fragment.appendChild(div);
  }
  document.body.appendChild(fragment);
  return 'Added 100 divs efficiently';
"
```

### Data Transformation

**CSV Generation:**
```bash
inspekt eval "
  const rows = Array.from(document.querySelectorAll('table tr'));
  return rows.map(row =>
    Array.from(row.cells).map(cell => cell.textContent).join(',')
  ).join('\n');
" --format raw > data.csv
```

**JSON Transformation:**
```bash
inspekt eval "
  const links = Array.from(document.links);
  return links.reduce((acc, link) => {
    acc[link.textContent] = link.href;
    return acc;
  }, {});
" --format json
```

### State Management

**Store data globally:**
```bash
# Set
inspekt eval "window.inspektData = {extracted: Date.now(), items: [1,2,3]}"

# Get
inspekt eval "window.inspektData"

# Update
inspekt eval "window.inspektData.items.push(4); window.inspektData"
```

### Console Integration

```bash
# Log to browser console
inspekt eval "console.log('Debug:', document.title); document.title"

# Console table
inspekt eval "
  const data = Array.from(document.links).slice(0, 5).map(a => ({
    text: a.textContent,
    href: a.href
  }));
  console.table(data);
  return data.length;
"

# Console time
inspekt eval "
  console.time('query');
  const result = document.querySelectorAll('*').length;
  console.timeEnd('query');
  return result;
"
```

### Browser APIs

**Local Storage:**
```bash
inspekt eval "localStorage.getItem('token')"
inspekt eval "localStorage.setItem('key', 'value')"
inspekt eval "Object.keys(localStorage)"
```

**Cookies:**
```bash
inspekt eval "document.cookie"
inspekt eval "document.cookie.split(';').length"
```

**Performance API:**
```bash
inspekt eval "performance.now()"
inspekt eval "performance.memory.usedJSHeapSize"
inspekt eval "performance.timing.loadEventEnd - performance.timing.navigationStart"
```

**Clipboard API:**
```bash
inspekt eval "await navigator.clipboard.readText()"
inspekt eval "await navigator.clipboard.writeText('Hello from CLI')"
```

---

## Best Practices

### 1. Return Structured Data

```bash
# Good - structured return
inspekt eval "
  return {
    success: true,
    count: document.links.length,
    timestamp: Date.now()
  };
"

# Avoid - multiple console.logs
inspekt eval "
  console.log('Links:', document.links.length);
  console.log('Images:', document.images.length);
"
```

### 2. Use Meaningful Variable Names

```bash
# Good
inspekt eval "
  const productElements = document.querySelectorAll('.product');
  const productData = Array.from(productElements).map(extractProductInfo);
  return productData;
"

# Avoid
inspekt eval "
  const a = document.querySelectorAll('.product');
  const b = Array.from(a).map(c => extractProductInfo(c));
  return b;
"
```

### 3. Handle Edge Cases

```bash
inspekt eval "
  const element = document.querySelector('.may-not-exist');
  if (!element) {
    return { error: 'Element not found' };
  }
  return { text: element.textContent };
"
```

### 4. Comment Complex Code

```bash
inspekt eval "
  // Extract all external links
  const allLinks = Array.from(document.querySelectorAll('a'));

  // Filter to external only
  const externalLinks = allLinks.filter(link =>
    link.hostname !== location.hostname && link.hostname !== ''
  );

  // Return count and sample
  return {
    total: externalLinks.length,
    sample: externalLinks.slice(0, 5).map(l => l.href)
  };
"
```

### 5. Use Functions for Reusability

**script.js:**
```javascript
function extractProductData(selector) {
  const products = document.querySelectorAll(selector);
  return Array.from(products).map(product => ({
    name: product.querySelector('.name')?.textContent?.trim(),
    price: product.querySelector('.price')?.textContent?.trim(),
    available: !product.classList.contains('out-of-stock')
  })).filter(p => p.name && p.price);
}

return extractProductData('.product-item');
```

---

## Debugging Tips

### 1. Use Browser DevTools

Open browser console while running commands to see:
- `console.log()` output
- JavaScript errors with stack traces
- Network requests
- Performance metrics

### 2. Test in REPL First

```bash
inspekt repl
inspekt> document.querySelector('.complex-selector')
inspekt> Array.from(document.querySelectorAll('.items')).length
inspekt> exit
```

### 3. Break Down Complex Code

```bash
# Step 1: Test selector
inspekt eval "document.querySelectorAll('.product').length"

# Step 2: Test extraction
inspekt eval "document.querySelector('.product .name').textContent"

# Step 3: Combine
inspekt eval "Array.from(document.querySelectorAll('.product')).map(p => p.querySelector('.name').textContent)"
```

### 4. Add Debug Output

```bash
inspekt eval "
  console.log('Starting extraction...');
  const products = document.querySelectorAll('.product');
  console.log('Found products:', products.length);
  const data = Array.from(products).map(p => {
    const name = p.querySelector('.name')?.textContent;
    console.log('Extracted:', name);
    return {name};
  });
  console.log('Complete:', data.length);
  return data;
"
```

---

## Common Pitfalls

### 1. Forgetting to Return

```bash
# Wrong - no return
inspekt eval "
  const links = document.querySelectorAll('a');
  links.length;
"
# Output: undefined

# Correct
inspekt eval "
  const links = document.querySelectorAll('a');
  return links.length;
"
# Output: 15
```

### 2. Async Without Await

```bash
# Wrong - returns Promise
inspekt eval "fetch('/api/data').then(r => r.json())"
# Output: [object Promise]

# Correct - await the promise
inspekt eval "await fetch('/api/data').then(r => r.json())"
# Output: {data: [...]}
```

### 3. Quoting Issues

```bash
# Wrong - quote mismatch
inspekt eval 'document.querySelector("div[data-id="123"]")'

# Correct - escape or use heredoc
inspekt eval "document.querySelector(\"div[data-id='123']\")"
```

### 4. Not Checking Null

```bash
# Wrong - may throw error
inspekt eval "document.querySelector('.missing').click()"

# Correct - check first
inspekt eval "document.querySelector('.missing')?.click() ?? 'Element not found'"
```

---

## Next Steps

- **[Element Interaction](element-interaction.md)** - Click, inspect, and interact with elements
- **[Data Extraction](data-extraction.md)** - Extract structured data
- **[Advanced Usage](advanced.md)** - Complex patterns and scripting
