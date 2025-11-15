// Extract page structure in natural reading flow with Markdown formatting
// Provides a snapshot of the page for AI analysis

(function() {
  const output = [];

  // Helper: Get computed font size
  function getFontSize(el) {
    const size = window.getComputedStyle(el).fontSize;
    return parseFloat(size);
  }

  // Helper: Find largest text on page
  function findLargestText() {
    const candidates = document.querySelectorAll('h1, h2, h3, h4, h5, h6, p, span, div');
    let largest = null;
    let largestSize = 0;

    candidates.forEach(el => {
      const text = el.textContent.trim();
      if (text.length > 5 && text.length < 200) {
        const size = getFontSize(el);
        if (size > largestSize) {
          largestSize = size;
          largest = el;
        }
      }
    });

    return { element: largest, size: largestSize };
  }

  // Helper: Clean text by removing problematic characters
  function cleanText(text) {
    // Replace backslashes with forward slashes to avoid escape sequence issues
    // Replace other problematic characters
    return text
      .replace(/\\/g, '/')     // Convert backslashes to forward slashes
      .replace(/[\r\n\t]/g, ' ')  // Convert line breaks and tabs to spaces
      .replace(/\s+/g, ' ')    // Normalize whitespace
      .trim();
  }

  // Helper: Get first sentence from text
  function getFirstSentence(text) {
    text = text.trim();
    const match = text.match(/^[^.!?]+[.!?]+/);
    if (match) {
      return cleanText(match[0].trim());
    }
    // If no sentence ending found, return first 150 chars
    const truncated = text.substring(0, 150) + (text.length > 150 ? '...' : '');
    return cleanText(truncated);
  }

  // Helper: Check for importance keywords
  function getImportanceMarkers(text) {
    const markers = [];
    const lower = text.toLowerCase();

    if (lower.includes('important')) markers.push('IMPORTANT');
    if (lower.includes('new') || lower.includes('nuevo') || lower.includes('nouveau') || lower.includes('nieuw')) markers.push('NEW');
    if (lower.includes('update')) markers.push('UPDATE');
    if (lower.includes('warning') || lower.includes('caution') || lower.includes('alert')) markers.push('WARNING');

    return markers;
  }

  // Helper: Find next sibling paragraph
  function getNextParagraph(element) {
    let next = element.nextElementSibling;
    let attempts = 0;

    while (next && attempts < 5) {
      if (next.tagName === 'P' && next.textContent.trim().length > 20) {
        return getFirstSentence(next.textContent);
      }
      // Also check first child if it's a container
      const firstP = next.querySelector('p');
      if (firstP && firstP.textContent.trim().length > 20) {
        return getFirstSentence(firstP.textContent);
      }
      next = next.nextElementSibling;
      attempts++;
    }
    return null;
  }

  // Helper: Check if image should be included
  function shouldIncludeImage(img) {
    if (!img.alt || img.alt.trim() === '') return false;
    if (img.naturalWidth < 200) return false;

    const altLower = img.alt.toLowerCase();
    const iconWords = ['icon', 'logo', 'button', 'arrow', 'bullet'];
    return !iconWords.some(word => altLower.includes(word));
  }

  // Helper: Get list items (first 5)
  function getListItems(listEl) {
    const items = listEl.querySelectorAll('li');
    const result = [];

    for (let i = 0; i < Math.min(5, items.length); i++) {
      const text = items[i].textContent.trim().replace(/\s+/g, ' ');
      if (text) result.push(cleanText(text));
    }

    return {
      items: result,
      total: items.length,
      type: listEl.tagName.toLowerCase()
    };
  }

  // Helper: Check if element is visible
  function isVisible(el) {
    const style = window.getComputedStyle(el);
    return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
  }

  // Find the largest text element
  const largestInfo = findLargestText();

  // Process content within a container - now finds ALL elements, not just direct children
  function processContent(container, indent = '') {
    if (!container) return;

    // Find all headings within this container
    const headings = container.querySelectorAll('h1, h2, h3, h4, h5, h6');
    const processedHeadings = new Set();

    headings.forEach(heading => {
      if (!isVisible(heading)) return;
      if (processedHeadings.has(heading)) return;
      processedHeadings.add(heading);

      const level = heading.tagName.substring(1);
      const text = cleanText(heading.textContent.trim());
      const fontSize = getFontSize(heading);
      const markers = getImportanceMarkers(heading.textContent.trim());

      let headingLine = indent + '#'.repeat(parseInt(level)) + ' ' + text;

      // Add font size
      headingLine += ' (' + Math.round(fontSize) + 'px)';

      // Mark if largest
      if (heading === largestInfo.element) {
        headingLine += ' **[LARGEST TEXT]**';
      }

      // Add importance markers
      if (markers.length > 0) {
        headingLine += ' **[' + markers.join(', ') + ']**';
      }

      output.push(headingLine);

      // Try to find first paragraph after heading
      const para = getNextParagraph(heading);
      if (para) {
        output.push(indent + para);
      }
      output.push('');

      // Check for images right after this heading
      let nextEl = heading.nextElementSibling;
      if (nextEl) {
        // Check for image in next element
        if (nextEl.tagName === 'IMG' && shouldIncludeImage(nextEl)) {
          output.push(indent + "![" + cleanText(nextEl.alt) + "](image)");
          output.push('');
        } else {
          const img = nextEl.querySelector('img');
          if (img && shouldIncludeImage(img)) {
            output.push(indent + "![" + cleanText(img.alt) + "](image)");
            output.push('');
          }
        }

        // Check for lists
        if (nextEl.tagName === 'UL' || nextEl.tagName === 'OL') {
          const listData = getListItems(nextEl);
          listData.items.forEach((item, idx) => {
            const bullet = listData.type === 'ol' ? (idx + 1) + '.' : '-';
            output.push(indent + bullet + ' ' + item);
          });
          if (listData.total > listData.items.length) {
            output.push(indent + '  _(' + (listData.total - listData.items.length) + ' more items)_');
          }
          output.push('');
        } else {
          // Check for lists within the next element
          const list = nextEl.querySelector('ul, ol');
          if (list) {
            const listData = getListItems(list);
            listData.items.forEach((item, idx) => {
              const bullet = listData.type === 'ol' ? (idx + 1) + '.' : '-';
              output.push(indent + bullet + ' ' + item);
            });
            if (listData.total > listData.items.length) {
              output.push(indent + '  _(' + (listData.total - listData.items.length) + ' more items)_');
            }
            output.push('');
          }
        }

        // Check for blockquotes
        if (nextEl.tagName === 'BLOCKQUOTE') {
          const text = cleanText(nextEl.textContent.trim().replace(/\s+/g, ' '));
          output.push(indent + '> ' + text);
          output.push('');
        } else {
          const quote = nextEl.querySelector('blockquote');
          if (quote) {
            const text = cleanText(quote.textContent.trim().replace(/\s+/g, ' '));
            output.push(indent + '> ' + text);
            output.push('');
          }
        }
      }
    });
  }

  // Start building output - use string concatenation to avoid template literal issues
  output.push('# ' + cleanText(document.title));
  output.push('');

  // URL info
  output.push('**URL:** ' + window.location.href);
  output.push('');

  // Language info
  const lang = document.documentElement.lang || 'unknown';
  const langLinks = document.querySelectorAll('link[rel="alternate"][hreflang], a[hreflang]');
  const altLangs = Array.from(langLinks)
    .map(l => l.getAttribute('hreflang'))
    .filter(l => l && l !== lang)
    .filter((v, i, a) => a.indexOf(v) === i) // unique
    .slice(0, 5);

  if (altLangs.length > 0) {
    output.push('**Language:** ' + lang + ' (also available: ' + altLangs.join(', ') + ')');
  } else {
    output.push('**Language:** ' + lang);
  }
  output.push('');
  output.push('---');
  output.push('');

  // Navigation
  const navElements = document.querySelectorAll('nav, [role="navigation"]');
  if (navElements.length > 0) {
    output.push('## Navigation');
    output.push('');

    navElements.forEach((nav, idx) => {
      const links = Array.from(nav.querySelectorAll('a'))
        .map(a => cleanText(a.textContent.trim()))
        .filter(t => t.length > 0 && t.length < 100)
        .slice(0, 10);

      if (links.length > 0) {
        output.push(links.join(' | '));
      }
    });

    output.push('');
    output.push('---');
    output.push('');
  }

  // Main content
  const main = document.querySelector('main, [role="main"]');
  if (main) {
    output.push('## Main Content');
    output.push('');
    processContent(main);
    output.push('---');
    output.push('');
  }

  // Sidebar/Complementary
  const aside = document.querySelector('aside, [role="complementary"]');
  if (aside) {
    output.push('## Sidebar');
    output.push('');
    processContent(aside);
    output.push('---');
    output.push('');
  }

  // Footer
  const footer = document.querySelector('footer, [role="contentinfo"]');
  if (footer) {
    output.push('## Footer');
    output.push('');

    const footerLinks = Array.from(footer.querySelectorAll('a'))
      .map(a => cleanText(a.textContent.trim()))
      .filter(t => t.length > 0 && t.length < 100)
      .slice(0, 8);

    if (footerLinks.length > 0) {
      output.push(footerLinks.join(' | '));

      const totalFooterLinks = footer.querySelectorAll('a').length;
      if (totalFooterLinks > footerLinks.length) {
        output.push('_(' + totalFooterLinks + ' links total)_');
      }
    }

    output.push('');
  }

  return output.join('\n');
})()
