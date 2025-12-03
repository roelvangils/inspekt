"""
Info command group - Page information and analysis.

This module provides comprehensive page inspection through focused subcommands:
- (default): Brief summary with browser/device info
- all: Complete output (all categories)
- performance: Load times and Core Web Vitals
- meta: Meta tags, Open Graph, Twitter Card
- seo: SEO analysis including robots.txt
- security: HTTPS status, security headers
- accessibility: A11y analysis, headings, landmarks
- resources: Scripts, stylesheets, media, fonts
- storage: Cookies, localStorage, sessionStorage
- tech: Detected frameworks and technologies
- domain: IP, SSL cert, WHOIS (server-side lookups)
- layout: Viewport, document size, scroll position
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

import click

from inspekt.app.cli.base import builtin_open
from inspekt.app.cli.table import Table
from inspekt.client import BridgeClient


# =============================================================================
# Helper Functions
# =============================================================================


def _print_info_table(
    title: str, rows: list[tuple[str, str, str | None]], key_width: int = 22, value_width: int = 55
) -> None:
    """Print a key-value information table with consistent formatting."""
    if not rows:
        return

    click.echo()
    click.echo(click.style(title, bold=True))
    click.echo()

    table = Table(["Property", "Value"], [key_width, value_width], ["left", "left"])
    table.print_header()

    for key, value, color in rows:
        if color:
            table.print_row([key, str(value)], [None, color])
        else:
            table.print_row([key, str(value)])

    table.print_footer()


def _print_list_table(
    title: str,
    headers: list[str],
    rows: list[list[str]],
    widths: list[int],
    colors: list[list[str | None]] | None = None,
) -> None:
    """Print a multi-column table for list-style data."""
    if not rows:
        return

    click.echo()
    click.echo(click.style(title, bold=True))
    click.echo()

    alignments = ["left"] * len(headers)
    table = Table(headers, widths, alignments)
    table.print_header()

    for i, row in enumerate(rows):
        row_colors = colors[i] if colors and i < len(colors) else None
        table.print_row(row, row_colors)

    table.print_footer()


def _truncate_value(value: str, max_len: int = 55) -> str:
    """Truncate a value with ellipsis if too long."""
    if len(value) <= max_len:
        return value
    return value[: max_len - 3] + "..."


def _get_bridge_client() -> BridgeClient:
    """Get a BridgeClient instance and verify connection."""
    client = BridgeClient()
    if not client.is_alive():
        click.echo("Error: Bridge server is not running. Start it with: inspekt start", err=True)
        sys.exit(1)
    return client


def _get_basic_info(client: BridgeClient) -> dict:
    """Get basic page info (URL, title, domain, etc.)."""
    code = """
    ({
        url: location.href,
        title: document.title,
        domain: location.hostname,
        protocol: location.protocol,
        readyState: document.readyState,
        width: window.innerWidth,
        height: window.innerHeight
    })
    """
    result = client.execute(code)
    if result.get("ok"):
        return result.get("result", {})
    raise RuntimeError(result.get("error", "Failed to get basic info"))


def _get_bridge_version(client: BridgeClient) -> tuple[str, str, str]:
    """Get bridge version, type, and browser name."""
    code = """
    (function() {
        const version = window.__INSPEKT_BRIDGE_VERSION__ || window.__ZEN_BRIDGE_VERSION__ || 'unknown';
        const type = (window.__INSPEKT_BRIDGE_EXTENSION__ || window.__ZEN_BRIDGE_EXTENSION__) ? 'extension' : 'userscript';
        const ua = navigator.userAgent;
        let browserName = 'Unknown';
        if (ua.includes('Firefox')) browserName = 'Firefox';
        else if (ua.includes('Edg')) browserName = 'Edge';
        else if (ua.includes('Chrome')) browserName = 'Chrome';
        else if (ua.includes('Safari')) browserName = 'Safari';
        return version + '|' + type + '|' + browserName;
    })()
    """
    result = client.execute(code, timeout=2.0)
    if result.get("ok"):
        parts = result.get("result", "unknown|userscript|Unknown").split("|")
        return (
            parts[0],
            parts[1] if len(parts) > 1 else "userscript",
            parts[2] if len(parts) > 2 else "Unknown",
        )
    return "unknown", "userscript", "Unknown"


# =============================================================================
# Data Collection Functions (Browser-side)
# =============================================================================


def _collect_summary_data(client: BridgeClient) -> dict:
    """Collect summary data: basic info + browser/device."""
    code = """
    ({
        url: location.href,
        title: document.title,
        domain: location.hostname,
        protocol: location.protocol,
        readyState: document.readyState,
        width: window.innerWidth,
        height: window.innerHeight,
        device: {
            platform: navigator.platform,
            language: navigator.language,
            screenResolution: screen.width + 'x' + screen.height,
            devicePixelRatio: window.devicePixelRatio,
            touchSupport: 'ontouchstart' in window || navigator.maxTouchPoints > 0,
            cookiesEnabled: navigator.cookieEnabled,
            onlineStatus: navigator.onLine
        },
        cookieCount: document.cookie.split(';').filter(c => c.trim()).length,
        isSecure: location.protocol === 'https:'
    })
    """
    result = client.execute(code)
    if result.get("ok"):
        return result.get("result", {})
    raise RuntimeError(result.get("error", "Failed to collect summary data"))


def _collect_performance_data(client: BridgeClient) -> dict:
    """Collect performance metrics and Core Web Vitals."""
    code = """
    (function() {
        const result = {};

        if (window.performance && window.performance.timing) {
            const timing = performance.timing;
            const loadTime = timing.loadEventEnd - timing.navigationStart;
            const domContentLoaded = timing.domContentLoadedEventEnd - timing.navigationStart;
            const ttfb = timing.responseStart - timing.navigationStart;

            result.pageLoadTime = loadTime > 0 ? loadTime : null;
            result.domContentLoaded = domContentLoaded > 0 ? domContentLoaded : null;
            result.timeToFirstByte = ttfb > 0 ? ttfb : null;
        }

        if (performance.getEntriesByType) {
            const paintEntries = performance.getEntriesByType('paint');
            paintEntries.forEach(entry => {
                if (entry.name === 'first-paint') {
                    result.firstPaint = Math.round(entry.startTime);
                }
                if (entry.name === 'first-contentful-paint') {
                    result.firstContentfulPaint = Math.round(entry.startTime);
                }
            });

            try {
                const lcpEntries = performance.getEntriesByType('largest-contentful-paint');
                if (lcpEntries.length > 0) {
                    result.largestContentfulPaint = Math.round(lcpEntries[lcpEntries.length - 1].startTime);
                }
            } catch (e) {}

            // Core Web Vitals
            try {
                const layoutShifts = performance.getEntriesByType('layout-shift');
                if (layoutShifts.length > 0) {
                    result.cls = layoutShifts.reduce((sum, entry) => {
                        return !entry.hadRecentInput ? sum + entry.value : sum;
                    }, 0);
                }
            } catch (e) {}

            try {
                const firstInput = performance.getEntriesByType('first-input');
                if (firstInput.length > 0) {
                    result.fid = Math.round(firstInput[0].processingStart - firstInput[0].startTime);
                }

                const interactions = performance.getEntriesByType('event');
                if (interactions.length > 0) {
                    const durations = interactions.map(e => e.duration).filter(d => d > 0);
                    if (durations.length > 0) {
                        result.inp = Math.round(Math.max(...durations));
                    }
                }
            } catch (e) {}
        }

        return result;
    })()
    """
    result = client.execute(code)
    if result.get("ok"):
        return result.get("result", {})
    raise RuntimeError(result.get("error", "Failed to collect performance data"))


def _collect_meta_data(client: BridgeClient) -> dict:
    """Collect meta tags, Open Graph, Twitter Card, language, encoding."""
    code = """
    ({
        specifiedLanguage: document.documentElement.lang || null,
        charset: document.characterSet || null,
        metaTags: Array.from(document.querySelectorAll('head meta')).map(meta => {
            const attrs = {};
            for (let attr of meta.attributes) {
                attrs[attr.name] = attr.value;
            }
            return attrs;
        }),
        openGraph: (() => {
            const og = {};
            document.querySelectorAll('meta[property^="og:"]').forEach(meta => {
                const prop = meta.getAttribute('property').replace('og:', '');
                og[prop] = meta.getAttribute('content');
            });
            return og;
        })(),
        twitterCard: (() => {
            const twitter = {};
            document.querySelectorAll('meta[name^="twitter:"]').forEach(meta => {
                const prop = meta.getAttribute('name').replace('twitter:', '');
                twitter[prop] = meta.getAttribute('content');
            });
            return twitter;
        })()
    })
    """
    result = client.execute(code)
    if result.get("ok"):
        return result.get("result", {})
    raise RuntimeError(result.get("error", "Failed to collect meta data"))


def _collect_seo_data(client: BridgeClient) -> dict:
    """Collect SEO data: canonical, description, keywords, structured data."""
    code = """
    ({
        canonical: (() => {
            const canonical = document.querySelector('link[rel="canonical"]');
            return canonical ? canonical.href : null;
        })(),
        description: (() => {
            const desc = document.querySelector('meta[name="description"]');
            return desc ? desc.getAttribute('content') : null;
        })(),
        keywords: (() => {
            const kw = document.querySelector('meta[name="keywords"]');
            return kw ? kw.getAttribute('content') : null;
        })(),
        robots: (() => {
            const robots = document.querySelector('meta[name="robots"]');
            return robots ? robots.getAttribute('content') : null;
        })(),
        sitemap: (() => {
            const sitemap = document.querySelector('link[rel="sitemap"]');
            return sitemap ? sitemap.href : null;
        })(),
        favicon: (() => {
            const icon = document.querySelector('link[rel="icon"], link[rel="shortcut icon"]');
            if (icon) {
                const href = icon.href;
                if (href.endsWith('.svg')) return 'SVG';
                if (href.endsWith('.png')) return 'PNG';
                if (href.endsWith('.ico')) return 'ICO';
                return 'Yes';
            }
            return null;
        })(),
        alternateLanguages: Array.from(document.querySelectorAll('link[rel="alternate"][hreflang]')).map(link => ({
            lang: link.getAttribute('hreflang'),
            href: link.href
        })),
        jsonLd: (() => {
            const types = [];
            document.querySelectorAll('script[type="application/ld+json"]').forEach(script => {
                try {
                    const data = JSON.parse(script.textContent);
                    const type = data['@type'] || (data['@graph'] && data['@graph'][0] && data['@graph'][0]['@type']);
                    if (type) types.push(type);
                } catch (e) {}
            });
            return types;
        })(),
        microdataCount: document.querySelectorAll('[itemscope]').length
    })
    """
    result = client.execute(code)
    if result.get("ok"):
        return result.get("result", {})
    raise RuntimeError(result.get("error", "Failed to collect SEO data"))


def _collect_security_data(client: BridgeClient) -> dict:
    """Collect security info: HTTPS, mixed content, CSP meta."""
    code = """
    ({
        isSecure: location.protocol === 'https:',
        hasMixedContent: (() => {
            const insecure = Array.from(document.querySelectorAll('script, img, link, iframe')).some(el => {
                const src = el.src || el.href;
                return src && src.startsWith('http:');
            });
            return location.protocol === 'https:' && insecure;
        })(),
        cspMeta: (() => {
            const csp = document.querySelector('meta[http-equiv="Content-Security-Policy"]');
            return csp ? csp.getAttribute('content') : null;
        })(),
        referrerPolicy: (() => {
            const referrer = document.querySelector('meta[name="referrer"]');
            return referrer ? referrer.getAttribute('content') : null;
        })()
    })
    """
    result = client.execute(code)
    if result.get("ok"):
        return result.get("result", {})
    raise RuntimeError(result.get("error", "Failed to collect security data"))


def _collect_accessibility_data(client: BridgeClient) -> dict:
    """Collect accessibility data: landmarks, headings, alt text, labels."""
    code = """
    ({
        landmarkCount: document.querySelectorAll('[role="banner"], [role="navigation"], [role="main"], [role="complementary"], [role="contentinfo"], [role="search"], [role="region"], header, nav, main, aside, footer').length,
        landmarks: (() => {
            const landmarks = {};
            document.querySelectorAll('[role="banner"], [role="navigation"], [role="main"], [role="complementary"], [role="contentinfo"], [role="search"], [role="region"], header:not([role]), nav:not([role]), main:not([role]), aside:not([role]), footer:not([role])').forEach(el => {
                const role = el.getAttribute('role') || el.tagName.toLowerCase();
                landmarks[role] = (landmarks[role] || 0) + 1;
            });
            return landmarks;
        })(),
        headingStructure: (() => {
            const structure = {h1: 0, h2: 0, h3: 0, h4: 0, h5: 0, h6: 0};
            document.querySelectorAll('h1, h2, h3, h4, h5, h6, [role="heading"]').forEach(h => {
                if (h.hasAttribute('role')) {
                    const level = parseInt(h.getAttribute('aria-level') || '1');
                    const key = 'h' + level;
                    if (structure[key] !== undefined) structure[key]++;
                } else {
                    structure[h.tagName.toLowerCase()]++;
                }
            });
            return structure;
        })(),
        imagesWithoutAlt: Array.from(document.images).filter(img => !img.hasAttribute('alt')).length,
        totalImages: document.images.length,
        formLabelsIssues: (() => {
            const inputs = document.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="button"]), select, textarea');
            let missingLabels = 0;
            inputs.forEach(input => {
                const hasLabel = input.labels && input.labels.length > 0;
                const hasAriaLabel = input.hasAttribute('aria-label') || input.hasAttribute('aria-labelledby');
                if (!hasLabel && !hasAriaLabel) missingLabels++;
            });
            return {total: inputs.length, missingLabels};
        })(),
        linksWithoutText: Array.from(document.querySelectorAll('a')).filter(link => {
            const text = link.textContent.trim();
            const ariaLabel = link.getAttribute('aria-label');
            const ariaLabelledby = link.getAttribute('aria-labelledby');
            const title = link.getAttribute('title');
            return !text && !ariaLabel && !ariaLabelledby && !title;
        }).length,
        buttonsWithoutLabels: Array.from(document.querySelectorAll('button')).filter(btn => {
            const text = btn.textContent.trim();
            const ariaLabel = btn.getAttribute('aria-label');
            const ariaLabelledby = btn.getAttribute('aria-labelledby');
            const title = btn.getAttribute('title');
            return !text && !ariaLabel && !ariaLabelledby && !title;
        }).length,
        hasSkipLink: (() => {
            const links = Array.from(document.querySelectorAll('a[href^="#"]'));
            return links.some(link => {
                const text = link.textContent.toLowerCase();
                const href = link.getAttribute('href');
                return (text.includes('skip') || text.includes('jump')) &&
                       (href === '#main' || href === '#content' || href.includes('main') || href.includes('content'));
            });
        })(),
        ariaAttributeCount: document.querySelectorAll('[aria-label], [aria-labelledby], [aria-describedby], [role], [aria-hidden], [aria-live], [aria-expanded], [aria-controls]').length,
        hasLangAttribute: document.documentElement.hasAttribute('lang'),
        forms: Array.from(document.querySelectorAll('form')).map((form, i) => ({
            id: form.id || form.name || `Form ${i + 1}`,
            action: form.action || 'JavaScript',
            method: (form.method || 'GET').toUpperCase(),
            fieldCount: form.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="button"]), select, textarea').length,
            issues: (() => {
                const issues = [];
                form.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="button"]), select, textarea').forEach(input => {
                    const hasLabel = input.labels && input.labels.length > 0;
                    const hasAriaLabel = input.hasAttribute('aria-label') || input.hasAttribute('aria-labelledby');
                    if (!hasLabel && !hasAriaLabel) issues.push(`${input.type || input.tagName.toLowerCase()} without label`);
                });
                return issues;
            })()
        }))
    })
    """
    result = client.execute(code)
    if result.get("ok"):
        return result.get("result", {})
    raise RuntimeError(result.get("error", "Failed to collect accessibility data"))


def _collect_resources_data(client: BridgeClient) -> dict:
    """Collect resources: scripts, stylesheets, images, media, fonts, network."""
    code = """
    (function() {
        const currentDomain = window.location.hostname;
        const externalDomains = new Set();

        // Check external resources
        Array.from(document.scripts).forEach(script => {
            if (script.src) {
                try {
                    const url = new URL(script.src);
                    if (url.hostname !== currentDomain && url.hostname) {
                        externalDomains.add(url.hostname);
                    }
                } catch (e) {}
            }
        });
        Array.from(document.querySelectorAll('link[href]')).forEach(link => {
            if (link.href) {
                try {
                    const url = new URL(link.href);
                    if (url.hostname !== currentDomain && url.hostname) {
                        externalDomains.add(url.hostname);
                    }
                } catch (e) {}
            }
        });
        Array.from(document.images).forEach(img => {
            if (img.src) {
                try {
                    const url = new URL(img.src);
                    if (url.hostname !== currentDomain && url.hostname) {
                        externalDomains.add(url.hostname);
                    }
                } catch (e) {}
            }
        });

        // Font detection
        const fonts = {
            googleFonts: [],
            customFonts: [],
            totalFontFiles: 0
        };

        document.querySelectorAll('link[href*="fonts.googleapis.com"]').forEach(link => {
            const match = link.href.match(/family=([^&:]+)/);
            if (match) {
                const families = match[1].split('|');
                families.forEach(family => {
                    const decoded = decodeURIComponent(family.replace(/\\+/g, ' '));
                    if (!fonts.googleFonts.includes(decoded)) {
                        fonts.googleFonts.push(decoded);
                    }
                });
            }
        });

        const customFontNames = new Set();
        try {
            Array.from(document.styleSheets).forEach(sheet => {
                try {
                    Array.from(sheet.cssRules || []).forEach(rule => {
                        if (rule instanceof CSSFontFaceRule) {
                            const fontFamily = rule.style.getPropertyValue('font-family');
                            if (fontFamily) {
                                const cleanName = fontFamily.replace(/['"]/g, '').trim();
                                if (cleanName) customFontNames.add(cleanName);
                            }
                        }
                    });
                } catch (e) {}
            });
        } catch (e) {}
        fonts.customFonts = Array.from(customFontNames);

        // Network stats from Performance API
        let network = null;
        if (performance && performance.getEntriesByType) {
            try {
                const resources = performance.getEntriesByType('resource');
                let totalSize = 0;
                let largestResource = null;
                let largestSize = 0;

                resources.forEach(resource => {
                    const size = resource.transferSize || resource.encodedBodySize || 0;
                    totalSize += size;
                    if (size > largestSize) {
                        largestSize = size;
                        largestResource = {
                            name: resource.name.split('/').pop() || resource.name,
                            url: resource.name,
                            size: size
                        };
                    }
                });

                fonts.totalFontFiles = resources.filter(r => r.name.match(/\\.(woff2?|ttf|otf|eot)$/i)).length;

                network = {
                    totalRequests: resources.length,
                    totalSize: totalSize,
                    largestResource: largestResource
                };
            } catch (e) {}
        }

        return {
            scriptCount: document.scripts.length,
            stylesheetCount: document.styleSheets.length,
            imageCount: document.images.length,
            linkCount: document.links.length,
            formCount: document.forms.length,
            iframeCount: document.querySelectorAll('iframe').length,
            videos: document.querySelectorAll('video').length,
            audio: document.querySelectorAll('audio').length,
            svgImages: document.querySelectorAll('svg, img[src$=".svg"]').length,
            thirdParty: {
                externalDomainCount: externalDomains.size,
                externalDomains: Array.from(externalDomains).slice(0, 10)
            },
            fonts: fonts,
            network: network
        };
    })()
    """
    result = client.execute(code)
    if result.get("ok"):
        return result.get("result", {})
    raise RuntimeError(result.get("error", "Failed to collect resources data"))


def _collect_storage_data(client: BridgeClient) -> dict:
    """Collect storage info: cookies, localStorage, sessionStorage."""
    code = """
    ({
        cookieCount: document.cookie.split(';').filter(c => c.trim()).length,
        cookieNames: document.cookie.split(';').map(c => c.trim().split('=')[0]).filter(Boolean),
        localStorageSize: (() => {
            try {
                return Object.keys(localStorage).reduce((acc, key) =>
                    acc + key.length + localStorage[key].length, 0);
            } catch (e) { return 0; }
        })(),
        localStorageKeys: (() => {
            try { return Object.keys(localStorage); } catch (e) { return []; }
        })(),
        sessionStorageSize: (() => {
            try {
                return Object.keys(sessionStorage).reduce((acc, key) =>
                    acc + key.length + sessionStorage[key].length, 0);
            } catch (e) { return 0; }
        })(),
        sessionStorageKeys: (() => {
            try { return Object.keys(sessionStorage); } catch (e) { return []; }
        })(),
        hasServiceWorker: 'serviceWorker' in navigator
    })
    """
    result = client.execute(code)
    if result.get("ok"):
        return result.get("result", {})
    raise RuntimeError(result.get("error", "Failed to collect storage data"))


def _collect_tech_data(client: BridgeClient) -> dict:
    """Collect detected technologies: frameworks, CMS, analytics."""
    code = """
    (function() {
        const detected = {};

        const addTech = (category, name, version = null) => {
            if (!detected[category]) detected[category] = [];
            const tech = version ? name + ' ' + version : name;
            if (!detected[category].includes(tech)) {
                detected[category].push(tech);
            }
        };

        // JavaScript Frameworks
        if (window.React || document.querySelector('[data-reactroot], [data-reactid]')) {
            addTech('JavaScript Framework', 'React', window.React?.version);
        }
        if (window.Vue) addTech('JavaScript Framework', 'Vue.js', window.Vue?.version);
        if (window.angular || document.querySelector('[ng-app], [ng-version]')) {
            const ngVersion = document.querySelector('[ng-version]')?.getAttribute('ng-version');
            addTech('JavaScript Framework', 'Angular', ngVersion);
        }
        if (window.Svelte) addTech('JavaScript Framework', 'Svelte');
        if (window.jQuery) addTech('JavaScript Library', 'jQuery', window.jQuery?.fn?.jquery);
        if (window._) addTech('JavaScript Library', 'Lodash/Underscore');
        if (window.moment) addTech('JavaScript Library', 'Moment.js');
        if (window.THREE) addTech('JavaScript Library', 'Three.js');
        if (window.d3) addTech('JavaScript Library', 'D3.js');
        if (window.Chart) addTech('JavaScript Library', 'Chart.js');
        if (window.Alpine) addTech('JavaScript Framework', 'Alpine.js');
        if (window.htmx) addTech('JavaScript Library', 'htmx');
        if (document.querySelector('#__next')) addTech('JavaScript Framework', 'Next.js');
        if (document.querySelector('#__nuxt')) addTech('JavaScript Framework', 'Nuxt.js');

        // CMS
        const generator = document.querySelector('meta[name="generator"]')?.content;
        if (generator) {
            if (generator.includes('WordPress')) addTech('CMS', 'WordPress', generator.match(/WordPress ([\\d.]+)/)?.[1]);
            if (generator.includes('Drupal')) addTech('CMS', 'Drupal', generator.match(/Drupal ([\\d.]+)/)?.[1]);
            if (generator.includes('Joomla')) addTech('CMS', 'Joomla');
            if (generator.includes('Ghost')) addTech('CMS', 'Ghost');
        }
        if (window.Shopify || document.querySelector('link[href*="shopify"]')) addTech('CMS', 'Shopify');
        if (document.querySelector('meta[content*="Wix.com"]')) addTech('CMS', 'Wix');
        if (document.querySelector('script[src*="squarespace"]')) addTech('CMS', 'Squarespace');
        if (document.querySelector('meta[name="notion-site"]')) addTech('CMS', 'Notion');

        // Analytics
        if (window.ga || window.gtag || window.google_tag_manager) addTech('Analytics', 'Google Analytics');
        if (window.dataLayer) addTech('Tag Manager', 'Google Tag Manager');
        if (window.fbq) addTech('Analytics', 'Facebook Pixel');
        if (window.hj) addTech('Analytics', 'Hotjar');
        if (window.mixpanel) addTech('Analytics', 'Mixpanel');
        if (window.analytics && window.analytics.initialize) addTech('Analytics', 'Segment');
        if (window._paq) addTech('Analytics', 'Matomo/Piwik');
        if (window.plausible) addTech('Analytics', 'Plausible');
        if (window.fathom) addTech('Analytics', 'Fathom');

        // CSS Frameworks
        const allClasses = Array.from(document.querySelectorAll('[class]')).map(el => el.className).join(' ');
        if (document.querySelector('link[href*="bootstrap"]') || /\\bbs-|\\bbtn-|\\bcol-/.test(allClasses)) {
            addTech('CSS Framework', 'Bootstrap');
        }
        if (/\\btw-|\\bflex|\\bgrid|\\bbg-|\\btext-/.test(allClasses) && document.querySelector('script[src*="tailwind"]')) {
            addTech('CSS Framework', 'Tailwind CSS');
        }
        if (window.MaterialUI || document.querySelector('[class*="MuiButton"]')) addTech('CSS Framework', 'Material-UI');
        if (document.querySelector('link[href*="bulma"]')) addTech('CSS Framework', 'Bulma');
        if (document.querySelector('link[href*="foundation"]')) addTech('CSS Framework', 'Foundation');

        // Font Services
        if (document.querySelector('link[href*="fonts.googleapis.com"]')) addTech('Font Service', 'Google Fonts');
        if (document.querySelector('link[href*="typekit"], script[src*="typekit"]')) addTech('Font Service', 'Adobe Fonts');

        // CDN
        const scripts = Array.from(document.scripts).map(s => s.src);
        if (scripts.some(s => s.includes('cloudflare'))) addTech('CDN', 'Cloudflare');
        if (scripts.some(s => s.includes('fastly'))) addTech('CDN', 'Fastly');
        if (scripts.some(s => s.includes('jsdelivr'))) addTech('CDN', 'jsDelivr');
        if (scripts.some(s => s.includes('unpkg'))) addTech('CDN', 'unpkg');
        if (scripts.some(s => s.includes('cdnjs'))) addTech('CDN', 'cdnjs');

        // Payment
        if (window.Stripe) addTech('Payment', 'Stripe');
        if (window.paypal) addTech('Payment', 'PayPal');
        if (window.Square) addTech('Payment', 'Square');

        return detected;
    })()
    """
    result = client.execute(code)
    if result.get("ok"):
        return result.get("result", {})
    raise RuntimeError(result.get("error", "Failed to collect tech data"))


def _collect_layout_data(client: BridgeClient) -> dict:
    """Collect layout data: viewport, document size, scroll position."""
    code = """
    ({
        viewportWidth: window.innerWidth,
        viewportHeight: window.innerHeight,
        documentWidth: document.documentElement.scrollWidth,
        documentHeight: document.documentElement.scrollHeight,
        scrollX: window.scrollX,
        scrollY: window.scrollY,
        visiblePercentage: Math.min(100, (window.innerHeight / document.documentElement.scrollHeight * 100))
    })
    """
    result = client.execute(code)
    if result.get("ok"):
        return result.get("result", {})
    raise RuntimeError(result.get("error", "Failed to collect layout data"))


# =============================================================================
# Server-side Data Collection Functions
# =============================================================================


def _get_domain_metrics(domain: str) -> dict | None:
    """Fetch domain metrics: IP, geolocation, WHOIS, SSL info."""
    if not domain or domain == "N/A":
        return None

    import datetime
    import socket
    import ssl

    import requests

    metrics = {}

    try:
        # Get IP address
        try:
            ip = socket.gethostbyname(domain)
            metrics["ip"] = ip

            # Get geolocation
            try:
                geo_response = requests.get(f"http://ip-api.com/json/{ip}", timeout=3)
                if geo_response.status_code == 200:
                    geo_data = geo_response.json()
                    if geo_data.get("status") == "success":
                        metrics["geolocation"] = {
                            "country": geo_data.get("country"),
                            "region": geo_data.get("regionName"),
                            "city": geo_data.get("city"),
                            "isp": geo_data.get("isp"),
                            "org": geo_data.get("org"),
                        }
            except Exception:
                pass
        except socket.gaierror:
            pass

        # Get SSL certificate info
        try:
            context = ssl.create_default_context()
            with socket.create_connection((domain, 443), timeout=3) as sock:
                with context.wrap_socket(sock, server_hostname=domain) as ssock:
                    cert = ssock.getpeercert()

                    issuer = dict(x[0] for x in cert.get("issuer", []))
                    issuer_name = issuer.get("organizationName", issuer.get("commonName", "Unknown"))

                    not_after = cert.get("notAfter")
                    if not_after:
                        expiry_date = datetime.datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
                        days_remaining = (expiry_date - datetime.datetime.now()).days

                        metrics["ssl"] = {
                            "issuer": issuer_name,
                            "expiry": expiry_date.strftime("%Y-%m-%d"),
                            "days_remaining": days_remaining,
                        }
        except Exception:
            pass

        # Get WHOIS info
        try:
            import whois

            w = whois.whois(domain)
            whois_data = {}

            creation_date = w.creation_date
            if isinstance(creation_date, list):
                creation_date = creation_date[0]
            if creation_date:
                whois_data["creation_date"] = (
                    creation_date.strftime("%Y-%m-%d") if hasattr(creation_date, "strftime") else str(creation_date)
                )

            expiration_date = w.expiration_date
            if isinstance(expiration_date, list):
                expiration_date = expiration_date[0]
            if expiration_date:
                whois_data["expiration_date"] = (
                    expiration_date.strftime("%Y-%m-%d")
                    if hasattr(expiration_date, "strftime")
                    else str(expiration_date)
                )

            if w.registrar:
                whois_data["registrar"] = (
                    w.registrar
                    if isinstance(w.registrar, str)
                    else w.registrar[0] if isinstance(w.registrar, list) else str(w.registrar)
                )

            if whois_data:
                metrics["whois"] = whois_data
        except ImportError:
            pass
        except Exception:
            pass

    except Exception:
        pass

    return metrics if metrics else None


def _get_response_headers(url: str) -> dict | None:
    """Fetch HTTP response headers from the given URL."""
    try:
        import requests

        response = requests.head(url, timeout=3, allow_redirects=True)
        headers = dict(response.headers)

        return {
            "server": headers.get("Server"),
            "cacheControl": headers.get("Cache-Control"),
            "contentEncoding": headers.get("Content-Encoding"),
            "etag": headers.get("ETag"),
            "lastModified": headers.get("Last-Modified"),
            "contentType": headers.get("Content-Type"),
            "xFrameOptions": headers.get("X-Frame-Options"),
            "xContentTypeOptions": headers.get("X-Content-Type-Options"),
            "strictTransportSecurity": headers.get("Strict-Transport-Security"),
            "contentSecurityPolicy": headers.get("Content-Security-Policy"),
            "permissionsPolicy": headers.get("Permissions-Policy"),
            "referrerPolicy": headers.get("Referrer-Policy"),
            "xXssProtection": headers.get("X-XSS-Protection"),
        }
    except Exception:
        return None


def _get_robots_txt(url: str) -> dict | None:
    """Fetch and parse robots.txt for the given URL."""
    try:
        import requests

        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

        response = requests.get(robots_url, timeout=3)
        if response.status_code == 200:
            content = response.text
            lines = content.split("\n")

            result = {
                "exists": True,
                "url": robots_url,
                "size": len(content),
                "lines": len(lines),
                "userAgents": [],
                "sitemaps": [],
                "disallowRules": 0,
                "allowRules": 0,
            }

            for line in lines:
                line = line.strip()
                if line.startswith("User-agent:"):
                    agent = line.split(":", 1)[1].strip()
                    if agent and agent not in result["userAgents"]:
                        result["userAgents"].append(agent)
                elif line.startswith("Disallow:"):
                    result["disallowRules"] += 1
                elif line.startswith("Allow:"):
                    result["allowRules"] += 1
                elif line.startswith("Sitemap:"):
                    sitemap = line.split(":", 1)[1].strip()
                    if sitemap:
                        result["sitemaps"].append(sitemap)

            return result
        else:
            return {"exists": False, "status": response.status_code}

    except Exception as e:
        return {"exists": False, "error": str(e)}


# =============================================================================
# Print Functions for Each Category
# =============================================================================


def _print_summary(data: dict, version: str, bridge_type: str, browser: str) -> None:
    """Print summary output."""
    bridge_label = "Extension" if bridge_type == "extension" else "Userscript"
    protocol = data.get("protocol", "N/A")
    is_local_file = protocol == "file:"

    title = data.get("title", "")
    if not title or title.strip() == "":
        title = "-"
    else:
        title = _truncate_value(title)

    domain = data.get("domain", "N/A")
    if is_local_file or not domain:
        domain = "-"

    basic_rows = [
        ("Extension", f"v{version} ({browser} {bridge_label})", None),
        ("URL", _truncate_value(data.get("url", "N/A")), None),
        ("Title", title, None),
        ("Domain", domain, None),
        ("Protocol", protocol, "green" if data.get("isSecure") else None),
        ("Viewport", f"{data.get('width', 'N/A')}x{data.get('height', 'N/A')}", None),
    ]
    _print_info_table("Summary", basic_rows)

    # Device info
    device = data.get("device", {})
    if device:
        device_rows = [
            ("Platform", device.get("platform", "N/A"), None),
            ("Language", device.get("language", "N/A"), None),
            ("Screen", device.get("screenResolution", "N/A"), None),
            ("Pixel Ratio", str(device.get("devicePixelRatio", "N/A")), None),
            ("Touch Support", "Yes" if device.get("touchSupport") else "No", None),
            ("Cookies", str(data.get("cookieCount", 0)), None),
        ]
        _print_info_table("Browser/Device", device_rows)


def _print_performance(data: dict) -> None:
    """Print performance output."""
    perf_rows = []

    if data.get("timeToFirstByte"):
        perf_rows.append(("Time to First Byte", f"{data['timeToFirstByte']}ms", None))
    if data.get("firstPaint"):
        perf_rows.append(("First Paint", f"{data['firstPaint']}ms", None))
    if data.get("firstContentfulPaint"):
        perf_rows.append(("First Contentful Paint", f"{data['firstContentfulPaint']}ms", None))
    if data.get("domContentLoaded"):
        perf_rows.append(("DOM Content Loaded", f"{data['domContentLoaded']}ms", None))
    if data.get("largestContentfulPaint"):
        perf_rows.append(("Largest Contentful Paint", f"{data['largestContentfulPaint']}ms", None))
    if data.get("pageLoadTime"):
        perf_rows.append(("Page Load Time", f"{data['pageLoadTime']}ms", None))

    if perf_rows:
        _print_info_table("Performance Metrics", perf_rows)

    # Core Web Vitals
    cwv_rows = []

    if "cls" in data:
        cls_val = float(data["cls"])
        if cls_val < 0.1:
            cls_status, cls_color = "Good", "green"
        elif cls_val < 0.25:
            cls_status, cls_color = "Needs Improvement", "yellow"
        else:
            cls_status, cls_color = "Poor", "red"
        cwv_rows.append(("CLS", f"{data['cls']:.3f} ({cls_status})", cls_color))

    if "fid" in data:
        fid_val = int(data["fid"])
        if fid_val < 100:
            fid_status, fid_color = "Good", "green"
        elif fid_val < 300:
            fid_status, fid_color = "Needs Improvement", "yellow"
        else:
            fid_status, fid_color = "Poor", "red"
        cwv_rows.append(("FID", f"{data['fid']}ms ({fid_status})", fid_color))

    if "inp" in data:
        inp_val = int(data["inp"])
        if inp_val < 200:
            inp_status, inp_color = "Good", "green"
        elif inp_val < 500:
            inp_status, inp_color = "Needs Improvement", "yellow"
        else:
            inp_status, inp_color = "Poor", "red"
        cwv_rows.append(("INP", f"{data['inp']}ms ({inp_status})", inp_color))

    if cwv_rows:
        _print_info_table("Core Web Vitals", cwv_rows)


def _print_meta(data: dict) -> None:
    """Print meta tags output."""
    lang_rows = [
        ("Declared Language", data.get("specifiedLanguage") or "Not set", None),
        ("Character Set", data.get("charset") or "N/A", None),
    ]
    _print_info_table("Language & Encoding", lang_rows)

    # Open Graph
    og = data.get("openGraph", {})
    if og:
        og_rows = []
        for key in ["title", "type", "image", "url", "description", "site_name"]:
            if key in og:
                og_rows.append((f"og:{key}", _truncate_value(og[key], 50), None))
        if og_rows:
            _print_info_table(f"Open Graph ({len(og)} tags)", og_rows)

    # Twitter Card
    twitter = data.get("twitterCard", {})
    if twitter:
        twitter_rows = []
        for key in ["card", "title", "description", "image", "site", "creator"]:
            if key in twitter:
                twitter_rows.append((f"twitter:{key}", _truncate_value(twitter[key], 50), None))
        if twitter_rows:
            _print_info_table(f"Twitter Card ({len(twitter)} tags)", twitter_rows)

    # All meta tags
    meta_tags = data.get("metaTags", [])
    if meta_tags:
        meta_rows = []
        for meta in meta_tags:
            if "name" in meta and "content" in meta:
                meta_rows.append((meta["name"], _truncate_value(meta["content"]), None))
            elif "property" in meta and "content" in meta:
                meta_rows.append((meta["property"], _truncate_value(meta["content"]), None))
            elif "charset" in meta:
                meta_rows.append(("charset", meta["charset"], None))
            elif "http-equiv" in meta:
                meta_rows.append((meta["http-equiv"], meta.get("content", ""), None))
        if meta_rows:
            _print_info_table(f"Meta Tags ({len(meta_tags)})", meta_rows)


def _print_seo(data: dict, robots_data: dict | None) -> None:
    """Print SEO output."""
    seo_rows = []

    if data.get("canonical"):
        seo_rows.append(("Canonical", _truncate_value(data["canonical"]), None))
    if data.get("description"):
        seo_rows.append(("Description", _truncate_value(data["description"]), None))
    if data.get("keywords"):
        seo_rows.append(("Keywords", _truncate_value(data["keywords"]), None))
    if data.get("robots"):
        seo_rows.append(("Robots", data["robots"], None))
    if data.get("favicon"):
        seo_rows.append(("Favicon", data["favicon"], None))
    if data.get("sitemap"):
        seo_rows.append(("Sitemap Link", _truncate_value(data["sitemap"], 50), None))

    alt_langs = data.get("alternateLanguages", [])
    if alt_langs:
        lang_list = ", ".join([lang["lang"] for lang in alt_langs[:3]])
        if len(alt_langs) > 3:
            lang_list += f" (+{len(alt_langs) - 3} more)"
        seo_rows.append(("Alternate Languages", lang_list, None))

    if seo_rows:
        _print_info_table("SEO", seo_rows)

    # Structured Data
    json_ld = data.get("jsonLd", [])
    microdata = data.get("microdataCount", 0)
    if json_ld or microdata > 0:
        struct_rows = []
        if json_ld:
            type_info = f" ({', '.join(json_ld[:5])})" if json_ld else ""
            struct_rows.append(("JSON-LD", f"{len(json_ld)} blocks{type_info}", None))
        if microdata > 0:
            struct_rows.append(("Microdata", f"{microdata} items", None))
        _print_info_table("Structured Data", struct_rows)

    # Robots.txt
    if robots_data and robots_data.get("exists"):
        robots_rows = [
            ("Status", "Found", "green"),
            ("Size", f"{robots_data['size']:,} bytes ({robots_data['lines']} lines)", None),
        ]
        if robots_data.get("userAgents"):
            agents = robots_data["userAgents"]
            if len(agents) <= 3:
                robots_rows.append(("User-agents", ", ".join(agents), None))
            else:
                robots_rows.append(("User-agents", f"{len(agents)} defined", None))
        if robots_data.get("disallowRules", 0) > 0:
            robots_rows.append(("Disallow rules", str(robots_data["disallowRules"]), None))
        if robots_data.get("allowRules", 0) > 0:
            robots_rows.append(("Allow rules", str(robots_data["allowRules"]), None))
        if robots_data.get("sitemaps"):
            sitemaps = robots_data["sitemaps"]
            robots_rows.append(("Sitemaps", f"{len(sitemaps)} declared", None))
        _print_info_table("Robots.txt", robots_rows)
    elif robots_data and not robots_data.get("exists"):
        _print_info_table("Robots.txt", [("Status", "Not found", "yellow")])


def _print_security(data: dict, headers: dict | None) -> None:
    """Print security output."""
    sec_rows = []

    https_status = "Yes" if data.get("isSecure") else "No"
    https_color = "green" if data.get("isSecure") else "red"
    sec_rows.append(("HTTPS", https_status, https_color))

    if data.get("isSecure") and data.get("hasMixedContent"):
        sec_rows.append(("Mixed Content", "Warning - Insecure resources detected", "yellow"))

    if data.get("cspMeta"):
        sec_rows.append(("CSP Meta", _truncate_value(data["cspMeta"], 50), None))

    if data.get("referrerPolicy"):
        sec_rows.append(("Referrer Policy", data["referrerPolicy"], None))

    if sec_rows:
        _print_info_table("Security", sec_rows)

    # Security Headers
    if headers:
        security_headers = {
            "xFrameOptions": "X-Frame-Options",
            "xContentTypeOptions": "X-Content-Type-Options",
            "strictTransportSecurity": "Strict-Transport-Security",
            "contentSecurityPolicy": "Content-Security-Policy",
            "permissionsPolicy": "Permissions-Policy",
            "referrerPolicy": "Referrer-Policy",
            "xXssProtection": "X-XSS-Protection",
        }

        sec_header_rows = []
        for key, label in security_headers.items():
            value = headers.get(key)
            if value:
                sec_header_rows.append((label, _truncate_value(value, 55), None))
        if sec_header_rows:
            _print_info_table("Security Headers", sec_header_rows)

        # Response Headers
        response_headers = {
            "server": "Server",
            "cacheControl": "Cache-Control",
            "contentEncoding": "Content-Encoding",
            "etag": "ETag",
            "lastModified": "Last-Modified",
            "contentType": "Content-Type",
        }

        resp_header_rows = []
        for key, label in response_headers.items():
            value = headers.get(key)
            if value:
                resp_header_rows.append((label, _truncate_value(value, 55), None))
        if resp_header_rows:
            _print_info_table("Response Headers", resp_header_rows)


def _print_accessibility(data: dict) -> None:
    """Print accessibility output."""
    a11y_rows = []

    # Landmarks
    landmarks = data.get("landmarks", {})
    if landmarks:
        landmark_summary = ", ".join([f"{role}: {count}" for role, count in landmarks.items()])
        a11y_rows.append(("Landmarks", f"{data.get('landmarkCount', 0)} total ({landmark_summary})", None))
    else:
        a11y_rows.append(("Landmarks", f"{data.get('landmarkCount', 0)} total", None))

    # Headings
    heading_structure = data.get("headingStructure", {})
    total_headings = sum(heading_structure.values())
    if total_headings > 0:
        heading_parts = [
            f"{level.upper()}: {heading_structure.get(level, 0)}"
            for level in ["h1", "h2", "h3", "h4", "h5", "h6"]
            if heading_structure.get(level, 0) > 0
        ]
        a11y_rows.append(("Headings", f"{total_headings} total ({', '.join(heading_parts)})", None))

    # Lang attribute
    if data.get("hasLangAttribute"):
        a11y_rows.append(("Lang Attribute", "Present", "green"))
    else:
        a11y_rows.append(("Lang Attribute", "Missing", "yellow"))

    # Skip link
    if data.get("hasSkipLink"):
        a11y_rows.append(("Skip Link", "Present", "green"))

    # ARIA usage
    if data.get("ariaAttributeCount"):
        a11y_rows.append(("ARIA Usage", f"{data['ariaAttributeCount']} attributes", None))

    if a11y_rows:
        _print_info_table("Accessibility", a11y_rows)

    # Issues
    issue_rows = []

    img_no_alt = data.get("imagesWithoutAlt", 0)
    total_images = data.get("totalImages", 0)
    if img_no_alt > 0:
        issue_rows.append(("Images without alt", f"{img_no_alt}/{total_images}", "yellow"))

    form_issues = data.get("formLabelsIssues", {})
    if form_issues.get("missingLabels", 0) > 0:
        issue_rows.append(
            ("Form inputs without labels", f"{form_issues['missingLabels']}/{form_issues['total']}", "yellow")
        )

    if data.get("linksWithoutText", 0) > 0:
        issue_rows.append(("Links without text", str(data["linksWithoutText"]), "yellow"))

    if data.get("buttonsWithoutLabels", 0) > 0:
        issue_rows.append(("Buttons without labels", str(data["buttonsWithoutLabels"]), "yellow"))

    if issue_rows:
        _print_info_table("Accessibility Issues", issue_rows)
        click.echo(click.style("  Hint: Run `inspekt axe` for detailed accessibility analysis.", fg="bright_black"))

    # Forms
    forms = data.get("forms", [])
    if forms:
        form_list_rows = []
        form_colors = []
        for form in forms:
            issues = len(form.get("issues", []))
            action = _truncate_value(form["action"], 30) if form["action"] and form["action"] != "JavaScript" else "-"
            issue_text = str(issues) if issues > 0 else "0"
            form_list_rows.append([form["id"], form["method"], action, str(form["fieldCount"]), issue_text])
            form_colors.append([None, None, None, None, "yellow" if issues > 0 else None])
        _print_list_table(
            f"Forms ({len(forms)})", ["ID", "Method", "Action", "Fields", "Issues"], form_list_rows, [20, 8, 25, 8, 8], form_colors
        )


def _print_resources(data: dict) -> None:
    """Print resources output."""
    resource_rows = [
        ("Scripts", str(data.get("scriptCount", 0)), None),
        ("Stylesheets", str(data.get("stylesheetCount", 0)), None),
        ("Images", str(data.get("imageCount", 0)), None),
        ("Links", str(data.get("linkCount", 0)), None),
        ("Forms", str(data.get("formCount", 0)), None),
        ("Iframes", str(data.get("iframeCount", 0)), None),
    ]
    _print_info_table("Resources", resource_rows)

    # Media
    media_rows = []
    if data.get("videos", 0) > 0:
        media_rows.append(("Videos", str(data["videos"]), None))
    if data.get("audio", 0) > 0:
        media_rows.append(("Audio", str(data["audio"]), None))
    if data.get("svgImages", 0) > 0:
        media_rows.append(("SVG Images", str(data["svgImages"]), None))
    if media_rows:
        _print_info_table("Media", media_rows)

    # Fonts
    fonts = data.get("fonts", {})
    if fonts and (fonts.get("googleFonts") or fonts.get("customFonts") or fonts.get("totalFontFiles", 0) > 0):
        font_rows = []
        google_fonts = fonts.get("googleFonts", [])
        if google_fonts:
            font_list = ", ".join(google_fonts[:5])
            if len(google_fonts) > 5:
                font_list += f" (+{len(google_fonts) - 5} more)"
            font_rows.append(("Google Fonts", f"{len(google_fonts)}: {font_list}", None))
        custom_fonts = fonts.get("customFonts", [])
        if custom_fonts:
            custom_list = ", ".join(custom_fonts[:5])
            if len(custom_fonts) > 5:
                custom_list += f" (+{len(custom_fonts) - 5} more)"
            font_rows.append(("Custom @font-face", f"{len(custom_fonts)}: {custom_list}", None))
        if fonts.get("totalFontFiles", 0) > 0:
            font_rows.append(("Font Files", str(fonts["totalFontFiles"]), None))
        if font_rows:
            _print_info_table("Fonts", font_rows)

    # Third-party
    third_party = data.get("thirdParty", {})
    if third_party and third_party.get("externalDomainCount", 0) > 0:
        domains = third_party.get("externalDomains", [])
        third_party_rows = [("External Domains", str(third_party["externalDomainCount"]), None)]
        if domains:
            domain_list = ", ".join(domains[:5])
            if len(domains) > 5:
                domain_list += f" (+{len(domains) - 5} more)"
            third_party_rows.append(("Domains", domain_list, None))
        _print_info_table("Third-Party Resources", third_party_rows)

    # Network
    network = data.get("network")
    if network:
        network_rows = []
        if network.get("totalRequests"):
            network_rows.append(("Total Requests", str(network["totalRequests"]), None))
        if network.get("totalSize"):
            size_mb = network["totalSize"] / (1024 * 1024)
            network_rows.append(("Total Size", f"{size_mb:.2f} MB", None))
        largest = network.get("largestResource")
        if largest:
            size_kb = largest["size"] / 1024
            network_rows.append(("Largest Resource", f"{largest['name']} ({size_kb:.2f} KB)", None))
        if network_rows:
            _print_info_table("Network", network_rows)


def _print_storage(data: dict) -> None:
    """Print storage output."""

    def format_size(kb: float) -> str:
        if kb < 0.01:
            return "Empty"
        return f"{kb:.2f} KB"

    storage_rows = [
        ("Cookies", str(data.get("cookieCount", 0)) if data.get("cookieCount", 0) > 0 else "None", None),
        ("LocalStorage", format_size(data.get("localStorageSize", 0) / 1024), None),
        ("SessionStorage", format_size(data.get("sessionStorageSize", 0) / 1024), None),
        ("Service Worker", "Yes" if data.get("hasServiceWorker") else "No", None),
    ]
    _print_info_table("Storage", storage_rows)

    # Cookie names
    cookie_names = data.get("cookieNames", [])
    if cookie_names:
        cookie_list_rows = [[name] for name in cookie_names[:8]]
        if len(cookie_names) > 8:
            cookie_list_rows.append([f"... and {len(cookie_names) - 8} more"])
        _print_list_table("Cookie Names", ["Name"], cookie_list_rows, [55])

    # LocalStorage keys
    ls_keys = data.get("localStorageKeys", [])
    if ls_keys:
        ls_list_rows = [[key] for key in ls_keys[:8]]
        if len(ls_keys) > 8:
            ls_list_rows.append([f"... and {len(ls_keys) - 8} more"])
        _print_list_table("LocalStorage Keys", ["Key"], ls_list_rows, [55])

    # SessionStorage keys
    ss_keys = data.get("sessionStorageKeys", [])
    if ss_keys:
        ss_list_rows = [[key] for key in ss_keys[:8]]
        if len(ss_keys) > 8:
            ss_list_rows.append([f"... and {len(ss_keys) - 8} more"])
        _print_list_table("SessionStorage Keys", ["Key"], ss_list_rows, [55])


def _print_tech(data: dict) -> None:
    """Print technologies output."""
    if not data:
        click.echo("\nNo technologies detected.")
        return

    tech_rows = []
    for category, techs in sorted(data.items()):
        if techs:
            tech_list = ", ".join(techs[:5])
            if len(techs) > 5:
                tech_list += f" (+{len(techs) - 5} more)"
            tech_rows.append((category, tech_list, None))

    if tech_rows:
        _print_info_table("Technologies Detected", tech_rows)
    else:
        click.echo("\nNo technologies detected.")


def _print_domain(metrics: dict | None) -> None:
    """Print domain metrics output."""
    if not metrics:
        click.echo("\nNo domain metrics available.")
        return

    domain_rows = []

    if metrics.get("ip"):
        domain_rows.append(("IP Address", metrics["ip"], None))

    geo = metrics.get("geolocation", {})
    if geo:
        location_parts = [geo.get("city"), geo.get("region"), geo.get("country")]
        location = ", ".join([p for p in location_parts if p])
        if location:
            domain_rows.append(("Location", location, None))
        if geo.get("isp"):
            domain_rows.append(("ISP", geo["isp"], None))
        if geo.get("org"):
            domain_rows.append(("Organization", geo["org"], None))

    ssl_info = metrics.get("ssl", {})
    if ssl_info:
        if ssl_info.get("issuer"):
            domain_rows.append(("SSL Issuer", ssl_info["issuer"], None))
        if ssl_info.get("expiry"):
            domain_rows.append(("SSL Expires", ssl_info["expiry"], None))
        if ssl_info.get("days_remaining"):
            days = ssl_info["days_remaining"]
            if days < 30:
                domain_rows.append(("SSL Status", f"Expires in {days} days", "yellow"))
            else:
                domain_rows.append(("SSL Status", f"Valid ({days} days remaining)", "green"))

    whois = metrics.get("whois", {})
    if whois:
        if whois.get("creation_date"):
            domain_rows.append(("Registered", whois["creation_date"], None))
        if whois.get("expiration_date"):
            domain_rows.append(("Expires", whois["expiration_date"], None))
        if whois.get("registrar"):
            domain_rows.append(("Registrar", whois["registrar"], None))

    if domain_rows:
        _print_info_table("Domain Metrics", domain_rows)
    else:
        click.echo("\nNo domain metrics available.")


def _print_layout(data: dict) -> None:
    """Print layout output."""
    layout_rows = [
        ("Viewport", f"{data.get('viewportWidth', 'N/A')}x{data.get('viewportHeight', 'N/A')}px", None),
        ("Document Size", f"{data.get('documentWidth', 'N/A')}x{data.get('documentHeight', 'N/A')}px", None),
        ("Scroll Position", f"X: {data.get('scrollX', 0)}, Y: {data.get('scrollY', 0)}", None),
        ("Visible", f"{data.get('visiblePercentage', 100):.0f}% of page height", None),
    ]
    _print_info_table("Layout", layout_rows)


# =============================================================================
# Command Group and Subcommands
# =============================================================================


@click.group(invoke_without_command=True)
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.pass_context
def info(ctx, output_json):
    """
    Page information and analysis.

    Without a subcommand, shows a brief summary. Use subcommands for detailed info:

    \b
      inspekt info              Brief summary with browser/device info
      inspekt info all          Complete output (all categories)
      inspekt info performance  Load times and Core Web Vitals
      inspekt info meta         Meta tags, Open Graph, Twitter Card
      inspekt info seo          SEO analysis including robots.txt
      inspekt info security     HTTPS status, security headers
      inspekt info accessibility A11y analysis, headings, landmarks
      inspekt info resources    Scripts, stylesheets, media, fonts
      inspekt info storage      Cookies, localStorage, sessionStorage
      inspekt info tech         Detected frameworks and technologies
      inspekt info domain       IP, SSL cert, WHOIS (server-side)
      inspekt info layout       Viewport, document size, scroll
    """
    ctx.ensure_object(dict)
    ctx.obj["output_json"] = output_json

    if ctx.invoked_subcommand is None:
        # Default: show summary
        try:
            client = _get_bridge_client()
            data = _collect_summary_data(client)
            version, bridge_type, browser = _get_bridge_version(client)

            if output_json:
                data["bridgeVersion"] = version
                data["bridgeType"] = bridge_type
                data["browser"] = browser
                click.echo(json.dumps(data, indent=2))
            else:
                _print_summary(data, version, bridge_type, browser)

        except (ConnectionError, TimeoutError, RuntimeError) as e:
            if output_json:
                click.echo(json.dumps({"ok": False, "error": str(e)}))
            else:
                click.echo(f"Error: {e}", err=True)
            sys.exit(1)


@info.command(name="all")
@click.pass_context
def info_all(ctx):
    """Show all information categories."""
    output_json = ctx.obj.get("output_json", False)

    try:
        client = _get_bridge_client()
        version, bridge_type, browser = _get_bridge_version(client)
        basic = _get_basic_info(client)
        url = basic.get("url", "")
        domain = basic.get("domain", "")

        if output_json:
            all_data = {
                "bridgeVersion": version,
                "bridgeType": bridge_type,
                "browser": browser,
                "summary": _collect_summary_data(client),
                "performance": _collect_performance_data(client),
                "meta": _collect_meta_data(client),
                "seo": _collect_seo_data(client),
                "security": _collect_security_data(client),
                "accessibility": _collect_accessibility_data(client),
                "resources": _collect_resources_data(client),
                "storage": _collect_storage_data(client),
                "tech": _collect_tech_data(client),
                "layout": _collect_layout_data(client),
                "domain": _get_domain_metrics(domain),
                "responseHeaders": _get_response_headers(url),
                "robotsTxt": _get_robots_txt(url),
            }
            click.echo(json.dumps(all_data, indent=2))
        else:
            # Print all sections
            summary_data = _collect_summary_data(client)
            _print_summary(summary_data, version, bridge_type, browser)

            perf_data = _collect_performance_data(client)
            _print_performance(perf_data)

            meta_data = _collect_meta_data(client)
            _print_meta(meta_data)

            seo_data = _collect_seo_data(client)
            robots_data = _get_robots_txt(url)
            _print_seo(seo_data, robots_data)

            security_data = _collect_security_data(client)
            headers = _get_response_headers(url)
            _print_security(security_data, headers)

            a11y_data = _collect_accessibility_data(client)
            _print_accessibility(a11y_data)

            resources_data = _collect_resources_data(client)
            _print_resources(resources_data)

            storage_data = _collect_storage_data(client)
            _print_storage(storage_data)

            tech_data = _collect_tech_data(client)
            _print_tech(tech_data)

            layout_data = _collect_layout_data(client)
            _print_layout(layout_data)

            domain_metrics = _get_domain_metrics(domain)
            _print_domain(domain_metrics)

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        if output_json:
            click.echo(json.dumps({"ok": False, "error": str(e)}))
        else:
            click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@info.command(name="performance")
@click.pass_context
def info_performance(ctx):
    """Performance metrics and Core Web Vitals."""
    output_json = ctx.obj.get("output_json", False)

    try:
        client = _get_bridge_client()
        data = _collect_performance_data(client)

        if output_json:
            click.echo(json.dumps(data, indent=2))
        else:
            _print_performance(data)

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        if output_json:
            click.echo(json.dumps({"ok": False, "error": str(e)}))
        else:
            click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@info.command(name="meta")
@click.pass_context
def info_meta(ctx):
    """Meta tags, Open Graph, Twitter Card, language, encoding."""
    output_json = ctx.obj.get("output_json", False)

    try:
        client = _get_bridge_client()
        data = _collect_meta_data(client)

        if output_json:
            click.echo(json.dumps(data, indent=2))
        else:
            _print_meta(data)

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        if output_json:
            click.echo(json.dumps({"ok": False, "error": str(e)}))
        else:
            click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@info.command(name="seo")
@click.pass_context
def info_seo(ctx):
    """SEO analysis including robots.txt."""
    output_json = ctx.obj.get("output_json", False)

    try:
        client = _get_bridge_client()
        data = _collect_seo_data(client)
        basic = _get_basic_info(client)
        robots_data = _get_robots_txt(basic.get("url", ""))

        if output_json:
            data["robotsTxt"] = robots_data
            click.echo(json.dumps(data, indent=2))
        else:
            _print_seo(data, robots_data)

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        if output_json:
            click.echo(json.dumps({"ok": False, "error": str(e)}))
        else:
            click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@info.command(name="security")
@click.pass_context
def info_security(ctx):
    """HTTPS status, security headers, response headers."""
    output_json = ctx.obj.get("output_json", False)

    try:
        client = _get_bridge_client()
        data = _collect_security_data(client)
        basic = _get_basic_info(client)
        headers = _get_response_headers(basic.get("url", ""))

        if output_json:
            data["responseHeaders"] = headers
            click.echo(json.dumps(data, indent=2))
        else:
            _print_security(data, headers)

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        if output_json:
            click.echo(json.dumps({"ok": False, "error": str(e)}))
        else:
            click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@info.command(name="accessibility")
@click.pass_context
def info_accessibility(ctx):
    """Accessibility analysis: landmarks, headings, forms, ARIA."""
    output_json = ctx.obj.get("output_json", False)

    try:
        client = _get_bridge_client()
        data = _collect_accessibility_data(client)

        if output_json:
            click.echo(json.dumps(data, indent=2))
        else:
            _print_accessibility(data)

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        if output_json:
            click.echo(json.dumps({"ok": False, "error": str(e)}))
        else:
            click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@info.command(name="resources")
@click.pass_context
def info_resources(ctx):
    """Scripts, stylesheets, images, media, fonts, network."""
    output_json = ctx.obj.get("output_json", False)

    try:
        client = _get_bridge_client()
        data = _collect_resources_data(client)

        if output_json:
            click.echo(json.dumps(data, indent=2))
        else:
            _print_resources(data)

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        if output_json:
            click.echo(json.dumps({"ok": False, "error": str(e)}))
        else:
            click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@info.command(name="storage")
@click.pass_context
def info_storage(ctx):
    """Cookies, localStorage, sessionStorage, service worker."""
    output_json = ctx.obj.get("output_json", False)

    try:
        client = _get_bridge_client()
        data = _collect_storage_data(client)

        if output_json:
            click.echo(json.dumps(data, indent=2))
        else:
            _print_storage(data)

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        if output_json:
            click.echo(json.dumps({"ok": False, "error": str(e)}))
        else:
            click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@info.command(name="tech")
@click.pass_context
def info_tech(ctx):
    """Detected frameworks, CMS, analytics, and technologies."""
    output_json = ctx.obj.get("output_json", False)

    try:
        client = _get_bridge_client()
        data = _collect_tech_data(client)

        if output_json:
            click.echo(json.dumps(data, indent=2))
        else:
            _print_tech(data)

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        if output_json:
            click.echo(json.dumps({"ok": False, "error": str(e)}))
        else:
            click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@info.command(name="domain")
@click.pass_context
def info_domain(ctx):
    """IP address, geolocation, SSL certificate, WHOIS data."""
    output_json = ctx.obj.get("output_json", False)

    try:
        client = _get_bridge_client()
        basic = _get_basic_info(client)
        domain = basic.get("domain", "")
        metrics = _get_domain_metrics(domain)

        if output_json:
            click.echo(json.dumps(metrics or {}, indent=2))
        else:
            _print_domain(metrics)

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        if output_json:
            click.echo(json.dumps({"ok": False, "error": str(e)}))
        else:
            click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@info.command(name="layout")
@click.pass_context
def info_layout(ctx):
    """Viewport, document size, scroll position."""
    output_json = ctx.obj.get("output_json", False)

    try:
        client = _get_bridge_client()
        data = _collect_layout_data(client)

        if output_json:
            click.echo(json.dumps(data, indent=2))
        else:
            _print_layout(data)

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        if output_json:
            click.echo(json.dumps({"ok": False, "error": str(e)}))
        else:
            click.echo(f"Error: {e}", err=True)
        sys.exit(1)
