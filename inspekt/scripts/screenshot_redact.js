/**
 * screenshot_redact.js
 *
 * Pre-capture redaction script for screenshots.
 * Applies visual redaction to sensitive form fields and elements containing sensitive text.
 *
 * Usage:
 *   Execute with options: {
 *     action: 'apply' | 'restore',
 *     style: 'blur' | 'bar' | 'pixelate',  // Redaction style (default: 'blur')
 *     rootSelector?: string,      // Scope redaction to this element (for node screenshots)
 *     selectors?: string[],       // Additional selectors to redact
 *     patterns?: string[]         // Additional text patterns to match
 *   }
 *   Returns: { ok: true, redactedCount: number, elements: [...] } or { ok: false, error: string }
 */

(function() {
    'use strict';

    const options = OPTIONS_PLACEHOLDER;
    const action = options.action || 'apply';
    const style = options.style || 'blur';

    // Determine the root element to scan (scoped for node screenshots, body for viewport/page)
    let rootElement = document.body;
    if (options.rootSelector) {
        const el = document.querySelector(options.rootSelector);
        if (el) {
            rootElement = el;
        }
    } else if (window.__INSPEKT_INSPECTED_ELEMENT__) {
        // Use the currently inspected element if no selector provided
        rootElement = window.__INSPEKT_INSPECTED_ELEMENT__;
    }

    // Store original styles so we can restore them
    const STORAGE_KEY = '__inspekt_redacted_elements__';

    // CSS class prefix for redacted elements
    const REDACT_CLASS = '__inspekt-redacted__';

    // Default selectors for sensitive form fields
    const DEFAULT_SELECTORS = [
        // Password fields
        'input[type="password"]',
        // Credit card fields (common autocomplete values)
        'input[autocomplete*="cc-"]',
        'input[autocomplete="cc-number"]',
        'input[autocomplete="cc-csc"]',
        'input[autocomplete="cc-exp"]',
        // Personal identification
        'input[autocomplete="ssn"]',
        'input[name*="ssn"]',
        'input[name*="social"]',
        // Sensitive by name patterns
        'input[name*="password"]',
        'input[name*="secret"]',
        'input[name*="api_key"]',
        'input[name*="apikey"]',
        'input[name*="token"]',
        // Common credit card field names
        'input[name*="card"]',
        'input[name*="credit"]',
        'input[name*="cvv"]',
        'input[name*="cvc"]',
        'input[name*="ccv"]',
    ];

    // Patterns to detect sensitive text content
    const SENSITIVE_TEXT_PATTERNS = [
        // Credit card numbers (4 groups of 4 digits)
        /\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}/,
        // US SSN (XXX-XX-XXXX)
        /\d{3}-\d{2}-\d{4}/,
        // JWT tokens (start with eyJ)
        /eyJ[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]*/,
        // AWS access keys (AKIA...)
        /AKIA[0-9A-Z]{16}/,
        // AWS secret keys (40 chars after common prefixes)
        /aws[_-]?secret[_-]?(?:access[_-]?)?key[:\s=]+['"]?[A-Za-z0-9\/+=]{40}/i,
        // Stripe keys (sk_live_, sk_test_, pk_live_, pk_test_, rk_live_, rk_test_)
        /[spr]k_(?:live|test)_[A-Za-z0-9]{20,}/,
        // Stripe webhook secrets
        /whsec_[A-Za-z0-9]{24,}/,
        // GitHub tokens (ghp_, gho_, ghu_, ghs_, ghr_)
        /gh[pousr]_[A-Za-z0-9]{36,}/,
        // Slack tokens (xoxb, xoxp, xoxa, xoxr, xoxs)
        /xox[bpars]-[A-Za-z0-9\-]+/,
        // Google API keys
        /AIza[A-Za-z0-9\-_]{35}/,
        // Generic secret/key patterns with prefixes (require prefix for safety)
        /(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token)[:\s=]+['"]?[A-Za-z0-9\-_]{20,}/i,
    ];

    // Email pattern for masking (not blurring)
    const EMAIL_PATTERN = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g;

    /**
     * Mask an email address: john.doe@company.com → j…e@company.com
     */
    function maskEmail(email) {
        const atIndex = email.indexOf('@');
        if (atIndex < 1) return email;

        const localPart = email.substring(0, atIndex);
        const domain = email.substring(atIndex);

        if (localPart.length <= 2) {
            // Very short local part: just show first char
            return localPart[0] + '…' + domain;
        }

        // Show first and last character of local part
        return localPart[0] + '…' + localPart[localPart.length - 1] + domain;
    }

    /**
     * Find and mask email addresses in text content and input values.
     * Returns array of { element, originalValue, type } for restoration.
     */
    function maskEmails() {
        const masked = [];

        // 1. Mask emails in input fields (type="email" or containing email values)
        const inputs = rootElement.querySelectorAll('input[type="email"], input[autocomplete="email"], input[name*="email"]');
        for (const input of inputs) {
            const value = input.value || '';
            if (EMAIL_PATTERN.test(value)) {
                EMAIL_PATTERN.lastIndex = 0; // Reset regex
                masked.push({
                    element: input,
                    originalValue: value,
                    type: 'input'
                });
                input.value = value.replace(EMAIL_PATTERN, maskEmail);
            }
        }

        // 2. Also check all text inputs for email-like values
        const textInputs = rootElement.querySelectorAll('input[type="text"], input:not([type])');
        for (const input of textInputs) {
            const value = input.value || '';
            if (EMAIL_PATTERN.test(value)) {
                EMAIL_PATTERN.lastIndex = 0;
                // Skip if already masked
                if (masked.some(m => m.element === input)) continue;
                masked.push({
                    element: input,
                    originalValue: value,
                    type: 'input'
                });
                input.value = value.replace(EMAIL_PATTERN, maskEmail);
            }
        }

        // 3. Mask emails in text nodes
        const walker = document.createTreeWalker(
            rootElement,
            NodeFilter.SHOW_TEXT,
            null,
            false
        );

        let node;
        while (node = walker.nextNode()) {
            const text = node.textContent;
            if (EMAIL_PATTERN.test(text)) {
                EMAIL_PATTERN.lastIndex = 0;
                masked.push({
                    element: node,
                    originalValue: text,
                    type: 'text'
                });
                node.textContent = text.replace(EMAIL_PATTERN, maskEmail);
            }
        }

        return masked;
    }

    // Inject styles for the selected redaction style
    function ensureRedactStyle(redactStyle) {
        const styleId = '__inspekt_redact_style__';
        let styleEl = document.getElementById(styleId);
        if (styleEl) styleEl.remove();

        styleEl = document.createElement('style');
        styleEl.id = styleId;

        if (redactStyle === 'blur') {
            // Gaussian blur using text-shadow (doesn't affect element borders)
            // Text is already randomized for security, blur adds visual indicator
            styleEl.textContent = `
                .${REDACT_CLASS} {
                    color: transparent !important;
                    text-shadow: 0 0 8px rgba(0, 0, 0, 0.9) !important;
                    user-select: none !important;
                    pointer-events: none !important;
                }
                .${REDACT_CLASS}::placeholder {
                    color: transparent !important;
                    text-shadow: none !important;
                }
            `;
        } else if (redactStyle === 'bar') {
            // Bar style: just set color for █ block characters
            styleEl.textContent = `
                .${REDACT_CLASS} {
                    color: #aaa !important;
                }
            `;
        }

        document.head.appendChild(styleEl);
    }

    // Find all sensitive elements by selector (scoped to rootElement)
    function findBySelectors(selectors) {
        const elements = new Set();

        for (const selector of selectors) {
            try {
                const matches = rootElement.querySelectorAll(selector);
                matches.forEach(el => elements.add(el));
            } catch (e) {
                // Invalid selector, skip
                console.warn(`[Inspekt Redact] Invalid selector: ${selector}`);
            }
        }

        return Array.from(elements);
    }

    // Find elements containing sensitive text patterns (scoped to rootElement)
    function findByTextPatterns(patterns) {
        const elements = new Set();

        // Convert string patterns to RegExp
        const regexPatterns = patterns.map(p => {
            if (p instanceof RegExp) return p;
            try {
                return new RegExp(p, 'gi');
            } catch (e) {
                return null;
            }
        }).filter(Boolean);

        // Walk text nodes within rootElement
        const walker = document.createTreeWalker(
            rootElement,
            NodeFilter.SHOW_TEXT,
            null,
            false
        );

        let node;
        while (node = walker.nextNode()) {
            const text = node.textContent.trim();
            if (!text || text.length < 6) continue;

            // Check against patterns
            for (const pattern of regexPatterns) {
                if (pattern.test(text)) {
                    // Add the parent element (the one that contains this text)
                    let parent = node.parentElement;
                    // Walk up to find a suitable element to redact
                    while (parent && parent !== document.body) {
                        // Don't redact huge container elements
                        if (parent.offsetWidth > 500 || parent.offsetHeight > 200) {
                            parent = parent.parentElement;
                            continue;
                        }
                        elements.add(parent);
                        break;
                    }
                    break;
                }
            }
        }

        return Array.from(elements);
    }

    // Find elements with sensitive input values (scoped to rootElement)
    function findInputsWithSensitiveValues() {
        const elements = [];

        // Check all visible inputs within rootElement
        const inputs = rootElement.querySelectorAll('input:not([type="hidden"]), textarea');

        for (const input of inputs) {
            const value = input.value || '';
            if (!value || value.length < 4) continue;

            // Check if value matches sensitive patterns
            for (const pattern of SENSITIVE_TEXT_PATTERNS) {
                if (pattern.test(value)) {
                    elements.push(input);
                    break;
                }
            }
        }

        return elements;
    }

    // Black block character for bar-style redaction
    const BLOCK_CHAR = '█';

    // Character sets for randomization
    const CHARS_LOWER = 'abcdefghijklmnopqrstuvwxyz';
    const CHARS_UPPER = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
    const CHARS_DIGIT = '0123456789';

    /**
     * Replace text with block characters, preserving length
     */
    function toBlocks(text) {
        return text.replace(/\S/g, BLOCK_CHAR);
    }

    /**
     * Randomize text while preserving character types (for security layer under blur/pixelate)
     * - Lowercase letters → random lowercase
     * - Uppercase letters → random uppercase
     * - Digits → random digits
     * - Special chars → random from all
     * - Whitespace preserved
     */
    function randomizeText(text) {
        let result = '';
        for (let i = 0; i < text.length; i++) {
            const c = text[i];
            if (/\s/.test(c)) {
                result += c; // Preserve whitespace
            } else if (/[a-z]/.test(c)) {
                result += CHARS_LOWER[Math.floor(Math.random() * CHARS_LOWER.length)];
            } else if (/[A-Z]/.test(c)) {
                result += CHARS_UPPER[Math.floor(Math.random() * CHARS_UPPER.length)];
            } else if (/[0-9]/.test(c)) {
                result += CHARS_DIGIT[Math.floor(Math.random() * CHARS_DIGIT.length)];
            } else {
                // Special characters: randomize with mixed alphanumeric
                const allChars = CHARS_LOWER + CHARS_DIGIT;
                result += allChars[Math.floor(Math.random() * allChars.length)];
            }
        }
        return result;
    }

    // Apply redaction to elements
    function applyRedaction(elements, redactStyle) {
        // Inject CSS for all styles
        ensureRedactStyle(redactStyle);

        const redacted = [];
        const storage = [];

        for (const el of elements) {
            if (el.classList.contains(REDACT_CLASS)) continue;

            // Store original state
            const originalData = {
                element: el,
                originalFilter: el.style.filter,
                originalUserSelect: el.style.userSelect,
                originalPosition: el.style.position,
                originalColor: el.style.color,
            };

            const isInputElement = ['INPUT', 'TEXTAREA'].includes(el.tagName);

            if (redactStyle === 'bar') {
                // Bar style: replace characters with █ blocks
                if (isInputElement) {
                    originalData.originalValue = el.value;
                    el.value = toBlocks(el.value);
                } else {
                    // For text elements, replace text content
                    originalData.originalTextContent = el.textContent;
                    el.textContent = toBlocks(el.textContent);
                }
                // Apply class for #aaa color
                el.classList.add(REDACT_CLASS);
            } else {
                // Blur/pixelate: first randomize text (security layer), then apply CSS effect
                if (isInputElement) {
                    originalData.originalValue = el.value;
                    el.value = randomizeText(el.value);
                } else {
                    originalData.originalTextContent = el.textContent;
                    el.textContent = randomizeText(el.textContent);
                }
                // Apply visual effect on top of randomized text
                el.classList.add(REDACT_CLASS);
            }

            storage.push(originalData);

            // Record info for reporting
            redacted.push({
                tag: el.tagName.toLowerCase(),
                type: el.type || null,
                name: el.name || null,
                id: el.id || null,
                selector: generateSelector(el),
                style: redactStyle,
            });
        }

        // Store for restoration (maskedEmails added separately in main execution)
        window[STORAGE_KEY] = { storage, style: redactStyle, maskedEmails: [] };

        return redacted;
    }

    // Restore redacted elements
    function restoreRedaction() {
        const data = window[STORAGE_KEY] || {};
        const storage = data.storage || [];
        const maskedEmails = data.maskedEmails || [];
        const redactStyle = data.style || 'blur';

        // Restore redacted elements
        for (const item of storage) {
            const el = item.element;
            if (!el) continue;

            // Restore bar-style redaction (text replaced with █ blocks)
            if (item.originalValue !== undefined) {
                el.value = item.originalValue;
            }
            if (item.originalTextContent !== undefined) {
                el.textContent = item.originalTextContent;
            }

            // Restore blur/pixelate-style redaction (CSS classes)
            if (el.classList) {
                el.classList.remove(REDACT_CLASS);
                el.classList.remove(`${REDACT_CLASS}--text`);
            }
            el.style.filter = item.originalFilter || '';
            el.style.userSelect = item.originalUserSelect || '';
            el.style.position = item.originalPosition || '';
            el.style.color = item.originalColor || '';
        }

        // Restore masked email addresses
        for (const item of maskedEmails) {
            if (item.type === 'input' && item.element) {
                item.element.value = item.originalValue;
            } else if (item.type === 'text' && item.element) {
                item.element.textContent = item.originalValue;
            }
        }

        // Clean up
        window[STORAGE_KEY] = null;

        // Remove style element
        const styleEl = document.getElementById('__inspekt_redact_style__');
        if (styleEl) styleEl.remove();

        return { ok: true, restored: storage.length + maskedEmails.length };
    }

    // Generate a simple selector for an element
    function generateSelector(el) {
        if (el.id) return `#${el.id}`;
        if (el.name) return `${el.tagName.toLowerCase()}[name="${el.name}"]`;
        if (el.className && typeof el.className === 'string') {
            const classes = el.className.split(' ').filter(c => c && !c.startsWith('__inspekt'));
            if (classes.length > 0) return `${el.tagName.toLowerCase()}.${classes[0]}`;
        }
        return el.tagName.toLowerCase();
    }

    // Main execution
    try {
        if (action === 'restore') {
            return restoreRedaction();
        }

        // Default to 'apply'
        const selectors = options.selectors || DEFAULT_SELECTORS;
        const usePatterns = options.includePatterns !== false;
        const customPatterns = options.patterns || [];

        // Collect all sensitive elements
        const selectorElements = findBySelectors(selectors);
        const patternElements = usePatterns ? findByTextPatterns([...SENSITIVE_TEXT_PATTERNS, ...customPatterns]) : [];
        const sensitiveInputs = findInputsWithSensitiveValues();

        // Combine and deduplicate
        const allElements = new Set([...selectorElements, ...patternElements, ...sensitiveInputs]);
        const uniqueElements = Array.from(allElements);

        // Apply visual redaction with selected style (blur/bar/pixelate)
        const redacted = applyRedaction(uniqueElements, style);

        // Apply email masking (j…e@domain.com style) - always done regardless of style
        const maskedEmails = maskEmails();

        // Store masked emails for restoration
        if (window[STORAGE_KEY]) {
            window[STORAGE_KEY].maskedEmails = maskedEmails;
        }

        return {
            ok: true,
            redactedCount: redacted.length,
            maskedEmailsCount: maskedEmails.length,
            elements: redacted,
            style: style,
            selectorsUsed: selectors.length,
            patternsUsed: usePatterns ? SENSITIVE_TEXT_PATTERNS.length + customPatterns.length : 0,
        };

    } catch (error) {
        return {
            ok: false,
            error: error.message || String(error)
        };
    }
})();
