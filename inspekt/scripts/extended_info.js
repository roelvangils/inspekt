// Extended page information - additional metrics beyond core info
// Returns performance, structured data, media, console, content stats, etc.

(function() {
  const extended = {};

  // 1. Performance Metrics
  extended.performance = (() => {
    if (!window.performance || !window.performance.timing) return null;

    const timing = performance.timing;
    const navigation = performance.navigation;

    const loadTime = timing.loadEventEnd - timing.navigationStart;
    const domContentLoaded = timing.domContentLoadedEventEnd - timing.navigationStart;
    const ttfb = timing.responseStart - timing.navigationStart;

    const result = {
      pageLoadTime: loadTime > 0 ? (loadTime / 1000).toFixed(2) : null,
      domContentLoaded: domContentLoaded > 0 ? (domContentLoaded / 1000).toFixed(2) : null,
      timeToFirstByte: ttfb > 0 ? ttfb : null,
      navigationType: navigation.type === 0 ? 'navigate' : navigation.type === 1 ? 'reload' : 'back_forward'
    };

    // Try to get paint timings
    if (performance.getEntriesByType) {
      const paintEntries = performance.getEntriesByType('paint');
      paintEntries.forEach(entry => {
        if (entry.name === 'first-paint') {
          result.firstPaint = (entry.startTime / 1000).toFixed(2);
        }
        if (entry.name === 'first-contentful-paint') {
          result.firstContentfulPaint = (entry.startTime / 1000).toFixed(2);
        }
      });

      // Try to get LCP
      try {
        const lcpEntries = performance.getEntriesByType('largest-contentful-paint');
        if (lcpEntries.length > 0) {
          const lcp = lcpEntries[lcpEntries.length - 1];
          result.largestContentfulPaint = (lcp.startTime / 1000).toFixed(2);
        }
      } catch (e) {}
    }

    return result;
  })()

  // 2. More Accessibility Details
  extended.accessibility = (() => {
    const linksWithoutText = Array.from(document.querySelectorAll('a')).filter(link => {
      const text = link.textContent.trim();
      const ariaLabel = link.getAttribute('aria-label');
      const ariaLabelledby = link.getAttribute('aria-labelledby');
      const title = link.getAttribute('title');
      return !text && !ariaLabel && !ariaLabelledby && !title;
    }).length;

    const buttonsWithoutLabels = Array.from(document.querySelectorAll('button')).filter(btn => {
      const text = btn.textContent.trim();
      const ariaLabel = btn.getAttribute('aria-label');
      const ariaLabelledby = btn.getAttribute('aria-labelledby');
      const title = btn.getAttribute('title');
      return !text && !ariaLabel && !ariaLabelledby && !title;
    }).length;

    const hasSkipLink = (() => {
      const links = Array.from(document.querySelectorAll('a[href^="#"]'));
      return links.some(link => {
        const text = link.textContent.toLowerCase();
        const href = link.getAttribute('href');
        return (text.includes('skip') || text.includes('jump')) &&
               (href === '#main' || href === '#content' || href.includes('main') || href.includes('content'));
      });
    })()

    const ariaCount = document.querySelectorAll('[aria-label], [aria-labelledby], [aria-describedby], [role], [aria-hidden], [aria-live], [aria-expanded], [aria-controls]').length;

    return {
      linksWithoutText,
      buttonsWithoutLabels,
      hasSkipLink,
      ariaAttributeCount: ariaCount,
      langAttribute: document.documentElement.hasAttribute('lang')
    };
  })()

  // 3. Structured Data (Schema.org)
  extended.structuredData = (() => {
    const jsonLd = [];
    const scripts = document.querySelectorAll('script[type="application/ld+json"]');
    scripts.forEach(script => {
      try {
        const data = JSON.parse(script.textContent);
        const type = data['@type'] || (data['@graph'] && data['@graph'][0] && data['@graph'][0]['@type']);
        if (type) {
          jsonLd.push(type);
        }
      } catch (e) {}
    });

    const microdata = document.querySelectorAll('[itemscope]').length;

    return {
      jsonLdCount: jsonLd.length,
      jsonLdTypes: jsonLd,
      microdataCount: microdata
    };
  })()

  // 4. Media Content
  extended.media = (() => {
    return {
      videos: document.querySelectorAll('video').length,
      audio: document.querySelectorAll('audio').length,
      svgImages: document.querySelectorAll('svg, img[src$=".svg"]').length
    };
  })()

  // 5. More SEO
  extended.seoExtra = (() => {
    const sitemap = (() => {
      const sitemapLink = document.querySelector('link[rel="sitemap"]');
      return sitemapLink ? sitemapLink.href : null;
    })()

    const favicon = (() => {
      const icon = document.querySelector('link[rel="icon"], link[rel="shortcut icon"]');
      if (icon) {
        const href = icon.href;
        if (href.endsWith('.svg')) return 'SVG';
        if (href.endsWith('.png')) return 'PNG';
        if (href.endsWith('.ico')) return 'ICO';
        return 'Yes';
      }
      return null;
    })()

    const alternateLanguages = Array.from(document.querySelectorAll('link[rel="alternate"][hreflang]')).map(link => ({
      lang: link.getAttribute('hreflang'),
      href: link.href
    }));

    return {
      sitemap,
      favicon,
      alternateLanguages
    };
  })()

  // 6. Console Messages (capture new messages)
  extended.consoleStats = (() => {
    // We can't reliably get historical console messages, but we can report if console methods exist
    return {
      available: typeof console !== 'undefined',
      note: 'Real-time console monitoring would require persistent connection'
    };
  })()

  // 7. Third-party Resources
  extended.thirdParty = (() => {
    const currentDomain = window.location.hostname;
    const externalDomains = new Set();

    // Check scripts
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

    // Check links (stylesheets, etc.)
    Array.from(document.querySelectorAll('link[href]')).forEach(link => {
      const href = link.href;
      if (href) {
        try {
          const url = new URL(href);
          if (url.hostname !== currentDomain && url.hostname) {
            externalDomains.add(url.hostname);
          }
        } catch (e) {}
      }
    });

    // Check images
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

    return {
      externalDomainCount: externalDomains.size,
      externalDomains: Array.from(externalDomains).slice(0, 10) // Top 10
    };
  })()

  // 8. Content Stats
  extended.content = (() => {
    const mainElement = document.querySelector('main, [role="main"], article') || document.body;
    const text = mainElement.textContent || '';
    const words = text.trim().split(/\s+/).filter(w => w.length > 0).length;
    const chars = text.length;
    const readingTime = Math.ceil(words / 200); // Average reading speed

    const languageLinks = Array.from(document.querySelectorAll('a[hreflang], [lang]:not(html)')).length;

    return {
      wordCount: words,
      charCount: chars,
      estimatedReadingTime: readingTime,
      languageSwitchers: languageLinks,
      paragraphs: mainElement.querySelectorAll('p').length,
      lists: mainElement.querySelectorAll('ul, ol').length
    };
  })()

  // 9. Network Summary (from Performance API)
  extended.network = (() => {
    if (!performance || !performance.getEntriesByType) return null;

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

      return {
        totalRequests: resources.length,
        totalSize: totalSize,
        largestResource: largestResource
      };
    } catch (e) {
      return null;
    }
  })()

  // 10. Font Details
  extended.fonts = (() => {
    const fonts = {
      googleFonts: [],
      customFonts: [],
      totalFontFiles: 0
    };

    // Check for Google Fonts
    const googleFontLinks = document.querySelectorAll('link[href*="fonts.googleapis.com"]');
    googleFontLinks.forEach(link => {
      const href = link.href;
      const match = href.match(/family=([^&:]+)/);
      if (match) {
        const families = match[1].split('|');
        families.forEach(family => {
          const decoded = decodeURIComponent(family.replace(/\+/g, ' '));
          if (!fonts.googleFonts.includes(decoded)) {
            fonts.googleFonts.push(decoded);
          }
        });
      }
    });

    // Check for @font-face in stylesheets and extract font family names
    const customFontNames = new Set();
    try {
      Array.from(document.styleSheets).forEach(sheet => {
        try {
          Array.from(sheet.cssRules || []).forEach(rule => {
            if (rule instanceof CSSFontFaceRule) {
              const fontFamily = rule.style.getPropertyValue('font-family');
              if (fontFamily) {
                // Clean up quotes and whitespace
                const cleanName = fontFamily.replace(/['"]/g, '').trim();
                if (cleanName) {
                  customFontNames.add(cleanName);
                }
              }
            }
          });
        } catch (e) {
          // Cross-origin stylesheet, can't access
        }
      });
    } catch (e) {}
    fonts.customFonts = Array.from(customFontNames);

    // Count font files from performance entries
    if (performance && performance.getEntriesByType) {
      const resources = performance.getEntriesByType('resource');
      fonts.totalFontFiles = resources.filter(r =>
        r.name.match(/\.(woff2?|ttf|otf|eot)$/i)
      ).length;
    }

    return fonts;
  })()

  // 11. Form Details
  extended.forms = (() => {
    const forms = [];

    document.querySelectorAll('form').forEach((form, index) => {
      const formData = {
        id: form.id || form.name || `Form ${index + 1}`,
        action: form.action || 'JavaScript',
        method: form.method.toUpperCase() || 'GET',
        fields: [],
        issues: []
      };

      // Get all input fields
      const inputs = form.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="button"]), select, textarea');
      inputs.forEach(input => {
        const field = {
          type: input.type || input.tagName.toLowerCase(),
          name: input.name,
          id: input.id
        };

        // Check for label
        const hasLabel = input.labels && input.labels.length > 0;
        const hasAriaLabel = input.hasAttribute('aria-label') || input.hasAttribute('aria-labelledby');

        if (!hasLabel && !hasAriaLabel) {
          field.missingLabel = true;
          formData.issues.push(`${field.type} field without label`);
        }

        formData.fields.push(field);
      });

      forms.push(formData);
    });

    return forms;
  })()

  // 12. More Core Web Vitals
  extended.coreWebVitals = (() => {
    const vitals = {};

    // Try to get CLS (Cumulative Layout Shift)
    try {
      if (performance.getEntriesByType) {
        const layoutShifts = performance.getEntriesByType('layout-shift');
        if (layoutShifts.length > 0) {
          const cls = layoutShifts.reduce((sum, entry) => {
            if (!entry.hadRecentInput) {
              return sum + entry.value;
            }
            return sum;
          }, 0);
          vitals.cls = cls.toFixed(3);
        }
      }
    } catch (e) {}

    // Try to get FID/INP (First Input Delay / Interaction to Next Paint)
    try {
      if (performance.getEntriesByType) {
        const firstInput = performance.getEntriesByType('first-input');
        if (firstInput.length > 0) {
          vitals.fid = Math.round(firstInput[0].processingStart - firstInput[0].startTime);
        }

        // INP is newer and may not be available
        const interactions = performance.getEntriesByType('event');
        if (interactions.length > 0) {
          const durations = interactions.map(e => e.duration).filter(d => d > 0);
          if (durations.length > 0) {
            vitals.inp = Math.round(Math.max(...durations));
          }
        }
      }
    } catch (e) {}

    return Object.keys(vitals).length > 0 ? vitals : null;
  })()

  return extended;
})()
