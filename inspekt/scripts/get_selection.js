// Get the current text selection in the browser
(function() {
    const selection = window.getSelection();

    if (!selection || selection.rangeCount === 0) {
        return {
            ok: true,
            hasSelection: false,
            text: '',
            html: ''
        };
    }

    const selectedText = selection.toString();

    if (!selectedText || selectedText.trim() === '') {
        return {
            ok: true,
            hasSelection: false,
            text: '',
            html: ''
        };
    }

    // Get HTML content of selection
    let html = '';
    try {
        const range = selection.getRangeAt(0);
        const fragment = range.cloneContents();
        const div = document.createElement('div');
        div.appendChild(fragment);

        // Remove empty elements (elements with no text content and no meaningful children)
        const removeEmptyElements = (container) => {
            const elements = container.querySelectorAll('*');
            // Process in reverse order to handle nested empty elements
            for (let i = elements.length - 1; i >= 0; i--) {
                const el = elements[i];
                // Check if element is empty (no text, no images, no inputs, etc.)
                const hasText = el.textContent.trim().length > 0;
                const hasMeaningfulContent = el.querySelector('img, input, textarea, video, audio, iframe, canvas, svg');
                if (!hasText && !hasMeaningfulContent) {
                    el.remove();
                }
            }
        };
        removeEmptyElements(div);

        html = div.innerHTML;
    } catch (e) {
        // HTML extraction failed, just use text
    }

    // Trim trailing whitespace from text
    const trimmedText = selectedText.replace(/\s+$/, '');

    // Get the element that contains the selection start
    const anchorNode = selection.anchorNode;
    const anchorElement = anchorNode.nodeType === Node.ELEMENT_NODE
        ? anchorNode
        : anchorNode.parentElement;

    // Get selection position info
    const range = selection.getRangeAt(0);
    const rect = range.getBoundingClientRect();

    return {
        ok: true,
        hasSelection: true,
        text: trimmedText,
        html: html,
        length: trimmedText.length,
        rangeCount: selection.rangeCount,
        isCollapsed: selection.isCollapsed,
        position: {
            x: Math.round(rect.left),
            y: Math.round(rect.top),
            width: Math.round(rect.width),
            height: Math.round(rect.height)
        },
        container: {
            tag: anchorElement ? anchorElement.tagName.toLowerCase() : null,
            id: anchorElement ? anchorElement.id || null : null,
            class: anchorElement ? anchorElement.className || null : null
        }
    };
})()
