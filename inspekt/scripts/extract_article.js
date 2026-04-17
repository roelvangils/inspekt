// Extract article content from a page without external dependencies
// Custom implementation that identifies main content and cleans it

(function() {
  // Helper: Check if element is likely content (not nav/ads/footer)
  function isContentElement(el) {
    if (!el || !el.tagName) return false;

    var tag = el.tagName.toLowerCase();
    var className = (el.className || '').toLowerCase();
    var id = (el.id || '').toLowerCase();
    var combined = className + ' ' + id;

    // Skip non-content elements
    if (['script', 'style', 'noscript', 'iframe', 'embed', 'object'].indexOf(tag) !== -1) {
      return false;
    }

    // Skip navigation, ads, footers, etc.
    var skipPatterns = [
      'nav', 'menu', 'sidebar', 'footer', 'header', 'banner',
      'ad', 'advertisement', 'promo', 'sponsor',
      'comment', 'social', 'share', 'related',
      'widget', 'cookie', 'popup', 'modal'
    ];

    for (var i = 0; i < skipPatterns.length; i++) {
      if (combined.indexOf(skipPatterns[i]) !== -1) {
        return false;
      }
    }

    return true;
  }

  // Helper: Get text content length (visible text only)
  function getTextLength(el) {
    var text = (el.textContent || '').trim();
    return text.length;
  }

  // Helper: Get text density (text length / HTML length)
  function getTextDensity(el) {
    var textLen = getTextLength(el);
    var htmlLen = el.innerHTML.length;
    return htmlLen > 0 ? textLen / htmlLen : 0;
  }

  // Helper: Count paragraph-like elements
  function countParagraphs(el) {
    return el.querySelectorAll('p, div').length;
  }

  // Helper: Clean text
  function cleanText(text) {
    return text
      .replace(/\s+/g, ' ')  // Normalize whitespace
      .replace(/\n\s*\n\s*\n/g, '\n\n')  // Max 2 newlines
      .trim();
  }

  // Helper: Extract clean text from element
  function extractText(el) {
    var parts = [];
    var children = el.childNodes;

    for (var i = 0; i < children.length; i++) {
      var child = children[i];

      if (child.nodeType === 3) {
        // Text node
        var text = child.textContent.trim();
        if (text) parts.push(text);
      } else if (child.nodeType === 1) {
        // Element node
        var tag = child.tagName.toLowerCase();

        if (['script', 'style', 'noscript'].indexOf(tag) !== -1) {
          continue;
        }

        if (tag === 'p' || tag === 'div' || tag === 'article' || tag === 'section') {
          var childText = extractText(child);
          if (childText) parts.push(childText);
        } else if (tag === 'br') {
          parts.push('\n');
        } else if (tag === 'h1' || tag === 'h2' || tag === 'h3' || tag === 'h4' || tag === 'h5' || tag === 'h6') {
          var heading = child.textContent.trim();
          if (heading) parts.push('\n\n' + heading + '\n');
        } else if (tag === 'li') {
          var listText = child.textContent.trim();
          if (listText) parts.push('• ' + listText + '\n');
        } else if (tag === 'blockquote') {
          var quoteText = child.textContent.trim();
          if (quoteText) parts.push('\n> ' + quoteText + '\n');
        } else {
          var otherText = extractText(child);
          if (otherText) parts.push(otherText);
        }
      }
    }

    return cleanText(parts.join(' '));
  }

  // Find the article title
  function findTitle() {
    // Try meta tags first
    var ogTitle = document.querySelector('meta[property="og:title"]');
    if (ogTitle && ogTitle.content) return ogTitle.content;

    var twitterTitle = document.querySelector('meta[name="twitter:title"]');
    if (twitterTitle && twitterTitle.content) return twitterTitle.content;

    // Try h1
    var h1 = document.querySelector('h1');
    if (h1) return h1.textContent.trim();

    // Fall back to document title
    return document.title;
  }

  // Find the author/byline
  function findAuthor() {
    // Try meta tags
    var authorMeta = document.querySelector('meta[name="author"]');
    if (authorMeta && authorMeta.content) return authorMeta.content;

    var ogAuthor = document.querySelector('meta[property="article:author"]');
    if (ogAuthor && ogAuthor.content) return ogAuthor.content;

    // Look for common author patterns
    var authorPatterns = [
      '[class*="author"]',
      '[class*="byline"]',
      '[rel="author"]',
      '[itemprop="author"]'
    ];

    for (var i = 0; i < authorPatterns.length; i++) {
      var authorEl = document.querySelector(authorPatterns[i]);
      if (authorEl) {
        var authorText = authorEl.textContent.trim();
        if (authorText.length < 100) {
          return authorText.replace(/^by\s+/i, '');
        }
      }
    }

    return null;
  }

  // Helper: Score element for content likelihood
  function scoreElement(el) {
    var textLen = getTextLength(el);
    var density = getTextDensity(el);
    var paragraphs = countParagraphs(el);
    return textLen * 0.5 + density * 1000 + paragraphs * 10;
  }

  // Find the main content element
  function findMainContent() {
    // Try semantic HTML5 elements first
    var article = document.querySelector('article');
    if (article && getTextLength(article) > 500) return article;

    var main = document.querySelector('main, [role="main"]');
    if (main && getTextLength(main) > 500) return main;

    // Look for common article container patterns
    var contentPatterns = [
      '[class*="article"]', '[class*="content"]', '[class*="post"]', '[class*="entry"]',
      '[id*="article"]', '[id*="content"]', '[id*="post"]'
    ];

    var bestCandidate = null;
    var bestScore = 0;

    for (var i = 0; i < contentPatterns.length; i++) {
      var candidates = document.querySelectorAll(contentPatterns[i]);
      for (var j = 0; j < candidates.length; j++) {
        var candidate = candidates[j];
        if (!isContentElement(candidate)) continue;

        var score = scoreElement(candidate);
        if (score > bestScore && getTextLength(candidate) > 200) {
          bestScore = score;
          bestCandidate = candidate;
        }
      }
    }

    if (bestCandidate) return bestCandidate;

    // Last resort: scan all major containers
    var allContainers = document.querySelectorAll('div, section, article');
    for (var k = 0; k < allContainers.length; k++) {
      var container = allContainers[k];
      if (!isContentElement(container)) continue;

      var len = getTextLength(container);
      if (len > bestScore && countParagraphs(container) > 3) {
        bestScore = len;
        bestCandidate = container;
      }
    }

    return bestCandidate || document.body;
  }

  // Main extraction
  try {
    var title = findTitle();
    var author = findAuthor();
    var contentElement = findMainContent();

    if (!contentElement) {
      return {
        error: 'Could not identify main content area',
        url: window.location.href
      };
    }

    var content = extractText(contentElement);

    if (!content || content.length < 100) {
      return {
        error: 'Could not extract sufficient article content. This page may not be an article.',
        url: window.location.href
      };
    }

    // Create excerpt (first 200 chars)
    var excerpt = content.substring(0, 200);
    if (content.length > 200) {
      excerpt += '…';
    }

    return {
      title: title,
      byline: author,
      content: content,
      excerpt: excerpt,
      length: content.length,
      url: window.location.href,
      lang: document.documentElement.lang || null
    };
  } catch (error) {
    return {
      error: 'Error extracting article: ' + error.message,
      url: window.location.href
    };
  }
})()
