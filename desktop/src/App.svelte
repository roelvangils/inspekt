<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { listen, type UnlistenFn } from "@tauri-apps/api/event";
  import { open, save } from "@tauri-apps/plugin-dialog";
  import { invoke, convertFileSrc } from "@tauri-apps/api/core";
  import { getCurrentWindow } from "@tauri-apps/api/window";
  import Welcome from "./lib/components/Welcome.svelte";
  import DropZone from "./lib/components/DropZone.svelte";
  import ProgressView from "./lib/components/ProgressView.svelte";
  import ReportView from "./lib/components/ReportView.svelte";
  import TabBar from "./lib/components/tabs/TabBar.svelte";
  import TabPanel from "./lib/components/tabs/TabPanel.svelte";
  import InteractivePreview from "./lib/components/preview/InteractivePreview.svelte";
  import { preferences, loadPreferences, addRecentFile, type Preferences } from "./lib/stores/preferences";
  import { reportData, appState, appError, loadReport, clearReport, startCheck, clearError, type AppState, type AppError } from "./lib/stores/report";
  import { activeTab, setActiveTab, type ActiveTab } from "./lib/stores/ui";
  import { zoomIn, zoomOut, setZoom } from "./lib/stores/preview";
  import type { ReportData } from "./lib/types/report";
  import type { PreviewPageData, PreviewStructureNode } from "./lib/types/preview";
  import { migrateSchema } from "./lib/utils/schema-migration";

  let showWelcome = $state(false);
  let currentState = $state<AppState>("idle");
  let currentReport = $state<ReportData | null>(null);
  let currentPrefs = $state<Preferences | null>(null);
  let currentError = $state<AppError | null>(null);

  // Preview data for InteractivePreview component
  let previewPages = $state<PreviewPageData[]>([]);
  let previewTree = $state<PreviewStructureNode | null>(null);

  // Track the current PDFI extraction path for cleanup
  let currentPdfiExtractionPath = $state<string | null>(null);

  // Track paths for Save functionality
  let sourcePdfPath = $state<string | null>(null);
  let assetsBasePath = $state<string | null>(null);
  let currentPackagePath = $state<string | null>(null); // Original .pdfi path if opened from package

  // Tab state
  let currentActiveTab = $state<ActiveTab>("report");

  // Computed: whether preview is available (reactive)
  let hasPreviewAvailable = $derived(
    Boolean(currentReport?.interactive_preview?.enabled && previewPages.length > 0)
  );

  let unlistenOpen: UnlistenFn | null = null;
  let unlistenClose: UnlistenFn | null = null;
  let unlistenFileDrop: UnlistenFn | null = null;
  let unlistenDeepLink: UnlistenFn | null = null;
  let unlistenToggleSidebar: UnlistenFn | null = null;
  let unlistenSave: UnlistenFn | null = null;
  let unlistenSaveAs: UnlistenFn | null = null;
  let unlistenZoomIn: UnlistenFn | null = null;
  let unlistenZoomOut: UnlistenFn | null = null;
  let unlistenZoomReset: UnlistenFn | null = null;
  let unlistenZoomFit: UnlistenFn | null = null;

  // Subscribe to stores
  $effect(() => {
    const unsubPrefs = preferences.subscribe((p) => {
      currentPrefs = p;
      showWelcome = p?.showWelcome ?? false;
    });
    const unsubState = appState.subscribe((s) => {
      currentState = s;
    });
    const unsubReport = reportData.subscribe((r) => {
      currentReport = r;
      // Update dock badge when report changes
      updateDockBadge(r);

      // Extract preview data when report changes (e.g., after PDF check completes)
      // This ensures we don't show stale preview data from a previous session
      if (r) {
        const extractedPreviewPages = extractPreviewPages(r, "");
        const extractedPreviewTree = extractPreviewTree(r);
        previewPages = extractedPreviewPages;
        previewTree = extractedPreviewTree;
      } else {
        // Clear preview data when report is cleared
        previewPages = [];
        previewTree = null;
      }
    });
    const unsubError = appError.subscribe((e) => {
      currentError = e;
    });
    const unsubTab = activeTab.subscribe((t) => {
      currentActiveTab = t;
    });

    return () => {
      unsubPrefs();
      unsubState();
      unsubReport();
      unsubError();
      unsubTab();
    };
  });

  onMount(async () => {
    await loadPreferences();

    // Listen for menu events
    unlistenOpen = await listen("menu-open", handleMenuOpen);
    unlistenClose = await listen("menu-close", handleMenuClose);
    unlistenToggleSidebar = await listen("menu-toggle-sidebar", () => {
      // Emit a custom event for the sidebar to listen to
      window.dispatchEvent(new CustomEvent("toggle-sidebar"));
    });

    // Listen for save events
    unlistenSave = await listen("menu-save", handleMenuSave);
    unlistenSaveAs = await listen("menu-save-as", handleMenuSaveAs);

    // Listen for zoom events from View menu (⌘+, ⌘-, ⌘0, ⌘9)
    unlistenZoomIn = await listen("menu-zoom-in", () => {
      if (currentActiveTab === "preview") zoomIn();
    });
    unlistenZoomOut = await listen("menu-zoom-out", () => {
      if (currentActiveTab === "preview") zoomOut();
    });
    unlistenZoomReset = await listen("menu-zoom-reset", () => {
      if (currentActiveTab === "preview") setZoom(1);
    });
    unlistenZoomFit = await listen("menu-zoom-fit", () => {
      // Dispatch custom event for PreviewCanvas to handle (needs container dimensions)
      if (currentActiveTab === "preview") {
        window.dispatchEvent(new CustomEvent("preview:fit-to-width"));
      }
    });

    // Listen for file drops from native drag-drop
    unlistenFileDrop = await listen<string>("file-dropped", async (event) => {
      await handleFileOpen(event.payload);
    });

    // Listen for deep link events (inspekt://open?file=/path/to/file.pdf)
    unlistenDeepLink = await listen<string>("deep-link", async (event) => {
      const url = new URL(event.payload);
      const filePath = url.searchParams.get("file");
      if (filePath) {
        await handleFileOpen(filePath);
      }
    });

    // Update window title based on file
    updateWindowTitle();

    // Forward critical errors to Rust terminal (dev mode only)
    window.onerror = (message, source, lineno, colno, error) => {
      invoke('log_from_frontend', {
        level: 'error',
        message: `${message} at ${source}:${lineno}:${colno}`
      }).catch(() => {});
    };

    window.onunhandledrejection = (event) => {
      invoke('log_from_frontend', {
        level: 'error',
        message: `Unhandled rejection: ${event.reason}`
      }).catch(() => {});
    };
  });

  onDestroy(() => {
    unlistenOpen?.();
    unlistenClose?.();
    unlistenFileDrop?.();
    unlistenDeepLink?.();
    unlistenToggleSidebar?.();
    unlistenSave?.();
    unlistenSaveAs?.();
    unlistenZoomIn?.();
    unlistenZoomOut?.();
    unlistenZoomReset?.();
    unlistenZoomFit?.();

    // Fire-and-forget cleanup of PDFI extraction
    cleanupPdfiExtraction().catch(() => {});
  });

  async function handleFileOpen(path: string) {
    const lowerPath = path.toLowerCase();
    const isJson = lowerPath.endsWith(".json");
    const isPdfi = lowerPath.endsWith(".pdfi");

    try {
      // Clean up any previous PDFI extraction before opening a new file
      if (!isPdfi) {
        await cleanupPdfiExtraction();
      }

      if (isPdfi) {
        // Handle .pdfi package (ZIP archive)
        await handlePdfiPackage(path);
      } else if (isJson) {
        const data = await invoke<Record<string, unknown>>("read_json_file", { path });
        const report = migrateSchema(data) as ReportData;
        await addRecentFile(path);

        // Extract preview data from report if available
        const extractedPreviewPages = extractPreviewPages(report, path);
        const extractedPreviewTree = extractPreviewTree(report);

        previewPages = extractedPreviewPages;
        previewTree = extractedPreviewTree;

        // Track source PDF path for save functionality
        sourcePdfPath = report.metadata?.file_path ?? null;
        assetsBasePath = path.replace(/\.json$/i, '_assets');
        currentPackagePath = null;

        loadReport(report, path);
        setActiveTab("report"); // Reset to report tab when opening new file
        await showCompletionNotification(report);
      } else if (lowerPath.endsWith(".pdf")) {
        await addRecentFile(path);
        startCheck(path, true); // Always generate interactive preview data
      }
      updateWindowTitle();
    } catch (error) {
      console.error("Failed to open file:", error);
    }
  }

  /**
   * Clean up the current PDFI extraction directory.
   */
  async function cleanupPdfiExtraction(): Promise<void> {
    if (currentPdfiExtractionPath) {
      try {
        await invoke("cleanup_pdfi_extraction", { path: currentPdfiExtractionPath });
      } catch (error) {
        console.warn("Failed to cleanup PDFI extraction:", error);
      }
      currentPdfiExtractionPath = null;
    }
  }

  /**
   * Handle opening a .pdfi package.
   * Extracts the package to a temp directory and loads the report.
   */
  async function handlePdfiPackage(packagePath: string): Promise<void> {
    try {
      // Clean up any previous extraction first
      await cleanupPdfiExtraction();

      // Extract the .pdfi package using Tauri command
      const extractedPath = await invoke<string>("extract_pdfi_package", { path: packagePath });
      currentPdfiExtractionPath = extractedPath;

      // Read the report.json from the extracted directory
      const reportPath = `${extractedPath}/report.json`;
      const data = await invoke<Record<string, unknown>>("read_json_file", { path: reportPath });
      const report = migrateSchema(data) as ReportData;

      await addRecentFile(packagePath);

      // Extract preview data, resolving asset paths relative to extracted directory
      const extractedPreviewPages = extractPreviewPagesFromPackage(report, extractedPath);
      const extractedPreviewTree = extractPreviewTree(report);

      previewPages = extractedPreviewPages;
      previewTree = extractedPreviewTree;

      // Track paths for save functionality
      sourcePdfPath = `${extractedPath}/source.pdf`;
      assetsBasePath = `${extractedPath}/assets`;
      currentPackagePath = packagePath; // Remember where we opened from

      loadReport(report, packagePath);
      setActiveTab("report"); // Reset to report tab when opening new file
      await showCompletionNotification(report);
    } catch (error) {
      console.error("Failed to open PDFI package:", error);
      // Fallback: try to open as a regular zip and extract manually
      throw error;
    }
  }

  /**
   * Extract preview pages from a PDFI package, resolving asset paths.
   * Uses convertFileSrc() to convert filesystem paths to Tauri asset URLs.
   */
  function extractPreviewPagesFromPackage(report: ReportData, extractedPath: string): PreviewPageData[] {
    if (!report.preview_pages || report.preview_pages.length === 0) {
      return [];
    }

    // Handle both camelCase (old format) and snake_case (CLI output) field names
    return report.preview_pages.map(page => {
      const p = page as Record<string, unknown>;
      const pageImage = (p.pageImage ?? p.page_image) as string;
      const pdfSource = (p.pdfSource ?? p.pdf_src) as string | undefined;
      const thumbnail = (p.thumbnail ?? p.thumbnail) as string;
      const pageWidth = (p.pageWidth ?? p.page_width) as number;
      const pageHeight = (p.pageHeight ?? p.page_height) as number;
      const pageNum = (p.pageNum ?? p.page_num) as number;
      const dpi = (p.dpi ?? 150) as number;
      const tags = (p.tags ?? []) as Array<Record<string, unknown>>;
      const untaggedImages = (p.untaggedImages ?? p.untagged_images) as Array<Record<string, unknown>> | undefined;
      const vectorGraphics = (p.vectorGraphics ?? p.vector_graphics) as Array<Record<string, unknown>> | undefined;

      // Resolve asset paths and convert to Tauri asset URLs
      const fullPageImagePath = `${extractedPath}/${pageImage}`;
      const fullThumbnailPath = `${extractedPath}/${thumbnail}`;
      // PDF source may be a file path (external assets) or data URI (embedded)
      const fullPdfSourcePath = pdfSource && !pdfSource.startsWith('data:')
        ? `${extractedPath}/${pdfSource}`
        : undefined;

      return {
        // Convert filesystem paths to Tauri asset protocol URLs
        pageImage: convertFileSrc(fullPageImagePath),
        pdfSource: fullPdfSourcePath ? convertFileSrc(fullPdfSourcePath) : pdfSource,
        thumbnail: convertFileSrc(fullThumbnailPath),
        tags: tags.map(tag => ({
          tag_type: tag.tag_type as string,
          bbox: tag.bbox as [number, number, number, number] | null,
          reading_order: tag.reading_order as number,
          text_preview: tag.text_preview as string | null,
          alt_text: tag.alt_text as string | null,
          has_issues: tag.has_issues as boolean,
          node_id: tag.node_id as string | null,
          detected_language: (tag.detected_language ?? null) as string | null,
          image_page: tag.image_page as number | undefined,
          image_index: tag.image_index as number | undefined,
        })),
        pageWidth,
        pageHeight,
        pageNum,
        dpi,
        imageWidth: Math.round(pageWidth * (dpi / 72)),
        imageHeight: Math.round(pageHeight * (dpi / 72)),
        untaggedImages: untaggedImages?.map(img => ({
          bbox: img.bbox as [number, number, number, number],
          width: img.width as number,
          height: img.height as number,
          index: img.index as number,
        })),
        vectorGraphics: vectorGraphics?.map(vg => ({
          bbox: vg.bbox as [number, number, number, number],
          width: vg.width as number,
          height: vg.height as number,
          index: vg.index as number,
        })),
      };
    });
  }

  /**
   * Extract preview page data from the report.
   * Handles both embedded data and external assets.
   * Supports both camelCase (old format) and snake_case (CLI output) field names.
   */
  function extractPreviewPages(report: ReportData, reportPath: string): PreviewPageData[] {
    // Check for embedded preview pages first
    if (report.preview_pages && report.preview_pages.length > 0) {
      return report.preview_pages.map(page => {
        const p = page as Record<string, unknown>;
        const pageImage = (p.pageImage ?? p.page_image) as string;
        const pdfSource = (p.pdfSource ?? p.pdf_src) as string | undefined;
        const thumbnail = (p.thumbnail ?? p.thumbnail) as string;
        const pageWidth = (p.pageWidth ?? p.page_width) as number;
        const pageHeight = (p.pageHeight ?? p.page_height) as number;
        const pageNum = (p.pageNum ?? p.page_num) as number;
        const dpi = (p.dpi ?? 150) as number;
        const tags = (p.tags ?? []) as Array<Record<string, unknown>>;
        const untaggedImages = (p.untaggedImages ?? p.untagged_images) as Array<Record<string, unknown>> | undefined;
        const vectorGraphics = (p.vectorGraphics ?? p.vector_graphics) as Array<Record<string, unknown>> | undefined;

        return {
          pageImage,
          pdfSource,
          thumbnail,
          tags: tags.map(tag => ({
            tag_type: tag.tag_type as string,
            bbox: tag.bbox as [number, number, number, number] | null,
            reading_order: tag.reading_order as number,
            text_preview: tag.text_preview as string | null,
            alt_text: tag.alt_text as string | null,
            has_issues: tag.has_issues as boolean,
            node_id: tag.node_id as string | null,
            detected_language: (tag.detected_language ?? null) as string | null,
            image_page: tag.image_page as number | undefined,
            image_index: tag.image_index as number | undefined,
          })),
          pageWidth,
          pageHeight,
          pageNum,
          dpi,
          // Calculate image dimensions from page dimensions and DPI
          imageWidth: Math.round(pageWidth * (dpi / 72)),
          imageHeight: Math.round(pageHeight * (dpi / 72)),
          untaggedImages: untaggedImages?.map(img => ({
            bbox: img.bbox as [number, number, number, number],
            width: img.width as number,
            height: img.height as number,
            index: img.index as number,
          })),
          vectorGraphics: vectorGraphics?.map(vg => ({
            bbox: vg.bbox as [number, number, number, number],
            width: vg.width as number,
            height: vg.height as number,
            index: vg.index as number,
          })),
        };
      });
    }

    // TODO: Load from external assets folder if available
    // The assets folder would be at: reportPath.replace('.json', '_assets/')

    return [];
  }

  /**
   * Extract preview structure tree from the report.
   */
  function extractPreviewTree(report: ReportData): PreviewStructureNode | null {
    // Check for embedded preview structure tree
    if (report.preview_structure_tree) {
      return convertToPreviewNode(report.preview_structure_tree);
    }

    // Fall back to converting the standard structure tree if available
    if (report.structure?.root) {
      return convertStructureNode(report.structure.root, 0);
    }

    return null;
  }

  /**
   * Convert report structure node to preview structure node.
   */
  function convertToPreviewNode(node: NonNullable<ReportData["preview_structure_tree"]>): PreviewStructureNode {
    return {
      tag_type: node.tag_type,
      node_id: node.node_id,
      page_number: node.page_number,
      text_content: node.text_content,
      alt_text: node.alt_text,
      is_heading: node.is_heading,
      has_issues: node.has_issues,
      children: node.children.map(child => convertToPreviewNode(child)),
    };
  }

  /**
   * Convert standard structure node to preview structure node.
   */
  function convertStructureNode(
    node: NonNullable<NonNullable<ReportData["structure"]>["root"]>,
    pageNum: number
  ): PreviewStructureNode {
    const isHeading = node.tag_type.startsWith('H') && node.tag_type.length <= 3;

    return {
      tag_type: node.tag_type,
      node_id: null,
      page_number: pageNum,
      text_content: node.text_content,
      alt_text: node.alt_text,
      is_heading: isHeading || node.is_heading,
      has_issues: node.has_issues,
      children: node.children.map(child => convertStructureNode(child, pageNum)),
    };
  }

  /**
   * Handle Save menu action (Cmd+S).
   * If opened from a .pdfi, save to that location.
   * Otherwise, prompt for save location.
   */
  async function handleMenuSave() {
    if (!currentReport) return;

    if (currentPackagePath) {
      // Save to original location
      await saveToPath(currentPackagePath);
    } else {
      // No existing path, act like Save As
      await handleMenuSaveAs();
    }
  }

  /**
   * Handle Save As menu action (Cmd+Shift+S).
   * Always prompts for a new save location.
   */
  async function handleMenuSaveAs() {
    if (!currentReport) return;

    try {
      const defaultName = currentReport.metadata?.file_name?.replace(/\.pdf$/i, '.pdfi') ?? 'report.pdfi';
      const savePath = await save({
        defaultPath: defaultName,
        filters: [
          { name: "PDFI Packages", extensions: ["pdfi"] },
        ],
      });

      if (savePath) {
        await saveToPath(savePath);
        currentPackagePath = savePath; // Remember for future saves
      }
    } catch (error) {
      console.error("Failed to save file:", error);
    }
  }

  /**
   * Save the current report to a .pdfi package at the given path.
   */
  async function saveToPath(outputPath: string) {
    if (!currentReport) return;

    try {
      await invoke("save_as_pdfi", {
        reportJson: JSON.stringify(currentReport),
        sourcePdfPath: sourcePdfPath,
        assetsPath: assetsBasePath,
        outputPath: outputPath,
      });

      // Show success notification
      if (currentPrefs?.showNotifications) {
        await invoke("show_notification", {
          title: "Report Saved",
          body: `Saved to ${outputPath.split('/').pop()}`,
        });
      }
    } catch (error) {
      console.error("Failed to save PDFI package:", error);
      // Could show an error dialog here
    }
  }

  async function handleMenuOpen() {
    try {
      const selected = await open({
        multiple: false,
        filters: [
          { name: "Inspekt Files", extensions: ["pdfi", "json", "pdf"] },
          { name: "PDFI Packages", extensions: ["pdfi"] },
          { name: "JSON Reports", extensions: ["json"] },
          { name: "PDF Documents", extensions: ["pdf"] },
        ],
      });

      if (selected) {
        await handleFileOpen(selected as string);
      }
    } catch (error) {
      console.error("Failed to open file:", error);
    }
  }

  async function handleMenuClose() {
    if (currentState === "viewing") {
      // Clean up any PDFI extraction before closing
      await cleanupPdfiExtraction();

      clearReport();
      previewPages = [];
      previewTree = null;
      sourcePdfPath = null;
      assetsBasePath = null;
      currentPackagePath = null;
      setActiveTab("report");
      clearDockBadge();
      updateWindowTitle();
    }
  }

  async function updateWindowTitle() {
    const window = getCurrentWindow();
    if (currentReport?.metadata?.file_name) {
      await window.setTitle(`${currentReport.metadata.file_name} - Inspekt PDF Viewer`);
    } else {
      await window.setTitle("Inspekt PDF Viewer");
    }
  }

  async function showCompletionNotification(report: ReportData) {
    // Only show if notifications are enabled
    if (!currentPrefs?.showNotifications) return;

    const issueCount = countIssues(report);
    const score = report.score?.score ?? 0;

    let body = `Score: ${Math.round(score)}/100`;
    if (issueCount > 0) {
      body += ` • ${issueCount} issue${issueCount === 1 ? '' : 's'} found`;
    } else {
      body += ` • No issues found`;
    }

    try {
      await invoke("show_notification", {
        title: "PDF Check Complete",
        body,
      });
    } catch (error) {
      console.warn("Failed to show notification:", error);
    }
  }

  function countIssues(report: ReportData): number {
    let count = 0;

    // Count failed checks
    if (report.checks) {
      for (const check of report.checks) {
        if (check.status === "fail") count++;
      }
    }

    // Count issues from vera results
    if (report.vera_results?.failed) {
      count += report.vera_results.failed;
    }

    return count;
  }

  async function updateDockBadge(report: ReportData | null) {
    if (!report) {
      await clearDockBadge();
      return;
    }

    const issueCount = countIssues(report);

    try {
      await invoke("set_dock_badge", {
        count: issueCount > 0 ? issueCount : null,
      });
    } catch (error) {
      // Dock badge might not be supported on all platforms
      console.debug("Dock badge not available:", error);
    }
  }

  async function clearDockBadge() {
    try {
      await invoke("set_dock_badge", { count: null });
    } catch (error) {
      console.debug("Dock badge not available:", error);
    }
  }

  // Update title when report changes
  $effect(() => {
    if (currentReport) {
      updateWindowTitle();
    }
  });

  function handleWelcomeDismiss() {
    showWelcome = false;
  }

  /**
   * Enhance the current report by generating preview data.
   * This re-runs the PDF check with the --preview flag.
   */
  async function handleEnhanceReport() {
    if (!currentReport?.metadata?.file_path) {
      console.error("No source PDF path available");
      return;
    }

    const pdfPath = currentReport.metadata.file_path;

    // Check if the source PDF exists
    try {
      await invoke("get_file_info", { path: pdfPath });
    } catch {
      // PDF not found - show error
      console.error("Source PDF not found:", pdfPath);
      // Could show a dialog here asking user to locate the file
      return;
    }

    // Start a new check with preview enabled
    // The ProgressView will handle the UI
    startCheck(pdfPath, true); // true = generate preview data
  }
