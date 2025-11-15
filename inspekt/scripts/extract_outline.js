// Extract page outline from headings (H1-H6 and ARIA headings)
// Returns hierarchical structure of all headings

(function() {
  const headings = [];

  // Get native heading elements (H1-H6)
  const nativeHeadings = document.querySelectorAll('h1, h2, h3, h4, h5, h6');

  nativeHeadings.forEach(heading => {
    const level = parseInt(heading.tagName.substring(1)); // Extract number from H1-H6
    const text = heading.textContent.trim().replace(/\s+/g, ' ');

    headings.push({
      level: level,
      text: text,
      type: 'native',
      tag: heading.tagName.toLowerCase(),
      element: heading  // Store element reference for sorting
    });
  });

  // Get ARIA headings (role="heading" with aria-level)
  const ariaHeadings = document.querySelectorAll('[role="heading"][aria-level]');

  ariaHeadings.forEach(heading => {
    const level = parseInt(heading.getAttribute('aria-level'));
    const text = heading.textContent.trim().replace(/\s+/g, ' ');

    // Only include if level is valid (1-6)
    if (level >= 1 && level <= 6) {
      headings.push({
        level: level,
        text: text,
        type: 'aria',
        tag: heading.tagName.toLowerCase(),
        element: heading  // Store element reference for sorting
      });
    }
  });

  // Sort headings by their appearance in the document using element references
  headings.sort((a, b) => {
    if (!a.element || !b.element) return 0;

    const position = a.element.compareDocumentPosition(b.element);

    if (position & Node.DOCUMENT_POSITION_FOLLOWING) {
      return -1;  // a comes before b
    } else if (position & Node.DOCUMENT_POSITION_PRECEDING) {
      return 1;   // b comes before a
    }

    return 0;  // same element or unrelated
  });

  // Remove element references before returning (not serializable)
  const cleanedHeadings = headings.map(h => ({
    level: h.level,
    text: h.text,
    type: h.type,
    tag: h.tag
  }));

  return {
    headings: cleanedHeadings,
    total: cleanedHeadings.length,
    url: window.location.href
  };
})()
