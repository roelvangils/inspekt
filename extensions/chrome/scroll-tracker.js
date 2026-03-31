/**
 * Scroll position tracker for the virtual scrollbar feature.
 * Runs in the MAIN world (via manifest "world": "MAIN") so that
 * window.__INSPEKT_SCROLL__ is visible to CDP Runtime.evaluate.
 */
if (!window.__INSPEKT_SCROLL_INIT__) {
    window.__INSPEKT_SCROLL_INIT__ = true;
    window.__INSPEKT_SCROLL__ = { top: 0, height: 0, client: 0, left: 0, width: 0, clientW: 0 };

    function __inspektUpdateScroll() {
        const d = document.documentElement;
        const b = document.body;
        // Detect page background for adaptive scrollbar color
        var bg = '';
        try {
            var htmlBg = getComputedStyle(d).backgroundColor;
            var bodyBg = b ? getComputedStyle(b).backgroundColor : '';
            bg = (htmlBg && htmlBg !== 'rgba(0, 0, 0, 0)' && htmlBg !== 'transparent') ? htmlBg : bodyBg;
        } catch(e) {}

        window.__INSPEKT_SCROLL__ = {
            top: d.scrollTop || (b && b.scrollTop) || 0,
            height: Math.max(d.scrollHeight, (b && b.scrollHeight) || 0),
            client: d.clientHeight,
            left: d.scrollLeft || (b && b.scrollLeft) || 0,
            width: Math.max(d.scrollWidth, (b && b.scrollWidth) || 0),
            clientW: d.clientWidth,
            bg: bg
        };
    }

    window.addEventListener('scroll', __inspektUpdateScroll, { passive: true });
    window.addEventListener('resize', __inspektUpdateScroll, { passive: true });

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', __inspektUpdateScroll, { once: true });
    } else {
        __inspektUpdateScroll();
    }
    window.addEventListener('load', __inspektUpdateScroll, { once: true });
}
