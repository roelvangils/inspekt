/**
 * Hide the main page scrollbar (html element only) via CSS injection.
 * Runs at document_start so no scrollbar flash occurs.
 * Nested scrollable containers keep their native scrollbars.
 *
 * The scroll position tracker is injected separately from background.js
 * using chrome.scripting.executeScript (MAIN world) to bypass CSP.
 */
(() => {
    const style = document.createElement('style');
    style.id = '__inspekt_scrollbar_hide__';
    style.textContent =
        'html::-webkit-scrollbar { display: none !important; width: 0 !important; height: 0 !important; }' +
        'html::-webkit-scrollbar-track { display: none !important; }' +
        'html::-webkit-scrollbar-thumb { display: none !important; }' +
        'html { scrollbar-width: none !important; }';
    (document.head || document.documentElement).appendChild(style);
})();
