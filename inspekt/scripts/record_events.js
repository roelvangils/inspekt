// Record browser events for later replay
// Uses ACTION_PLACEHOLDER pattern: 'start', 'poll', 'stop'
(function() {
    const action = 'ACTION_PLACEHOLDER';
    const config = CONFIG_PLACEHOLDER;

    // ==================== AUDIO MODULE ====================
    // Provides audio feedback during recording (when config.audio is true)

    const RecordAudio = {
        ctx: null,
        initialized: false,
        enabled: false,

        init() {
            if (this.initialized) return this.enabled;
            if (!config.audio) {
                this.enabled = false;
                this.initialized = true;
                return false;
            }

            try {
                this.ctx = new (window.AudioContext || window.webkitAudioContext)();
                this.enabled = true;
                this.initialized = true;
                if (this.ctx.state === 'suspended') {
                    this.ctx.resume();
                }
            } catch (e) {
                console.warn('Inspekt: Web Audio API not available');
                this.enabled = false;
            }
            return this.enabled;
        },

        ensureReady() {
            if (!this.init()) return false;
            if (this.ctx.state === 'suspended') {
                this.ctx.resume();
            }
            return true;
        },

        playTone(frequency, duration, type = 'sine', volume = 0.3, startDelay = 0) {
            if (!this.ensureReady()) return;

            const osc = this.ctx.createOscillator();
            const gain = this.ctx.createGain();

            osc.connect(gain);
            gain.connect(this.ctx.destination);

            osc.frequency.value = frequency;
            osc.type = type;

            const now = this.ctx.currentTime + startDelay;
            gain.gain.setValueAtTime(volume, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + duration);

            osc.start(now);
            osc.stop(now + duration);
        },

        // Recording started - ascending major chord (C4 → E4 → G4)
        playStart() {
            if (!this.ensureReady()) return;
            const notes = [261.63, 329.63, 392.00];
            const noteDuration = 0.12;
            notes.forEach((freq, i) => {
                this.playTone(freq, noteDuration * 1.5, 'sine', 0.25, i * noteDuration);
            });
        },

        // Recording resumed - single rising tone
        playResume() {
            if (!this.ensureReady()) return;
            const osc = this.ctx.createOscillator();
            const gain = this.ctx.createGain();

            osc.connect(gain);
            gain.connect(this.ctx.destination);

            const now = this.ctx.currentTime;
            osc.frequency.setValueAtTime(300, now);
            osc.frequency.exponentialRampToValueAtTime(500, now + 0.15);
            osc.type = 'sine';

            gain.gain.setValueAtTime(0.25, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.2);

            osc.start(now);
            osc.stop(now + 0.2);
        },

        // Recording stopped - descending resolution (B4 → F4 → C4)
        playStop() {
            if (!this.ensureReady()) return;
            const notes = [493.88, 349.23, 261.63];
            const noteDuration = 0.14;
            notes.forEach((freq, i) => {
                this.playTone(freq, noteDuration * 1.8, 'sine', 0.25, i * noteDuration);
            });
        },

        // Recording paused - descending two-note (A4 → E4)
        playPause() {
            if (!this.ensureReady()) return;
            this.playTone(440, 0.1, 'sine', 0.25, 0);     // A4
            this.playTone(330, 0.15, 'sine', 0.25, 0.12); // E4
        },

        // Undo action - quick descending "whoosh"
        playUndo() {
            if (!this.ensureReady()) return;
            this.playTone(600, 0.08, 'sine', 0.25, 0);
            this.playTone(400, 0.1, 'sine', 0.25, 0.06);
        },

        // Redo action - quick ascending "whoosh"
        playRedo() {
            if (!this.ensureReady()) return;
            this.playTone(400, 0.08, 'sine', 0.25, 0);
            this.playTone(600, 0.1, 'sine', 0.25, 0.06);
        }
    };

    // ==================== INDEXEDDB MODULE ====================
    // Persists events to survive page navigation

    const DB_NAME = 'inspekt-recording';
    const STORE_NAME = 'events';

    const EventDB = {
        db: null,

        async init() {
            if (this.db) return this.db;

            return new Promise((resolve, reject) => {
                const request = indexedDB.open(DB_NAME, 1);

                request.onupgradeneeded = (e) => {
                    const db = e.target.result;
                    if (!db.objectStoreNames.contains(STORE_NAME)) {
                        const store = db.createObjectStore(STORE_NAME, { keyPath: 'id', autoIncrement: true });
                        store.createIndex('recordingId', 'recordingId', { unique: false });
                    }
                };

                request.onsuccess = () => {
                    this.db = request.result;
                    resolve(this.db);
                };

                request.onerror = () => {
                    console.warn('Inspekt: IndexedDB not available');
                    reject(request.error);
                };
            });
        },

        async persistEvent(event, recordingId) {
            try {
                const db = await this.init();
                const tx = db.transaction(STORE_NAME, 'readwrite');
                tx.objectStore(STORE_NAME).add({
                    recordingId: recordingId,
                    timestamp: event.timestamp,
                    event: event
                });
            } catch (e) {
                // Silently fail - events are still in memory
            }
        },

        async recoverEvents(recordingId) {
            try {
                const db = await this.init();
                const tx = db.transaction(STORE_NAME, 'readonly');
                const store = tx.objectStore(STORE_NAME);
                const events = [];

                return new Promise((resolve) => {
                    const index = store.index('recordingId');
                    const request = index.openCursor(IDBKeyRange.only(recordingId));

                    request.onsuccess = (e) => {
                        const cursor = e.target.result;
                        if (cursor) {
                            events.push(cursor.value.event);
                            cursor.continue();
                        } else {
                            // Sort by timestamp
                            events.sort((a, b) => a.timestamp - b.timestamp);
                            resolve(events);
                        }
                    };

                    request.onerror = () => resolve([]);
                });
            } catch (e) {
                return [];
            }
        },

        async clearEvents(recordingId) {
            try {
                const db = await this.init();
                const tx = db.transaction(STORE_NAME, 'readwrite');
                const store = tx.objectStore(STORE_NAME);
                const index = store.index('recordingId');
                const request = index.openCursor(IDBKeyRange.only(recordingId));

                request.onsuccess = (e) => {
                    const cursor = e.target.result;
                    if (cursor) {
                        cursor.delete();
                        cursor.continue();
                    }
                };
            } catch (e) {
                // Silently fail
            }
        },

        async clearAll() {
            try {
                const db = await this.init();
                const tx = db.transaction(STORE_NAME, 'readwrite');
                tx.objectStore(STORE_NAME).clear();
            } catch (e) {
                // Silently fail
            }
        }
    };

    // Helper to persist event (called when recording events)
    function persistEventToStorage(event) {
        const recordingId = window.__INSPEKT_RECORD_ID__;
        if (recordingId) {
            EventDB.persistEvent(event, recordingId);
        }
    }

    // Helper to record an event (push to array + persist to IndexedDB)
    // Skips recording when paused (Ctrl+Alt+P)
    function recordEvent(event) {
        // Don't record events while paused
        if (window.__INSPEKT_PAUSED__) {
            return;
        }
        window.__INSPEKT_RECORD_EVENTS__.push(event);
        persistEventToStorage(event);
    }

    // Helper to consume one-shot flags (reads value and resets to false)
    function consumeFlag(name) {
        const value = !!window[name];
        window[name] = false;
        return value;
    }

    // ==================== UTILITY FUNCTIONS ====================

    /**
     * Generate CSS selector path for an element.
     * Stops at element with ID for shorter, more stable selectors.
     */
    function getCSSPath(el) {
        if (!(el instanceof Element)) return '';

        const path = [];
        while (el.nodeType === Node.ELEMENT_NODE) {
            let selector = el.nodeName.toLowerCase();

            if (el.id) {
                selector += '#' + CSS.escape(el.id);
                path.unshift(selector);
                break;
            } else {
                let sibling = el;
                let nth = 1;
                while (sibling.previousElementSibling) {
                    sibling = sibling.previousElementSibling;
                    if (sibling.nodeName.toLowerCase() === selector) nth++;
                }
                if (nth !== 1) selector += ':nth-of-type(' + nth + ')';
            }

            path.unshift(selector);
            el = el.parentNode;
        }

        return path.join(' > ');
    }

    /**
     * Generate multiple selectors for an element, ordered by reliability.
     */
    function generateSelectors(element) {
        const selectors = [];

        // 1. ID selector (highest priority)
        if (element.id) {
            selectors.push('#' + CSS.escape(element.id));
        }

        // 2. data-testid variants (common in React/Vue/testing)
        const testIdAttrs = ['data-testid', 'data-test-id', 'data-cy', 'data-test'];
        for (const attr of testIdAttrs) {
            const value = element.getAttribute(attr);
            if (value) {
                selectors.push(`[${attr}="${CSS.escape(value)}"]`);
                break; // Only add one test ID selector
            }
        }

        // 3. aria-label (good for accessibility-focused selectors)
        const ariaLabel = element.getAttribute('aria-label');
        if (ariaLabel) {
            selectors.push(`[aria-label="${CSS.escape(ariaLabel)}"]`);
        }

        // 4. name attribute (for form elements)
        const name = element.getAttribute('name');
        if (name) {
            selectors.push(`${element.tagName.toLowerCase()}[name="${CSS.escape(name)}"]`);
        }

        // 5. Type-specific selectors
        const tag = element.tagName.toLowerCase();
        if (tag === 'input' && element.type) {
            const type = element.type;
            if (element.placeholder) {
                selectors.push(`input[type="${type}"][placeholder="${CSS.escape(element.placeholder)}"]`);
            }
        }

        // 6. Unique text content for buttons/links
        if (['button', 'a'].includes(tag)) {
            const text = (element.textContent || '').trim();
            if (text && text.length < 50 && !text.includes('\n')) {
                // Can't use text in CSS, but it's useful for fallback strategies
            }
        }

        // 7. CSS path (always include as final fallback)
        const cssPath = getCSSPath(element);
        if (cssPath && !selectors.includes(cssPath)) {
            selectors.push(cssPath);
        }

        // Ensure we have at least one selector
        if (selectors.length === 0) {
            selectors.push(cssPath || tag);
        }

        return selectors;
    }

    /**
     * Check if an element is effectively hidden (not perceivable).
     * Per ACCNAME 1.2: hidden elements should not contribute to accessible name
     * unless referenced by aria-labelledby.
     */
    function isEffectivelyHidden(el) {
        if (!el || el.nodeType !== 1) return true;
        if (el.hidden) return true;
        if (el.getAttribute('aria-hidden') === 'true') return true;

        const style = window.getComputedStyle(el);
        return style.display === 'none' ||
               style.visibility === 'hidden';
    }

    /**
     * Get text content from CSS pseudo-elements (::before, ::after).
     * Per ACCNAME 1.2: pseudo-element content should be included.
     */
    function getPseudoElementText(el) {
        if (!el || el.nodeType !== 1) return '';

        let text = '';

        try {
            const beforeContent = window.getComputedStyle(el, '::before').content;
            if (beforeContent && beforeContent !== 'none' && beforeContent !== 'normal') {
                // CSS content values are quoted strings - remove the quotes
                const beforeText = beforeContent.replace(/^["']|["']$/g, '');
                if (beforeText) text += beforeText + ' ';
            }

            const afterContent = window.getComputedStyle(el, '::after').content;
            if (afterContent && afterContent !== 'none' && afterContent !== 'normal') {
                const afterText = afterContent.replace(/^["']|["']$/g, '');
                if (afterText) text += ' ' + afterText;
            }
        } catch (e) {
            // getComputedStyle may fail in some edge cases
        }

        return text.trim();
    }

    /**
     * Compute the accessible name for an element following ARIA specification.
     */
    function computeAccessibleName(el, visited = new Set()) {
        if (!el || el.nodeType !== 1) return '';

        // Prevent infinite recursion
        if (visited.has(el)) return '';
        visited.add(el);

        // aria-labelledby (highest priority)
        const labelledBy = el.getAttribute('aria-labelledby');
        if (labelledBy) {
            const ids = labelledBy.trim().split(/\s+/);
            const labels = ids.map(id => {
                const labelEl = document.getElementById(id);
                return labelEl ? computeAccessibleName(labelEl, visited) || labelEl.textContent.trim() : '';
            }).filter(text => text);
            if (labels.length > 0) {
                return labels.join(' ');
            }
        }

        // aria-label
        const ariaLabel = el.getAttribute('aria-label');
        if (ariaLabel && ariaLabel.trim()) {
            return ariaLabel.trim();
        }

        const tagName = el.tagName.toLowerCase();

        // For form controls: associated <label> element
        if (['input', 'select', 'textarea'].includes(tagName) && el.id) {
            const label = document.querySelector(`label[for="${el.id}"]`);
            if (label) {
                return computeAccessibleName(label, visited) || label.textContent.trim();
            }
        }

        // For input type="button/submit/reset": value attribute
        if (tagName === 'input' && ['button', 'submit', 'reset'].includes(el.type)) {
            const value = el.getAttribute('value');
            if (value) return value;
        }

        // For img/area: alt attribute
        if (['img', 'area'].includes(tagName)) {
            const alt = el.getAttribute('alt');
            if (alt) return alt;
        }

        // For input type="image": alt attribute
        if (tagName === 'input' && el.type === 'image') {
            const alt = el.getAttribute('alt');
            if (alt) return alt;
        }

        // For SVG: <title> child element
        if (tagName === 'svg') {
            const titleEl = el.querySelector('title');
            if (titleEl) return titleEl.textContent.trim();
        }

        // For buttons/links: compute name from content (recursive)
        if (['button', 'a'].includes(tagName)) {
            const name = computeAccessibleNameFromContent(el, visited);
            if (name && name.length < 200) return name;
        }

        // title attribute (fallback)
        const title = el.getAttribute('title');
        if (title && title.trim()) {
            return title.trim();
        }

        // placeholder (for inputs)
        if (['input', 'textarea'].includes(tagName)) {
            const placeholder = el.getAttribute('placeholder');
            if (placeholder && placeholder.trim()) {
                return placeholder.trim();
            }
        }

        return '';
    }

    /**
     * Recursively compute accessible name from element content.
     * This handles cases like <a><img alt="Name"></a> where the name
     * comes from child elements rather than text content.
     * Per ACCNAME 1.2: includes pseudo-element content and embedded control values.
     */
    function computeAccessibleNameFromContent(el, visited = new Set()) {
        if (!el) return '';

        const parts = [];

        // Include ::before pseudo-element content
        const beforeText = getPseudoElementText(el).split(' ')[0]; // Get just the before part
        const beforeContent = window.getComputedStyle(el, '::before').content;
        if (beforeContent && beforeContent !== 'none' && beforeContent !== 'normal') {
            const beforeStr = beforeContent.replace(/^["']|["']$/g, '');
            if (beforeStr) parts.push(beforeStr);
        }

        // Process child nodes
        for (const child of el.childNodes) {
            if (child.nodeType === Node.TEXT_NODE) {
                // Text node - add trimmed text
                const text = child.textContent.trim();
                if (text) parts.push(text);
            } else if (child.nodeType === Node.ELEMENT_NODE) {
                // Element node - check for accessible name
                const childTag = child.tagName.toLowerCase();

                // Skip hidden elements (using comprehensive check)
                if (isEffectivelyHidden(child)) {
                    continue;
                }

                // Check for aria-label first
                const childAriaLabel = child.getAttribute('aria-label');
                if (childAriaLabel && childAriaLabel.trim()) {
                    parts.push(childAriaLabel.trim());
                    continue;
                }

                // img/area - use alt
                if (['img', 'area'].includes(childTag)) {
                    const alt = child.getAttribute('alt');
                    if (alt) parts.push(alt);
                    continue;
                }

                // svg - use title child
                if (childTag === 'svg') {
                    const titleEl = child.querySelector('title');
                    if (titleEl) {
                        parts.push(titleEl.textContent.trim());
                        continue;
                    }
                }

                // input type="image" - use alt
                if (childTag === 'input' && child.type === 'image') {
                    const alt = child.getAttribute('alt');
                    if (alt) parts.push(alt);
                    continue;
                }

                // Embedded form controls - use their value per ACCNAME 1.2
                if (childTag === 'input' && !['hidden', 'image'].includes(child.type)) {
                    const value = child.value;
                    if (value) parts.push(value);
                    continue;
                }

                if (childTag === 'select') {
                    const selectedOption = child.options[child.selectedIndex];
                    if (selectedOption) {
                        parts.push(selectedOption.text);
                    }
                    continue;
                }

                if (childTag === 'textarea') {
                    const value = child.value;
                    if (value) parts.push(value);
                    continue;
                }

                // Recurse into other elements
                const childName = computeAccessibleNameFromContent(child, visited);
                if (childName) parts.push(childName);
            }
        }

        // Include ::after pseudo-element content
        const afterContent = window.getComputedStyle(el, '::after').content;
        if (afterContent && afterContent !== 'none' && afterContent !== 'normal') {
            const afterStr = afterContent.replace(/^["']|["']$/g, '');
            if (afterStr) parts.push(afterStr);
        }

        return parts.join(' ').trim();
    }

    /**
     * Get all focusable elements on the page in tab order.
     * Used to manually handle Tab navigation for media elements.
     */
    function getFocusableElements() {
        const selector = [
            'a[href]',
            'button:not([disabled])',
            'input:not([disabled]):not([type="hidden"])',
            'select:not([disabled])',
            'textarea:not([disabled])',
            '[tabindex]:not([tabindex="-1"])',
            '[contenteditable="true"]',
            'audio[controls]',
            'video[controls]'
        ].join(', ');

        const elements = Array.from(document.querySelectorAll(selector));

        // Filter out hidden elements and sort by tabindex
        return elements.filter(el => {
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') {
                return false;
            }
            if (el.offsetParent === null && style.position !== 'fixed') {
                return false;
            }
            return true;
        }).sort((a, b) => {
            const tabA = parseInt(a.getAttribute('tabindex') || '0', 10);
            const tabB = parseInt(b.getAttribute('tabindex') || '0', 10);
            if (tabA > 0 && tabB > 0) return tabA - tabB;
            if (tabA > 0) return -1;
            if (tabB > 0) return 1;
            return 0;
        });
    }

    /**
     * Check if an element is a media element (audio/video with controls).
     */
    function isMediaElement(element) {
        if (!element) return false;
        const tag = element.tagName.toLowerCase();
        return (tag === 'audio' || tag === 'video') && element.hasAttribute('controls');
    }

    /**
     * Check if an element is a native control input with closed Shadow DOM.
     * These inputs have complex internal controls (sliders, date pickers, etc.)
     * that use closed Shadow DOM - they cannot be accessed by JavaScript.
     */
    function isNativeControlInput(element) {
        if (!element || element.tagName !== 'INPUT') return false;
        const type = (element.type || '').toLowerCase();
        return ['range', 'date', 'time', 'datetime-local', 'month', 'week', 'number', 'color'].includes(type);
    }

    /**
     * Check if an element is ANY native control (media OR input with closed Shadow DOM).
     */
    function isNativeControl(element) {
        return isMediaElement(element) || isNativeControlInput(element);
    }

    // Track interaction state for native controls (media elements and native inputs)
    // Interaction keypresses are handled silently via APIs, not recorded.
    // Only the final value is recorded when the user tabs away.
    let nativeControlState = {
        element: null,
        initialValue: null,
        isInteracting: false
    };

    /**
     * Get the current value of a native control (for tracking changes).
     */
    function getNativeControlValue(element) {
        if (isMediaElement(element)) {
            // For media: track playback state (paused, currentTime, volume, muted)
            return JSON.stringify({
                paused: element.paused,
                currentTime: Math.round(element.currentTime),
                volume: Math.round(element.volume * 100),
                muted: element.muted
            });
        } else if (isNativeControlInput(element)) {
            return element.value;
        }
        return null;
    }

    /**
     * Handle interaction keypresses on native controls silently.
     * Uses the API to change state but does NOT record the keypress.
     * Returns true if the key was handled, false otherwise.
     */
    function handleNativeControlKeypress(element, event) {
        const key = event.key;

        // Start tracking if not already
        if (!nativeControlState.isInteracting || nativeControlState.element !== element) {
            nativeControlState = {
                element: element,
                initialValue: getNativeControlValue(element),
                isInteracting: true
            };
        }

        // Media element handling
        if (isMediaElement(element)) {
            // Space or Enter: toggle play/pause
            if (key === ' ' || key === 'Enter') {
                event.preventDefault();
                if (element.paused) {
                    element.play();
                } else {
                    element.pause();
                }
                return true;
            }

            // Arrow keys: seek and volume
            if (key === 'ArrowRight') {
                event.preventDefault();
                element.currentTime = Math.min(element.duration || 0, element.currentTime + 5);
                return true;
            }
            if (key === 'ArrowLeft') {
                event.preventDefault();
                element.currentTime = Math.max(0, element.currentTime - 5);
                return true;
            }
            if (key === 'ArrowUp') {
                event.preventDefault();
                element.volume = Math.min(1, element.volume + 0.1);
                return true;
            }
            if (key === 'ArrowDown') {
                event.preventDefault();
                element.volume = Math.max(0, element.volume - 0.1);
                return true;
            }

            // M: toggle mute
            if (key === 'm' || key === 'M') {
                event.preventDefault();
                element.muted = !element.muted;
                return true;
            }

            return false;
        }

        // Native input handling
        if (isNativeControlInput(element)) {
            const type = element.type.toLowerCase();

            // Arrow keys: step up/down
            if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(key)) {
                event.preventDefault();

                if (type === 'range') {
                    // Range: left/down = stepDown, right/up = stepUp
                    if (key === 'ArrowUp' || key === 'ArrowRight') {
                        element.stepUp();
                    } else {
                        element.stepDown();
                    }
                } else if (type === 'number') {
                    // Number: up = stepUp, down = stepDown (left/right move cursor)
                    if (key === 'ArrowUp') {
                        element.stepUp();
                    } else if (key === 'ArrowDown') {
                        element.stepDown();
                    } else {
                        // Left/Right navigate within the field - don't intercept
                        return false;
                    }
                } else if (['date', 'time', 'datetime-local', 'month', 'week'].includes(type)) {
                    // Date/time inputs: up/right = stepUp, down/left = stepDown
                    if (key === 'ArrowUp' || key === 'ArrowRight') {
                        element.stepUp();
                    } else {
                        element.stepDown();
                    }
                }

                // Dispatch input event so page reacts
                element.dispatchEvent(new Event('input', { bubbles: true }));
                return true;
            }

            // Home/End for range inputs
            if (type === 'range' && (key === 'Home' || key === 'End')) {
                event.preventDefault();
                const min = parseFloat(element.min) || 0;
                const max = parseFloat(element.max) || 100;
                element.value = key === 'Home' ? min : max;
                element.dispatchEvent(new Event('input', { bubbles: true }));
                return true;
            }

            // PageUp/PageDown for range inputs (larger steps)
            if (type === 'range' && (key === 'PageUp' || key === 'PageDown')) {
                event.preventDefault();
                const step = parseFloat(element.step) || 1;
                const bigStep = step * 10;
                const current = parseFloat(element.value) || 0;
                const min = parseFloat(element.min) || 0;
                const max = parseFloat(element.max) || 100;

                if (key === 'PageUp') {
                    element.value = Math.min(max, current + bigStep);
                } else {
                    element.value = Math.max(min, current - bigStep);
                }
                element.dispatchEvent(new Event('input', { bubbles: true }));
                return true;
            }

            return false;
        }

        return false;
    }

    /**
     * Record the final value of a native control when interaction ends.
     * Called when user tabs away or element loses focus.
     */
    function flushNativeControlState() {
        if (!nativeControlState.isInteracting || !nativeControlState.element) {
            return;
        }

        const element = nativeControlState.element;
        const currentValue = getNativeControlValue(element);

        // Only record if value actually changed
        if (currentValue !== nativeControlState.initialValue) {
            if (isNativeControlInput(element)) {
                // Record as a 'set' action with the final value and input type
                const inputType = (element.type || '').toLowerCase();
                const targetInfo = getTargetInfo(element);
                targetInfo.input_type = inputType;

                recordEvent({
                    action: 'set',
                    timestamp: getTimestamp(),
                    target: targetInfo,
                    value: element.value
                });
            }
            // Note: We don't record media state changes as they're ephemeral
            // and don't affect replay (media always starts fresh)
        }

        // Reset state
        nativeControlState = { element: null, initialValue: null, isInteracting: false };
    }

    /**
     * Check if an element is interactive (for hover filtering).
     */
    function isInteractiveElement(element) {
        const interactiveTags = ['a', 'button', 'input', 'select', 'textarea', 'details', 'summary'];
        const tag = element.tagName.toLowerCase();

        if (interactiveTags.includes(tag)) return true;

        // Check for interactive roles
        const role = element.getAttribute('role');
        const interactiveRoles = ['button', 'link', 'menuitem', 'tab', 'checkbox', 'radio', 'option', 'switch'];
        if (role && interactiveRoles.includes(role)) return true;

        // Check for click handlers or tabindex
        if (element.getAttribute('onclick') || element.getAttribute('tabindex') !== null) return true;

        // Check for cursor: pointer style
        const style = window.getComputedStyle(element);
        if (style.cursor === 'pointer') return true;

        return false;
    }

    /**
     * Get Shadow DOM information for an element.
     * Returns info about whether element is inside a Shadow DOM and its host.
     */
    function getShadowDOMInfo(element) {
        if (!element || element.nodeType !== 1) {
            return { inShadowDOM: false };
        }

        const rootNode = element.getRootNode();

        // Check if element is inside a Shadow DOM
        if (rootNode instanceof ShadowRoot) {
            const host = rootNode.host;
            // Generate a selector for the shadow host
            const hostSelectors = generateSelectors(host);

            return {
                inShadowDOM: true,
                shadowHost: hostSelectors[0],
                shadowHostFallbacks: hostSelectors.slice(1, 3),
                shadowMode: rootNode.mode  // 'open' or 'closed'
            };
        }

        return { inShadowDOM: false };
    }

    /**
     * Generate a piercing selector for Shadow DOM elements.
     * Format: "hostSelector >>> innerSelector"
     */
    function generatePiercingSelector(element, shadowInfo) {
        if (!shadowInfo.inShadowDOM) {
            return null;
        }

        // Get selectors for the inner element (within shadow root)
        const innerSelectors = generateSelectors(element);
        const innerSelector = innerSelectors[0];

        // Combine with shadow host selector
        return `${shadowInfo.shadowHost} >>> ${innerSelector}`;
    }

    /**
     * Get target information for an element.
     */
    function getTargetInfo(element) {
        const selectors = generateSelectors(element);
        const text = (element.textContent || '').trim().substring(0, 100);

        // Check if element is inside Shadow DOM
        const shadowInfo = getShadowDOMInfo(element);

        const targetInfo = {
            selector: selectors[0],
            fallback_selectors: selectors.slice(1, 4), // Keep up to 3 fallbacks
            text: text || null,
            accessible_name: computeAccessibleName(element) || null,
            tag: element.tagName.toLowerCase(),
            role: element.getAttribute('role') || null
        };

        // Add Shadow DOM info if element is inside a shadow root
        if (shadowInfo.inShadowDOM) {
            targetInfo.shadow_host = shadowInfo.shadowHost;
            targetInfo.piercing_selector = generatePiercingSelector(element, shadowInfo);
        }

        return targetInfo;
    }

    /**
     * Get the current timestamp relative to recording start.
     */
    function getTimestamp() {
        return Date.now() - window.__INSPEKT_RECORD_START__;
    }

    // ==================== EVENT HANDLERS ====================

    // Click deduplication state - prevents recording both pointerdown and click
    let lastClickRecord = {
        element: null,
        timestamp: 0
    };

    const CLICK_DEDUP_THRESHOLD = 500; // ms - ignore duplicate clicks within this window

    function recordClick(element, event, source) {
        // Flush any pending native control state before processing new click
        // This captures the value when user clicks away from a native control
        if (nativeControlState.isInteracting && nativeControlState.element !== element) {
            flushNativeControlState();
        }

        // Skip clicks on summary elements inside details
        // The toggle event on the details element handles this more accurately
        if (element.tagName === 'SUMMARY' || element.closest('summary')) {
            return;
        }

        // Skip clicks on native control inputs (range, date, time, color, etc.)
        // Only the final value matters, captured by the 'set' action when tabbing away
        // But DO initialize tracking state so we capture the value on blur/Tab
        if (isNativeControlInput(element)) {
            // Start tracking this native control if not already
            if (!nativeControlState.isInteracting || nativeControlState.element !== element) {
                nativeControlState = {
                    element: element,
                    initialValue: getNativeControlValue(element),
                    isInteracting: true
                };
            }
            return;
        }

        const timestamp = getTimestamp();

        // Check for duplicate (same element within threshold)
        if (lastClickRecord.element === element &&
            (timestamp - lastClickRecord.timestamp) < CLICK_DEDUP_THRESHOLD) {
            return; // Skip duplicate
        }

        // Update dedup state
        lastClickRecord = { element, timestamp };

        // Detect keyboard activation vs mouse click
        // - pointerdown/mousedown are ALWAYS physical interactions → "click"
        // - click event with detail === 0 means keyboard activation (Enter/Space) → "activate"
        // - click event with detail >= 1 means mouse click → "click"
        const isKeyboardActivation = (source === 'click' && event.detail === 0);

        // Get target info (includes selector, fallback_selectors, text, etc.)
        const targetInfo = getTargetInfo(element);

        // For mouse clicks, capture additional info for robust replay
        let clickAt = null;

        if (!isKeyboardActivation) {
            const elementUnderCursor = document.elementFromPoint(event.clientX, event.clientY);

            // If cursor is over a different element (e.g., SVG child), add its selector to fallbacks
            if (elementUnderCursor && elementUnderCursor !== element) {
                const cursorSelectors = generateSelectors(elementUnderCursor);
                // Merge cursor element's selector into fallbacks (avoid duplicates)
                const existingFallbacks = targetInfo.fallback_selectors || [];
                const cursorSelector = cursorSelectors[0];
                if (cursorSelector && !existingFallbacks.includes(cursorSelector)) {
                    targetInfo.fallback_selectors = [...existingFallbacks, cursorSelector];
                }
            }

            // Calculate click position as percentages within the element
            // This is more resilient than absolute coordinates across viewports
            const targetElement = elementUnderCursor || element;
            const rect = targetElement.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0) {
                clickAt = [
                    Math.round(((event.clientX - rect.left) / rect.width) * 100),
                    Math.round(((event.clientY - rect.top) / rect.height) * 100)
                ];
            }
        }

        const eventData = {
            action: isKeyboardActivation ? 'activate' : 'click',
            timestamp: timestamp,
            target: targetInfo
        };

        // Add click_at for mouse clicks (position as [x%, y%] within element)
        if (clickAt) {
            eventData.click_at = clickAt;
        }

        recordEvent(eventData);
    }

    function handleClick(event) {
        // Primary button only (left click)
        if (event.button !== 0) return;
        // Use composedPath() to get actual target through Shadow DOM boundaries
        const realTarget = event.composedPath()[0] || event.target;
        recordClick(realTarget, event, 'click');
    }

    function handleToggle(event) {
        // Handle toggle events on details elements
        const details = event.target;
        if (details.tagName !== 'DETAILS') return;

        const timestamp = getTimestamp();
        const summary = details.querySelector('summary');
        const targetElement = summary || details;
        const targetInfo = getTargetInfo(targetElement);

        const eventData = {
            action: 'toggle',
            timestamp: timestamp,
            target: targetInfo,
            value: details.open ? 'open' : 'closed'
        };

        recordEvent(eventData);
    }

    function handleContextMenu(event) {
        // Right click (button === 2)
        // Use composedPath() to get actual target through Shadow DOM boundaries
        const element = event.composedPath()[0] || event.target;

        // Skip right-clicks on native control inputs
        if (isNativeControlInput(element)) {
            return;
        }

        const timestamp = getTimestamp();
        const targetInfo = getTargetInfo(element);

        // Check if cursor is over a different element and add to fallbacks
        const elementUnderCursor = document.elementFromPoint(event.clientX, event.clientY);
        if (elementUnderCursor && elementUnderCursor !== element) {
            const cursorSelectors = generateSelectors(elementUnderCursor);
            const existingFallbacks = targetInfo.fallback_selectors || [];
            const cursorSelector = cursorSelectors[0];
            if (cursorSelector && !existingFallbacks.includes(cursorSelector)) {
                targetInfo.fallback_selectors = [...existingFallbacks, cursorSelector];
            }
        }

        // Calculate click position as percentages
        const targetElement = elementUnderCursor || element;
        const rect = targetElement.getBoundingClientRect();
        let clickAt = null;
        if (rect.width > 0 && rect.height > 0) {
            clickAt = [
                Math.round(((event.clientX - rect.left) / rect.width) * 100),
                Math.round(((event.clientY - rect.top) / rect.height) * 100)
            ];
        }

        const eventData = {
            action: 'rightclick',
            timestamp: timestamp,
            target: targetInfo
        };

        if (clickAt) {
            eventData.click_at = clickAt;
        }

        recordEvent(eventData);
    }

    function handlePointerDown(event) {
        // Primary button only (left click/touch)
        if (event.button !== 0) return;
        // Use composedPath() to get actual target through Shadow DOM boundaries
        const realTarget = event.composedPath()[0] || event.target;

        // Flush any pending native control state when clicking on a DIFFERENT element
        // This must happen BEFORE we capture new initial value or process the click
        if (nativeControlState.isInteracting && nativeControlState.element !== realTarget) {
            flushNativeControlState();
        }

        // For native controls: capture initial value BEFORE the click changes it
        if (isNativeControlInput(realTarget)) {
            if (!nativeControlState.isInteracting || nativeControlState.element !== realTarget) {
                nativeControlState = {
                    element: realTarget,
                    initialValue: getNativeControlValue(realTarget),
                    isInteracting: true
                };
            }
        }

        recordClick(realTarget, event, 'pointerdown');
    }

    function handleMouseDown(event) {
        // Primary button only
        if (event.button !== 0) return;
        // Use composedPath() to get actual target through Shadow DOM boundaries
        const realTarget = event.composedPath()[0] || event.target;

        // Flush any pending native control state when clicking on a DIFFERENT element
        // This must happen BEFORE we capture new initial value or process the click
        if (nativeControlState.isInteracting && nativeControlState.element !== realTarget) {
            flushNativeControlState();
        }

        // For native controls: capture initial value BEFORE the click changes it
        if (isNativeControlInput(realTarget)) {
            if (!nativeControlState.isInteracting || nativeControlState.element !== realTarget) {
                nativeControlState = {
                    element: realTarget,
                    initialValue: getNativeControlValue(realTarget),
                    isInteracting: true
                };
            }
        }

        recordClick(realTarget, event, 'mousedown');
    }

    // Track typing in input fields
    let typingState = {
        element: null,
        startValue: '',
        startTime: 0,
        lastTime: 0
    };

    /**
     * Check if an element is a text-like input that should use "type" action.
     */
    function isTextInput(element) {
        const tag = element.tagName.toLowerCase();

        if (tag === 'textarea') return true;
        if (element.isContentEditable) return true;

        if (tag === 'input') {
            const type = (element.type || 'text').toLowerCase();
            // These input types accept text input
            const textTypes = ['text', 'password', 'email', 'search', 'tel', 'url', 'number', 'date', 'time', 'datetime-local', 'month', 'week'];
            return textTypes.includes(type);
        }

        return false;
    }

    function flushTypingBuffer() {
        if (!typingState.element) return;

        const currentValue = typingState.element.value || typingState.element.textContent || '';

        // Only record if value actually changed
        if (currentValue !== typingState.startValue) {
            const isPassword = typingState.element.type === 'password';
            const config = window.__INSPEKT_RECORD_CONFIG__ || {};

            recordEvent({
                action: 'type',
                timestamp: typingState.startTime,
                target: getTargetInfo(typingState.element),
                value: (isPassword && config.maskPasswords !== false) ? '\u2022'.repeat(8) : currentValue,
                sensitive: isPassword
            });
        }

        typingState = { element: null, startValue: '', startTime: 0, lastTime: 0 };
    }

    function handleInput(event) {
        // Use composedPath to get actual target (works with Shadow DOM)
        const element = event.composedPath()[0] || event.target;
        const now = getTimestamp();

        // Only track text-like inputs with the typing buffer
        // Radio, checkbox, and select are handled by handleChange
        if (!isTextInput(element)) {
            return;
        }

        // Skip native control inputs - they're handled by nativeControlState
        // and only recorded when the user tabs away (not on a timer)
        if (isNativeControlInput(element)) {
            return;
        }

        // Check if this is a new element or enough time has passed
        if (typingState.element !== element) {
            // Flush previous typing
            flushTypingBuffer();

            // Start new buffer
            typingState = {
                element: element,
                startValue: '', // Will capture final value
                startTime: now,
                lastTime: now
            };
        } else {
            typingState.lastTime = now;
        }
    }

    /**
     * Handle file upload - reads file contents as base64 and records upload action.
     * Small files (≤100KB) have content embedded; large files are marked for external storage.
     */
    const FILE_SIZE_THRESHOLD = 100 * 1024;  // 100KB

    function handleFileUpload(element, timestamp) {
        if (!element.files || element.files.length === 0) return;

        const files = Array.from(element.files);
        const filePromises = files.map(file => {
            return new Promise((resolve) => {
                const fileInfo = {
                    name: file.name,
                    type: file.type || 'application/octet-stream',
                    size: file.size,
                    lastModified: file.lastModified
                };

                const reader = new FileReader();
                reader.onload = () => {
                    fileInfo.content = reader.result;
                    // Mark large files for external storage (Python will save them separately)
                    if (file.size > FILE_SIZE_THRESHOLD) {
                        fileInfo.needs_external_storage = true;
                    }
                    resolve(fileInfo);
                };
                reader.onerror = () => {
                    // On error, record file metadata without content
                    fileInfo.error = 'Failed to read file';
                    resolve(fileInfo);
                };
                reader.readAsDataURL(file);
            });
        });

        Promise.all(filePromises).then(fileInfos => {
            recordEvent({
                action: 'upload',
                timestamp: timestamp,
                target: getTargetInfo(element),
                files: fileInfos
            });
        });
    }

    /**
     * Handle change events for radio, checkbox, and select elements.
     * Uses composedPath() to get the actual target element inside Shadow DOM.
     */
    function handleChange(event) {
        // Use composedPath to get actual target (works with Shadow DOM)
        const element = event.composedPath()[0] || event.target;
        const tag = element.tagName.toLowerCase();
        const now = getTimestamp();

        if (tag === 'input') {
            const type = (element.type || '').toLowerCase();

            if (type === 'checkbox') {
                // Checkbox: record check or uncheck
                recordEvent({
                    action: element.checked ? 'check' : 'uncheck',
                    timestamp: now,
                    target: getTargetInfo(element),
                    value: element.value || null
                });
                return;
            }

            if (type === 'radio') {
                // Radio: record radio action (radios can only be checked, not unchecked directly)
                recordEvent({
                    action: 'radio',
                    timestamp: now,
                    target: getTargetInfo(element),
                    value: element.value || null
                });
                return;
            }

            if (type === 'file') {
                // File input: read file contents and record upload action
                handleFileUpload(element, now);
                return;
            }
        }

        if (tag === 'select') {
            // Select: record the selected option(s)
            const isMultiple = element.multiple;
            let selectedValues = [];
            let selectedTexts = [];

            for (const option of element.selectedOptions) {
                selectedValues.push(option.value);
                selectedTexts.push(option.text);
            }

            recordEvent({
                action: 'select',
                timestamp: now,
                target: getTargetInfo(element),
                value: isMultiple ? selectedValues : selectedValues[0],
                option_text: isMultiple ? selectedTexts : selectedTexts[0]
            });
            return;
        }
    }

    function handleKeyDown(event) {
        const now = getTimestamp();
        const currentElement = document.activeElement;

        // =====================================================================
        // Recording Control Shortcuts (Pause, Undo, Redo)
        // Using Ctrl+Shift+key pattern (works on both macOS and Windows)
        // Note: Ctrl+Alt doesn't work on macOS because Alt/Option is for special characters
        // =====================================================================
        if (event.ctrlKey && event.shiftKey && !event.altKey && !event.metaKey) {
            // Pause toggle: Ctrl+Shift+P
            if (event.key === 'p' || event.key === 'P') {
                event.preventDefault();
                event.stopPropagation();

                // Flush any pending typing BEFORE toggling pause
                flushTypingBuffer();

                window.__INSPEKT_PAUSE_TOGGLED__ = true;
                window.__INSPEKT_PAUSED__ = !window.__INSPEKT_PAUSED__;

                // Play appropriate sound
                if (window.__INSPEKT_PAUSED__) {
                    RecordAudio.playPause();
                } else {
                    RecordAudio.playResume();
                }
                return; // Don't record this keypress
            }

            // Undo: Ctrl+Shift+Z
            if (event.key === 'z' || event.key === 'Z') {
                event.preventDefault();
                event.stopPropagation();
                window.__INSPEKT_UNDO_REQUESTED__ = true;
                RecordAudio.playUndo();
                return; // Don't record this keypress
            }

            // Redo: Ctrl+Shift+Y
            if (event.key === 'y' || event.key === 'Y') {
                event.preventDefault();
                event.stopPropagation();
                window.__INSPEKT_REDO_REQUESTED__ = true;
                RecordAudio.playRedo();
                return; // Don't record this keypress
            }
        }

        // Check for Ctrl+C - this is the stop recording signal
        if (event.key === 'c' && event.ctrlKey && !event.metaKey && !event.altKey) {
            // Set stop flag - Python will detect this on next poll
            window.__INSPEKT_STOP_REQUESTED__ = true;
            // Prevent default copy behavior during recording
            event.preventDefault();
            event.stopPropagation();
            // Sound is played by Python cleanup (via __INSPEKT_VISUAL__.audio.playStop)
            return;
        }

        // =====================================================================
        // Native Control Interaction Keys (handled silently - NOT recorded)
        // =====================================================================
        // When focused on a native control (media or input with closed Shadow DOM),
        // interaction keypresses (Space, arrows, etc.) use the API to change state
        // but are NEVER recorded. Only the final value is recorded on Tab/blur.

        if (isNativeControl(currentElement) && event.key !== 'Tab') {
            // Try to handle the keypress via the native control handler
            // If handled, return early without recording
            if (handleNativeControlKeypress(currentElement, event)) {
                return; // Handled silently - no recording
            }
        }

        // Check if this is a special key
        const isSpecialKey = event.key === 'Enter' || event.key === 'Tab' ||
                            event.key === 'Escape' || event.key.startsWith('Arrow') ||
                            event.key === 'Backspace' || event.key === 'Delete' ||
                            event.key === 'Home' || event.key === 'End' ||
                            event.key === 'PageUp' || event.key === 'PageDown' ||
                            event.ctrlKey || event.metaKey || event.altKey;

        if (isSpecialKey) {
            // Flush any pending typing first
            flushTypingBuffer();

            // Build modifiers array
            const modifiers = [];
            if (event.ctrlKey) modifiers.push('ctrl');
            if (event.metaKey) modifiers.push('meta');
            if (event.altKey) modifiers.push('alt');
            if (event.shiftKey) modifiers.push('shift');

            // Don't record lone modifier key presses
            if (['Control', 'Meta', 'Alt', 'Shift'].includes(event.key)) {
                return;
            }

            const keypressEvent = {
                action: 'keypress',
                timestamp: now,
                key: event.key,
                modifiers: modifiers
            };

            // For Tab/Shift-Tab, capture the element that receives focus
            // We record inside the RAF to ensure we capture the correct target
            // even when tabbing rapidly
            if (event.key === 'Tab') {
                // =====================================================================
                // Native Control Tab Handling (single tab stop)
                // =====================================================================
                // Native controls (media elements and inputs with closed Shadow DOM)
                // are treated as single tab stops. We intercept Tab and manually move
                // focus to prevent getting stuck in the closed Shadow DOM.

                if (isNativeControl(currentElement)) {
                    event.preventDefault();
                    event.stopPropagation();

                    // Flush any pending native control state (record final value if changed)
                    flushNativeControlState();

                    const focusable = getFocusableElements();
                    const currentIndex = focusable.indexOf(currentElement);
                    let nextIndex;

                    if (modifiers.includes('shift')) {
                        // Shift+Tab: go backwards
                        nextIndex = currentIndex <= 0 ? focusable.length - 1 : currentIndex - 1;
                    } else {
                        // Tab: go forwards
                        nextIndex = currentIndex >= focusable.length - 1 ? 0 : currentIndex + 1;
                    }

                    const nextElement = focusable[nextIndex];
                    if (nextElement) {
                        nextElement.focus();
                        // Record with the new focused element as target
                        const selectors = generateSelectors(nextElement);
                        const targetTag = nextElement.tagName.toLowerCase();
                        keypressEvent.target = {
                            selector: selectors[0],
                            fallback_selectors: selectors.slice(1, 4),
                            accessible_name: computeAccessibleName(nextElement) || null,
                            tag: targetTag,
                            role: nextElement.getAttribute('role') || null
                        };
                        // Include input type for native control inputs
                        if (targetTag === 'input' && nextElement.type) {
                            keypressEvent.target.input_type = nextElement.type.toLowerCase();
                        }
                    }
                    recordEvent(keypressEvent);
                    return;
                }

                // =====================================================================
                // Shift+Tab to Native Control (prevent focus entering Shadow DOM)
                // =====================================================================
                // When Shift+Tab would move focus to a native control, intercept and
                // focus the element directly instead of its internal controls.

                if (modifiers.includes('shift')) {
                    const focusable = getFocusableElements();
                    const currentIndex = focusable.indexOf(currentElement);
                    const prevIndex = currentIndex <= 0 ? focusable.length - 1 : currentIndex - 1;
                    const prevElement = focusable[prevIndex];

                    if (prevElement && isNativeControl(prevElement)) {
                        // Intercept: focus the native control directly
                        event.preventDefault();
                        event.stopPropagation();

                        prevElement.focus();
                        const selectors = generateSelectors(prevElement);
                        const targetTag = prevElement.tagName.toLowerCase();
                        keypressEvent.target = {
                            selector: selectors[0],
                            fallback_selectors: selectors.slice(1, 4),
                            accessible_name: null,  // Will show "Native X" in display
                            tag: targetTag,
                            role: prevElement.getAttribute('role') || null
                        };
                        // Include input type for native control inputs
                        if (targetTag === 'input' && prevElement.type) {
                            keypressEvent.target.input_type = prevElement.type.toLowerCase();
                        }
                        recordEvent(keypressEvent);
                        return;
                    }
                }

                // Normal Tab handling (non-native-control elements)
                requestAnimationFrame(() => {
                    const focusedElement = document.activeElement;
                    if (focusedElement && focusedElement !== document.body) {
                        const selectors = generateSelectors(focusedElement);
                        const targetTag = focusedElement.tagName.toLowerCase();
                        keypressEvent.target = {
                            selector: selectors[0],
                            fallback_selectors: selectors.slice(1, 4),
                            accessible_name: computeAccessibleName(focusedElement) || null,
                            tag: targetTag,
                            role: focusedElement.getAttribute('role') || null
                        };
                        // Include input type for input elements
                        if (targetTag === 'input' && focusedElement.type) {
                            keypressEvent.target.input_type = focusedElement.type.toLowerCase();
                        }
                    }
                    // Record after capturing target (fixes race condition with rapid tabbing)
                    recordEvent(keypressEvent);
                });
            } else {
                // Other special keys: record immediately
                recordEvent(keypressEvent);
            }
        }
    }

    // Hover tracking state
    let hoverState = {
        element: null,
        enterTime: 0,
        timeout: null
    };

    function handleMouseEnter(event) {
        // Use composedPath to get actual target (works with Shadow DOM)
        const element = event.composedPath()[0] || event.target;
        const config = window.__INSPEKT_RECORD_CONFIG__ || {};

        // Skip hover on native control inputs
        if (isNativeControlInput(element)) {
            return;
        }

        // Only track hover on interactive elements
        if (!config.includeHover || !isInteractiveElement(element)) {
            return;
        }

        // Clear any pending hover
        if (hoverState.timeout) {
            clearTimeout(hoverState.timeout);
        }

        hoverState = {
            element: element,
            enterTime: getTimestamp(),
            timeout: null
        };
    }

    function handleMouseLeave(event) {
        // Use composedPath to get actual target (works with Shadow DOM)
        const element = event.composedPath()[0] || event.target;
        const config = window.__INSPEKT_RECORD_CONFIG__ || {};
        const minDuration = config.minHoverDuration || 200;

        if (hoverState.element !== element) {
            return;
        }

        const duration = getTimestamp() - hoverState.enterTime;

        // Only record if hover lasted long enough
        if (duration >= minDuration) {
            recordEvent({
                action: 'hover',
                timestamp: hoverState.enterTime,
                target: getTargetInfo(element),
                position: null // Hover doesn't need precise position
            });
        }

        hoverState = { element: null, enterTime: 0, timeout: null };
    }

    // Scroll tracking state (debounced)
    let scrollState = {
        timeout: null,
        lastScrollTop: window.scrollY,
        lastScrollLeft: window.scrollX,
        scrollStartTime: 0
    };

    function handleScroll(event) {
        // Debounce scroll events - only record after scrolling stops
        const now = getTimestamp();

        // Track when scrolling started
        if (!scrollState.timeout) {
            scrollState.scrollStartTime = now;
            scrollState.lastScrollTop = window.scrollY;
            scrollState.lastScrollLeft = window.scrollX;
        }

        // Clear existing timeout
        if (scrollState.timeout) {
            clearTimeout(scrollState.timeout);
        }

        // Set new timeout to record scroll after movement stops
        scrollState.timeout = setTimeout(() => {
            const currentScrollTop = window.scrollY;
            const currentScrollLeft = window.scrollX;

            // Calculate scroll delta
            const deltaY = currentScrollTop - scrollState.lastScrollTop;
            const deltaX = currentScrollLeft - scrollState.lastScrollLeft;

            // Only record if there was significant scroll (more than 50px in any direction)
            if (Math.abs(deltaY) > 50 || Math.abs(deltaX) > 50) {
                recordEvent({
                    action: 'scroll',
                    timestamp: scrollState.scrollStartTime,
                    scroll: {
                        x: currentScrollLeft,
                        y: currentScrollTop,
                        deltaX: deltaX,
                        deltaY: deltaY
                    }
                });
            }

            // Update last known position
            scrollState.lastScrollTop = currentScrollTop;
            scrollState.lastScrollLeft = currentScrollLeft;
            scrollState.timeout = null;
        }, 150); // Wait 150ms after last scroll event
    }

    // Navigation tracking
    let lastUrl = '';

    function handleNavigation() {
        const currentUrl = location.href;
        if (currentUrl !== lastUrl) {
            recordEvent({
                action: 'navigate',
                timestamp: getTimestamp(),
                url: currentUrl
            });
            lastUrl = currentUrl;
        }
    }

    // ==================== ACTION HANDLERS ====================

    /**
     * Detect custom elements that might have closed shadow DOM.
     * Custom elements (hyphenated tag names) with no .shadowRoot could have:
     * 1. No shadow DOM at all (fine)
     * 2. Closed shadow DOM (we can't access it)
     *
     * We use heuristics to identify likely closed shadow DOM:
     * - Custom element (has hyphen in tag name)
     * - No .shadowRoot property
     * - Has rendered content (offsetWidth/Height > 0)
     * - But has no light DOM children (childNodes is empty or only whitespace)
     */
    function detectPotentialClosedShadowDOM() {
        const warnings = [];
        const customElements = document.querySelectorAll('*');

        for (const el of customElements) {
            const tagName = el.tagName.toLowerCase();

            // Custom elements must have a hyphen in their name
            if (!tagName.includes('-')) continue;

            // If it has an accessible shadowRoot, it's open - no problem
            if (el.shadowRoot) continue;

            // Check if element has rendered content but no light DOM children
            const hasRenderedContent = el.offsetWidth > 0 || el.offsetHeight > 0;
            const hasLightDOMContent = Array.from(el.childNodes).some(
                node => node.nodeType === Node.ELEMENT_NODE ||
                       (node.nodeType === Node.TEXT_NODE && node.textContent.trim())
            );

            // If it renders content but has no light DOM, likely has closed shadow DOM
            if (hasRenderedContent && !hasLightDOMContent) {
                warnings.push({
                    tagName: tagName,
                    id: el.id || null,
                    className: el.className || null,
                    selector: el.id ? `#${el.id}` : tagName
                });
            }
        }

        // Deduplicate by tagName (only report each component type once)
        const uniqueByTag = {};
        for (const w of warnings) {
            if (!uniqueByTag[w.tagName]) {
                uniqueByTag[w.tagName] = w;
            }
        }

        return Object.values(uniqueByTag);
    }

    /**
     * Detect media elements (audio/video with controls) on the page.
     * Returns count and details for warning the user about single tab stop behavior.
     */
    function detectMediaElements() {
        const audioElements = document.querySelectorAll('audio[controls]');
        const videoElements = document.querySelectorAll('video[controls]');

        const count = audioElements.length + videoElements.length;
        if (count === 0) return null;

        return {
            count: count,
            audioCount: audioElements.length,
            videoCount: videoElements.length
        };
    }

    /**
     * Detect native control inputs (range, date, time, color, etc.) on the page.
     * Returns count and details for warning the user about single tab stop behavior.
     */
    function detectNativeControlInputs() {
        const nativeTypes = ['range', 'date', 'time', 'datetime-local', 'month', 'week', 'number', 'color'];
        const counts = {};
        let total = 0;

        for (const type of nativeTypes) {
            const elements = document.querySelectorAll(`input[type="${type}"]`);
            if (elements.length > 0) {
                counts[type] = elements.length;
                total += elements.length;
            }
        }

        if (total === 0) return null;

        return {
            count: total,
            types: counts
        };
    }

    /**
     * Detect file inputs on the page.
     * Returns count for warning the user that file uploads cannot be recorded.
     */
    function detectFileInputs() {
        const fileInputs = document.querySelectorAll('input[type="file"]');
        if (fileInputs.length === 0) return null;

        return {
            count: fileInputs.length,
            elements: Array.from(fileInputs).slice(0, 5).map(el => ({
                id: el.id || null,
                name: el.name || null,
                selector: el.id ? `#${el.id}` : (el.name ? `input[name="${el.name}"]` : 'input[type="file"]')
            }))
        };
    }

    if (action === 'start') {
        // Check if already recording
        if (window.__INSPEKT_RECORD_ACTIVE__) {
            return { ok: true, message: 'Recording already active' };
        }

        // Generate unique recording ID for IndexedDB persistence
        const recordingId = config.recordingId || ('rec_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9));

        // Initialize state
        window.__INSPEKT_RECORD_ACTIVE__ = true;
        window.__INSPEKT_RECORD_START__ = Date.now();
        window.__INSPEKT_RECORD_EVENTS__ = [];
        window.__INSPEKT_RECORD_INDEX__ = 0;
        window.__INSPEKT_RECORD_CONFIG__ = config || {};
        window.__INSPEKT_RECORD_ID__ = recordingId;

        // Clear any old events from previous recordings
        EventDB.clearAll();

        // Sound is played by Python (via __INSPEKT_VISUAL__.audio.playStart)

        // Store initial URL
        lastUrl = location.href;

        // Record initial navigation
        const navEvent = {
            action: 'navigate',
            timestamp: 0,
            url: location.href
        };
        recordEvent(navEvent);
        persistEventToStorage(navEvent);

        // Attach event listeners
        // Use capture phase (true) to catch events before stopPropagation
        document.addEventListener('click', handleClick, true);
        document.addEventListener('contextmenu', handleContextMenu, true);
        document.addEventListener('pointerdown', handlePointerDown, true);
        document.addEventListener('mousedown', handleMouseDown, true);
        document.addEventListener('input', handleInput, true);
        document.addEventListener('change', handleChange, true);
        document.addEventListener('keydown', handleKeyDown, true);
        document.addEventListener('mouseenter', handleMouseEnter, true);
        document.addEventListener('mouseleave', handleMouseLeave, true);
        document.addEventListener('toggle', handleToggle, true);
        window.addEventListener('scroll', handleScroll, { passive: true });
        window.addEventListener('popstate', handleNavigation);
        window.addEventListener('hashchange', handleNavigation);

        // Store handlers for cleanup
        window.__INSPEKT_RECORD_HANDLERS__ = {
            click: handleClick,
            contextmenu: handleContextMenu,
            pointerdown: handlePointerDown,
            mousedown: handleMouseDown,
            input: handleInput,
            change: handleChange,
            keydown: handleKeyDown,
            mouseenter: handleMouseEnter,
            mouseleave: handleMouseLeave,
            toggle: handleToggle,
            scroll: handleScroll,
            popstate: handleNavigation,
            hashchange: handleNavigation
        };

        // =======================================================================
        // Dialog Element Support
        // Intercept showModal(), show(), and close() methods to record dialog actions
        // =======================================================================

        const originalShowModal = HTMLDialogElement.prototype.showModal;
        const originalShow = HTMLDialogElement.prototype.show;
        const originalClose = HTMLDialogElement.prototype.close;

        HTMLDialogElement.prototype.showModal = function() {
            originalShowModal.call(this);
            recordEvent({
                action: 'dialog',
                timestamp: getTimestamp(),
                target: getTargetInfo(this),
                value: 'modal'
            });
        };

        HTMLDialogElement.prototype.show = function() {
            originalShow.call(this);
            recordEvent({
                action: 'dialog',
                timestamp: getTimestamp(),
                target: getTargetInfo(this),
                value: 'modeless'
            });
        };

        HTMLDialogElement.prototype.close = function(returnValue) {
            recordEvent({
                action: 'dialog',
                timestamp: getTimestamp(),
                target: getTargetInfo(this),
                value: 'close'
            });
            originalClose.call(this, returnValue);
        };

        // Store original methods for cleanup
        window.__INSPEKT_RECORD_DIALOG_ORIGINALS__ = {
            showModal: originalShowModal,
            show: originalShow,
            close: originalClose
        };

        // =======================================================================
        // Shadow DOM Support for Non-Composed Events
        // Events like 'change', 'input', 'focus', 'blur' have composed:false,
        // meaning they don't cross shadow boundaries. We need to attach
        // listeners directly to shadow roots to capture these events.
        // =======================================================================

        const shadowRootsWithListeners = new WeakSet();

        function attachShadowRootListeners(shadowRoot) {
            if (shadowRootsWithListeners.has(shadowRoot)) {
                return; // Already attached
            }

            // Attach non-composed event listeners to this shadow root
            // These events don't bubble across shadow boundaries
            shadowRoot.addEventListener('change', handleChange, true);
            shadowRoot.addEventListener('input', handleInput, true);
            // Focus/blur are also non-composed (focusin/focusout ARE composed)
            // We don't currently record focus events, but adding for completeness
            // shadowRoot.addEventListener('focus', handleFocus, true);
            // shadowRoot.addEventListener('blur', handleBlur, true);

            shadowRootsWithListeners.add(shadowRoot);
        }

        function findAndAttachToShadowRoots(root) {
            // Find all elements that might have shadow roots
            const elements = root.querySelectorAll('*');
            for (const el of elements) {
                if (el.shadowRoot) {
                    attachShadowRootListeners(el.shadowRoot);
                    // Recursively check for nested shadow roots
                    findAndAttachToShadowRoots(el.shadowRoot);
                }
            }
        }

        // Attach to existing shadow roots
        findAndAttachToShadowRoots(document);

        // Watch for new elements with shadow roots using MutationObserver
        const shadowObserver = new MutationObserver((mutations) => {
            for (const mutation of mutations) {
                for (const node of mutation.addedNodes) {
                    if (node.nodeType === Node.ELEMENT_NODE) {
                        // Check if this element has a shadow root
                        if (node.shadowRoot) {
                            attachShadowRootListeners(node.shadowRoot);
                            findAndAttachToShadowRoots(node.shadowRoot);
                        }
                        // Check descendants
                        if (node.querySelectorAll) {
                            findAndAttachToShadowRoots(node);
                        }
                    }
                }
            }
        });

        shadowObserver.observe(document.body, {
            childList: true,
            subtree: true
        });

        window.__INSPEKT_SHADOW_OBSERVER__ = shadowObserver;

        // Intercept Element.prototype.attachShadow to catch dynamically created
        // shadow roots that MutationObserver might miss (e.g., when an existing
        // element gets a shadow root attached via JavaScript)
        const originalAttachShadow = Element.prototype.attachShadow;
        Element.prototype.attachShadow = function(init) {
            const shadowRoot = originalAttachShadow.call(this, init);
            // Only attach listeners if it's an open shadow root
            // (closed shadow roots return the shadow root but .shadowRoot is null)
            if (init.mode === 'open') {
                attachShadowRootListeners(shadowRoot);
            }
            return shadowRoot;
        };
        window.__INSPEKT_ORIGINAL_ATTACH_SHADOW__ = originalAttachShadow;

        // Intercept pushState/replaceState for SPA navigation
        const originalPushState = history.pushState;
        const originalReplaceState = history.replaceState;

        history.pushState = function(...args) {
            originalPushState.apply(this, args);
            handleNavigation();
        };

        history.replaceState = function(...args) {
            originalReplaceState.apply(this, args);
            handleNavigation();
        };

        window.__INSPEKT_RECORD_ORIGINAL_PUSH_STATE__ = originalPushState;
        window.__INSPEKT_RECORD_ORIGINAL_REPLACE_STATE__ = originalReplaceState;

        // Flush typing buffer periodically
        window.__INSPEKT_RECORD_FLUSH_INTERVAL__ = setInterval(() => {
            if (typingState.element && (getTimestamp() - typingState.lastTime) > 500) {
                flushTypingBuffer();
            }
        }, 500);

        // Check for potential closed shadow DOM components
        const closedShadowWarnings = detectPotentialClosedShadowDOM();

        // Check for media elements (audio/video with controls)
        const mediaElements = detectMediaElements();

        // Check for native control inputs (range, date, time, color, etc.)
        const nativeControlInputs = detectNativeControlInputs();

        // Check for file inputs (cannot record file paths due to browser security)
        const fileInputs = detectFileInputs();

        return {
            ok: true,
            message: 'Recording started',
            startUrl: location.href,
            startTime: window.__INSPEKT_RECORD_START__,
            recordingId: recordingId,
            viewport: {
                width: window.innerWidth,
                height: window.innerHeight
            },
            scroll: {
                x: window.scrollX || window.pageXOffset || 0,
                y: window.scrollY || window.pageYOffset || 0
            },
            zoom: window.devicePixelRatio || 1,
            userAgent: navigator.userAgent,
            closedShadowWarnings: closedShadowWarnings,
            mediaElements: mediaElements,
            nativeControlInputs: nativeControlInputs,
            fileInputs: fileInputs
        };

    } else if (action === 'poll') {
        // Check if recording is active (may have been lost due to navigation)
        if (!window.__INSPEKT_RECORD_ACTIVE__) {
            return {
                ok: true,
                events: [],
                hasEvents: false,
                totalEvents: 0,
                recordingActive: false,
                currentUrl: location.href
            };
        }

        // Flush any pending typing
        if (typingState.element && (getTimestamp() - typingState.lastTime) > 300) {
            flushTypingBuffer();
        }

        // Get new events since last poll
        const allEvents = window.__INSPEKT_RECORD_EVENTS__ || [];
        const lastIndex = window.__INSPEKT_RECORD_INDEX__ || 0;
        const newEvents = allEvents.slice(lastIndex);

        // Update index
        window.__INSPEKT_RECORD_INDEX__ = allEvents.length;

        return {
            ok: true,
            events: newEvents,
            hasEvents: newEvents.length > 0,
            totalEvents: allEvents.length,
            recordingActive: true,
            currentUrl: location.href,
            stopRequested: !!window.__INSPEKT_STOP_REQUESTED__,
            // Recording control signals (one-shot flags, consumed after reading)
            pauseToggled: consumeFlag('__INSPEKT_PAUSE_TOGGLED__'),
            isPaused: !!window.__INSPEKT_PAUSED__,
            undoRequested: consumeFlag('__INSPEKT_UNDO_REQUESTED__'),
            redoRequested: consumeFlag('__INSPEKT_REDO_REQUESTED__')
        };

    } else if (action === 'stop') {
        // Sound is played by Python cleanup (via __INSPEKT_VISUAL__.audio.playStop)

        // Flush any remaining typing
        flushTypingBuffer();

        // Clear IndexedDB (events are saved to file, no longer needed)
        EventDB.clearAll();

        // Remove event listeners
        const handlers = window.__INSPEKT_RECORD_HANDLERS__ || {};
        if (handlers.click) document.removeEventListener('click', handlers.click, true);
        if (handlers.contextmenu) document.removeEventListener('contextmenu', handlers.contextmenu, true);
        if (handlers.pointerdown) document.removeEventListener('pointerdown', handlers.pointerdown, true);
        if (handlers.mousedown) document.removeEventListener('mousedown', handlers.mousedown, true);
        if (handlers.input) document.removeEventListener('input', handlers.input, true);
        if (handlers.change) document.removeEventListener('change', handlers.change, true);
        if (handlers.keydown) document.removeEventListener('keydown', handlers.keydown, true);
        if (handlers.mouseenter) document.removeEventListener('mouseenter', handlers.mouseenter, true);
        if (handlers.mouseleave) document.removeEventListener('mouseleave', handlers.mouseleave, true);
        if (handlers.toggle) document.removeEventListener('toggle', handlers.toggle, true);
        if (handlers.scroll) window.removeEventListener('scroll', handlers.scroll);
        if (handlers.popstate) window.removeEventListener('popstate', handlers.popstate);
        if (handlers.hashchange) window.removeEventListener('hashchange', handlers.hashchange);

        // Restore history methods
        if (window.__INSPEKT_RECORD_ORIGINAL_PUSH_STATE__) {
            history.pushState = window.__INSPEKT_RECORD_ORIGINAL_PUSH_STATE__;
        }
        if (window.__INSPEKT_RECORD_ORIGINAL_REPLACE_STATE__) {
            history.replaceState = window.__INSPEKT_RECORD_ORIGINAL_REPLACE_STATE__;
        }

        // Restore dialog methods
        const dialogOriginals = window.__INSPEKT_RECORD_DIALOG_ORIGINALS__;
        if (dialogOriginals) {
            if (dialogOriginals.showModal) {
                HTMLDialogElement.prototype.showModal = dialogOriginals.showModal;
            }
            if (dialogOriginals.show) {
                HTMLDialogElement.prototype.show = dialogOriginals.show;
            }
            if (dialogOriginals.close) {
                HTMLDialogElement.prototype.close = dialogOriginals.close;
            }
        }

        // Disconnect shadow DOM observer
        if (window.__INSPEKT_SHADOW_OBSERVER__) {
            window.__INSPEKT_SHADOW_OBSERVER__.disconnect();
        }

        // Restore original attachShadow
        if (window.__INSPEKT_ORIGINAL_ATTACH_SHADOW__) {
            Element.prototype.attachShadow = window.__INSPEKT_ORIGINAL_ATTACH_SHADOW__;
        }

        // Clear interval
        if (window.__INSPEKT_RECORD_FLUSH_INTERVAL__) {
            clearInterval(window.__INSPEKT_RECORD_FLUSH_INTERVAL__);
        }

        // Collect final events
        const allEvents = window.__INSPEKT_RECORD_EVENTS__ || [];
        const startTime = window.__INSPEKT_RECORD_START__ || Date.now();
        const duration = Date.now() - startTime;

        // Cleanup
        delete window.__INSPEKT_RECORD_ACTIVE__;
        delete window.__INSPEKT_RECORD_START__;
        delete window.__INSPEKT_RECORD_EVENTS__;
        delete window.__INSPEKT_RECORD_INDEX__;
        delete window.__INSPEKT_RECORD_CONFIG__;
        delete window.__INSPEKT_RECORD_ID__;
        delete window.__INSPEKT_RECORD_HANDLERS__;
        delete window.__INSPEKT_RECORD_ORIGINAL_PUSH_STATE__;
        delete window.__INSPEKT_RECORD_ORIGINAL_REPLACE_STATE__;
        delete window.__INSPEKT_RECORD_FLUSH_INTERVAL__;
        delete window.__INSPEKT_SHADOW_OBSERVER__;
        delete window.__INSPEKT_ORIGINAL_ATTACH_SHADOW__;

        return {
            ok: true,
            message: 'Recording stopped',
            events: allEvents,
            totalEvents: allEvents.length,
            duration: duration
        };

    } else if (action === 'resume') {
        // Resume recording on a new page after navigation
        // This is called when the CLI detects recording was lost
        if (window.__INSPEKT_RECORD_ACTIVE__) {
            return { ok: true, message: 'Recording already active', alreadyActive: true };
        }

        // Get the inherited start time and recording ID from config (passed from CLI)
        const inheritedStartTime = config.inheritedStartTime || Date.now();
        const recordingId = config.recordingId;

        // Initialize state FIRST (before async recovery)
        window.__INSPEKT_RECORD_ACTIVE__ = true;
        window.__INSPEKT_RECORD_START__ = inheritedStartTime;
        window.__INSPEKT_RECORD_EVENTS__ = [];
        window.__INSPEKT_RECORD_INDEX__ = 0;
        window.__INSPEKT_RECORD_CONFIG__ = config || {};
        window.__INSPEKT_RECORD_ID__ = recordingId;

        // Try to recover events from IndexedDB (they survive page navigation on same origin)
        // This helps capture events that happened just before navigation (within the 100ms poll interval)
        // The CLI will deduplicate based on timestamp, so duplicates are harmless
        try {
            EventDB.recoverEvents(recordingId).then(events => {
                if (events && events.length > 0) {
                    // Prepend recovered events to the current events array
                    const currentEvents = window.__INSPEKT_RECORD_EVENTS__ || [];
                    window.__INSPEKT_RECORD_EVENTS__ = [...events, ...currentEvents];
                    // Reset index to 0 so recovered events are included in next poll
                    window.__INSPEKT_RECORD_INDEX__ = 0;
                }
                // Clear IndexedDB after recovery to prevent re-recovery on subsequent resumes
                EventDB.clearEvents(recordingId);
            }).catch(() => {
                // Silently fail - IndexedDB might not be available
            });
        } catch (e) {
            // Silently fail
        }

        // Play resume sound
        RecordAudio.playResume();

        // Store current URL (don't record navigate event - CLI will add it)
        lastUrl = location.href;

        // Attach event listeners (same as 'start')
        document.addEventListener('click', handleClick, true);
        document.addEventListener('contextmenu', handleContextMenu, true);
        document.addEventListener('pointerdown', handlePointerDown, true);
        document.addEventListener('mousedown', handleMouseDown, true);
        document.addEventListener('input', handleInput, true);
        document.addEventListener('change', handleChange, true);
        document.addEventListener('keydown', handleKeyDown, true);
        document.addEventListener('mouseenter', handleMouseEnter, true);
        document.addEventListener('mouseleave', handleMouseLeave, true);
        document.addEventListener('toggle', handleToggle, true);
        window.addEventListener('scroll', handleScroll, { passive: true });
        window.addEventListener('popstate', handleNavigation);
        window.addEventListener('hashchange', handleNavigation);

        // Store handlers for cleanup
        window.__INSPEKT_RECORD_HANDLERS__ = {
            click: handleClick,
            contextmenu: handleContextMenu,
            pointerdown: handlePointerDown,
            mousedown: handleMouseDown,
            input: handleInput,
            change: handleChange,
            keydown: handleKeyDown,
            mouseenter: handleMouseEnter,
            mouseleave: handleMouseLeave,
            toggle: handleToggle,
            scroll: handleScroll,
            popstate: handleNavigation,
            hashchange: handleNavigation
        };

        // Shadow DOM Support for Non-Composed Events (same as 'start')
        const shadowRootsWithListeners = new WeakSet();

        function attachShadowRootListeners(shadowRoot) {
            if (shadowRootsWithListeners.has(shadowRoot)) return;
            shadowRoot.addEventListener('change', handleChange, true);
            shadowRoot.addEventListener('input', handleInput, true);
            shadowRootsWithListeners.add(shadowRoot);
        }

        function findAndAttachToShadowRoots(root) {
            const elements = root.querySelectorAll('*');
            for (const el of elements) {
                if (el.shadowRoot) {
                    attachShadowRootListeners(el.shadowRoot);
                    findAndAttachToShadowRoots(el.shadowRoot);
                }
            }
        }

        findAndAttachToShadowRoots(document);

        const shadowObserver = new MutationObserver((mutations) => {
            for (const mutation of mutations) {
                for (const node of mutation.addedNodes) {
                    if (node.nodeType === Node.ELEMENT_NODE) {
                        if (node.shadowRoot) {
                            attachShadowRootListeners(node.shadowRoot);
                            findAndAttachToShadowRoots(node.shadowRoot);
                        }
                        if (node.querySelectorAll) {
                            findAndAttachToShadowRoots(node);
                        }
                    }
                }
            }
        });

        shadowObserver.observe(document.body, { childList: true, subtree: true });
        window.__INSPEKT_SHADOW_OBSERVER__ = shadowObserver;

        // Intercept attachShadow for dynamically created shadow roots
        const originalAttachShadow = Element.prototype.attachShadow;
        Element.prototype.attachShadow = function(init) {
            const shadowRoot = originalAttachShadow.call(this, init);
            if (init.mode === 'open') {
                attachShadowRootListeners(shadowRoot);
            }
            return shadowRoot;
        };
        window.__INSPEKT_ORIGINAL_ATTACH_SHADOW__ = originalAttachShadow;

        // Intercept pushState/replaceState for SPA navigation
        const originalPushState = history.pushState;
        const originalReplaceState = history.replaceState;

        history.pushState = function(...args) {
            originalPushState.apply(this, args);
            handleNavigation();
        };

        history.replaceState = function(...args) {
            originalReplaceState.apply(this, args);
            handleNavigation();
        };

        window.__INSPEKT_RECORD_ORIGINAL_PUSH_STATE__ = originalPushState;
        window.__INSPEKT_RECORD_ORIGINAL_REPLACE_STATE__ = originalReplaceState;

        // Flush typing buffer periodically
        window.__INSPEKT_RECORD_FLUSH_INTERVAL__ = setInterval(() => {
            if (typingState.element && (getTimestamp() - typingState.lastTime) > 500) {
                flushTypingBuffer();
            }
        }, 500);

        return {
            ok: true,
            message: 'Recording resumed',
            resumedUrl: location.href,
            inheritedStartTime: inheritedStartTime
        };
    }

    return { ok: false, error: 'Invalid action: ' + action };
})()
