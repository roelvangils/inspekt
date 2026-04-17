// Extract article content using Mozilla Readability
// This script requires Readability.js to be loaded first
//
// Readability is the library used by Firefox Reader View.
// It provides robust article extraction even on complex pages.

(function() {
  // Check if Readability is loaded
  if (typeof Readability === 'undefined') {
    return {
      error: 'Readability library not loaded. typeof=' + typeof Readability,
      url: window.location.href
    };
  }

  try {
    // Firefox's approach: serialize and re-parse for a clean document
    // This works better than cloneNode for SPAs and complex pages
    var serializer = new XMLSerializer();
    var docString = serializer.serializeToString(document);

    // Parse the serialized HTML into a fresh document
    var parser = new DOMParser();
    var documentClone = parser.parseFromString(docString, 'text/html');

    // Verify the parsed document is valid
    if (!documentClone || !documentClone.documentElement) {
      return {
        error: 'Failed to parse document',
        url: window.location.href
      };
    }

    // Set the base URI for relative URL resolution
    var base = documentClone.createElement('base');
    base.href = window.location.href;
    documentClone.head.insertBefore(base, documentClone.head.firstChild);

    // Pre-process: Remove elements that Readability should exclude but sometimes misses
    // Readability's heuristics can fail on modern SPAs with complex DOM structures
    var removeSelectors = [
      'nav',                    // Navigation elements (Readability only checks role, not tag)
      '[role="navigation"]',
      '[role="banner"]',        // Page headers
      '[role="contentinfo"]',   // Page footers
      'header:not(article header)',  // Page-level headers (not article headers)
      'footer:not(article footer)'   // Page-level footers (not article footers)
    ];

    removeSelectors.forEach(function(selector) {
      var elements = documentClone.querySelectorAll(selector);
      for (var i = 0; i < elements.length; i++) {
        elements[i].remove();
      }
    });

    // Create Readability instance with options
    var reader = new Readability(documentClone, {
      // Keep classes that might be useful for styling
      keepClasses: false,
      // Debug mode off
      debug: false,
      // Minimum content length to be considered an article
      charThreshold: 100
    });

    // Parse the article
    var article;
    try {
      article = reader.parse();
    } catch (parseError) {
      return {
        error: 'Readability.parse() failed: ' + parseError.message,
        url: window.location.href
      };
    }

    if (!article) {
      return {
        error: 'Could not extract article content. This page may not be an article.',
        url: window.location.href
      };
    }

    // Extract plain text from HTML content
    function htmlToText(html) {
      var temp = document.createElement('div');
      temp.innerHTML = html;

      // Remove scripts and styles
      var scripts = temp.querySelectorAll('script, style, noscript');
      for (var i = 0; i < scripts.length; i++) {
        scripts[i].remove();
      }

      // Get text content
      var text = temp.textContent || temp.innerText || '';

      // Clean up whitespace
      text = text
        .replace(/\s+/g, ' ')
        .replace(/\n\s*\n\s*\n/g, '\n\n')
        .trim();

      return text;
    }

    // Get plain text content
    var textContent = article.textContent || htmlToText(article.content);

    // Create excerpt (first 200 chars of text)
    var excerpt = textContent.substring(0, 200);
    if (textContent.length > 200) {
      excerpt += '…';
    }

    // Get published date from meta tags if Readability didn't find it
    var publishedDate = article.publishedTime;
    if (!publishedDate) {
      var dateSelectors = [
        'meta[property="article:published_time"]',
        'meta[name="date"]',
        'meta[name="DC.date"]',
        'time[datetime]',
        '[itemprop="datePublished"]'
      ];

      for (var j = 0; j < dateSelectors.length; j++) {
        var dateEl = document.querySelector(dateSelectors[j]);
        if (dateEl) {
          publishedDate = dateEl.getAttribute('content') ||
                          dateEl.getAttribute('datetime') ||
                          dateEl.textContent;
          if (publishedDate) break;
        }
      }
    }

    return {
      // Core fields matching extract_article.js interface
      title: article.title || document.title,
      byline: article.byline || null,
      content: textContent,
      excerpt: article.excerpt || excerpt,
      length: textContent.length,
      url: window.location.href,
      lang: article.lang || document.documentElement.lang || null,

      // Additional Readability-specific fields
      siteName: article.siteName || null,
      publishedDate: publishedDate || null,
      dir: article.dir || null,

      // HTML content (if needed for rich display)
      htmlContent: article.content || null,

      // Metadata
      extractor: 'readability',
      extractorVersion: '0.6.0'
    };

  } catch (error) {
    return {
      error: 'Error extracting article: ' + error.message,
      url: window.location.href
    };
  }
})()
