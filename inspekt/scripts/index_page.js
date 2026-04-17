// Index page: Extract complete page structure in document order with semantic information and accessible names
// Creates a comprehensive Markdown representation suitable for AI/LLM processing

(async function() {
  // First, wait for images to load (up to 5 seconds)
  const images = Array.from(document.querySelectorAll('img'));
  const imageLoadPromises = images.map(img => {
    return new Promise((resolve) => {
      if (img.complete) {
        resolve();
      } else {
        const timeout = setTimeout(() => {
          img.removeEventListener('load', onLoad);
          img.removeEventListener('error', onLoad);
          resolve();
        }, 5000);

        const onLoad = () => {
          clearTimeout(timeout);
          resolve();
        };

        img.addEventListener('load', onLoad);
        img.addEventListener('error', onLoad);
      }
    });
  });

  await Promise.all(imageLoadPromises);

  const output = [];
  const processedElements = new WeakSet();
  var largestImage = null;
  var largestImageSize = 0;

  // Helper: Get accessible name (follows ARIA hierarchy)
  function getAccessibleName(el, allowTextContent = true) {
    // Try aria-label first
    if (el.hasAttribute('aria-label')) {
      return el.getAttribute('aria-label').trim();
    }

    // Try aria-labelledby
    if (el.hasAttribute('aria-labelledby')) {
      const ids = el.getAttribute('aria-labelledby').split(' ');
      const labels = ids.map(id => {
        const labelEl = document.getElementById(id);
        return labelEl ? labelEl.textContent.trim() : '';
      }).filter(t => t);
      if (labels.length > 0) return labels.join(' ');
    }

    // For inputs, try associated label
    if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT') {
      const label = el.closest('label') || document.querySelector(`label[for="${el.id}"]`);
      if (label) return label.textContent.trim();

      // Try placeholder
      if (el.placeholder) return el.placeholder.trim();
    }

    // For images, try alt text
    if (el.tagName === 'IMG' && el.alt) {
      return el.alt.trim();
    }

    // Try title attribute
    if (el.title) return el.title.trim();

    // Only use text content if explicitly allowed (not for landmarks)
    if (!allowTextContent) return '';

    // Try text content (truncated)
    const text = el.textContent.trim().replace(/\s+/g, ' ');
    if (text && text.length < 300) return text;
    if (text && text.length >= 300) return text.substring(0, 297) + '…';

    return '';
  }

  // Helper: Clean text by removing problematic characters
  function cleanText(text) {
    return text
      .replace(/\\/g, '/')
      .replace(/[\r\n\t]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  // Helper: Check if element is visible
  function isVisible(el) {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    return style.display !== 'none' &&
           style.visibility !== 'hidden' &&
           style.opacity !== '0';
  }

  // Helper: Check if element is interactive
  function isInteractive(el) {
    const tag = el.tagName.toLowerCase();

    if (tag === 'a' && el.href) return true;
    if (tag === 'button') return true;
    if (tag === 'input' && el.type !== 'hidden') return true;
    if (tag === 'textarea' || tag === 'select') return true;

    const role = el.getAttribute('role');
    if (role && ['button', 'link', 'menuitem', 'tab', 'option', 'checkbox', 'radio', 'switch'].includes(role)) {
      return true;
    }

    if (el.onclick || el.getAttribute('onclick')) return true;
    if (el.hasAttribute('tabindex') && el.getAttribute('tabindex') !== '-1') return true;

    return false;
  }

  // Helper: Get element type/role
  function getElementType(el) {
    const tag = el.tagName.toLowerCase();

    if (el.hasAttribute('role')) {
      return el.getAttribute('role');
    }

    if (tag === 'input') {
      return 'input:' + (el.type || 'text');
    }

    return tag;
  }

  // Helper: Format interactive element
  function formatInteractiveElement(el, indent = '') {
    const name = getAccessibleName(el);
    if (!name) return null;

    const type = getElementType(el);
    const cleanName = cleanText(name);

    if (el.href) {
      return indent + '**[' + type + ']** ' + cleanName + ' → `' + el.href + '`';
    } else {
      return indent + '**[' + type + ']** ' + cleanName;
    }
  }

  // Process element and its children in document order
  function processElement(el, indent = '') {
    const tag = el.tagName ? el.tagName.toLowerCase() : 'unknown';

    // Debug: Check if this element has IMG descendants
    const hasImgInside = el.querySelector && el.querySelector('img') !== null;

    // Debug: Log IMG elements BEFORE any filtering
    if (tag === 'img') {
      console.log('[Zen Index] processElement called with IMG');
      console.log('[Zen Index] - processedElements.has(el):', processedElements.has(el));
      console.log('[Zen Index] - isVisible(el):', isVisible(el));
    }

    // Debug: Log when we skip elements that contain images
    if (!el || processedElements.has(el)) {
      if (hasImgInside && tag !== 'img') {
        console.log('[Zen Index] ⚠️ SKIPPING', tag, 'with IMG inside - already processed');
      }
      return;
    }
    if (!isVisible(el)) {
      if (hasImgInside && tag !== 'img') {
        console.log('[Zen Index] ⚠️ SKIPPING', tag, 'with IMG inside - not visible');
      }
      return;
    }

    // Debug: Log every element we process
    if (tag === 'img') {
      console.log('[Zen Index] Processing IMG element (passed all checks)');
    }

    // Skip script, style, and other non-content elements
    if (['script', 'style', 'noscript', 'iframe'].includes(tag)) return;

    processedElements.add(el);

    // Headings
    if (/^h[1-6]$/.test(tag)) {
      const level = parseInt(tag.substring(1));
      const text = cleanText(el.textContent);
      if (text) {
        output.push(indent + '#'.repeat(level) + ' ' + text);
        output.push('');
      }
      return; // Heading content is already included
    }

    // Paragraphs
    if (tag === 'p') {
      const text = cleanText(el.textContent);
      if (text && text.length > 50) {
        output.push(indent + text);
        output.push('');
      }
      return; // Don't process children separately
    }

    // Lists
    if (tag === 'ul' || tag === 'ol') {
      const items = el.querySelectorAll(':scope > li');
      items.forEach((li, idx) => {
        if (!isVisible(li)) return;
        const text = cleanText(li.textContent);
        if (text) {
          const bullet = tag === 'ol' ? (idx + 1) + '.' : '-';
          output.push(indent + bullet + ' ' + text);
        }
      });
      output.push('');
      return; // Don't process children separately
    }

    // Images
    if (tag === 'img') {
      // Track largest image for vision AI (regardless of alt text)
      const imageSize = el.naturalWidth * el.naturalHeight;

      // Debug: log image info
      console.log('[Zen Index] Image found:', {
        src: el.src.substring(0, 100),
        alt: el.alt,
        naturalWidth: el.naturalWidth,
        naturalHeight: el.naturalHeight,
        complete: el.complete,
        imageSize: imageSize
      });

      if (imageSize > largestImageSize && el.naturalWidth >= 150 && el.naturalHeight >= 150) {
        largestImageSize = imageSize;
        largestImage = el;
        console.log('[Zen Index] New largest image:', largestImageSize, 'px²');
      }

      // Only show images with alt text in the output
      if (el.alt && el.alt.trim()) {
        // Skip small images (likely icons/decorative)
        if (el.naturalWidth >= 150 && el.naturalHeight >= 150) {
          const alt = cleanText(el.alt);
          output.push(indent + '![' + alt + '] (' + el.naturalWidth + 'x' + el.naturalHeight + 'px)');
          output.push('');
        }
      }
      return;
    }

    // Blockquotes
    if (tag === 'blockquote') {
      const text = cleanText(el.textContent);
      if (text) {
        output.push(indent + '> ' + text);
        output.push('');
      }
      return;
    }

    // Tables
    if (tag === 'table') {
      const caption = el.querySelector('caption');
      if (caption) {
        output.push(indent + '**Table**: ' + cleanText(caption.textContent));
      } else {
        output.push(indent + '**Table**');
      }

      // Extract table data
      const rows = el.querySelectorAll('tr');
      if (rows.length > 0 && rows.length <= 20) { // Only show reasonable-sized tables
        rows.forEach((row, idx) => {
          const cells = row.querySelectorAll('th, td');
          if (cells.length > 0) {
            const cellTexts = Array.from(cells).map(cell => cleanText(cell.textContent));
            output.push(indent + '  ' + cellTexts.join(' | '));
          }
        });
      } else if (rows.length > 20) {
        output.push(indent + '  _(' + rows.length + ' rows)_');
      }
      output.push('');
      return;
    }

    // Interactive elements (buttons, links, inputs, etc.)
    if (isInteractive(el)) {
      const formatted = formatInteractiveElement(el, indent);
      if (formatted) {
        output.push(formatted);
        output.push('');
      }
      // Don't return early for DIVs - they might contain images even if interactive
      // Only skip children for actual interactive elements like buttons, links, inputs
      if (!['div', 'section', 'article', 'aside', 'main', 'header', 'footer', 'nav'].includes(tag)) {
        return;
      }
      // For interactive containers, fall through to process children
    }

    // Landmark regions (nav, main, aside, header, footer, section, article)
    if (['nav', 'main', 'aside', 'header', 'footer', 'section', 'article'].includes(tag)) {
      const role = el.getAttribute('role') || tag;
      // For landmarks, only use explicit aria-label or aria-labelledby (not textContent)
      const name = getAccessibleName(el, false);

      if (name) {
        output.push(indent + '## [' + role + '] ' + cleanText(name));
      } else {
        output.push(indent + '## [' + role + ']');
      }
      output.push('');

      // Process children of landmark with increased indent
      const children = Array.from(el.children);
      children.forEach(child => processElement(child, indent + '  '));

      output.push('');
      return;
    }

    // For other containers, process children without adding container markup
    const children = Array.from(el.children);

    // Debug: Check if this container has any img descendants (recursive)
    const hasImgDescendant = el.querySelector('img') !== null;
    if (hasImgDescendant) {
      console.log('[Zen Index] Container', tag, 'has IMG descendant, processing', children.length, 'children…');
    }

    children.forEach((child, idx) => {
      const childTag = child.tagName ? child.tagName.toLowerCase() : 'unknown';
      if (hasImgDescendant) {
        console.log('[Zen Index] Processing child', idx, 'of', tag, ':', child.tagName);
      }
      // Special check for IMG
      if (childTag === 'img') {
        console.log('[Zen Index] *** FOUND IMG AS DIRECT CHILD! ***');
        console.log('[Zen Index] IMG details:', {
          src: child.src,
          alt: child.alt,
          naturalWidth: child.naturalWidth,
          naturalHeight: child.naturalHeight,
          complete: child.complete
        });
      }
      processElement(child, indent);
    });
  }

  // Build the markdown output
  const pageTitle = cleanText(document.title);
  const pageUrl = window.location.href;
  const pageLang = document.documentElement.lang || 'unknown';

  output.push('# ' + pageTitle);
  output.push('');
  output.push('**URL:** ' + pageUrl);
  output.push('**Language:** ' + pageLang);
  output.push('');
  output.push('---');
  output.push('');

  // Start processing from body
  const body = document.body;
  console.log('[Zen Index] Starting DOM traversal from body');
  console.log('[Zen Index] Body has', body ? body.children.length : 0, 'direct children');

  // Check if any images exist in the entire document
  const allImgs = document.querySelectorAll('img');
  console.log('[Zen Index] Total IMG elements in document:', allImgs.length);

  if (body) {
    const children = Array.from(body.children);
    children.forEach((child, idx) => {
      console.log('[Zen Index] Processing body child', idx, ':', child.tagName);
      processElement(child, '');
    });
  }

  console.log('[Zen Index] DOM traversal complete. Processed elements:', processedElements.size || 'N/A');

  // Add statistics at the end
  output.push('---');
  output.push('');
  output.push('## Page Statistics');
  output.push('');

  const allHeadings = document.querySelectorAll('h1, h2, h3, h4, h5, h6');
  const visibleHeadings = Array.from(allHeadings).filter(h => isVisible(h));
  output.push('- Total headings: ' + visibleHeadings.length);

  const allLinks = document.querySelectorAll('a[href]');
  const visibleLinks = Array.from(allLinks).filter(a => isVisible(a));
  output.push('- Total links: ' + visibleLinks.length);

  const allButtons = document.querySelectorAll('button, [role="button"]');
  const visibleButtons = Array.from(allButtons).filter(b => isVisible(b));
  output.push('- Total buttons: ' + visibleButtons.length);

  const allImages = document.querySelectorAll('img[alt]');
  const visibleImages = Array.from(allImages).filter(img => isVisible(img) && img.alt.trim() && img.naturalWidth >= 150);
  output.push('- Total images with alt text: ' + visibleImages.length);

  const allLists = document.querySelectorAll('ul, ol');
  const visibleLists = Array.from(allLists).filter(l => isVisible(l));
  output.push('- Total lists: ' + visibleLists.length);

  // Try to convert largest image to base64 in browser, fall back to server-side download for CORS issues
  var imageData = null;
  console.log('[Zen Index] Largest image found:', largestImage ? {
    src: largestImage.src.substring(0, 100),
    alt: largestImage.alt,
    size: largestImageSize + 'px²'
  } : 'NONE');

  if (largestImage) {
    // Try browser-side conversion first (works for same-origin images)
    try {
      const canvas = document.createElement('canvas');
      canvas.width = largestImage.naturalWidth;
      canvas.height = largestImage.naturalHeight;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(largestImage, 0, 0);

      // Try to export to base64 - this will throw if CORS-tainted
      const dataUrl = canvas.toDataURL('image/jpeg', 0.6);

      console.log('[Zen Index] ✓ Browser-side base64 conversion successful');
      imageData = {
        dataUrl: dataUrl,
        alt: largestImage.alt || '',
        width: largestImage.naturalWidth,
        height: largestImage.naturalHeight
      };
    } catch (corsError) {
      // CORS error - fall back to server-side download
      console.log('[Zen Index] Browser conversion failed (CORS), will use server-side download');
      console.log('[Zen Index] Error:', corsError.message);
      imageData = {
        url: largestImage.src,
        alt: largestImage.alt || '',
        width: largestImage.naturalWidth,
        height: largestImage.naturalHeight
      };
    }
  }

  const result = {
    markdown: output.join('\n'),
    largestImage: imageData
  };

  console.log('[Zen Index] Returning result with largestImage:', imageData ? 'YES' : 'NO');

  return result;
})()
