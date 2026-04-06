// Extract article content using Defuddle
// This script requires defuddle.js to be loaded first
//
// Defuddle is created by the Obsidian team as a modern alternative to
// Mozilla Readability. It's more conservative (keeps uncertain content)
// and better handles modern SPAs.

(function() {
  // Check if Defuddle is loaded
  if (typeof Defuddle === 'undefined') {
    return {
      error: 'Defuddle library not loaded. typeof=' + typeof Defuddle,
      url: window.location.href
    };
  }

  try {
    // Create Defuddle instance and parse
    // Defuddle works directly on the document (doesn't need a clone)
    var defuddle = new Defuddle(document, {
      url: window.location.href,
      debug: false
    });

    var result = defuddle.parse();

    if (!result || !result.content) {
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
    var textContent = htmlToText(result.content);

    // Create excerpt (first 200 chars of text)
    var excerpt = textContent.substring(0, 200);
    if (textContent.length > 200) {
      excerpt += '...';
    }

    // Get published date - Defuddle returns it directly
    var publishedDate = result.published || null;

    // If not found, try meta tags
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
      // Core fields matching extract_article_readability.js interface
      title: result.title || document.title,
      byline: result.author || null,
      content: textContent,
      excerpt: result.description || excerpt,
      length: textContent.length,
      url: window.location.href,
      lang: document.documentElement.lang || null,

      // Additional fields
      siteName: result.site || result.domain || null,
      publishedDate: publishedDate,
      dir: result.dir || null,

      // HTML content (for Markdown conversion)
      htmlContent: result.content || null,

      // Metadata
      extractor: 'defuddle',
      extractorVersion: '0.6.6',

      // Defuddle-specific extras
      wordCount: result.wordCount || null,
      parseTime: result.parseTime || null,
      image: result.image || null
    };

  } catch (error) {
    return {
      error: 'Error extracting article: ' + error.message,
      url: window.location.href
    };
  }
})()
