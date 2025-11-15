// Extract all links from the current page
// Returns array of link objects with href, text, and type (internal/external)

(function() {
  const currentDomain = window.location.hostname;
  const links = [];

  // Compute accessible name for an element following ARIA specification
  function getAccessibleName(element) {
    // 1. Check aria-labelledby
    const labelledby = element.getAttribute('aria-labelledby');
    if (labelledby) {
      const ids = labelledby.split(/\s+/);
      const texts = ids.map(id => {
        const el = document.getElementById(id);
        return el ? el.textContent.trim() : '';
      }).filter(Boolean);
      if (texts.length > 0) {
        return texts.join(' ').replace(/\s+/g, ' ');
      }
    }

    // 2. Check aria-label
    const ariaLabel = element.getAttribute('aria-label');
    if (ariaLabel && ariaLabel.trim()) {
      return ariaLabel.trim().replace(/\s+/g, ' ');
    }

    // 3. Check for image with alt text
    const img = element.querySelector('img[alt]');
    if (img) {
      const alt = img.getAttribute('alt').trim();
      if (alt) {
        return alt.replace(/\s+/g, ' ');
      }
    }

    // 4. Get text content (excluding hidden elements)
    let text = '';
    const walker = document.createTreeWalker(
      element,
      NodeFilter.SHOW_TEXT,
      {
        acceptNode: function(node) {
          // Skip if parent element is hidden
          const parent = node.parentElement;
          if (parent) {
            const style = window.getComputedStyle(parent);
            if (style.display === 'none' || style.visibility === 'hidden') {
              return NodeFilter.FILTER_REJECT;
            }
          }
          return NodeFilter.FILTER_ACCEPT;
        }
      }
    );

    let node;
    while (node = walker.nextNode()) {
      text += node.textContent;
    }
    text = text.trim().replace(/\s+/g, ' ');

    if (text) {
      return text;
    }

    // 5. Fallback to title attribute
    const title = element.getAttribute('title');
    if (title && title.trim()) {
      return title.trim().replace(/\s+/g, ' ');
    }

    return '';
  }

  // Get all anchor elements
  const anchors = document.querySelectorAll('a[href]');

  anchors.forEach(anchor => {
    const href = anchor.href;

    // Skip empty hrefs, javascript:, mailto:, tel:, etc.
    if (!href ||
        href.startsWith('javascript:') ||
        href.startsWith('mailto:') ||
        href.startsWith('tel:') ||
        href === '#') {
      return;
    }

    // Get the accessible name for the link
    const accessibleName = getAccessibleName(anchor);

    // Parse URL
    let urlData = {
      protocol: '',
      hostname: '',
      pathname: '',
      search: '',
      hash: '',
      port: ''
    };
    let internal = true;
    let external = false;

    try {
      const url = new URL(href);
      urlData.protocol = url.protocol;
      urlData.hostname = url.hostname;
      urlData.pathname = url.pathname;
      urlData.search = url.search;
      urlData.hash = url.hash;
      urlData.port = url.port;

      if (url.hostname !== currentDomain) {
        internal = false;
        external = true;
      }
    } catch (e) {
      // If URL parsing fails, treat as internal (relative URL)
      internal = true;
      external = false;
    }

    // Get target attribute
    const target = anchor.getAttribute('target') || null;
    const opensInNewWindow = target === '_blank';

    // Parse rel attribute
    const relAttr = anchor.getAttribute('rel') || '';
    const relTokens = relAttr.toLowerCase().split(/\s+/);
    const noopener = relTokens.includes('noopener');
    const noreferrer = relTokens.includes('noreferrer');
    const nofollow = relTokens.includes('nofollow');
    const sponsored = relTokens.includes('sponsored');
    const ugc = relTokens.includes('ugc');

    // Download attribute
    const isDownload = anchor.hasAttribute('download');
    const downloadFilename = anchor.getAttribute('download') || null;

    // Accessibility context
    const hasAriaLabel = anchor.hasAttribute('aria-label');
    const hasAriaLabelledby = anchor.hasAttribute('aria-labelledby');

    // Check if has visible text
    let hasVisibleText = false;
    const walker = document.createTreeWalker(
      anchor,
      NodeFilter.SHOW_TEXT,
      {
        acceptNode: function(node) {
          const parent = node.parentElement;
          if (parent) {
            const style = window.getComputedStyle(parent);
            if (style.display === 'none' || style.visibility === 'hidden') {
              return NodeFilter.FILTER_REJECT;
            }
          }
          return NodeFilter.FILTER_ACCEPT;
        }
      }
    );
    let textContent = '';
    let node;
    while (node = walker.nextNode()) {
      textContent += node.textContent;
    }
    hasVisibleText = textContent.trim().length > 0;

    // Check if it's an image-only link
    const images = anchor.querySelectorAll('img');
    const isImageLink = images.length > 0 && !hasVisibleText;

    // Get id, classes, role
    const id = anchor.id || null;
    const classes = anchor.className ? anchor.className.split(/\s+/).filter(Boolean) : [];
    const role = anchor.getAttribute('role') || null;

    // Build link object
    const linkData = {
      accessibleName: accessibleName,
      url: href,
      internal: internal,
      external: external,
      protocol: urlData.protocol,
      hostname: urlData.hostname,
      pathname: urlData.pathname,
      search: urlData.search,
      hash: urlData.hash,
      port: urlData.port,
      target: target,
      opensInNewWindow: opensInNewWindow,
      rel: relAttr || null,
      noopener: noopener,
      noreferrer: noreferrer,
      nofollow: nofollow,
      sponsored: sponsored,
      ugc: ugc,
      isDownload: isDownload,
      downloadFilename: downloadFilename,
      hasAriaLabel: hasAriaLabel,
      hasAriaLabelledby: hasAriaLabelledby,
      hasVisibleText: hasVisibleText,
      isImageLink: isImageLink,
      id: id,
      classes: classes,
      role: role,
      // Legacy fields for backward compatibility
      href: href,
      text: accessibleName,
      type: internal ? 'internal' : 'external'
    };

    links.push(linkData);
  });

  return {
    links: links,
    total: links.length,
    domain: currentDomain
  };
})()
