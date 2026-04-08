// Highlight elements matching a CSS selector
// Usage: Replace 'SELECTOR' with your actual selector
(function(selector) {
    const elements = document.querySelectorAll(selector);

    if (elements.length === 0) {
        return `No elements found matching: ${selector}`;
    }

    // Remove previous highlights
    document.querySelectorAll('[data-inspekt-highlight]').forEach(el => {
        el.style.outline = '';
        el.removeAttribute('data-inspekt-highlight');
    });

    // Add new highlights
    elements.forEach((el, index) => {
        el.style.outline = '3px solid #ff6b6b';
        el.setAttribute('data-inspekt-highlight', index);
    });

    return `Highlighted ${elements.length} element(s) matching: ${selector}`;
})('SELECTOR')  // Replace SELECTOR with actual selector like 'a', '.class', '#id'
