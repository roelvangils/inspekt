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
from inspekt.client import BridgeClient


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
            click.echo(f"Extension:    v{userscript_version} ({browser_name} {bridge_label})")
            click.echo(f"URL:          {data.get('url', 'N/A')}")
            click.echo(f"Title:        {data.get('title', 'N/A')}")
            click.echo(f"State:        {data.get('readyState', 'N/A')}")
            click.echo(f"Domain:       {data.get('domain', 'N/A')}")
            click.echo(f"Protocol:     {data.get('protocol', 'N/A')}")
            click.echo(f"Viewport:     {data.get('width', 'N/A')}x{data.get('height', 'N/A')}")

            if extended:
                click.echo("")
                click.echo("=== Extended Information ===")
                click.echo("")

                # Language and encoding (with natural language detection)
                declared_lang = data.get("specifiedLanguage", "N/A")
                click.echo(f"Language:           {declared_lang}")

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
                                detected = detect(
                                    para_text
                                )  # Returns ISO 639-1 code (e.g., 'en', 'fr')
                                if detected:
                                    # Compare with declared language
                                    if (
                                        declared_lang != "N/A"
                                        and declared_lang.lower() != detected.lower()
                                    ):
                                        click.echo(f"  Detected:         {detected}")
                                        click.echo(
                                            f'  ⚠️  Language mismatch! Content appears to be "{detected}" but lang="{declared_lang}"'
                                        )
                                    else:
                                        click.echo(f"  Detected:         {detected} ✓ matches")
                            except LangDetectException:
                                pass  # Could not detect language
                except ImportError:
                    pass  # langdetect not installed
                except Exception:
                    pass  # Language detection failed

                click.echo(f"Character Set:      {data.get('charset', 'N/A')}")

                # Resources
                click.echo("")
                click.echo("Resources:")
                click.echo(f"  Scripts:          {data.get('scriptCount', 0)}")
                click.echo(f"  Stylesheets:      {data.get('stylesheetCount', 0)}")
                click.echo(f"  Images:           {data.get('imageCount', 0)}")
                click.echo(f"  Links:            {data.get('linkCount', 0)}")
                click.echo(f"  Forms:            {data.get('formCount', 0)}")
                click.echo(f"  Iframes:          {data.get('iframeCount', 0)}")

                # Performance Metrics (from extended data)
                extended_data = data.get("_extended", {})
                perf = extended_data.get("performance", {})
                if perf:
                    click.echo("")
                    click.echo("Performance:")
                    if perf.get("pageLoadTime"):
                        click.echo(f"  Page Load Time:    {perf['pageLoadTime']}s")
                    if perf.get("domContentLoaded"):
                        click.echo(f"  DOM Content Loaded: {perf['domContentLoaded']}s")
                    if perf.get("timeToFirstByte"):
                        click.echo(f"  Time to First Byte: {perf['timeToFirstByte']}ms")
                    if perf.get("firstPaint"):
                        click.echo(f"  First Paint:       {perf['firstPaint']}s")
                    if perf.get("firstContentfulPaint"):
                        click.echo(f"  First Contentful Paint: {perf['firstContentfulPaint']}s")
                    if perf.get("largestContentfulPaint"):
                        click.echo(f"  Largest Contentful Paint: {perf['largestContentfulPaint']}s")

                # Media Content (from extended data)
                media = extended_data.get("media", {})
                if media and (
                    media.get("videos", 0) > 0
                    or media.get("audio", 0) > 0
                    or media.get("svgImages", 0) > 0
                ):
                    click.echo("")
                    click.echo("Media:")
                    if media.get("videos", 0) > 0:
                        click.echo(f"  Videos:            {media['videos']}")
                    if media.get("audio", 0) > 0:
                        click.echo(f"  Audio:             {media['audio']}")
                    if media.get("svgImages", 0) > 0:
                        click.echo(f"  SVG Images:        {media['svgImages']}")

                # Content Stats (from extended data)
                content = extended_data.get("content", {})
                if content:
                    click.echo("")
                    click.echo("Content:")
                    if content.get("wordCount"):
                        click.echo(f"  Word Count:        ~{content['wordCount']:,} words")
                    if content.get("estimatedReadingTime"):
                        click.echo(
                            f"  Reading Time:      ~{content['estimatedReadingTime']} minutes"
                        )
                    if content.get("paragraphs"):
                        click.echo(f"  Paragraphs:        {content['paragraphs']}")
                    if content.get("lists"):
                        click.echo(f"  Lists:             {content['lists']}")
                    if content.get("languageSwitchers", 0) > 0:
                        click.echo(f"  Language Switchers: {content['languageSwitchers']}")

                # Document dimensions
                click.echo("")
                click.echo("Document Dimensions:")
                click.echo(f"  Total Height:     {data.get('scrollHeight', 'N/A')}px")
                click.echo(f"  Total Width:      {data.get('scrollWidth', 'N/A')}px")

                # Storage
                click.echo("")
                click.echo("Storage:")
                cookie_count = data.get("cookieCount", 0)
                click.echo(f"  Cookies:          {cookie_count}")

                # Get actual cookie names
                if cookie_count > 0:
                    try:
                        cookie_code = "document.cookie.split(';').map(c => c.trim().split('=')[0]).filter(Boolean)"
                        cookie_result = client.execute(cookie_code, timeout=2.0)
                        if cookie_result.get("ok"):
                            cookie_names = cookie_result.get("result", [])
                            if cookie_names:
                                for i, name in enumerate(cookie_names[:8], 1):
                                    click.echo(f"    {i}. {name}")
                                if len(cookie_names) > 8:
                                    click.echo(f"    ... and {len(cookie_names) - 8} more")
                    except Exception:
                        pass

                local_kb = data.get("localStorageSize", 0) / 1024
                click.echo(f"  LocalStorage:     {local_kb:.2f} KB")

                # Get localStorage keys
                if local_kb > 0:
                    try:
                        ls_code = "Object.keys(localStorage)"
                        ls_result = client.execute(ls_code, timeout=2.0)
                        if ls_result.get("ok"):
                            ls_keys = ls_result.get("result", [])
                            if ls_keys:
                                for i, key in enumerate(ls_keys[:8], 1):
                                    click.echo(f"    {i}. {key}")
                                if len(ls_keys) > 8:
                                    click.echo(f"    ... and {len(ls_keys) - 8} more")
                    except Exception:
                        pass

                session_kb = data.get("sessionStorageSize", 0) / 1024
                click.echo(f"  SessionStorage:   {session_kb:.2f} KB")

                # Get sessionStorage keys
                if session_kb > 0:
                    try:
                        ss_code = "Object.keys(sessionStorage)"
                        ss_result = client.execute(ss_code, timeout=2.0)
                        if ss_result.get("ok"):
                            ss_keys = ss_result.get("result", [])
                            if ss_keys:
                                for i, key in enumerate(ss_keys[:8], 1):
                                    click.echo(f"    {i}. {key}")
                                if len(ss_keys) > 8:
                                    click.echo(f"    ... and {len(ss_keys) - 8} more")
                    except Exception:
                        pass

                click.echo(f"  Service Worker:   {'Yes' if data.get('hasServiceWorker') else 'No'}")

                # Security Info
                security = data.get("security", {})
                if security:
                    click.echo("")
                    click.echo("Security:")
                    click.echo(f"  HTTPS:            {'Yes' if security.get('isSecure') else 'No'}")
                    if security.get("isSecure") and security.get("hasMixedContent"):
                        click.echo("  Mixed Content:    ⚠️  Warning - Insecure resources detected")
                    if security.get("cspMeta"):
                        csp = security.get("cspMeta", "")
                        if len(csp) > 50:
                            csp = csp[:47] + "..."
                        click.echo(f"  CSP Meta:         {csp}")
                    if security.get("referrerPolicy"):
                        click.echo(f"  Referrer Policy:  {security.get('referrerPolicy')}")

                # Accessibility
                a11y = data.get("accessibility", {})
                if a11y:
                    click.echo("")
                    click.echo("Accessibility:")
                    click.echo(f"  Landmarks:        {a11y.get('landmarkCount', 0)} total")
                    landmarks = a11y.get("landmarks", {})
                    if landmarks:
                        for role, count in landmarks.items():
                            click.echo(f"    {role}: {count}")

                    # Heading structure
                    heading_structure = a11y.get("headingStructure", {})
                    total_headings = sum(heading_structure.values())
                    if total_headings > 0:
                        click.echo(f"  Headings:         {total_headings} total")
                        for level in ["h1", "h2", "h3", "h4", "h5", "h6"]:
                            count = heading_structure.get(level, 0)
                            if count > 0:
                                click.echo(f"    {level.upper()}: {count}")

                    # A11y issues
                    img_no_alt = a11y.get("imagesWithoutAlt", 0)
                    if img_no_alt > 0:
                        click.echo(f"  ⚠️  Images w/o alt: {img_no_alt}")

                    form_issues = a11y.get("formLabelsIssues", {})
                    if form_issues.get("missingLabels", 0) > 0:
                        click.echo(
                            f"  ⚠️  Form inputs w/o labels: {form_issues['missingLabels']}/{form_issues['total']}"
                        )

                    # Extended accessibility info
                    a11y_ext = extended_data.get("accessibility", {})
                    if a11y_ext:
                        if a11y_ext.get("linksWithoutText", 0) > 0:
                            click.echo(f"  ⚠️  Links w/o text: {a11y_ext['linksWithoutText']}")
                        if a11y_ext.get("buttonsWithoutLabels", 0) > 0:
                            click.echo(
                                f"  ⚠️  Buttons w/o labels: {a11y_ext['buttonsWithoutLabels']}"
                            )
                        if a11y_ext.get("hasSkipLink"):
                            click.echo("  ✓  Page has skip link")
                        if not a11y_ext.get("langAttribute"):
                            click.echo("  ⚠️  Missing lang attribute")
                        if a11y_ext.get("ariaAttributeCount"):
                            click.echo(
                                f"  ARIA Usage:        {a11y_ext['ariaAttributeCount']} attributes"
                            )

                # Structured Data (from extended data)
                structured = extended_data.get("structuredData", {})
                if structured and (
                    structured.get("jsonLdCount", 0) > 0 or structured.get("microdataCount", 0) > 0
                ):
                    click.echo("")
                    click.echo("Structured Data:")
                    if structured.get("jsonLdCount", 0) > 0:
                        click.echo(f"  JSON-LD:           {structured['jsonLdCount']} blocks")
                        types = structured.get("jsonLdTypes", [])
                        if types:
                            click.echo(f"    Types: {', '.join(types[:5])}")
                    if structured.get("microdataCount", 0) > 0:
                        click.echo(f"  Microdata:         {structured['microdataCount']} items")

                # SEO Metrics
                seo = data.get("seo", {})
                if seo:
                    click.echo("")
                    click.echo("SEO:")
                    if seo.get("canonical"):
                        canonical = seo["canonical"]
                        if len(canonical) > 60:
                            canonical = canonical[:57] + "..."
                        click.echo(f"  Canonical:        {canonical}")
                    if seo.get("description"):
                        desc = seo["description"]
                        if len(desc) > 60:
                            desc = desc[:57] + "..."
                        click.echo(f"  Description:      {desc}")
                    if seo.get("keywords"):
                        kw = seo["keywords"]
                        if len(kw) > 60:
                            kw = kw[:57] + "..."
                        click.echo(f"  Keywords:         {kw}")
                    if seo.get("robots"):
                        click.echo(f"  Robots:           {seo['robots']}")

                    # Open Graph
                    og = seo.get("openGraph", {})
                    if og:
                        click.echo(f"  Open Graph:       {len(og)} tags")
                        for key in ["title", "type", "image", "url"]:
                            if key in og:
                                value = og[key]
                                if len(value) > 50:
                                    value = value[:47] + "..."
                                click.echo(f"    og:{key}: {value}")

                    # Twitter Card
                    twitter = seo.get("twitterCard", {})
                    if twitter:
                        click.echo(f"  Twitter Card:     {len(twitter)} tags")
                        for key in ["card", "title", "description", "image"]:
                            if key in twitter:
                                value = twitter[key]
                                if len(value) > 50:
                                    value = value[:47] + "..."
                                click.echo(f"    twitter:{key}: {value}")

                    # SEO Extras (from extended data)
                    seo_extra = extended_data.get("seoExtra", {})
                    if seo_extra:
                        if seo_extra.get("favicon"):
                            click.echo(f"  Favicon:           {seo_extra['favicon']}")
                        if seo_extra.get("sitemap"):
                            sitemap = seo_extra["sitemap"]
                            if len(sitemap) > 50:
                                sitemap = sitemap[:47] + "..."
                            click.echo(f"  Sitemap:           {sitemap}")
                        alt_langs = seo_extra.get("alternateLanguages", [])
                        if alt_langs:
                            click.echo(f"  Alternate Languages: {len(alt_langs)}")
                            for lang in alt_langs[:3]:
                                click.echo(f"    {lang['lang']}")

                # Robots.txt
                robots_data = _get_robots_txt(data.get("url"))
                if robots_data and robots_data.get("exists"):
                    click.echo("")
                    click.echo("Robots.txt:")
                    click.echo("  Status:            Found")
                    click.echo(
                        f"  Size:              {robots_data['size']:,} bytes ({robots_data['lines']} lines)"
                    )
                    if robots_data.get("userAgents"):
                        agents = robots_data["userAgents"]
                        if len(agents) <= 3:
                            click.echo(f"  User-agents:       {', '.join(agents)}")
                        else:
                            click.echo(f"  User-agents:       {len(agents)} defined")
                    if robots_data.get("disallowRules", 0) > 0:
                        click.echo(f"  Disallow rules:    {robots_data['disallowRules']}")
                    if robots_data.get("allowRules", 0) > 0:
                        click.echo(f"  Allow rules:       {robots_data['allowRules']}")
                    if robots_data.get("sitemaps"):
                        sitemaps = robots_data["sitemaps"]
                        click.echo(f"  Sitemaps:          {len(sitemaps)} declared")
                        for sitemap in sitemaps[:2]:
                            if len(sitemap) > 50:
                                sitemap = sitemap[:47] + "..."
                            click.echo(f"    {sitemap}")

                # Third-Party Resources (from extended data)
                third_party = extended_data.get("thirdParty", {})
                if third_party and third_party.get("externalDomainCount", 0) > 0:
                    click.echo("")
                    click.echo("Third-Party:")
                    click.echo(f"  External Domains:  {third_party['externalDomainCount']}")
                    domains = third_party.get("externalDomains", [])
                    if domains:
                        for domain in domains[:8]:
                            click.echo(f"    - {domain}")

                # Browser/Device Info
                device = data.get("device", {})
                if device:
                    click.echo("")
                    click.echo("Browser/Device:")
                    click.echo(f"  Platform:         {device.get('platform', 'N/A')}")
                    click.echo(f"  Language:         {device.get('language', 'N/A')}")
                    click.echo(f"  Screen:           {device.get('screenResolution', 'N/A')}")
                    click.echo(f"  Viewport:         {device.get('viewportSize', 'N/A')}")
                    click.echo(f"  Pixel Ratio:      {device.get('devicePixelRatio', 'N/A')}")
                    click.echo(
                        f"  Touch Support:    {'Yes' if device.get('touchSupport') else 'No'}"
                    )
                    click.echo(
                        f"  Cookies Enabled:  {'Yes' if device.get('cookiesEnabled') else 'No'}"
                    )
                    click.echo(
                        f"  Online:           {'Yes' if device.get('onlineStatus') else 'No'}"
                    )

                    ua = device.get("userAgent", "")
                    if ua:
                        if len(ua) > 80:
                            # Show first 80 chars on first line, rest on second line
                            click.echo(f"  User Agent:       {ua[:80]}")
                            remaining = ua[80:]
                            if len(remaining) > 60:
                                remaining = remaining[:57] + "..."
                            click.echo(f"                    {remaining}")
                        else:
                            click.echo(f"  User Agent:       {ua}")

                # Technologies Detected
                technologies = data.get("technologies", {})
                if technologies:
                    click.echo("")
                    click.echo("Technologies Detected:")
                    for category, techs in sorted(technologies.items()):
                        if techs:
                            click.echo(f"  {category}:")
                            for tech in techs:
                                click.echo(f"    - {tech}")

                # Domain Metrics (fetched from server-side)
                domain_metrics = _get_domain_metrics(data.get("domain"))
                if domain_metrics:
                    click.echo("")
                    click.echo("Domain Metrics:")

                    if domain_metrics.get("ip"):
                        click.echo(f"  IP Address:       {domain_metrics['ip']}")

                    geo = domain_metrics.get("geolocation", {})
                    if geo:
                        location_parts = [geo.get("city"), geo.get("region"), geo.get("country")]
                        location = ", ".join([p for p in location_parts if p])
                        if location:
                            click.echo(f"  Location:         {location}")
                        if geo.get("isp"):
                            click.echo(f"  ISP:              {geo['isp']}")
                        if geo.get("org"):
                            click.echo(f"  Organization:     {geo['org']}")

                    whois = domain_metrics.get("whois", {})
                    if whois:
                        if whois.get("creation_date"):
                            click.echo(f"  Registered:       {whois['creation_date']}")
                        if whois.get("expiration_date"):
                            click.echo(f"  Expires:          {whois['expiration_date']}")
                        if whois.get("registrar"):
                            click.echo(f"  Registrar:        {whois['registrar']}")

                    ssl_info = domain_metrics.get("ssl", {})
                    if ssl_info:
                        if ssl_info.get("issuer"):
                            click.echo(f"  SSL Issuer:       {ssl_info['issuer']}")
                        if ssl_info.get("expiry"):
                            click.echo(f"  SSL Expires:      {ssl_info['expiry']}")
                        if ssl_info.get("days_remaining"):
                            days = ssl_info["days_remaining"]
                            if days < 30:
                                click.echo(f"  SSL Status:       ⚠️  Expires in {days} days")
                            else:
                                click.echo(f"  SSL Status:       Valid ({days} days remaining)")

                # Network Summary (from extended data)
                network = extended_data.get("network", {})
                if network:
                    click.echo("")
                    click.echo("Network:")
                    if network.get("totalRequests"):
                        click.echo(f"  Total Requests:    {network['totalRequests']}")
                    if network.get("totalSize"):
                        size_mb = network["totalSize"] / (1024 * 1024)
                        click.echo(f"  Total Size:        {size_mb:.2f} MB")
                    largest = network.get("largestResource")
                    if largest:
                        size_kb = largest["size"] / 1024
                        click.echo(f"  Largest Resource:  {largest['name']} ({size_kb:.2f} KB)")

                # Fonts (from extended data)
                fonts = extended_data.get("fonts", {})
                if fonts and (
                    fonts.get("googleFonts")
                    or fonts.get("customFonts")
                    or fonts.get("totalFontFiles", 0) > 0
                ):
                    click.echo("")
                    click.echo("Fonts:")
                    google_fonts = fonts.get("googleFonts", [])
                    if google_fonts:
                        click.echo(f"  Google Fonts:      {len(google_fonts)}")
                        for font in google_fonts[:5]:
                            click.echo(f"    - {font}")
                        if len(google_fonts) > 5:
                            click.echo(f"    ... and {len(google_fonts) - 5} more")
                    custom_fonts = fonts.get("customFonts", [])
                    if custom_fonts:
                        click.echo(f"  Custom @font-face: {len(custom_fonts)}")
                        for font in custom_fonts[:5]:
                            click.echo(f"    - {font}")
                        if len(custom_fonts) > 5:
                            click.echo(f"    ... and {len(custom_fonts) - 5} more")
                    if fonts.get("totalFontFiles", 0) > 0:
                        click.echo(f"  Font Files:        {fonts['totalFontFiles']}")

                # Form Details (from extended data)
                forms = extended_data.get("forms", [])
                if forms:
                    click.echo("")
                    click.echo(f"Forms ({len(forms)}):")
                    for form in forms:
                        click.echo(f"  {form['id']}:")
                        click.echo(f"    Method:          {form['method']}")
                        if form["action"] and form["action"] != "JavaScript":
                            action = form["action"]
                            if len(action) > 50:
                                action = action[:47] + "..."
                            click.echo(f"    Action:          {action}")
                        click.echo(f"    Fields:          {len(form['fields'])}")
                        if form["issues"]:
                            click.echo(f"    ⚠️  Issues:       {len(form['issues'])}")
                            for issue in form["issues"][:3]:
                                click.echo(f"      - {issue}")
                            if len(form["issues"]) > 3:
                                click.echo(f"      ... and {len(form['issues']) - 3} more")

                # Core Web Vitals (from extended data)
                cwv = extended_data.get("coreWebVitals", {})
                if cwv:
                    click.echo("")
                    click.echo("Core Web Vitals:")
                    if "cls" in cwv:
                        cls_val = float(cwv["cls"])
                        cls_status = (
                            "✓ Good"
                            if cls_val < 0.1
                            else "⚠️  Needs Improvement"
                            if cls_val < 0.25
                            else "❌ Poor"
                        )
                        click.echo(f"  CLS:               {cwv['cls']} ({cls_status})")
                    if "fid" in cwv:
                        fid_val = int(cwv["fid"])
                        fid_status = (
                            "✓ Good"
                            if fid_val < 100
                            else "⚠️  Needs Improvement"
                            if fid_val < 300
                            else "❌ Poor"
                        )
                        click.echo(f"  FID:               {cwv['fid']}ms ({fid_status})")
                    if "inp" in cwv:
                        inp_val = int(cwv["inp"])
                        inp_status = (
                            "✓ Good"
                            if inp_val < 200
                            else "⚠️  Needs Improvement"
                            if inp_val < 500
                            else "❌ Poor"
                        )
                        click.echo(f"  INP:               {cwv['inp']}ms ({inp_status})")

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

                    has_security_headers = any(headers.get(k) for k in security_headers)
                    if has_security_headers:
                        click.echo("")
                        click.echo("Security Headers:")
                        for key, label in security_headers.items():
                            value = headers.get(key)
                            if value:
                                if len(value) > 60:
                                    value = value[:57] + "..."
                                click.echo(f"  {label}: {value}")

                    # Response Headers
                    response_headers = {
                        "server": "Server",
                        "cacheControl": "Cache-Control",
                        "contentEncoding": "Content-Encoding",
                        "etag": "ETag",
                        "lastModified": "Last-Modified",
                        "contentType": "Content-Type",
                    }

                    has_response_headers = any(headers.get(k) for k in response_headers)
                    if has_response_headers:
                        click.echo("")
                        click.echo("Response Headers:")
                        for key, label in response_headers.items():
                            value = headers.get(key)
                            if value:
                                if len(value) > 60:
                                    value = value[:57] + "..."
                                click.echo(f"  {label}: {value}")

                # Meta tags
                meta_tags = data.get("metaTags", [])
                if meta_tags:
                    click.echo("")
                    click.echo(f"Meta Tags ({len(meta_tags)}):")
                    for meta in meta_tags:
                        # Format meta tag nicely
                        if "name" in meta and "content" in meta:
                            content = meta["content"]
                            if len(content) > 60:
                                content = content[:57] + "..."
                            click.echo(f"  {meta['name']}: {content}")
                        elif "property" in meta and "content" in meta:
                            content = meta["content"]
                            if len(content) > 60:
                                content = content[:57] + "..."
                            click.echo(f"  {meta['property']}: {content}")
                        elif "charset" in meta:
                            click.echo(f"  charset: {meta['charset']}")
                        elif "http-equiv" in meta:
                            click.echo(f"  {meta['http-equiv']}: {meta.get('content', '')}")
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

    Execute JavaScript interactively. Type 'exit' or press Ctrl+D to quit.
    """
    client = BridgeClient()

    if not client.is_alive():
        click.echo("Error: Bridge server is not running. Start it with: inspekt server start", err=True)
        sys.exit(1)

    click.echo("Zen Browser REPL - Type JavaScript code, 'exit' to quit")
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
    except:
        pass

    while True:
        try:
            code = click.prompt("zen>", prompt_suffix=" ", default="", show_default=False)

            if not code.strip():
                continue

            if code.strip().lower() in ["exit", "quit"]:
                break

            try:
                result = client.execute(code, timeout=10.0)
                output = format_output(result, "auto")
                if output:
                    click.echo(output)
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
        click.echo("Error: Bridge server is not running. Start it with: inspekt server start", err=True)
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
        click.echo("Error: Bridge server is not running. Start it with: inspekt server start", err=True)
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
