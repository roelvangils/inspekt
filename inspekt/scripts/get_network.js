// Network request extraction using Performance API
// Returns detailed network timing information for all resources loaded by the page
//
// Usage: inspekt network [--type TYPE] [--json] [--sort FIELD]
//
// Note: This uses the Performance API which has limitations:
// - No HTTP status codes (only available via DevTools Network API)
// - No request/response headers
// - No response bodies
// - Buffer limit of ~150-250 entries
// - Only captures resources loaded after page navigation

(function() {
  if (!performance || !performance.getEntriesByType) {
    return {
      error: 'Performance API not available',
      entries: [],
      summary: null
    };
  }

  const resources = performance.getEntriesByType('resource');
  const currentDomain = window.location.hostname;

  // Map initiatorType to more user-friendly types
  const typeMap = {
    'script': 'script',
    'link': 'stylesheet',  // Usually CSS, but could be other link types
    'css': 'stylesheet',
    'img': 'image',
    'image': 'image',
    'fetch': 'fetch',
    'xmlhttprequest': 'xhr',
    'beacon': 'beacon',
    'video': 'video',
    'audio': 'audio',
    'track': 'track',
    'font': 'font',
    'iframe': 'document',
    'embed': 'embed',
    'object': 'object',
    'navigation': 'document',
    'other': 'other'
  };

  // Extract and format resource entries
  const entries = resources.map((entry, index) => {
    let url;
    let domain;
    let path;
    let filename;

    try {
      url = new URL(entry.name);
      domain = url.hostname;
      path = url.pathname;
      filename = path.split('/').pop() || path;
    } catch (e) {
      domain = '';
      path = entry.name;
      filename = entry.name;
    }

    // Determine if external
    const isExternal = domain && domain !== currentDomain;

    // Get transfer size (may be 0 for cross-origin requests without CORS headers)
    const transferSize = entry.transferSize || 0;
    const encodedSize = entry.encodedBodySize || 0;
    const decodedSize = entry.decodedBodySize || 0;

    // Calculate timing breakdown
    const dns = entry.domainLookupEnd - entry.domainLookupStart;
    const tcp = entry.connectEnd - entry.connectStart;
    const ssl = entry.secureConnectionStart > 0
      ? entry.connectEnd - entry.secureConnectionStart
      : 0;
    const ttfb = entry.responseStart - entry.requestStart;
    const download = entry.responseEnd - entry.responseStart;
    const total = entry.duration;

    // Determine resource type
    const initiatorType = entry.initiatorType || 'other';
    const type = typeMap[initiatorType] || initiatorType;

    // Try to refine type based on URL extension
    let refinedType = type;
    if (type === 'stylesheet' || type === 'other' || type === 'link') {
      const ext = filename.split('.').pop()?.toLowerCase();
      if (ext === 'css') refinedType = 'stylesheet';
      else if (ext === 'js') refinedType = 'script';
      else if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'ico', 'avif'].includes(ext)) refinedType = 'image';
      else if (['woff', 'woff2', 'ttf', 'otf', 'eot'].includes(ext)) refinedType = 'font';
      else if (['mp4', 'webm', 'ogg', 'mov'].includes(ext)) refinedType = 'video';
      else if (['mp3', 'wav', 'flac', 'aac'].includes(ext)) refinedType = 'audio';
      else if (ext === 'json') refinedType = 'fetch';
      else if (ext === 'html' || ext === 'htm') refinedType = 'document';
      else if (ext === 'xml') refinedType = 'xml';
      else if (ext === 'svg') refinedType = 'svg';
    }

    return {
      index: index + 1,
      url: entry.name,
      name: filename,
      domain: domain,
      path: path,
      type: refinedType,
      initiatorType: initiatorType,
      external: isExternal,

      // Size information
      transferSize: transferSize,
      encodedSize: encodedSize,
      decodedSize: decodedSize,

      // Timing information (in milliseconds)
      timing: {
        total: Math.round(total),
        dns: dns > 0 ? Math.round(dns) : 0,
        tcp: tcp > 0 ? Math.round(tcp) : 0,
        ssl: ssl > 0 ? Math.round(ssl) : 0,
        ttfb: ttfb > 0 ? Math.round(ttfb) : 0,
        download: download > 0 ? Math.round(download) : 0
      },

      // Start time relative to navigation
      startTime: Math.round(entry.startTime),

      // Protocol used
      protocol: entry.nextHopProtocol || 'unknown',

      // Cache status (heuristic based on transfer size)
      cached: transferSize === 0 && encodedSize > 0
    };
  });

  // Calculate summary statistics
  const summary = {
    totalRequests: entries.length,
    totalTransferSize: entries.reduce((sum, e) => sum + e.transferSize, 0),
    totalDecodedSize: entries.reduce((sum, e) => sum + e.decodedSize, 0),

    // Count by type
    byType: {},

    // Count by domain
    byDomain: {},

    // Timing stats
    averageDuration: entries.length > 0
      ? Math.round(entries.reduce((sum, e) => sum + e.timing.total, 0) / entries.length)
      : 0,
    slowestRequest: null,
    largestRequest: null,

    // Cache stats
    cachedRequests: entries.filter(e => e.cached).length,
    externalRequests: entries.filter(e => e.external).length
  };

  // Calculate counts by type
  entries.forEach(entry => {
    summary.byType[entry.type] = (summary.byType[entry.type] || 0) + 1;
    summary.byDomain[entry.domain] = (summary.byDomain[entry.domain] || 0) + 1;
  });

  // Find slowest and largest
  if (entries.length > 0) {
    const slowest = entries.reduce((max, e) => e.timing.total > max.timing.total ? e : max);
    const largest = entries.reduce((max, e) => e.transferSize > max.transferSize ? e : max);

    summary.slowestRequest = {
      name: slowest.name,
      url: slowest.url,
      duration: slowest.timing.total
    };

    summary.largestRequest = {
      name: largest.name,
      url: largest.url,
      size: largest.transferSize
    };
  }

  return {
    url: window.location.href,
    timestamp: new Date().toISOString(),
    entries: entries,
    summary: summary
  };
})()
