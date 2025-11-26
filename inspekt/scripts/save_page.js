// Save current page using SingleFile library
// This script wraps SingleFile's getPageData() function for use with Inspekt
//
// IMPORTANT: This script expects the SingleFile libraries to be injected
// BEFORE this script runs. The libraries should define the global 'singlefile' object.

(async function() {
  // Default options - can be overridden via __INSPEKT_SAVE_OPTIONS__
  const defaultOptions = {
    // Resource handling
    removeHiddenElements: true,
    removeUnusedStyles: true,
    removeUnusedFonts: true,
    removeFrames: false,
    removeImports: true,
    removeScripts: true,
    removeAudioSrc: true,
    removeVideoSrc: false,
    removeAlternativeFonts: true,
    removeAlternativeMedias: true,
    removeAlternativeImages: true,

    // Compression and optimization
    compressHTML: false,
    compressCSS: false,
    groupDuplicateImages: true,

    // Image handling
    loadDeferredImages: true,
    loadDeferredImagesMaxIdleTime: 1500,
    loadDeferredImagesBlockCookies: false,
    loadDeferredImagesBlockStorage: false,
    loadDeferredImagesKeepZoomLevel: false,

    // Other settings
    saveRawPage: false,
    insertCanonicalLink: true,
    insertMetaNoIndex: false,
    insertMetaCSP: true,
    insertSingleFileComment: true,
    blockScripts: true,
    blockAudios: true,
    blockVideos: false,

    // Content settings
    includeBOM: false,
    insertTextBody: false,
    resolveFragmentIdentifierURLs: false,
    saveFavicon: true,

    // URL handling
    url: window.location.href
  };

  // Merge with user options if provided
  const options = typeof __INSPEKT_SAVE_OPTIONS__ !== 'undefined'
    ? { ...defaultOptions, ...__INSPEKT_SAVE_OPTIONS__ }
    : defaultOptions;

  try {
    // Check if SingleFile is loaded
    if (typeof singlefile === 'undefined' || typeof singlefile.getPageData !== 'function') {
      return {
        ok: false,
        error: 'SingleFile library not loaded. The singlefile global is: ' + (typeof singlefile),
        url: window.location.href
      };
    }

    // Progress callback for status updates
    let lastProgress = '';
    options.onprogress = (event) => {
      if (event.type) {
        lastProgress = event.type;
      }
    };

    // Capture the page using SingleFile
    const pageData = await singlefile.getPageData(options, undefined, document, window);

    if (!pageData || !pageData.content) {
      return {
        ok: false,
        error: 'SingleFile returned empty content',
        url: window.location.href
      };
    }

    // Generate filename
    const title = pageData.title || document.title || 'Untitled';
    const cleanTitle = title
      .replace(/[<>:"/\\|?*]/g, '')
      .replace(/\s+/g, '_')
      .substring(0, 100);
    const date = new Date().toISOString().split('T')[0];
    const filename = `${cleanTitle}_${date}.html`;

    return {
      ok: true,
      content: pageData.content,
      title: pageData.title || document.title,
      filename: pageData.filename || filename,
      url: window.location.href,
      stats: {
        contentLength: pageData.content.length,
        lastProgress: lastProgress
      }
    };

  } catch (error) {
    return {
      ok: false,
      error: error.message || String(error),
      stack: error.stack,
      url: window.location.href
    };
  }
})()
