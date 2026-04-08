// Extract actionable elements from the page and add temporary action classes
// Returns structured data with landmarks, headings, and all actionable items

(function() {
  const ACTION_CLASS_PREFIX = 'inspekt-action-';
  let actionCounter = 0;
  const actionableElements = [];

  // Helper: Check if element is visible
  function isVisible(el) {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    return style.display !== 'none' &&
           style.visibility !== 'hidden' &&
           style.opacity !== '0' &&
           el.offsetWidth > 0 &&
           el.offsetHeight > 0;
  }

  // Helper: Check if element is actionable
  function isActionable(el) {
    // Links
    if (el.tagName === 'A' && el.href) return true;

    // Buttons
    if (el.tagName === 'BUTTON') return true;

    // Inputs (excluding hidden)
    if (el.tagName === 'INPUT' && el.type !== 'hidden') return true;

    // Textareas and selects
    if (el.tagName === 'TEXTAREA' || el.tagName === 'SELECT') return true;

    // Elements with role="button", role="link", etc.
    const role = el.getAttribute('role');
    if (role && ['button', 'link', 'menuitem', 'tab', 'option', 'checkbox', 'radio', 'switch'].includes(role)) {
      return true;
    }

    // Elements with click handlers
    if (el.onclick || el.getAttribute('onclick')) return true;

    // Elements with tabindex (focusable)
    if (el.hasAttribute('tabindex') && el.getAttribute('tabindex') !== '-1') return true;

    // Images inside links (but we already catch the link)
    // Forms (though we catch individual inputs)

    return false;
  }

  // Helper: Get accessible name
  function getAccessibleName(el) {
    // Try aria-label first
    if (el.hasAttribute('aria-label')) {
      return el.getAttribute('aria-label');
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
      if (el.placeholder) return el.placeholder;
    }

    // For images, try alt text
    if (el.tagName === 'IMG' && el.alt) {
      return el.alt;
    }

    // Try title attribute
    if (el.title) return el.title;

    // Try text content (truncated)
    const text = el.textContent.trim().replace(/\s+/g, ' ');
    if (text && text.length < 200) return text;
    if (text && text.length >= 200) return text.substring(0, 197) + '...';

    return '';
  }

  // Helper: Get element description
  function getElementDescription(el, actionId) {
    const tag = el.tagName.toLowerCase();
    const text = getAccessibleName(el);

    let type = 'unknown';
    if (el.tagName === 'A') type = 'link';
    else if (el.tagName === 'BUTTON') type = 'button';
    else if (el.tagName === 'INPUT') {
      type = `input-${el.type || 'text'}`;
    }
    else if (el.tagName === 'TEXTAREA') type = 'textarea';
    else if (el.tagName === 'SELECT') type = 'select';
    else if (el.getAttribute('role')) type = el.getAttribute('role');

    const description = {
      actionId: actionId,
      tag: tag,
      type: type,
      text: text,
      href: el.href || null,
      role: el.getAttribute('role') || null,
      ariaLabel: el.getAttribute('aria-label') || null,
    };

    // Add context (parent heading or landmark)
    const context = findContext(el);
    if (context) {
      description.context = context;
    }

    // Add position info
    const rect = el.getBoundingClientRect();
    description.position = {
      x: Math.round(rect.left + window.scrollX),
      y: Math.round(rect.top + window.scrollY),
      width: Math.round(rect.width),
      height: Math.round(rect.height)
    };

    return description;
  }

  // Helper: Find contextual information (nearest heading or landmark)
  function findContext(el) {
    let current = el.parentElement;
    let depth = 0;
    const maxDepth = 10;

    while (current && depth < maxDepth) {
      // Check for landmark roles
      const role = current.getAttribute('role');
      if (role && ['navigation', 'main', 'complementary', 'banner', 'contentinfo', 'search', 'form'].includes(role)) {
        return { type: 'landmark', role: role };
      }

      // Check for landmark tags
      if (['NAV', 'MAIN', 'ASIDE', 'HEADER', 'FOOTER'].includes(current.tagName)) {
        return { type: 'landmark', tag: current.tagName.toLowerCase() };
      }

      current = current.parentElement;
      depth++;
    }

    // Find nearest preceding heading
    let node = el.previousElementSibling;
    depth = 0;
    while (node && depth < 5) {
      if (/^H[1-6]$/.test(node.tagName)) {
        return { type: 'heading', level: parseInt(node.tagName[1]), text: node.textContent.trim().substring(0, 100) };
      }
      node = node.previousElementSibling;
      depth++;
    }

    return null;
  }

  // Extract landmarks structure
  function extractLandmarks() {
    const landmarks = [];

    // Find all landmark elements
    const landmarkSelectors = [
      'header, [role="banner"]',
      'nav, [role="navigation"]',
      'main, [role="main"]',
      'aside, [role="complementary"]',
      'footer, [role="contentinfo"]',
      '[role="search"]',
      '[role="form"]'
    ];

    landmarkSelectors.forEach(selector => {
      const elements = document.querySelectorAll(selector);
      elements.forEach(el => {
        if (!isVisible(el)) return;

        const role = el.getAttribute('role') || el.tagName.toLowerCase();
        const label = el.getAttribute('aria-label') || '';

        landmarks.push({
          role: role,
          label: label,
          tag: el.tagName.toLowerCase()
        });
      });
    });

    return landmarks;
  }

  // Extract headings structure
  function extractHeadings() {
    const headings = [];
    const headingElements = document.querySelectorAll('h1, h2, h3, h4, h5, h6, [role="heading"]');

    headingElements.forEach(el => {
      if (!isVisible(el)) return;

      let level = 1;
      if (el.tagName.match(/^H[1-6]$/)) {
        level = parseInt(el.tagName[1]);
      } else if (el.getAttribute('aria-level')) {
        level = parseInt(el.getAttribute('aria-level'));
      }

      headings.push({
        level: level,
        text: el.textContent.trim()
      });
    });

    return headings;
  }

  // Main processing: Find all actionable elements
  function processActionableElements() {
    // Get all potentially actionable elements
    const allElements = document.querySelectorAll('a, button, input, textarea, select, [role="button"], [role="link"], [onclick], [tabindex]');

    allElements.forEach(el => {
      if (!isVisible(el)) return;
      if (!isActionable(el)) return;

      // Generate action ID
      actionCounter++;
      const actionId = `${ACTION_CLASS_PREFIX}${String(actionCounter).padStart(3, '0')}`;

      // Add the class to the element
      el.classList.add(actionId);

      // Store element description
      const description = getElementDescription(el, actionId);
      actionableElements.push(description);
    });
  }

  // Execute extraction
  const landmarks = extractLandmarks();
  const headings = extractHeadings();
  processActionableElements();

  // Return structured data
  return {
    pageTitle: document.title,
    pageUrl: window.location.href,
    language: document.documentElement.lang || 'unknown',
    landmarks: landmarks,
    headings: headings,
    actionableElements: actionableElements,
    totalActions: actionCounter
  };
})()
