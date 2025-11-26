"""
Utility CLI commands for Inspekt.

This module contains utility commands:
- info: Display page information
- repl: Interactive REPL
- userscript: Show userscript installation instructions
- download: Download page files
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from inspekt.app.cli.base import builtin_open, format_output
from inspekt.app.cli.exec import _format_console_entry, _get_console_logs_since
from inspekt.app.cli.table import Table
from inspekt.client import BridgeClient


def _print_info_table(title: str, rows: list[tuple[str, str, str | None]], key_width: int = 22, value_width: int = 55) -> None:
    """
    Print a key-value information table with consistent formatting.

    Args:
        title: Table section title (e.g., "Basic Information")
        rows: List of (key, value, color) tuples. Color can be None.
        key_width: Width for the key column
        value_width: Width for the value column
    """
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


def _print_list_table(title: str, headers: list[str], rows: list[list[str]], widths: list[int], colors: list[list[str | None]] | None = None) -> None:
    """
    Print a multi-column table for list-style data.

    Args:
        title: Table section title
        headers: Column headers
        rows: List of row data (each row is a list of column values)
        widths: Column widths
        colors: Optional list of color lists for each row
    """
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
    return value[:max_len - 3] + "..."


def _get_domain_metrics(domain):
    """Fetch domain metrics including IP, geolocation, WHOIS, and SSL info."""
    if not domain or domain == "N/A":
        return None

    metrics = {}

    try:
        import datetime
        import socket
        import ssl

        import requests

        # Get IP address
        try:
            ip = socket.gethostbyname(domain)
            metrics["ip"] = ip

            # Get geolocation from ip-api.com (free, no auth required)
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
                pass  # Geolocation is optional

        except socket.gaierror:
            pass  # Can't resolve domain

        # Get SSL certificate info
        try:
            context = ssl.create_default_context()
            with socket.create_connection((domain, 443), timeout=3) as sock:
                with context.wrap_socket(sock, server_hostname=domain) as ssock:
                    cert = ssock.getpeercert()

                    # Extract issuer
                    issuer = dict(x[0] for x in cert.get("issuer", []))
                    issuer_name = issuer.get(
                        "organizationName", issuer.get("commonName", "Unknown")
                    )

                    # Extract expiry date
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
            pass  # SSL info is optional

        # Get WHOIS info (try python-whois if available)
        try:
            import whois

            w = whois.whois(domain)
            whois_data = {}

            # Handle dates (can be lists or single values)
            creation_date = w.creation_date
            if isinstance(creation_date, list):
                creation_date = creation_date[0]
            if creation_date:
                whois_data["creation_date"] = (
                    creation_date.strftime("%Y-%m-%d")
                    if hasattr(creation_date, "strftime")
                    else str(creation_date)
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
                    else w.registrar[0]
                    if isinstance(w.registrar, list)
                    else str(w.registrar)
                )

            if whois_data:
                metrics["whois"] = whois_data
        except ImportError:
            pass  # python-whois not installed
        except Exception:
            pass  # WHOIS lookup failed

    except Exception:
        pass  # Return whatever metrics we managed to collect

    return metrics if metrics else None


def _get_response_headers(url):
    """Fetch HTTP response headers from the given URL."""
    try:
        import requests

        response = requests.head(url, timeout=3, allow_redirects=True)
        headers = dict(response.headers)

        # Extract key headers
        return {
            "server": headers.get("Server"),
            "cacheControl": headers.get("Cache-Control"),
            "contentEncoding": headers.get("Content-Encoding"),
            "etag": headers.get("ETag"),
            "lastModified": headers.get("Last-Modified"),
            "contentType": headers.get("Content-Type"),
            # Security headers
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


def _get_robots_txt(url):
    """Fetch and parse robots.txt for the given URL."""
    try:
        from urllib.parse import urlparse

        import requests

        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

        response = requests.get(robots_url, timeout=3)
        if response.status_code == 200:
            content = response.text
            lines = content.split("\n")

            # Parse key directives
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

            current_agent = None
            for line in lines:
                line = line.strip()
                if line.startswith("User-agent:"):
                    agent = line.split(":", 1)[1].strip()
                    if agent and agent not in result["userAgents"]:
                        result["userAgents"].append(agent)
                    current_agent = agent
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


@click.command()
@click.option(
    "--extended", is_flag=True, help="Show extended information (language, meta tags, cookies)"
)
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def info(extended, output_json):
    """Get information about the current browser tab."""
    client = BridgeClient()

    if extended:
        code = """
        ({
            url: location.href,
            title: document.title,
            domain: location.hostname,
            protocol: location.protocol,
            readyState: document.readyState,
            width: window.innerWidth,
            height: window.innerHeight,
            // Extended info
            specifiedLanguage: document.documentElement.lang || 'N/A',
            charset: document.characterSet || 'N/A',
            metaTags: Array.from(document.querySelectorAll('head meta')).map(meta => {
                const attrs = {};
                for (let attr of meta.attributes) {
                    attrs[attr.name] = attr.value;
                }
                return attrs;
            }),
            cookieCount: document.cookie.split(';').filter(c => c.trim()).length,
            // Additional useful info
            scriptCount: document.scripts.length,
            stylesheetCount: document.styleSheets.length,
            imageCount: document.images.length,
            linkCount: document.links.length,
            formCount: document.forms.length,
            iframeCount: document.querySelectorAll('iframe').length,
            scrollHeight: document.documentElement.scrollHeight,
            scrollWidth: document.documentElement.scrollWidth,
            hasServiceWorker: 'serviceWorker' in navigator,
            localStorageSize: (() => {
                try {
                    return Object.keys(localStorage).reduce((acc, key) =>
                        acc + key.length + localStorage[key].length, 0);
                } catch (e) {
                    return 0;
                }
            })(),
            sessionStorageSize: (() => {
                try {
                    return Object.keys(sessionStorage).reduce((acc, key) =>
                        acc + key.length + sessionStorage[key].length, 0);
                } catch (e) {
                    return 0;
                }
            })(),
            // Security Info
            security: {
                isSecure: location.protocol === 'https:',
                hasMixedContent: (() => {
                    const insecureResources = Array.from(document.querySelectorAll('script, img, link, iframe')).some(el => {
                        const src = el.src || el.href;
                        return src && src.startsWith('http:');
                    });
                    return location.protocol === 'https:' && insecureResources;
                })(),
                cspMeta: (() => {
                    const cspMeta = document.querySelector('meta[http-equiv="Content-Security-Policy"]');
                    return cspMeta ? cspMeta.getAttribute('content') : null;
                })(),
                robotsMeta: (() => {
                    const robots = document.querySelector('meta[name="robots"]');
                    return robots ? robots.getAttribute('content') : null;
                })(),
                referrerPolicy: (() => {
                    const referrer = document.querySelector('meta[name="referrer"]');
                    return referrer ? referrer.getAttribute('content') : null;
                })()
            },
            // Accessibility
            accessibility: {
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
                tabIndexIssues: document.querySelectorAll('[tabindex]').length
            },
            // SEO Metrics
            seo: {
                canonical: (() => {
                    const canonical = document.querySelector('link[rel="canonical"]');
                    return canonical ? canonical.href : null;
                })(),
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
                })(),
                robots: (() => {
                    const robots = document.querySelector('meta[name="robots"]');
                    return robots ? robots.getAttribute('content') : null;
                })(),
                description: (() => {
                    const desc = document.querySelector('meta[name="description"]');
                    return desc ? desc.getAttribute('content') : null;
                })(),
                keywords: (() => {
                    const kw = document.querySelector('meta[name="keywords"]');
                    return kw ? kw.getAttribute('content') : null;
                })()
            },
            // Browser/Device Info
            device: {
                userAgent: navigator.userAgent,
                screenResolution: screen.width + 'x' + screen.height,
                viewportSize: window.innerWidth + 'x' + window.innerHeight,
                devicePixelRatio: window.devicePixelRatio,
                touchSupport: 'ontouchstart' in window || navigator.maxTouchPoints > 0,
                platform: navigator.platform,
                language: navigator.language,
                languages: navigator.languages.join(', '),
                cookiesEnabled: navigator.cookieEnabled,
                onlineStatus: navigator.onLine
            },
            // Technologies Detection
            technologies: (() => {
                const detected = {};

                // Helper to add detected tech
                const addTech = (category, name, version = null) => {
                    if (!detected[category]) detected[category] = [];
                    const tech = version ? `${name} ${version}` : name;
                    if (!detected[category].includes(tech)) {
                        detected[category].push(tech);
                    }
                };

                // JavaScript Frameworks & Libraries
                if (window.React || document.querySelector('[data-reactroot], [data-reactid]')) {
                    const version = window.React?.version;
                    addTech('JavaScript Framework', 'React', version);
                }
                if (window.Vue) {
                    const version = window.Vue?.version;
                    addTech('JavaScript Framework', 'Vue.js', version);
                }
                if (window.angular || document.querySelector('[ng-app], [ng-version]')) {
                    const ngVersion = document.querySelector('[ng-version]')?.getAttribute('ng-version');
                    addTech('JavaScript Framework', 'Angular', ngVersion);
                }
                if (window.Svelte) addTech('JavaScript Framework', 'Svelte');
                if (window.jQuery) {
                    const version = window.jQuery?.fn?.jquery;
                    addTech('JavaScript Library', 'jQuery', version);
                }
                if (window._) addTech('JavaScript Library', 'Lodash/Underscore');
                if (window.moment) addTech('JavaScript Library', 'Moment.js');
                if (window.THREE) addTech('JavaScript Library', 'Three.js');
                if (window.d3) addTech('JavaScript Library', 'D3.js');
                if (window.Chart) addTech('JavaScript Library', 'Chart.js');
                if (window.Alpine) addTech('JavaScript Framework', 'Alpine.js');
                if (window.htmx) addTech('JavaScript Library', 'htmx');

                // Next.js / Nuxt detection
                if (document.querySelector('#__next')) addTech('JavaScript Framework', 'Next.js');
                if (document.querySelector('#__nuxt')) addTech('JavaScript Framework', 'Nuxt.js');

                // CMS Detection
                const generator = document.querySelector('meta[name="generator"]')?.content;
                if (generator) {
                    if (generator.includes('WordPress')) addTech('CMS', 'WordPress', generator.match(/WordPress ([\\d.]+)/)?.[1]);
                    if (generator.includes('Drupal')) addTech('CMS', 'Drupal', generator.match(/Drupal ([\\d.]+)/)?.[1]);
                    if (generator.includes('Joomla')) addTech('CMS', 'Joomla');
                    if (generator.includes('Ghost')) addTech('CMS', 'Ghost');
                }
                if (window.Shopify) addTech('CMS', 'Shopify');
                if (document.querySelector('link[href*="shopify"]')) addTech('CMS', 'Shopify');
                if (document.querySelector('meta[content*="Wix.com"]')) addTech('CMS', 'Wix');
                if (document.querySelector('script[src*="squarespace"]')) addTech('CMS', 'Squarespace');
                if (document.querySelector('meta[name="notion-site"]')) addTech('CMS', 'Notion');

                // Analytics & Tracking
                if (window.ga || window.gtag || window.google_tag_manager) {
                    addTech('Analytics', 'Google Analytics');
                }
                if (window.dataLayer) addTech('Tag Manager', 'Google Tag Manager');
                if (window.fbq) addTech('Analytics', 'Facebook Pixel');
                if (window.hj) addTech('Analytics', 'Hotjar');
                if (window.mixpanel) addTech('Analytics', 'Mixpanel');
                if (window.analytics && window.analytics.initialize) addTech('Analytics', 'Segment');
                if (window._paq) addTech('Analytics', 'Matomo/Piwik');
                if (window.plausible) addTech('Analytics', 'Plausible');
                if (window.fathom) addTech('Analytics', 'Fathom');

                // UI Frameworks (check classes in body)
                const bodyClasses = document.body?.className || '';
                const allClasses = Array.from(document.querySelectorAll('[class]')).map(el => el.className).join(' ');

                if (document.querySelector('link[href*="bootstrap"]') || /\\bbs-|\\bbtn-|\\bcol-/.test(allClasses)) {
                    addTech('CSS Framework', 'Bootstrap');
                }
                if (/\\btw-|\\bflex|\\bgrid|\\bbg-|\\btext-/.test(allClasses) && document.querySelector('script[src*="tailwind"]')) {
                    addTech('CSS Framework', 'Tailwind CSS');
                }
                if (window.MaterialUI || document.querySelector('[class*="MuiButton"]')) {
                    addTech('CSS Framework', 'Material-UI');
                }
                if (document.querySelector('link[href*="bulma"]')) addTech('CSS Framework', 'Bulma');
                if (document.querySelector('link[href*="foundation"]')) addTech('CSS Framework', 'Foundation');

                // Font Services
                if (document.querySelector('link[href*="fonts.googleapis.com"]')) {
                    addTech('Font Service', 'Google Fonts');
                }
                if (document.querySelector('link[href*="typekit"], script[src*="typekit"]')) {
                    addTech('Font Service', 'Adobe Fonts (Typekit)');
                }

                // CDN Detection
                const scripts = Array.from(document.scripts).map(s => s.src);
                if (scripts.some(s => s.includes('cloudflare'))) addTech('CDN', 'Cloudflare');
                if (scripts.some(s => s.includes('fastly'))) addTech('CDN', 'Fastly');
                if (scripts.some(s => s.includes('jsdelivr'))) addTech('CDN', 'jsDelivr');
                if (scripts.some(s => s.includes('unpkg'))) addTech('CDN', 'unpkg');
                if (scripts.some(s => s.includes('cdnjs'))) addTech('CDN', 'cdnjs');

                // Payment Processors
                if (window.Stripe) addTech('Payment', 'Stripe');
                if (window.paypal) addTech('Payment', 'PayPal');
                if (window.Square) addTech('Payment', 'Square');

                // Server/Hosting hints from headers (limited in browser)
                const poweredBy = document.querySelector('meta[name="powered-by"]')?.content;
                if (poweredBy) addTech('Server', poweredBy);

                return detected;
            })()
        })
        """
    else:
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

    try:
        result = client.execute(code)

        if result.get("ok"):
            data = result.get("result") or {}

            if not data:
                click.echo("Error: No data returned from browser.", err=True)
                sys.exit(1)

            # Get userscript/extension version, type, and browser name
            # Support both new (INSPEKT) and legacy (ZEN) variable names
            version_code = """
            (function() {
                const version = window.__INSPEKT_BRIDGE_VERSION__ || window.__ZEN_BRIDGE_VERSION__ || 'unknown';
                const type = (window.__INSPEKT_BRIDGE_EXTENSION__ || window.__ZEN_BRIDGE_EXTENSION__) ? 'extension' : 'userscript';

                // Detect browser name from user agent
                const ua = navigator.userAgent;
                let browserName = 'Unknown';
                if (ua.includes('Firefox')) {
                    browserName = 'Firefox';
                } else if (ua.includes('Edg')) {
                    browserName = 'Edge';
                } else if (ua.includes('Chrome')) {
                    browserName = 'Chrome';
                } else if (ua.includes('Safari')) {
                    browserName = 'Safari';
                }

                return version + '|' + type + '|' + browserName;
            })()
            """
            version_result = client.execute(version_code, timeout=2.0)
            if version_result.get("ok"):
                version_info = version_result.get("result", "unknown|userscript|Unknown")
                parts = version_info.split("|") if "|" in version_info else [version_info, "userscript", "Unknown"]
                userscript_version = parts[0]
                bridge_type = parts[1] if len(parts) > 1 else "userscript"
                browser_name = parts[2] if len(parts) > 2 else "Unknown"
            else:
                userscript_version = "unknown"
                bridge_type = "userscript"
                browser_name = "Unknown"

            # If extended, also run the extended_info.js script
            if extended:
                try:
                    script_path = Path(__file__).parent.parent.parent / "scripts" / "extended_info.js"
                    if script_path.exists():
                        with builtin_open(script_path) as f:
                            extended_script = f.read()
                        extended_result = client.execute(extended_script, timeout=10.0)
                        if extended_result.get("ok"):
                            extended_data = extended_result.get("result", {})
                            # Merge extended data into main data
                            data["_extended"] = extended_data
                except Exception:
                    pass  # Extended info is optional

                # Add server-side data for JSON output
                if output_json:
                    # Add response headers
                    headers = _get_response_headers(data.get("url"))
                    if headers:
                        data["responseHeaders"] = headers

                    # Add robots.txt
                    robots_data = _get_robots_txt(data.get("url"))
                    if robots_data:
                        data["robotsTxt"] = robots_data

                    # Add domain metrics
                    domain_metrics = _get_domain_metrics(data.get("domain"))
                    if domain_metrics:
                        data["domainMetrics"] = domain_metrics

                    # Add detected language
                    try:
                        from langdetect import LangDetectException, detect

                        para_code = "Array.from(document.querySelectorAll('p')).map(p => p.textContent).join(' ').substring(0, 5000)"
                        para_result = client.execute(para_code, timeout=5.0)
                        if para_result.get("ok"):
                            para_text = para_result.get("result", "")
                            if para_text and len(para_text.strip()) > 50:
                                try:
                                    detected = detect(para_text)
                                    data["detectedLanguage"] = detected

                                    # Check if detected language matches declared language
                                    declared_lang = data.get("specifiedLanguage", "").lower()
                                    if declared_lang and declared_lang != "n/a":
                                        data["languageMatch"] = declared_lang == detected.lower()
                                except LangDetectException:
                                    pass
                    except ImportError:
                        pass

            # If JSON output is requested, output JSON and exit
            if output_json:
                import json

                data["userscriptVersion"] = userscript_version
                click.echo(json.dumps(data, indent=2))
                return

            # Basic info - Extension/browser info first
            bridge_label = "Extension" if bridge_type == "extension" else "Userscript"
            protocol = data.get('protocol', 'N/A')
            is_local_file = protocol == 'file:'

            # Handle empty title
            title = data.get('title', '')
            if not title or title.strip() == '':
                title = '-'
            else:
                title = _truncate_value(title)

            # Handle domain for local files
            domain = data.get('domain', 'N/A')
            if is_local_file or not domain:
                domain = '-'

            basic_rows = [
                ("Extension", f"v{userscript_version} ({browser_name} {bridge_label})", None),
                ("URL", _truncate_value(data.get('url', 'N/A')), None),
                ("Title", title, None),
                ("State", data.get('readyState', 'N/A'), None),
                ("Domain", domain, None),
                ("Protocol", protocol, None),
                ("Viewport", f"{data.get('width', 'N/A')}x{data.get('height', 'N/A')}", None),
            ]
            _print_info_table("Basic Information", basic_rows)

            if extended:
                # Language and encoding (with natural language detection)
                declared_lang = data.get("specifiedLanguage", "N/A")
                detected_lang = None
                lang_match = None

                # Detect actual language using langdetect
                try:
                    from langdetect import LangDetectException, detect

                    # Extract paragraph text for language detection
                    para_code = "Array.from(document.querySelectorAll('p')).map(p => p.textContent).join(' ').substring(0, 5000)"
                    para_result = client.execute(para_code, timeout=5.0)
                    if para_result.get("ok"):
                        para_text = para_result.get("result", "")
                        if para_text and len(para_text.strip()) > 50:
                            try:
                                detected_lang = detect(para_text)
                                if detected_lang:
                                    if declared_lang != "N/A" and declared_lang.lower() != detected_lang.lower():
                                        lang_match = False
                                    else:
                                        lang_match = True
                            except LangDetectException:
                                pass
                except ImportError:
                    pass
                except Exception:
                    pass

                # Build language rows
                lang_rows = [
                    ("Declared Language", declared_lang, None),
                ]
                if detected_lang:
                    if lang_match:
                        lang_rows.append(("Detected Language", f"{detected_lang} (matches)", "green"))
                    else:
                        lang_rows.append(("Detected Language", detected_lang, "yellow"))
                        lang_rows.append(("Warning", f'Content appears to be "{detected_lang}" but lang="{declared_lang}"', "yellow"))
                lang_rows.append(("Character Set", data.get('charset', 'N/A'), None))
                _print_info_table("Language & Encoding", lang_rows)

                # Resources - fetch single resource filenames if count is 1
                def _get_single_resource_name(js_code: str) -> str:
                    """Execute JS to get a single resource filename."""
                    try:
                        result = client.execute(js_code, timeout=2.0)
                        if result.get("ok"):
                            url = result.get("result", "")
                            if url:
                                # Extract filename from URL
                                from urllib.parse import urlparse
                                path = urlparse(url).path
                                filename = path.split('/')[-1] if '/' in path else path
                                return filename if filename else ""
                    except Exception:
                        pass
                    return ""

                def _format_resource_count(count: int, single_name: str = "") -> str:
                    """Format resource count with optional filename for single resources."""
                    if count == 0:
                        return "0"
                    elif count == 1 and single_name:
                        # Use bright_black (dark gray) for the filename
                        return f"1 {click.style(f'({single_name})', fg='bright_black')}"
                    return str(count)

                script_count = data.get('scriptCount', 0)
                style_count = data.get('stylesheetCount', 0)
                image_count = data.get('imageCount', 0)

                # Get single filenames
                script_name = _get_single_resource_name("document.querySelector('script[src]')?.src || ''") if script_count == 1 else ""
                style_name = _get_single_resource_name("document.querySelector('link[rel=stylesheet]')?.href || ''") if style_count == 1 else ""
                image_name = _get_single_resource_name("document.querySelector('img[src]')?.src || ''") if image_count == 1 else ""

                resource_rows = [
                    ("Scripts", _format_resource_count(script_count, script_name), None),
                    ("Stylesheets", _format_resource_count(style_count, style_name), None),
                    ("Images", _format_resource_count(image_count, image_name), None),
                    ("Links", str(data.get('linkCount', 0)), None),
                    ("Forms", str(data.get('formCount', 0)), None),
                    ("Iframes", str(data.get('iframeCount', 0)), None),
                ]
                _print_info_table("Resources", resource_rows)

                # Performance Metrics (from extended data)
                extended_data = data.get("_extended", {})
                perf = extended_data.get("performance", {})
                if perf:
                    perf_rows = []
                    if perf.get("timeToFirstByte"):
                        perf_rows.append(("Time to First Byte", f"{int(perf['timeToFirstByte'])}ms", None))
                    if perf.get("firstPaint"):
                        perf_rows.append(("First Paint", f"{int(float(perf['firstPaint']) * 1000)}ms", None))
                    if perf.get("firstContentfulPaint"):
                        perf_rows.append(("First Contentful Paint", f"{int(float(perf['firstContentfulPaint']) * 1000)}ms", None))
                    if perf.get("domContentLoaded"):
                        perf_rows.append(("DOM Content Loaded", f"{int(float(perf['domContentLoaded']) * 1000)}ms", None))
                    if perf.get("largestContentfulPaint"):
                        perf_rows.append(("Largest Contentful Paint", f"{int(float(perf['largestContentfulPaint']) * 1000)}ms", None))
                    if perf.get("pageLoadTime"):
                        perf_rows.append(("Page Load Time", f"{int(float(perf['pageLoadTime']) * 1000)}ms", None))
                    if perf_rows:
                        _print_info_table("Performance", perf_rows)

                # Media Content (from extended data)
                media = extended_data.get("media", {})
                if media and (
                    media.get("videos", 0) > 0
                    or media.get("audio", 0) > 0
                    or media.get("svgImages", 0) > 0
                ):
                    video_count = media.get("videos", 0)
                    audio_count = media.get("audio", 0)
                    svg_count = media.get("svgImages", 0)

                    # Get single filenames for media
                    video_name = _get_single_resource_name("document.querySelector('video source')?.src || document.querySelector('video')?.src || ''") if video_count == 1 else ""
                    audio_name = _get_single_resource_name("document.querySelector('audio source')?.src || document.querySelector('audio')?.src || ''") if audio_count == 1 else ""

                    media_rows = []
                    if video_count > 0:
                        media_rows.append(("Videos", _format_resource_count(video_count, video_name), None))
                    if audio_count > 0:
                        media_rows.append(("Audio", _format_resource_count(audio_count, audio_name), None))
                    if svg_count > 0:
                        media_rows.append(("SVG Images", str(svg_count), None))
                    if media_rows:
                        _print_info_table("Media", media_rows)

                # Content Stats (from extended data)
                content = extended_data.get("content", {})
                content_rows = []
                # Add page language at the start
                page_lang = declared_lang if declared_lang != "N/A" else "-"
                if detected_lang and lang_match:
                    content_rows.append(("Language", page_lang, None))
                elif detected_lang and not lang_match:
                    content_rows.append(("Language", f"{page_lang} (detected: {detected_lang})", "yellow"))
                else:
                    content_rows.append(("Language", page_lang, None))

                if content:
                    if content.get("wordCount"):
                        content_rows.append(("Word Count", f"~{content['wordCount']:,} words", None))
                    if content.get("estimatedReadingTime"):
                        content_rows.append(("Reading Time", f"~{content['estimatedReadingTime']} minutes", None))
                    if content.get("paragraphs"):
                        content_rows.append(("Paragraphs", str(content['paragraphs']), None))
                    if content.get("lists"):
                        content_rows.append(("Lists", str(content['lists']), None))
                    if content.get("languageSwitchers", 0) > 0:
                        content_rows.append(("Language Switchers", str(content['languageSwitchers']), None))
                if content_rows:
                    _print_info_table("Content", content_rows)

                # Dimensions
                viewport_width = data.get('width', 0)
                viewport_height = data.get('height', 0)
                scroll_height = data.get('scrollHeight', 0)
                scroll_width = data.get('scrollWidth', 0)

                # Calculate percentage visible
                visible_pct = (viewport_height / scroll_height * 100) if scroll_height > 0 else 100
                visible_pct = min(visible_pct, 100)  # Cap at 100%

                dim_rows = [
                    ("Viewport", f"{viewport_width}x{viewport_height}px", None),
                    ("Document Size", f"{scroll_width}x{scroll_height}px", None),
                    ("Visible", f"{visible_pct:.0f}% of page height", None),
                ]
                _print_info_table("Dimensions", dim_rows)

                # Storage - collect data first
                cookie_count = data.get("cookieCount", 0)
                local_kb = data.get("localStorageSize", 0) / 1024
                session_kb = data.get("sessionStorageSize", 0) / 1024

                # Get cookie names
                cookie_names = []
                if cookie_count > 0:
                    try:
                        cookie_code = "document.cookie.split(';').map(c => c.trim().split('=')[0]).filter(Boolean)"
                        cookie_result = client.execute(cookie_code, timeout=2.0)
                        if cookie_result.get("ok"):
                            cookie_names = cookie_result.get("result", [])
                    except Exception:
                        pass

                # Get localStorage keys
                ls_keys = []
                if local_kb > 0:
                    try:
                        ls_code = "Object.keys(localStorage)"
                        ls_result = client.execute(ls_code, timeout=2.0)
                        if ls_result.get("ok"):
                            ls_keys = ls_result.get("result", [])
                    except Exception:
                        pass

                # Get sessionStorage keys
                ss_keys = []
                if session_kb > 0:
                    try:
                        ss_code = "Object.keys(sessionStorage)"
                        ss_result = client.execute(ss_code, timeout=2.0)
                        if ss_result.get("ok"):
                            ss_keys = ss_result.get("result", [])
                    except Exception:
                        pass

                # Build storage table with better empty values
                def _format_storage_count(count: int) -> str:
                    return "None" if count == 0 else str(count)

                def _format_storage_size(kb: float) -> str:
                    if kb < 0.01:
                        return "Empty"
                    return f"{kb:.2f} KB"

                storage_rows = [
                    ("Cookies", _format_storage_count(cookie_count), None),
                    ("LocalStorage", _format_storage_size(local_kb), None),
                    ("SessionStorage", _format_storage_size(session_kb), None),
                    ("Service Worker", 'Yes' if data.get('hasServiceWorker') else 'No', None),
                ]
                _print_info_table("Storage", storage_rows)

                # Show cookie names if present
                if cookie_names:
                    cookie_list_rows = [[name] for name in cookie_names[:8]]
                    if len(cookie_names) > 8:
                        cookie_list_rows.append([f"... and {len(cookie_names) - 8} more"])
                    _print_list_table("Cookie Names", ["Name"], cookie_list_rows, [55])

                # Show localStorage keys if present
                if ls_keys:
                    ls_list_rows = [[key] for key in ls_keys[:8]]
                    if len(ls_keys) > 8:
                        ls_list_rows.append([f"... and {len(ls_keys) - 8} more"])
                    _print_list_table("LocalStorage Keys", ["Key"], ls_list_rows, [55])

                # Show sessionStorage keys if present
                if ss_keys:
                    ss_list_rows = [[key] for key in ss_keys[:8]]
                    if len(ss_keys) > 8:
                        ss_list_rows.append([f"... and {len(ss_keys) - 8} more"])
                    _print_list_table("SessionStorage Keys", ["Key"], ss_list_rows, [55])

                # Security Info
                security = data.get("security", {})
                if security:
                    sec_rows = []
                    https_status = 'Yes' if security.get('isSecure') else 'No'
                    https_color = 'green' if security.get('isSecure') else 'red'
                    sec_rows.append(("HTTPS", https_status, https_color))
                    if security.get("isSecure") and security.get("hasMixedContent"):
                        sec_rows.append(("Mixed Content", "Warning - Insecure resources detected", "yellow"))
                    if security.get("cspMeta"):
                        csp = _truncate_value(security.get("cspMeta", ""), 50)
                        sec_rows.append(("CSP Meta", csp, None))
                    if security.get("referrerPolicy"):
                        sec_rows.append(("Referrer Policy", security.get('referrerPolicy'), None))
                    if sec_rows:
                        _print_info_table("Security", sec_rows)

                # Accessibility
                a11y = data.get("accessibility", {})
                if a11y:
                    a11y_rows = []

                    # Landmarks summary
                    landmarks = a11y.get("landmarks", {})
                    if landmarks:
                        landmark_summary = ", ".join([f"{role}: {count}" for role, count in landmarks.items()])
                        a11y_rows.append(("Landmarks", f"{a11y.get('landmarkCount', 0)} total ({landmark_summary})", None))
                    else:
                        a11y_rows.append(("Landmarks", f"{a11y.get('landmarkCount', 0)} total", None))

                    # Heading structure
                    heading_structure = a11y.get("headingStructure", {})
                    total_headings = sum(heading_structure.values())
                    if total_headings > 0:
                        heading_parts = [f"{level.upper()}: {heading_structure.get(level, 0)}" for level in ["h1", "h2", "h3", "h4", "h5", "h6"] if heading_structure.get(level, 0) > 0]
                        a11y_rows.append(("Headings", f"{total_headings} total ({', '.join(heading_parts)})", None))

                    # A11y issues (without emoji)
                    img_no_alt = a11y.get("imagesWithoutAlt", 0)
                    if img_no_alt > 0:
                        a11y_rows.append(("Images w/o alt", str(img_no_alt), "yellow"))

                    form_issues = a11y.get("formLabelsIssues", {})
                    if form_issues.get("missingLabels", 0) > 0:
                        a11y_rows.append(("Form inputs w/o labels", f"{form_issues['missingLabels']}/{form_issues['total']}", "yellow"))

                    # Extended accessibility info
                    a11y_ext = extended_data.get("accessibility", {})
                    if a11y_ext:
                        if a11y_ext.get("linksWithoutText", 0) > 0:
                            a11y_rows.append(("Links w/o text", str(a11y_ext['linksWithoutText']), "yellow"))
                        if a11y_ext.get("buttonsWithoutLabels", 0) > 0:
                            a11y_rows.append(("Buttons w/o labels", str(a11y_ext['buttonsWithoutLabels']), "yellow"))
                        if a11y_ext.get("hasSkipLink"):
                            a11y_rows.append(("Skip Link", "Present", "green"))
                        if not a11y_ext.get("langAttribute"):
                            a11y_rows.append(("Lang Attribute", "Missing", "yellow"))
                        if a11y_ext.get("ariaAttributeCount"):
                            a11y_rows.append(("ARIA Usage", f"{a11y_ext['ariaAttributeCount']} attributes", None))

                    if a11y_rows:
                        _print_info_table("Accessibility", a11y_rows)
                        # Add hint about inspekt axe
                        click.echo(click.style("  Hint: Run `inspekt axe` for detailed accessibility information.", fg="bright_black"))

                # Structured Data (from extended data)
                structured = extended_data.get("structuredData", {})
                if structured and (
                    structured.get("jsonLdCount", 0) > 0 or structured.get("microdataCount", 0) > 0
                ):
                    struct_rows = []
                    if structured.get("jsonLdCount", 0) > 0:
                        types = structured.get("jsonLdTypes", [])
                        type_info = f" ({', '.join(types[:5])})" if types else ""
                        struct_rows.append(("JSON-LD", f"{structured['jsonLdCount']} blocks{type_info}", None))
                    if structured.get("microdataCount", 0) > 0:
                        struct_rows.append(("Microdata", f"{structured['microdataCount']} items", None))
                    if struct_rows:
                        _print_info_table("Structured Data", struct_rows)

                # SEO Metrics
                seo = data.get("seo", {})
                if seo:
                    seo_rows = []
                    if seo.get("canonical"):
                        seo_rows.append(("Canonical", _truncate_value(seo["canonical"]), None))
                    if seo.get("description"):
                        seo_rows.append(("Description", _truncate_value(seo["description"]), None))
                    if seo.get("keywords"):
                        seo_rows.append(("Keywords", _truncate_value(seo["keywords"]), None))
                    if seo.get("robots"):
                        seo_rows.append(("Robots", seo['robots'], None))

                    # SEO Extras (from extended data)
                    seo_extra = extended_data.get("seoExtra", {})
                    if seo_extra:
                        if seo_extra.get("favicon"):
                            seo_rows.append(("Favicon", seo_extra['favicon'], None))
                        if seo_extra.get("sitemap"):
                            seo_rows.append(("Sitemap", _truncate_value(seo_extra["sitemap"], 50), None))
                        alt_langs = seo_extra.get("alternateLanguages", [])
                        if alt_langs:
                            lang_list = ", ".join([lang['lang'] for lang in alt_langs[:3]])
                            if len(alt_langs) > 3:
                                lang_list += f" (+{len(alt_langs) - 3} more)"
                            seo_rows.append(("Alternate Languages", lang_list, None))

                    if seo_rows:
                        _print_info_table("SEO", seo_rows)

                    # Open Graph as separate table
                    og = seo.get("openGraph", {})
                    if og:
                        og_rows = []
                        for key in ["title", "type", "image", "url", "description"]:
                            if key in og:
                                og_rows.append((f"og:{key}", _truncate_value(og[key], 50), None))
                        if og_rows:
                            _print_info_table(f"Open Graph ({len(og)} tags)", og_rows)

                    # Twitter Card as separate table
                    twitter = seo.get("twitterCard", {})
                    if twitter:
                        twitter_rows = []
                        for key in ["card", "title", "description", "image"]:
                            if key in twitter:
                                twitter_rows.append((f"twitter:{key}", _truncate_value(twitter[key], 50), None))
                        if twitter_rows:
                            _print_info_table(f"Twitter Card ({len(twitter)} tags)", twitter_rows)

                # Robots.txt
                robots_data = _get_robots_txt(data.get("url"))
                if robots_data and robots_data.get("exists"):
                    robots_rows = [
                        ("Status", "Found", "green"),
                        ("Size", f"{robots_data['size']:,} bytes ({robots_data['lines']} lines)", None),
                    ]
                    if robots_data.get("userAgents"):
                        agents = robots_data["userAgents"]
                        if len(agents) <= 3:
                            robots_rows.append(("User-agents", ', '.join(agents), None))
                        else:
                            robots_rows.append(("User-agents", f"{len(agents)} defined", None))
                    if robots_data.get("disallowRules", 0) > 0:
                        robots_rows.append(("Disallow rules", str(robots_data['disallowRules']), None))
                    if robots_data.get("allowRules", 0) > 0:
                        robots_rows.append(("Allow rules", str(robots_data['allowRules']), None))
                    if robots_data.get("sitemaps"):
                        sitemaps = robots_data["sitemaps"]
                        sitemap_list = ", ".join([_truncate_value(s, 40) for s in sitemaps[:2]])
                        if len(sitemaps) > 2:
                            sitemap_list += f" (+{len(sitemaps) - 2} more)"
                        robots_rows.append(("Sitemaps", f"{len(sitemaps)} declared", None))
                    _print_info_table("Robots.txt", robots_rows)

                # Third-Party Resources (from extended data)
                third_party = extended_data.get("thirdParty", {})
                if third_party and third_party.get("externalDomainCount", 0) > 0:
                    domains = third_party.get("externalDomains", [])
                    third_party_rows = [
                        ("External Domains", str(third_party['externalDomainCount']), None),
                    ]
                    if domains:
                        domain_list = ", ".join(domains[:5])
                        if len(domains) > 5:
                            domain_list += f" (+{len(domains) - 5} more)"
                        third_party_rows.append(("Domains", domain_list, None))
                    _print_info_table("Third-Party Resources", third_party_rows)

                # Browser/Device Info
                device = data.get("device", {})
                if device:
                    device_rows = [
                        ("Platform", device.get('platform', 'N/A'), None),
                        ("Language", device.get('language', 'N/A'), None),
                        ("Screen", device.get('screenResolution', 'N/A'), None),
                        ("Viewport", device.get('viewportSize', 'N/A'), None),
                        ("Pixel Ratio", str(device.get('devicePixelRatio', 'N/A')), None),
                        ("Touch Support", 'Yes' if device.get('touchSupport') else 'No', None),
                        ("Cookies Enabled", 'Yes' if device.get('cookiesEnabled') else 'No', None),
                        ("Online", 'Yes' if device.get('onlineStatus') else 'No', None),
                    ]

                    ua = device.get("userAgent", "")
                    if ua:
                        device_rows.append(("User Agent", _truncate_value(ua), None))

                    _print_info_table("Browser/Device", device_rows)

                # Technologies Detected
                technologies = data.get("technologies", {})
                if technologies:
                    tech_rows = []
                    for category, techs in sorted(technologies.items()):
                        if techs:
                            tech_list = ", ".join(techs[:5])
                            if len(techs) > 5:
                                tech_list += f" (+{len(techs) - 5} more)"
                            tech_rows.append((category, tech_list, None))
                    if tech_rows:
                        _print_info_table("Technologies Detected", tech_rows)

                # Domain Metrics (fetched from server-side)
                domain_metrics = _get_domain_metrics(data.get("domain"))
                if domain_metrics:
                    domain_rows = []

                    if domain_metrics.get("ip"):
                        domain_rows.append(("IP Address", domain_metrics['ip'], None))

                    geo = domain_metrics.get("geolocation", {})
                    if geo:
                        location_parts = [geo.get("city"), geo.get("region"), geo.get("country")]
                        location = ", ".join([p for p in location_parts if p])
                        if location:
                            domain_rows.append(("Location", location, None))
                        if geo.get("isp"):
                            domain_rows.append(("ISP", geo['isp'], None))
                        if geo.get("org"):
                            domain_rows.append(("Organization", geo['org'], None))

                    whois = domain_metrics.get("whois", {})
                    if whois:
                        if whois.get("creation_date"):
                            domain_rows.append(("Registered", whois['creation_date'], None))
                        if whois.get("expiration_date"):
                            domain_rows.append(("Expires", whois['expiration_date'], None))
                        if whois.get("registrar"):
                            domain_rows.append(("Registrar", whois['registrar'], None))

                    ssl_info = domain_metrics.get("ssl", {})
                    if ssl_info:
                        if ssl_info.get("issuer"):
                            domain_rows.append(("SSL Issuer", ssl_info['issuer'], None))
                        if ssl_info.get("expiry"):
                            domain_rows.append(("SSL Expires", ssl_info['expiry'], None))
                        if ssl_info.get("days_remaining"):
                            days = ssl_info["days_remaining"]
                            if days < 30:
                                domain_rows.append(("SSL Status", f"⚠️  Expires in {days} days", "yellow"))
                            else:
                                domain_rows.append(("SSL Status", f"Valid ({days} days remaining)", "green"))

                    if domain_rows:
                        _print_info_table("Domain Metrics", domain_rows)

                # Network Summary (from extended data)
                network = extended_data.get("network", {})
                if network:
                    network_rows = []
                    if network.get("totalRequests"):
                        network_rows.append(("Total Requests", str(network['totalRequests']), None))
                    if network.get("totalSize"):
                        size_mb = network["totalSize"] / (1024 * 1024)
                        network_rows.append(("Total Size", f"{size_mb:.2f} MB", None))
                    largest = network.get("largestResource")
                    if largest:
                        size_kb = largest["size"] / 1024
                        network_rows.append(("Largest Resource", f"{largest['name']} ({size_kb:.2f} KB)", None))
                    if network_rows:
                        _print_info_table("Network", network_rows)

                # Fonts (from extended data)
                fonts = extended_data.get("fonts", {})
                if fonts and (
                    fonts.get("googleFonts")
                    or fonts.get("customFonts")
                    or fonts.get("totalFontFiles", 0) > 0
                ):
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
                        font_rows.append(("Font Files", str(fonts['totalFontFiles']), None))
                    if font_rows:
                        _print_info_table("Fonts", font_rows)

                # Form Details (from extended data)
                forms = extended_data.get("forms", [])
                if forms:
                    form_list_rows = []
                    form_colors = []
                    for form in forms:
                        method = form['method']
                        fields = len(form['fields'])
                        action = _truncate_value(form["action"], 30) if form["action"] and form["action"] != "JavaScript" else "-"
                        issues = len(form.get("issues", []))
                        issue_text = f"⚠️ {issues}" if issues > 0 else "0"
                        form_list_rows.append([form['id'], method, action, str(fields), issue_text])
                        form_colors.append([None, None, None, None, "yellow" if issues > 0 else None])
                    _print_list_table(f"Forms ({len(forms)})", ["ID", "Method", "Action", "Fields", "Issues"], form_list_rows, [20, 8, 25, 8, 8], form_colors)

                # Core Web Vitals (from extended data)
                cwv = extended_data.get("coreWebVitals", {})
                if cwv:
                    cwv_rows = []
                    if "cls" in cwv:
                        cls_val = float(cwv["cls"])
                        if cls_val < 0.1:
                            cls_status, cls_color = "✓ Good", "green"
                        elif cls_val < 0.25:
                            cls_status, cls_color = "⚠️ Needs Improvement", "yellow"
                        else:
                            cls_status, cls_color = "❌ Poor", "red"
                        cwv_rows.append(("CLS", f"{cwv['cls']} ({cls_status})", cls_color))
                    if "fid" in cwv:
                        fid_val = int(cwv["fid"])
                        if fid_val < 100:
                            fid_status, fid_color = "✓ Good", "green"
                        elif fid_val < 300:
                            fid_status, fid_color = "⚠️ Needs Improvement", "yellow"
                        else:
                            fid_status, fid_color = "❌ Poor", "red"
                        cwv_rows.append(("FID", f"{cwv['fid']}ms ({fid_status})", fid_color))
                    if "inp" in cwv:
                        inp_val = int(cwv["inp"])
                        if inp_val < 200:
                            inp_status, inp_color = "✓ Good", "green"
                        elif inp_val < 500:
                            inp_status, inp_color = "⚠️ Needs Improvement", "yellow"
                        else:
                            inp_status, inp_color = "❌ Poor", "red"
                        cwv_rows.append(("INP", f"{cwv['inp']}ms ({inp_status})", inp_color))
                    if cwv_rows:
                        _print_info_table("Core Web Vitals", cwv_rows)

                # Security Headers and Response Headers
                headers = _get_response_headers(data.get("url"))
                if headers:
                    # Security Headers
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

                # Meta tags
                meta_tags = data.get("metaTags", [])
                if meta_tags:
                    meta_rows = []
                    for meta in meta_tags:
                        # Format meta tag nicely
                        if "name" in meta and "content" in meta:
                            meta_rows.append((meta['name'], _truncate_value(meta["content"]), None))
                        elif "property" in meta and "content" in meta:
                            meta_rows.append((meta['property'], _truncate_value(meta["content"]), None))
                        elif "charset" in meta:
                            meta_rows.append(("charset", meta['charset'], None))
                        elif "http-equiv" in meta:
                            meta_rows.append((meta['http-equiv'], meta.get('content', ''), None))
                    if meta_rows:
                        _print_info_table(f"Meta Tags ({len(meta_tags)})", meta_rows)
        else:
            click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@click.command()
def repl():
    """
    Start an interactive REPL session.

    Execute JavaScript interactively. Console output is shown automatically.
    Type 'exit' or press Ctrl+D to quit.
    """
    from datetime import datetime, timezone

    client = BridgeClient()

    if not client.is_alive():
        click.echo("Error: Bridge server is not running. Start it with: inspekt start", err=True)
        sys.exit(1)

    click.echo("Inspekt REPL - Type JavaScript code, 'exit' to quit")
    click.echo("")

    # Get initial page info
    try:
        result = client.execute("({url: location.href, title: document.title})")
        if result.get("ok"):
            data = result.get("result", {})
            click.echo(
                f"Connected to: {data.get('title', 'Unknown')} ({data.get('url', 'Unknown')})"
            )
            click.echo("")
    except Exception:
        pass

    while True:
        try:
            code = click.prompt("inspekt>", prompt_suffix=" ", default="", show_default=False)

            if not code.strip():
                continue

            if code.strip().lower() in ["exit", "quit"]:
                break

            try:
                # Get timestamp before execution
                before_ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

                result = client.execute(code, timeout=10.0)

                # Show console output
                console_entries = _get_console_logs_since(before_ts)
                if console_entries:
                    for entry in console_entries:
                        click.echo(_format_console_entry(entry))

                # Show return value
                output = format_output(result, "auto")
                if output and output.strip():
                    click.echo(click.style("← ", dim=True) + output)

            except (ConnectionError, TimeoutError, RuntimeError) as e:
                click.echo(f"Error: {e}", err=True)

        except (EOFError, KeyboardInterrupt):
            click.echo("")
            break

    click.echo("Goodbye!")


@click.command()
def userscript():
    """Display the userscript that needs to be installed in your browser."""
    script_path = Path(__file__).parent.parent.parent / "userscript.js"

    if script_path.exists():
        click.echo(f"Userscript location: {script_path}")
        click.echo("")
        click.echo("To install:")
        click.echo("1. Install a userscript manager (Tampermonkey, Greasemonkey, Violentmonkey)")
        click.echo("2. Create a new script and paste the contents of userscript.js")
        click.echo("3. Save and enable the script")
        click.echo("")
        click.echo("Or use: cat userscript.js | pbcopy  (to copy to clipboard on macOS)")
    else:
        click.echo(f"Error: userscript.js not found at {script_path}", err=True)
        sys.exit(1)


@click.command()
@click.option(
    "-o",
    "--output",
    type=click.Path(),
    default=None,
    help="Output directory (default: ~/Downloads/<domain>)",
)
@click.option("--list", "list_only", is_flag=True, help="Only list files without downloading")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON (requires --list)")
@click.option("-t", "--timeout", type=float, default=30.0, help="Timeout in seconds (default: 30)")
def download(output, list_only, output_json, timeout):
    """
    Find and download files from the current page.

    Discovers images, PDFs, videos, audio files, documents and archives.
    Uses interactive selection with gum choose.

    Examples:

        zen download

        zen download --output ~/Downloads

        zen download --list
    """

    import requests

    client = BridgeClient()

    if not client.is_alive():
        click.echo("Error: Bridge server is not running. Start it with: inspekt start", err=True)
        sys.exit(1)

    # Execute the find_downloads script
    script_path = Path(__file__).parent.parent.parent / "scripts" / "find_downloads.js"

    if not script_path.exists():
        click.echo(f"Error: find_downloads.js script not found at {script_path}", err=True)
        sys.exit(1)

    click.echo("Scanning page for downloadable files...")

    try:
        result = client.execute_file(str(script_path), timeout=timeout)

        if not result.get("ok"):
            click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)

        result_data = result.get("result", {})

        # Handle new format with url and files
        if isinstance(result_data, dict) and "files" in result_data:
            files_by_category = result_data["files"]
            page_url = result_data.get("url", "")
        else:
            # Fallback for old format
            files_by_category = result_data
            page_url = ""

        # Count total files
        total_files = sum(len(files) for files in files_by_category.values())

        if total_files == 0:
            click.echo("No downloadable files found on this page.")
            return

        # Determine output directory
        if output is None:
            # Default: ~/Downloads/<domain>
            try:
                from urllib.parse import urlparse

                domain = urlparse(page_url).hostname or "unknown"
                domain = domain.replace("www.", "")  # Remove www. prefix
                downloads_dir = Path.home() / "Downloads" / domain
            except Exception:
                downloads_dir = Path.home() / "Downloads" / "zen-downloads"
        else:
            downloads_dir = Path(output)

        # Build options list for gum choose
        options = []
        option_map = {}  # Map display text to actual data

        # Category labels (lowercase)
        category_names = {
            "images": "images",
            "pdfs": "PDF documents",
            "videos": "videos",
            "audio": "audio files",
            "documents": "documents",
            "archives": "archives",
        }

        # Add "Download all" options per category
        for category, files in files_by_category.items():
            if files:
                count = len(files)
                display = f"Download all {category_names.get(category, category)} ({count} files)"
                options.append(display)
                option_map[display] = {"type": "category", "category": category, "files": files}

        # Add separator
        if options:
            separator = "─" * 60
            options.append(separator)
            option_map[separator] = {"type": "separator"}

        # Add individual files grouped by category
        for category, files in files_by_category.items():
            if files:
                # Add category header
                header = f"--- {category_names.get(category, category.upper())} ---"
                options.append(header)
                option_map[header] = {"type": "header"}

                # Add individual files
                for file_info in files:
                    filename = file_info["filename"]
                    url = file_info["url"]

                    # Try to get file size if in list mode
                    display = f"  {filename}"
                    options.append(display)
                    option_map[display] = {
                        "type": "file",
                        "filename": filename,
                        "url": url,
                        "category": category,
                    }

        # List only mode
        if list_only:
            if output_json:
                # Build JSON output
                json_output = {
                    "total": total_files,
                    "url": page_url,
                    "files": files_by_category
                }
                click.echo(json.dumps(json_output, indent=2))
            else:
                click.echo(f"\nFound {total_files} downloadable files:\n")
                for option in options:
                    if option_map.get(option, {}).get("type") not in ["separator", "category"]:
                        click.echo(option)
            return

        # Simple numbered list selection
        click.echo(f"\nFound {total_files} files. Select what to download:\n")

        # Build simple menu
        menu_options = []

        # Find largest image if we have images
        largest_image = None
        if files_by_category.get("images"):
            images_with_dims = [
                img
                for img in files_by_category["images"]
                if img.get("width", 0) > 0 and img.get("height", 0) > 0
            ]
            if images_with_dims:
                # Find image with largest area
                largest_image = max(
                    images_with_dims, key=lambda img: img.get("width", 0) * img.get("height", 0)
                )

        # Add largest image option first
        if largest_image:
            width = largest_image.get("width", 0)
            height = largest_image.get("height", 0)
            menu_options.append(
                {
                    "text": f"Download the largest image ({width}×{height}px)",
                    "data": {"type": "file", "files": [largest_image]},
                }
            )

        # Add category download options
        for category, files in files_by_category.items():
            if files:
                count = len(files)
                menu_options.append(
                    {
                        "text": f"Download all {category_names.get(category, category)} ({count} files)",
                        "data": {"type": "category", "category": category, "files": files},
                    }
                )

        # Display menu
        for i, opt in enumerate(menu_options, 1):
            click.echo(f" {i}. {opt['text']}")

        click.echo("\nFiles will be saved to:")
        click.echo(f"{downloads_dir}\n")

        try:
            choice = click.prompt("Enter number to download (0 to cancel)", type=int, default=0)

            if choice == 0:
                click.echo("Cancelled.")
                return

            if choice < 1 or choice > len(menu_options):
                click.echo("Invalid selection.")
                return

            selected_data = menu_options[choice - 1]["data"]

        except (KeyboardInterrupt, EOFError):
            click.echo("\nCancelled.")
            return
        except Exception as e:
            click.echo(f"Error: {e}", err=True)
            return

        # Process selection (selected_data already set above)
        if not selected_data:
            click.echo("Invalid selection.")
            return

        # Prepare download list
        files_to_download = []

        if selected_data["type"] == "category":
            # Download all files in category
            files_to_download = selected_data["files"]
            click.echo(f"\nDownloading {len(files_to_download)} files...")
        elif selected_data["type"] == "file":
            # Download file(s) - can be a list
            files_to_download = selected_data["files"]
            click.echo(f"\nDownloading {len(files_to_download)} file(s)...")

        # Create output directory if needed
        downloads_dir.mkdir(parents=True, exist_ok=True)

        # Download files
        success_count = 0
        for file_info in files_to_download:
            filename = file_info["filename"]
            url = file_info["url"]
            output_path = downloads_dir / filename

            try:
                click.echo(f"  Downloading {filename}...")
                response = requests.get(url, timeout=30)
                response.raise_for_status()

                with builtin_open(output_path, "wb") as f:
                    f.write(response.content)

                file_size = len(response.content)
                size_mb = file_size / (1024 * 1024)
                if size_mb >= 1:
                    size_str = f"{size_mb:.1f} MB"
                else:
                    size_str = f"{file_size / 1024:.1f} KB"

                click.echo(f"    Saved to {output_path} ({size_str})")
                success_count += 1

            except Exception as e:
                click.echo(f"    Error downloading {filename}: {e}", err=True)

        click.echo(f"\nDownloaded {success_count} of {len(files_to_download)} files successfully.")

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@click.command(name="md-link")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def md_link(output_json):
    """
    Get Markdown link for the current page.

    Returns [title](url) format with cleaned page title.
    Strips website name from title (splits on " |", " -", " –").

    Examples:

        inspekt md-link

        inspekt md-link --json
    """
    client = BridgeClient()

    if not client.is_alive():
        click.echo("Error: Bridge server is not running. Start it with: inspekt start", err=True)
        sys.exit(1)

    # Get current page URL and title
    code = """
    ({
        url: location.href,
        title: document.title
    })
    """

    try:
        result = client.execute(code)

        if result.get("ok"):
            data = result.get("result") or {}

            if not data:
                click.echo("Error: No data returned from browser.", err=True)
                sys.exit(1)

            url = data.get("url", "")
            raw_title = data.get("title", "")

            # Clean the title - strip website name
            cleaned_title = raw_title
            website_name = ""

            # Try splitting on common separators
            for separator in [" | ", " - ", " – ", " — "]:
                if separator in raw_title:
                    parts = raw_title.split(separator)
                    # Use the first part as the clean title, last part as website name
                    cleaned_title = parts[0].strip()
                    website_name = parts[-1].strip()
                    break

            # Create markdown link
            md_link_str = f"[{cleaned_title}]({url})"

            if output_json:
                import json
                output_data = {
                    "url": url,
                    "title": cleaned_title,
                    "raw_title": raw_title,
                    "website_name": website_name,
                    "markdown": md_link_str
                }
                click.echo(json.dumps(output_data, indent=2))
            else:
                click.echo(md_link_str)

        else:
            click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
