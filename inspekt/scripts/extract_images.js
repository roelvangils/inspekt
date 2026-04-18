// Extract all images from the current page.
// Invoked as (script)(config) by inspekt/app/cli/extract.py — must be a function
// that returns { images, pageUrl, pageTitle, dataUriCount, externalCount }.
//
// Per image the Python side consumes: src, bestQualitySrc, alt, title, filename,
// naturalWidth/Height, displayedWidth/Height, isDataUri, isBlobUri,
// sourceType ("img" | "css-background"), accessibleName, accessibleNameSource,
// isLinked, linkHref, nearestHeadingText.
(config) => {
    const images = [];
    let dataUriCount = 0;
    let externalCount = 0;

    const filenameFromUrl = (url) => {
        try {
            return new URL(url, document.baseURI).pathname.split("/").pop() || "";
        } catch (_) {
            return "";
        }
    };

    // Attributes commonly used by lazy-loading libraries (lazysizes, lozad,
    // blazy, Flickity, WordPress lazyload, etc.) to stash the real URL while
    // src/srcset carry a placeholder. Checked in the order libraries use them.
    const LAZY_SRCSET_ATTRS = ["data-srcset", "data-lazy-srcset", "data-flickity-lazyload-srcset"];
    const LAZY_SRC_ATTRS = [
        "data-src", "data-original", "data-lazy-src", "data-lazyload",
        "data-url", "data-defer-src", "data-hi-res-src", "data-flickity-lazyload",
    ];

    // Parse a srcset value into [{url, weight}] where weight is the descriptor
    // magnitude (w-descriptors as-is, x-descriptors scaled so 2x beats 800w).
    const parseSrcset = (value) => {
        if (!value) return [];
        return value.split(",").map(entry => {
            const parts = entry.trim().split(/\s+/);
            const url = parts[0];
            const desc = parts[1] || "1x";
            let weight = 0;
            if (desc.endsWith("w")) weight = parseFloat(desc);
            else if (desc.endsWith("x")) weight = parseFloat(desc) * 1000;
            return { url, weight };
        }).filter(e => e.url);
    };

    const resolveAbs = (url) => {
        try { return new URL(url, document.baseURI).href; } catch (_) { return url; }
    };

    const pickLargestFromSrcset = (value) => {
        const entries = parseSrcset(value);
        if (entries.length === 0) return null;
        entries.sort((a, b) => b.weight - a.weight);
        return resolveAbs(entries[0].url);
    };

    // Cascade to find the real URL. Data-* attrs win over currentSrc because
    // when present they typically hold the real asset while currentSrc is a
    // placeholder (LQIP blur, spacer.gif, 1×1 data URI).
    const resolveRealUrl = (img) => {
        for (const attr of LAZY_SRCSET_ATTRS) {
            const picked = pickLargestFromSrcset(img.getAttribute(attr));
            if (picked) return picked;
        }
        for (const attr of LAZY_SRC_ATTRS) {
            const v = img.getAttribute(attr);
            if (v && v.trim()) return resolveAbs(v.trim());
        }
        if (img.currentSrc) return img.currentSrc;
        const fromSrcset = pickLargestFromSrcset(img.getAttribute("srcset"));
        if (fromSrcset) return fromSrcset;
        return img.src || "";
    };

    // Find the highest-resolution entry available across all srcset-flavored
    // attributes, falling back to the resolved src.
    const bestQualityUrl = (img, resolvedSrc) => {
        for (const attr of ["srcset", ...LAZY_SRCSET_ATTRS]) {
            const picked = pickLargestFromSrcset(img.getAttribute(attr));
            if (picked) return picked;
        }
        return resolvedSrc;
    };

    // Walk up + previous-sibling chain bounded to ~30 nodes to find the nearest
    // preceding heading for context. Keeps it cheap on deep DOMs.
    const nearestHeadingText = (el) => {
        let steps = 0;
        let node = el;
        while (node && steps < 30) {
            let sib = node.previousElementSibling;
            while (sib && steps < 30) {
                if (/^H[1-6]$/.test(sib.tagName)) {
                    return (sib.textContent || "").trim().slice(0, 200);
                }
                const h = sib.querySelector ? sib.querySelector("h1, h2, h3, h4, h5, h6") : null;
                if (h) return (h.textContent || "").trim().slice(0, 200);
                sib = sib.previousElementSibling;
                steps++;
            }
            node = node.parentElement;
            steps++;
        }
        return "";
    };

    // WAI ARIA accessible-name fallback chain for <img>.
    const computeImgName = (img) => {
        const labelledby = img.getAttribute("aria-labelledby");
        if (labelledby) {
            const parts = labelledby.split(/\s+/)
                .map(id => document.getElementById(id))
                .filter(Boolean)
                .map(n => (n.textContent || "").trim());
            const joined = parts.join(" ").trim();
            if (joined) return { name: joined, source: "aria-labelledby" };
        }
        const arialabel = img.getAttribute("aria-label");
        if (arialabel && arialabel.trim()) {
            return { name: arialabel.trim(), source: "aria-label" };
        }
        if (img.hasAttribute("alt")) {
            const alt = img.getAttribute("alt");
            if (alt === "") {
                return { name: "", source: "empty alt (decorative)" };
            }
            return { name: alt.trim(), source: "alt attribute" };
        }
        const title = img.getAttribute("title");
        if (title && title.trim()) {
            return { name: title.trim(), source: "title attribute" };
        }
        const figure = img.closest("figure");
        if (figure) {
            const caption = figure.querySelector("figcaption");
            if (caption) {
                const t = (caption.textContent || "").trim();
                if (t) return { name: t, source: "figcaption" };
            }
        }
        return { name: "", source: "missing alt attribute" };
    };

    for (const img of document.images) {
        const src = resolveRealUrl(img);
        if (!src) continue;

        const isDataUri = src.startsWith("data:");
        const isBlobUri = src.startsWith("blob:");
        if (isDataUri) dataUriCount++;
        else if (!isBlobUri) externalCount++;

        const linkEl = img.closest("a[href]");
        const accName = computeImgName(img);

        images.push({
            src,
            bestQualitySrc: bestQualityUrl(img, src),
            alt: img.alt || "",
            title: img.title || "",
            filename: filenameFromUrl(src),
            naturalWidth: img.naturalWidth,
            naturalHeight: img.naturalHeight,
            displayedWidth: img.width,
            displayedHeight: img.height,
            isDataUri,
            isBlobUri,
            sourceType: "img",
            accessibleName: accName.name,
            accessibleNameSource: accName.source,
            isLinked: !!linkEl,
            linkHref: linkEl ? linkEl.href : "",
            nearestHeadingText: nearestHeadingText(img),
        });
    }

    // Optional CSS-background-image discovery. Disabled by default because
    // scanning every element's computed style is O(n) and the common case
    // doesn't need it.
    if (config && config.includeBackgroundImages) {
        const bgSeen = new Set();
        for (const el of document.querySelectorAll("*")) {
            const bg = getComputedStyle(el).backgroundImage;
            if (!bg || bg === "none") continue;
            const matches = [...bg.matchAll(/url\((?:"([^"]+)"|'([^']+)'|([^)]+))\)/g)];
            for (const m of matches) {
                const raw = (m[1] || m[2] || m[3] || "").trim();
                if (!raw) continue;
                let absUrl = raw;
                try { absUrl = new URL(raw, document.baseURI).href; } catch (_) { /* leave as-is */ }
                if (bgSeen.has(absUrl)) continue;
                bgSeen.add(absUrl);

                const isDataUri = absUrl.startsWith("data:");
                const isBlobUri = absUrl.startsWith("blob:");
                if (isDataUri) dataUriCount++;
                else if (!isBlobUri) externalCount++;

                const rect = el.getBoundingClientRect();
                const linkEl = el.closest("a[href]");

                images.push({
                    src: absUrl,
                    bestQualitySrc: absUrl,
                    alt: "",
                    title: "",
                    filename: filenameFromUrl(absUrl),
                    naturalWidth: 0,
                    naturalHeight: 0,
                    displayedWidth: Math.round(rect.width),
                    displayedHeight: Math.round(rect.height),
                    isDataUri,
                    isBlobUri,
                    sourceType: "css-background",
                    accessibleName: "",
                    accessibleNameSource: "none",
                    isLinked: !!linkEl,
                    linkHref: linkEl ? linkEl.href : "",
                    nearestHeadingText: nearestHeadingText(el),
                });
            }
        }
    }

    return {
        images,
        pageUrl: location.href,
        pageTitle: document.title || "",
        dataUriCount,
        externalCount,
    };
}
