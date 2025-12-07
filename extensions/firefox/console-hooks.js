/**
 * Console Hooks - Early Injection (Firefox)
 *
 * This content script runs at document_start to inject console hooks
 * into the MAIN world BEFORE any page scripts execute.
 *
 * Uses an external script file to bypass CSP restrictions on inline scripts.
 */

(function() {
    'use strict';

    // Inject console hooks into MAIN world via external script
    // Using an external file bypasses CSP 'unsafe-inline' restrictions
    const script = document.createElement('script');
    script.src = browser.runtime.getURL('scripts/console-hooks-inject.js');

    // Inject as early as possible - documentElement exists even at document_start
    (document.head || document.documentElement).appendChild(script);

    // Clean up after load
    script.onload = () => script.remove();
})();