</script>

<main class="app-container">
  {#if showWelcome && currentState === "idle"}
    <Welcome onDismiss={handleWelcomeDismiss} />
  {:else if currentState === "checking"}
    <ProgressView />
  {:else if currentState === "viewing" && currentReport}
    {@const viewTabs = [
      { id: "report" as const, label: "Report" },
      { id: "preview" as const, label: "Interactive Preview" },
    ]}
    <div class="tabbed-view">
      <TabBar tabs={viewTabs} />
      <div class="tab-content">
        <TabPanel tabId="report">
          <ReportView report={currentReport} />
        </TabPanel>
        <TabPanel tabId="preview">
          {#if hasPreviewAvailable}
            <div class="preview-tab-content">
              <InteractivePreview pages={previewPages} tree={previewTree} />
            </div>
          {:else}
            <div class="preview-empty-state">
              <div class="empty-state-card">
                <div class="empty-state-icon">
                  <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                    <circle cx="8.5" cy="8.5" r="1.5"/>
                    <polyline points="21 15 16 10 5 21"/>
                  </svg>
                </div>
                <h2>Interactive Preview Not Available</h2>
                <p class="empty-state-description">
                  This report doesn't include the visual preview data needed to show an interactive view of the PDF structure.
                </p>
                <div class="empty-state-features">
                  <h3>With Interactive Preview, you can:</h3>
                  <ul>
                    <li>See PDF tags overlaid on each page</li>
                    <li>Visualize the reading order</li>
                    <li>Inspect structure tree relationships</li>
                    <li>Identify untagged images and graphics</li>
                  </ul>
                </div>
                <button class="btn-enhance" onclick={() => handleEnhanceReport()}>
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                    <polyline points="17 8 12 3 7 8"/>
                    <line x1="12" y1="3" x2="12" y2="15"/>
                  </svg>
                  Enhance Report with Preview Data
                </button>
                <p class="empty-state-hint">
                  This will re-analyze the source PDF and generate page images with tag overlays.
                </p>
              </div>
            </div>
          {/if}
        </TabPanel>
      </div>
    </div>
  {:else if currentState === "error" && currentError}
    <div class="error-container">
      <div class="error-card">
        <div class="error-icon">⚠️</div>
        <h2>{currentError.title}</h2>
        <p class="error-message">{currentError.message}</p>
        {#if currentError.details}
          <details class="error-details">
            <summary>Details</summary>
            <pre>{currentError.details}</pre>
          </details>
        {/if}
        <button class="btn-retry" onclick={() => clearError()}>
          Try Again
        </button>
      </div>
    </div>
  {:else}
    <DropZone />
  {/if}
</main>

<style>
  .app-container {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }

  .tabbed-view {
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
  }

  .tab-content {
    flex: 1;
    min-height: 0;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  .preview-tab-content {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-height: 0;
    padding: 1rem;
    background: var(--surface-secondary);
  }

  .preview-empty-state {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    background: var(--surface-secondary);
  }

  .empty-state-card {
    background: var(--surface-primary);
    border-radius: var(--radius-xl);
    box-shadow: var(--shadow-lg);
    padding: 2.5rem;
    max-width: 480px;
    width: 100%;
    text-align: center;
  }

  .empty-state-icon {
    color: var(--text-tertiary);
    margin-bottom: 1.5rem;
  }

  .empty-state-card h2 {
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 0.75rem;
  }

  .empty-state-description {
    font-size: 0.9375rem;
    color: var(--text-secondary);
    line-height: 1.5;
    margin-bottom: 1.5rem;
  }

  .empty-state-features {
    text-align: left;
    background: var(--surface-secondary);
    border-radius: var(--radius-md);
    padding: 1rem 1.25rem;
    margin-bottom: 1.5rem;
  }

  .empty-state-features h3 {
    font-size: 0.8125rem;
    font-weight: 600;
    color: var(--text-secondary);
    margin-bottom: 0.5rem;
    text-transform: uppercase;
    letter-spacing: 0.025em;
  }

  .empty-state-features ul {
    margin: 0;
    padding-left: 1.25rem;
  }

  .empty-state-features li {
    font-size: 0.875rem;
    color: var(--text-secondary);
    line-height: 1.6;
  }

  .btn-enhance {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1.5rem;
    background: var(--color-primary);
    color: white;
    border: none;
    border-radius: var(--radius-md);
    font-size: 0.9375rem;
    font-weight: 500;
    cursor: pointer;
    transition: background var(--transition-fast);
  }

  .btn-enhance:hover {
    background: var(--color-primary-hover);
  }

  .btn-enhance:focus-visible {
    outline: 2px solid var(--color-primary);
    outline-offset: 2px;
  }

  .empty-state-hint {
    font-size: 0.8125rem;
    color: var(--text-tertiary);
    margin-top: 1rem;
  }

  .error-container {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    background: var(--surface-secondary);
  }

  .error-card {
    background: var(--surface-primary);
    border-radius: var(--radius-xl);
    box-shadow: var(--shadow-lg);
    padding: 2.5rem;
    max-width: 500px;
    width: 100%;
    text-align: center;
  }

  .error-icon {
    font-size: 3rem;
    margin-bottom: 1rem;
  }

  .error-card h2 {
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--color-error);
    margin-bottom: 0.75rem;
  }

  .error-message {
    font-size: 0.9375rem;
    color: var(--text-secondary);
    margin-bottom: 1.5rem;
    line-height: 1.5;
  }

  .error-details {
    text-align: left;
    margin-bottom: 1.5rem;
    background: var(--surface-secondary);
    border-radius: var(--radius-md);
    padding: 0.75rem;
  }

  .error-details summary {
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--text-secondary);
    cursor: pointer;
  }

  .error-details pre {
    margin-top: 0.75rem;
    font-size: 0.75rem;
    color: var(--text-tertiary);
    white-space: pre-wrap;
    word-break: break-all;
    max-height: 200px;
    overflow-y: auto;
  }

  .btn-retry {
    padding: 0.75rem 1.5rem;
    background: var(--color-primary);
    color: white;
    border: none;
    border-radius: var(--radius-md);
    font-size: 0.9375rem;
    font-weight: 500;
    cursor: pointer;
    transition: background var(--transition-fast);
  }

  .btn-retry:hover {
    background: var(--color-primary-hover);
  }
</style>
