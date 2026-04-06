/**
 * Press keys to the browser's active element.
 *
 * This is a stateless version of keyboard dispatch that:
 * - Uses document.activeElement (no virtual focus tracking)
 * - Processes keys sequentially with optional waits
 * - Handles Tab, Enter, Backspace, Delete, and printable characters
 * - Supports fixed or random delays between key presses
 *
 * Placeholders:
 * - KEY_SEQUENCE_PLACEHOLDER: JSON array of KeySpec objects
 * - DELAY_CONFIG_PLACEHOLDER: { delay, delayMin, delayMax }
 */
(function(keySequence, delayConfig) {
    'use strict';

    return new Promise(function(resolve) {
        var results = [];
        var index = 0;
        var keyCount = 0;

        /**
         * Check if input element supports selection APIs.
         * Only text, password, search, tel, and url input types support
         * selectionStart/selectionEnd. All others throw InvalidStateError.
         */
        function supportsSelection(el) {
            if (el.tagName !== 'INPUT') return true;
            var type = (el.type || 'text').toLowerCase();
            // These types SUPPORT selectionStart/selectionEnd
            var selectionTypes = ['text', 'password', 'search', 'tel', 'url'];
            return selectionTypes.indexOf(type) !== -1;
        }

        /**
         * Calculate delay in milliseconds between key presses.
         * Returns 0 for no delay, fixed delay, or random delay in range.
         */
        function getDelayMs() {
            // Fixed delay
            if (delayConfig.delay > 0) {
                return delayConfig.delay * 1000;
            }
            // Random delay in range
            if (delayConfig.delayMin !== null && delayConfig.delayMax !== null) {
                var min = delayConfig.delayMin * 1000;
                var max = delayConfig.delayMax * 1000;
                return min + Math.random() * (max - min);
            }
            // No delay (just 10ms for reliability)
            return 10;
        }

        /**
         * Get focusable elements on the page.
         */
        function getFocusableElements() {
            var selector = [
                'a[href]',
                'button:not([disabled])',
                'input:not([disabled]):not([type="hidden"])',
                'select:not([disabled])',
                'textarea:not([disabled])',
                '[tabindex]:not([tabindex="-1"])',
                '[contenteditable="true"]'
            ].join(', ');

            return Array.from(document.querySelectorAll(selector)).filter(function(el) {
                var style = window.getComputedStyle(el);
                return style.display !== 'none' &&
                       style.visibility !== 'hidden' &&
                       el.offsetWidth > 0 &&
                       el.offsetHeight > 0;
            });
        }

        /**
         * Handle Tab key navigation.
         */
        function handleTab(target, shiftKey) {
            var focusables = getFocusableElements();
            if (focusables.length === 0) return false;

            var currentIndex = focusables.indexOf(target);
            var nextIndex;

            if (shiftKey) {
                // Shift+Tab - go to previous
                nextIndex = currentIndex > 0 ? currentIndex - 1 : focusables.length - 1;
            } else {
                // Tab - go to next
                nextIndex = currentIndex < focusables.length - 1 ? currentIndex + 1 : 0;
            }

            var nextElement = focusables[nextIndex];
            if (nextElement) {
                nextElement.focus();
                return true;
            }
            return false;
        }

        /**
         * Handle Enter key activation.
         */
        function handleEnter(target) {
            var tag = target.tagName;
            var role = target.getAttribute('role');

            // Links and buttons - click them
            if (tag === 'A' || tag === 'BUTTON' || role === 'button' || role === 'link') {
                target.click();
                return true;
            }

            // Checkboxes and radios - toggle them
            if (tag === 'INPUT' && (target.type === 'checkbox' || target.type === 'radio')) {
                target.click();
                return true;
            }

            // Submit/button inputs - click them
            if (tag === 'INPUT' && (target.type === 'submit' || target.type === 'button')) {
                target.click();
                return true;
            }

            // Form inputs - submit the form
            if ((tag === 'INPUT' || tag === 'SELECT') && target.form) {
                if (target.form.requestSubmit) {
                    target.form.requestSubmit();
                } else {
                    target.form.submit();
                }
                return true;
            }

            // Elements with onclick handler
            if (target.onclick || target.getAttribute('onclick')) {
                target.click();
                return true;
            }

            return false;
        }

        /**
         * Handle Space key activation.
         * Space activates buttons and toggles checkboxes/radios.
         * For text inputs, it inserts a space character.
         */
        function handleSpace(target) {
            var tag = target.tagName;
            var role = target.getAttribute('role');

            // Buttons - click them
            if (tag === 'BUTTON' || role === 'button') {
                target.click();
                return true;
            }

            // Checkboxes and radios - toggle them
            if (tag === 'INPUT' && (target.type === 'checkbox' || target.type === 'radio')) {
                target.click();
                return true;
            }

            // Submit/button inputs - click them
            if (tag === 'INPUT' && (target.type === 'submit' || target.type === 'button')) {
                target.click();
                return true;
            }

            // Text inputs and textareas - insert a space character
            if (tag === 'INPUT' || tag === 'TEXTAREA') {
                // Only process if it's a text-like input (not checkbox, radio, button, etc.)
                var textTypes = ['text', 'password', 'email', 'search', 'tel', 'url', 'number'];
                if (tag === 'TEXTAREA' || textTypes.indexOf(target.type) !== -1) {
                    return handlePrintableChar(target, ' ');
                }
                // For other input types (file, range, color, etc.), do nothing
                return false;
            }

            // Contenteditable - insert a space
            if (target.contentEditable === 'true') {
                document.execCommand('insertText', false, ' ');
                return true;
            }

            // Elements with onclick handler
            if (target.onclick || target.getAttribute('onclick')) {
                target.click();
                return true;
            }

            return false;
        }

        /**
         * Handle Backspace key in text inputs.
         */
        function handleBackspace(target) {
            if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') {
                // Only process if input type supports selection APIs
                if (!supportsSelection(target)) {
                    return false;
                }

                var start = target.selectionStart || 0;
                var end = target.selectionEnd || 0;
                var value = target.value || '';

                if (start !== end) {
                    // Delete selection
                    target.value = value.substring(0, start) + value.substring(end);
                    target.selectionStart = target.selectionEnd = start;
                } else if (start > 0) {
                    // Delete character before cursor
                    target.value = value.substring(0, start - 1) + value.substring(start);
                    target.selectionStart = target.selectionEnd = start - 1;
                }

                target.dispatchEvent(new Event('input', { bubbles: true }));
                return true;
            }

            if (target.contentEditable === 'true') {
                document.execCommand('delete', false);
                return true;
            }

            return false;
        }

        /**
         * Handle Delete key in text inputs.
         */
        function handleDelete(target) {
            if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') {
                // Only process if input type supports selection APIs
                if (!supportsSelection(target)) {
                    return false;
                }

                var start = target.selectionStart || 0;
                var end = target.selectionEnd || 0;
                var value = target.value || '';

                if (start !== end) {
                    // Delete selection
                    target.value = value.substring(0, start) + value.substring(end);
                    target.selectionStart = target.selectionEnd = start;
                } else if (start < value.length) {
                    // Delete character after cursor
                    target.value = value.substring(0, start) + value.substring(start + 1);
                    target.selectionStart = target.selectionEnd = start;
                }

                target.dispatchEvent(new Event('input', { bubbles: true }));
                return true;
            }

            if (target.contentEditable === 'true') {
                document.execCommand('forwardDelete', false);
                return true;
            }

            return false;
        }

        /**
         * Handle printable character input.
         */
        function handlePrintableChar(target, key) {
            if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') {
                // Only process if input type supports selection APIs
                if (!supportsSelection(target)) {
                    return false;
                }

                var start = target.selectionStart || 0;
                var end = target.selectionEnd || 0;
                var value = target.value || '';

                target.value = value.substring(0, start) + key + value.substring(end);
                target.selectionStart = target.selectionEnd = start + 1;

                target.dispatchEvent(new InputEvent('input', {
                    data: key,
                    inputType: 'insertText',
                    bubbles: true
                }));
                return true;
            }

            if (target.contentEditable === 'true') {
                document.execCommand('insertText', false, key);
                return true;
            }

            return false;
        }

        /**
         * Get a description of the element for reporting.
         */
        function describeElement(el) {
            if (!el || el === document.body) return 'body';

            var desc = el.tagName.toLowerCase();
            if (el.id) desc += '#' + el.id;
            if (el.className && typeof el.className === 'string') {
                var classes = el.className.trim().split(/\s+/).slice(0, 2);
                if (classes.length > 0 && classes[0]) {
                    desc += '.' + classes.join('.');
                }
            }
            return desc;
        }

        /**
         * Process the next key in the sequence.
         */
        function processNext() {
            if (index >= keySequence.length) {
                // All done
                resolve({
                    ok: true,
                    message: 'Pressed ' + keyCount + ' key' + (keyCount !== 1 ? 's' : ''),
                    results: results
                });
                return;
            }

            var spec = keySequence[index];
            index++;

            // Handle Wait
            if (spec.type === 'wait') {
                var waitMs = (spec.wait_seconds || 0.5) * 1000;
                results.push({
                    type: 'wait',
                    seconds: spec.wait_seconds
                });
                setTimeout(processNext, waitMs);
                return;
            }

            // Handle Key
            var target = document.activeElement || document.body;
            var key = spec.key;
            var code = spec.code || '';

            // Create keyboard event options
            var eventInit = {
                key: key,
                code: code,
                ctrlKey: spec.ctrl || false,
                altKey: spec.alt || false,
                shiftKey: spec.shift || false,
                metaKey: spec.meta || false,
                bubbles: true,
                cancelable: true,
                composed: true
            };

            // Dispatch keydown
            var keydownEvent = new KeyboardEvent('keydown', eventInit);
            var prevented = !target.dispatchEvent(keydownEvent);

            var handled = false;

            // Handle special keys if not prevented by the page
            if (!prevented) {
                if (key === 'Tab') {
                    handled = handleTab(target, spec.shift);
                } else if (key === 'Enter') {
                    handled = handleEnter(target);
                } else if (key === ' ') {
                    // Space key - special handling (toggles checkboxes, activates buttons)
                    handled = handleSpace(target);
                } else if (key === 'Backspace') {
                    handled = handleBackspace(target);
                } else if (key === 'Delete') {
                    handled = handleDelete(target);
                } else if (key.length === 1 && !spec.ctrl && !spec.alt && !spec.meta) {
                    // Printable character (not Space, handled above)
                    target.dispatchEvent(new KeyboardEvent('keypress', eventInit));
                    handled = handlePrintableChar(target, key);
                }
            }

            // Dispatch keyup
            target.dispatchEvent(new KeyboardEvent('keyup', eventInit));

            keyCount++;
            results.push({
                type: 'key',
                key: key,
                target: describeElement(target),
                prevented: prevented,
                handled: handled
            });

            // Delay between keys (fixed, random, or minimal 10ms)
            var delayMs = getDelayMs();
            setTimeout(processNext, delayMs);
        }

        // Start processing
        if (keySequence.length === 0) {
            resolve({
                ok: true,
                message: 'No keys to press',
                results: []
            });
        } else {
            processNext();
        }
    });
})(KEY_SEQUENCE_PLACEHOLDER, DELAY_CONFIG_PLACEHOLDER)
