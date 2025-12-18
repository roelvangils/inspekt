/**
 * Visual and Audio Feedback for Inspekt Replay
 *
 * Provides visual cues (action indicator circle, typing indicator) and
 * audio feedback (synthesized sounds) during replay execution.
 */

(function () {
  'use strict';

  // Skip if already initialized
  if (window.__INSPEKT_VISUAL__) {
    return;
  }

  // ==========================================================================
  // Configuration
  // ==========================================================================

  const CONFIG = {
    // Animation timings (ms)
    fadeInDuration: 200,
    fadeOutDuration: 200,
    pulseDuration: 300,
    moveDuration: 400,
    shakeDuration: 400,

    // Circle indicator
    circleSize: 32,
    circleBorderWidth: 3,

    // Colors by action type
    colors: {
      click: '#3b82f6',      // blue
      activate: '#8b5cf6',   // purple
      type: '#f59e0b',       // amber
      set: '#f59e0b',        // amber (same as type for native control values)
      check: '#10b981',      // green
      uncheck: '#10b981',    // green
      select: '#06b6d4',     // cyan
      navigate: '#6366f1',   // indigo
      hover: '#64748b',      // slate
      error: '#ef4444',      // red
      success: '#22c55e',    // green
      default: '#3b82f6'     // blue
    },

    // Audio volume (0-1)
    audioVolume: 0.3
  };

  // ==========================================================================
  // CSS Styles
  // ==========================================================================

  // Font URLs - will be populated from extension or fallback to system fonts
  let fontUrlRegular = null;
  let fontUrlBold = null;
  let fontsLoaded = false;

  // Build styles dynamically to allow font URL injection
  function buildStyles() {
    // Font face declarations - only include if we have extension font URLs
    const fontFaceStyles = fontUrlRegular ? `
    /* JetBrains Mono Nerd Font for consistent icon rendering */
    @font-face {
      font-family: 'JetBrains Mono NF';
      src: url('${fontUrlRegular}') format('woff2');
      font-weight: 400;
      font-style: normal;
      font-display: block;
      /* Include Private Use Areas where Nerd Font icons live */
      unicode-range: U+0000-00FF, U+E000-U+F8FF, U+F0000-U+FFFFF;
    }
    @font-face {
      font-family: 'JetBrains Mono NF';
      src: url('${fontUrlBold}') format('woff2');
      font-weight: 700;
      font-style: normal;
      font-display: block;
      unicode-range: U+0000-00FF, U+E000-U+F8FF, U+F0000-U+FFFFF;
    }
    ` : '';

    return `${fontFaceStyles}
    @keyframes inspekt-fade-in {
      from { opacity: 0; transform: scale(0.5); }
      to { opacity: 1; transform: scale(1); }
    }

    @keyframes inspekt-fade-out {
      from { opacity: 1; transform: scale(1); }
      to { opacity: 0; transform: scale(0.5); }
    }

    @keyframes inspekt-pulse {
      0% { transform: scale(1); }
      50% { transform: scale(1.3); }
      100% { transform: scale(1); }
    }

    @keyframes inspekt-shake {
      0%, 100% { transform: translateX(0); }
      10%, 30%, 50%, 70%, 90% { transform: translateX(-4px); }
      20%, 40%, 60%, 80% { transform: translateX(4px); }
    }

    @keyframes inspekt-typing-dots {
      0%, 20% { content: '.'; }
      40% { content: '..'; }
      60%, 100% { content: '...'; }
    }

    #inspekt-overlay {
      position: fixed;
      top: 0;
      left: 0;
      width: 100vw;
      height: 100vh;
      pointer-events: none;
      z-index: 2147483647;
      overflow: hidden;
    }

    #inspekt-circle {
      position: absolute;
      width: ${CONFIG.circleSize}px;
      height: ${CONFIG.circleSize}px;
      border-radius: 50%;
      border: ${CONFIG.circleBorderWidth}px solid ${CONFIG.colors.default};
      background: transparent;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
      opacity: 0;
      transform: translate(-50%, -50%);
      will-change: transform, opacity, left, top;
    }

    #inspekt-circle.fade-in {
      animation: inspekt-fade-in ${CONFIG.fadeInDuration}ms ease-out forwards;
    }

    #inspekt-circle.fade-out {
      animation: inspekt-fade-out ${CONFIG.fadeOutDuration}ms ease-in forwards;
    }

    #inspekt-circle.pulse {
      animation: inspekt-pulse ${CONFIG.pulseDuration}ms ease-in-out;
    }

    #inspekt-circle.shake {
      animation: inspekt-shake ${CONFIG.shakeDuration}ms ease-in-out;
    }

    #inspekt-typing {
      position: absolute;
      display: none;
      padding: 4px 8px;
      background: rgba(0, 0, 0, 0.8);
      color: ${CONFIG.colors.type};
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      font-size: 12px;
      border-radius: 4px;
      white-space: nowrap;
      transform: translateX(0);
    }

    #inspekt-typing::after {
      content: '...';
      animation: inspekt-typing-dots 1s steps(1) infinite;
    }

    #inspekt-typing.visible {
      display: block;
    }

    .inspekt-select-preview {
      position: fixed;
      background: rgba(0, 0, 0, 0.85);
      color: ${CONFIG.colors.select};
      padding: 8px 12px;
      border-radius: 6px;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      font-size: 13px;
      font-weight: 500;
      z-index: 2147483647;
      pointer-events: none;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
      border: 1px solid ${CONFIG.colors.select};
      animation: inspekt-select-preview-in 0.2s ease-out forwards;
    }

    .inspekt-select-preview::before {
      content: '▼ ';
      font-size: 10px;
      opacity: 0.7;
    }

    .inspekt-select-preview.fade-out {
      animation: inspekt-select-preview-out 0.3s ease-in forwards;
    }

    @keyframes inspekt-select-preview-in {
      from {
        opacity: 0;
        transform: translateY(-4px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }

    @keyframes inspekt-select-preview-out {
      from {
        opacity: 1;
        transform: translateY(0);
      }
      to {
        opacity: 0;
        transform: translateY(4px);
      }
    }

    /* Focus ring overlay (fallback for Tab navigation when CSS injection fails) */
    #inspekt-focus-ring {
      position: absolute;
      pointer-events: none;
      border: 2px solid #0066ff;
      border-radius: 4px;
      box-shadow: 0 0 0 2px rgba(0, 102, 255, 0.3);
      opacity: 0;
      transition: opacity 0.15s ease-out,
                  left 0.15s ease-out,
                  top 0.15s ease-out,
                  width 0.15s ease-out,
                  height 0.15s ease-out;
    }

    #inspekt-focus-ring.visible {
      opacity: 1;
    }

    /* Interactive replay overlay */
    #inspekt-interactive-overlay {
      /* CSS Variables for dark/light mode */
      --overlay-bg: rgba(30, 30, 30, 0.85);
      --overlay-text: #ffffff;
      --overlay-text-dim: #999;
      --overlay-border: rgba(255, 255, 255, 0.15);
      --overlay-kbd-bg: rgba(255, 255, 255, 0.12);
      --overlay-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);

      position: fixed;
      z-index: 2147483647;
      min-width: 340px;
      max-width: 450px;

      /* Default corner: bottom-left */
      bottom: 20px;
      left: 20px;
      right: auto;
      top: auto;

      background: var(--overlay-bg);
      color: var(--overlay-text);
      padding: 18px 22px;
      border-radius: 12px;
      font-family: 'JetBrains Mono NF', 'JetBrains Mono', ui-monospace, SFMono-Regular, monospace;
      font-size: 14px;
      box-shadow: var(--overlay-shadow);
      border: 1px solid var(--overlay-border);

      /* Hidden by default, shown via .visible class */
      opacity: 0;

      /* macOS-like vibrancy effect */
      backdrop-filter: blur(20px) saturate(180%);
      -webkit-backdrop-filter: blur(20px) saturate(180%);

      /* Slide-in animation from right */
      animation: inspekt-interactive-in 0.3s ease-out;

      /* Smooth transitions for opacity and corner snapping */
      transition: opacity 0.15s ease-out, top 0.3s ease, bottom 0.3s ease, left 0.3s ease, right 0.3s ease;

      /* Draggable cursor */
      cursor: grab;
      user-select: none;
    }

    #inspekt-interactive-overlay.visible {
      opacity: 1;
    }

    /* Light mode overrides */
    @media (prefers-color-scheme: light) {
      #inspekt-interactive-overlay {
        --overlay-bg: rgba(255, 255, 255, 0.88);
        --overlay-text: #1a1a1a;
        --overlay-text-dim: #666;
        --overlay-border: rgba(0, 0, 0, 0.12);
        --overlay-kbd-bg: rgba(0, 0, 0, 0.08);
        --overlay-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
      }
    }

    /* Corner positioning */
    #inspekt-interactive-overlay[data-corner="bottom-left"] {
      bottom: 20px; left: 20px; right: auto; top: auto;
    }
    #inspekt-interactive-overlay[data-corner="bottom-right"] {
      bottom: 20px; right: 20px; left: auto; top: auto;
    }
    #inspekt-interactive-overlay[data-corner="top-left"] {
      top: 20px; left: 20px; right: auto; bottom: auto;
    }
    #inspekt-interactive-overlay[data-corner="top-right"] {
      top: 20px; right: 20px; left: auto; bottom: auto;
    }

    /* Dragging state */
    #inspekt-interactive-overlay.dragging {
      opacity: 0.85;
      cursor: grabbing;
      transition: none;
      transform: scale(0.98);
    }

    @keyframes inspekt-interactive-in {
      from {
        opacity: 0;
        transform: translateX(30px);
      }
      to {
        opacity: 1;
        transform: translateX(0);
      }
    }

    #inspekt-interactive-overlay .previous-step {
      color: var(--overlay-text-dim);
      font-size: 12px;
      margin-bottom: 8px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--overlay-border);
    }

    #inspekt-interactive-overlay .previous-step .checkmark {
      color: ${CONFIG.colors.success};
      margin-right: 4px;
    }

    #inspekt-interactive-overlay .step-counter {
      color: var(--overlay-text-dim);
      font-size: 11px;
      margin-bottom: 4px;
    }

    /* Progress bar */
    #inspekt-interactive-overlay .progress-bar {
      height: 3px;
      background: var(--overlay-border);
      border-radius: 2px;
      margin: 8px 0 10px 0;
      overflow: hidden;
    }

    #inspekt-interactive-overlay .progress-fill {
      height: 100%;
      background: ${CONFIG.colors.click};
      border-radius: 2px;
      transition: width 0.3s ease;
    }

    #inspekt-interactive-overlay .current-step {
      font-size: 15px;
      font-weight: 500;
      margin-bottom: 14px;
      line-height: 1.4;
    }

    #inspekt-interactive-overlay .current-step .action-icon {
      margin-right: 6px;
    }

    #inspekt-interactive-overlay .current-step .action-name {
      color: ${CONFIG.colors.click};
    }

    #inspekt-interactive-overlay .current-step .target-name {
      color: var(--overlay-text);
    }

    #inspekt-interactive-overlay .current-step .target-tag {
      color: var(--overlay-text-dim);
      font-size: 13px;
    }

    #inspekt-interactive-overlay .key-hints {
      display: flex;
      gap: 14px;
      font-size: 12px;
      color: var(--overlay-text-dim);
      padding-top: 12px;
      border-top: 1px solid var(--overlay-border);
    }

    #inspekt-interactive-overlay .key-hints kbd {
      background: var(--overlay-kbd-bg);
      padding: 3px 8px;
      border-radius: 4px;
      font-family: inherit;
      font-size: 11px;
      margin-right: 4px;
      border: 1px solid var(--overlay-border);
    }

    #inspekt-interactive-overlay.waiting {
      border-color: ${CONFIG.colors.click};
    }

    /* Drag target zones (shown when dragging) - frosted glass effect */
    .inspekt-drag-target {
      position: fixed;
      /* Width/height set dynamically in createDragTargets() to match overlay */
      min-width: 340px;
      max-width: 450px;
      border-radius: 12px;
      z-index: 2147483646;
      opacity: 0;
      pointer-events: none;
      /* Frosted glass effect */
      background: rgba(255, 255, 255, 0.25);
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
      border: 1px solid rgba(255, 255, 255, 0.3);
      box-shadow: 0 4px 30px rgba(0, 0, 0, 0.1);
      transition: opacity 0.2s ease, transform 0.2s ease, background 0.2s ease;
    }

    .inspekt-drag-target.visible {
      opacity: 1;
    }

    .inspekt-drag-target.hover {
      background: rgba(255, 255, 255, 0.4);
      border-color: ${CONFIG.colors.click};
      transform: scale(1.02);
      box-shadow: 0 4px 30px rgba(59, 130, 246, 0.2);
    }

    /* Corner positions for drag targets */
    .inspekt-drag-target[data-corner="top-left"] { top: 20px; left: 20px; }
    .inspekt-drag-target[data-corner="top-right"] { top: 20px; right: 20px; }
    .inspekt-drag-target[data-corner="bottom-left"] { bottom: 20px; left: 20px; }
    .inspekt-drag-target[data-corner="bottom-right"] { bottom: 20px; right: 20px; }

    /* Dark mode - slightly darker frosted glass */
    @media (prefers-color-scheme: dark) {
      .inspekt-drag-target {
        background: rgba(255, 255, 255, 0.15);
        border-color: rgba(255, 255, 255, 0.2);
      }
      .inspekt-drag-target.hover {
        background: rgba(255, 255, 255, 0.25);
      }
    }

    /* Overlay being dragged freely */
    #inspekt-interactive-overlay.free-drag {
      position: fixed !important;
      transition: none !important;
    }

    /* Snap animation when dropping */
    #inspekt-interactive-overlay.snapping {
      transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }

    /* Target indicator arrow for interactive mode */
    #inspekt-target-indicator {
      position: fixed;
      z-index: 2147483646;
      pointer-events: none;
      display: flex;
      align-items: center;
      gap: 8px;
      /* Smooth transitions for movement */
      transition: left 0.4s cubic-bezier(0.4, 0, 0.2, 1),
                  top 0.4s cubic-bezier(0.4, 0, 0.2, 1),
                  opacity 0.3s ease-out;
    }

    #inspekt-target-indicator .arrow {
      width: 48px;
      height: 48px;
      border-radius: 50%;
      background: var(--arrow-color, ${CONFIG.colors.click});
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4), 0 0 0 4px rgba(255, 255, 255, 0.2);
      animation: inspekt-arrow-pulse 1.2s ease-in-out infinite;
    }

    @keyframes inspekt-arrow-pulse {
      0%, 100% {
        transform: scale(1);
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4), 0 0 0 4px rgba(255, 255, 255, 0.2);
      }
      50% {
        transform: scale(1.15);
        box-shadow: 0 6px 30px rgba(0, 0, 0, 0.5), 0 0 0 8px rgba(255, 255, 255, 0.3);
      }
    }

    #inspekt-target-indicator .arrow svg {
      width: 28px;
      height: 28px;
      fill: white;
      filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.3));
    }

    /* Arrow pointing directions */
    #inspekt-target-indicator[data-direction="right"] .arrow svg {
      transform: rotate(0deg);
    }
    #inspekt-target-indicator[data-direction="left"] .arrow svg {
      transform: rotate(180deg);
    }
    #inspekt-target-indicator[data-direction="down"] .arrow svg {
      transform: rotate(90deg);
    }
    #inspekt-target-indicator[data-direction="up"] .arrow svg {
      transform: rotate(-90deg);
    }

    /* Spotlight effect - dims the page except for the target area */
    #inspekt-spotlight {
      position: fixed;
      z-index: 2147483644;
      pointer-events: none;
      border-radius: 50%;
      /* Radial gradient creates the soft feathered spotlight effect */
      background: radial-gradient(
        circle,
        transparent 0%,
        transparent 30%,
        rgba(0, 0, 0, 0.3) 60%,
        rgba(0, 0, 0, 0.55) 100%
      );
      /* Huge box-shadow extends the darkness to cover the entire viewport */
      box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.55);
      /* Blur the edges for a soft theatre spotlight look */
      filter: blur(15px);
      /* Smooth transitions for movement */
      transition: left 0.4s cubic-bezier(0.4, 0, 0.2, 1),
                  top 0.4s cubic-bezier(0.4, 0, 0.2, 1),
                  width 0.4s cubic-bezier(0.4, 0, 0.2, 1),
                  height 0.4s cubic-bezier(0.4, 0, 0.2, 1),
                  opacity 0.3s ease-out;
    }

    /* Assertion overlay - shows test results in interactive mode */
    #inspekt-assertion-overlay {
      /* Purple/blue color scheme to distinguish from main overlay */
      --assertion-bg: rgba(88, 28, 135, 0.9);
      --assertion-text: #ffffff;
      --assertion-text-dim: rgba(255, 255, 255, 0.7);
      --assertion-border: rgba(168, 85, 247, 0.5);
      --assertion-pass-bg: rgba(34, 197, 94, 0.2);
      --assertion-pass-border: rgba(34, 197, 94, 0.6);
      --assertion-fail-bg: rgba(239, 68, 68, 0.2);
      --assertion-fail-border: rgba(239, 68, 68, 0.6);

      position: fixed;
      z-index: 2147483647; /* Just below interactive overlay */

      /* Match width of interactive overlay */
      width: 340px;
      box-sizing: border-box;

      background: var(--assertion-bg);
      color: var(--assertion-text);
      padding: 12px 16px;
      border-radius: 10px;
      font-family: 'JetBrains Mono NF', 'JetBrains Mono', ui-monospace, SFMono-Regular, monospace;
      font-size: 13px;
      border: 1px solid var(--assertion-border);

      /* Vibrancy effect - match interactive overlay */
      backdrop-filter: blur(20px) saturate(180%);
      -webkit-backdrop-filter: blur(20px) saturate(180%);

      /* Subtle fade animation */
      opacity: 0;
      transition: opacity 0.2s ease-out;
      pointer-events: none;
    }

    #inspekt-assertion-overlay.visible {
      opacity: 1;
    }

    #inspekt-assertion-overlay.pass {
      --assertion-bg: rgba(20, 83, 45, 0.92);
      --assertion-border: var(--assertion-pass-border);
    }

    #inspekt-assertion-overlay.fail {
      --assertion-bg: rgba(127, 29, 29, 0.92);
      --assertion-border: var(--assertion-fail-border);
    }

    #inspekt-assertion-overlay .assertion-content {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    #inspekt-assertion-overlay .assertion-icon {
      font-size: 16px;
      flex-shrink: 0;
    }

    #inspekt-assertion-overlay .assertion-message {
      font-style: italic;
      line-height: 1.4;
      flex: 1;
    }

    #inspekt-assertion-overlay .assertion-details {
      font-size: 11px;
      color: var(--assertion-text-dim);
      margin-top: 8px;
      padding-top: 8px;
      border-top: 1px solid rgba(255, 255, 255, 0.15);
    }

    /* Light mode */
    @media (prefers-color-scheme: light) {
      #inspekt-assertion-overlay {
        --assertion-bg: rgba(147, 51, 234, 0.92);
        --assertion-text: #ffffff;
        --assertion-text-dim: rgba(255, 255, 255, 0.8);
      }
      #inspekt-assertion-overlay.pass {
        --assertion-bg: rgba(22, 163, 74, 0.92);
      }
      #inspekt-assertion-overlay.fail {
        --assertion-bg: rgba(220, 38, 38, 0.92);
      }
    }

    /* Checking/loading state */
    #inspekt-assertion-overlay.checking {
      --assertion-bg: rgba(88, 28, 135, 0.9);
    }

    #inspekt-assertion-overlay.checking .assertion-icon {
      animation: inspekt-assertion-spin 1s linear infinite;
    }

    @keyframes inspekt-assertion-spin {
      from { transform: rotate(0deg); }
      to { transform: rotate(360deg); }
    }

  `;
  }

  // ==========================================================================
  // DOM Setup
  // ==========================================================================

  function createOverlay() {
    // Inject styles (with dynamically loaded font URLs)
    const styleEl = document.createElement('style');
    styleEl.id = 'inspekt-visual-styles';
    styleEl.textContent = buildStyles();
    document.head.appendChild(styleEl);

    // Create overlay container
    const overlay = document.createElement('div');
    overlay.id = 'inspekt-overlay';

    // Create circle indicator
    const circle = document.createElement('div');
    circle.id = 'inspekt-circle';
    overlay.appendChild(circle);

    // Create typing indicator
    const typing = document.createElement('div');
    typing.id = 'inspekt-typing';
    typing.textContent = 'Typing';
    overlay.appendChild(typing);

    // Create focus ring indicator (for Tab navigation fallback)
    const focusRing = document.createElement('div');
    focusRing.id = 'inspekt-focus-ring';
    overlay.appendChild(focusRing);

    document.body.appendChild(overlay);

    return { overlay, circle, typing, focusRing };
  }

  // ==========================================================================
  // Visual Feedback Module
  // ==========================================================================

  const Visual = {
    elements: null,
    currentPosition: { x: 0, y: 0 },
    animationFrame: null,

    init() {
      if (!this.elements) {
        this.elements = createOverlay();
      }
    },

    /**
     * Set the circle color based on action type
     */
    setColor(actionType) {
      this.init();  // Ensure overlay exists before accessing elements
      const color = CONFIG.colors[actionType] || CONFIG.colors.default;
      this.elements.circle.style.borderColor = color;
    },

    /**
     * Move indicator to position with optional curved path
     */
    moveTo(x, y, curved = true) {
      return new Promise((resolve) => {
        this.init();

        const startX = this.currentPosition.x;
        const startY = this.currentPosition.y;
        const endX = x;
        const endY = y;

        // If no previous position, just set directly (no animation needed)
        if (startX === 0 && startY === 0) {
          const circle = this.elements.circle;
          circle.style.left = `${endX}px`;
          circle.style.top = `${endY}px`;
          this.currentPosition = { x: endX, y: endY };
          resolve();
          return;
        }

        const startTime = performance.now();
        const duration = CONFIG.moveDuration;

        // Calculate control point for Bezier curve (perpendicular offset)
        const midX = (startX + endX) / 2;
        const midY = (startY + endY) / 2;
        const distance = Math.sqrt((endX - startX) ** 2 + (endY - startY) ** 2);
        const offset = curved ? distance * 0.3 : 0;

        // Perpendicular direction
        const dx = endX - startX;
        const dy = endY - startY;
        const perpX = -dy / distance;
        const perpY = dx / distance;

        const controlX = midX + perpX * offset;
        const controlY = midY + perpY * offset;

        // Store reference at animation start to guard against cleanup during animation
        const circle = this.elements.circle;

        const animate = (currentTime) => {
          // Guard: if cleanup happened during animation, abort gracefully
          if (!this.elements || !circle.isConnected) {
            this.currentPosition = { x: endX, y: endY };
            resolve();
            return;
          }

          const elapsed = currentTime - startTime;
          const progress = Math.min(elapsed / duration, 1);

          // Ease-in-out function
          const eased = progress < 0.5
            ? 2 * progress * progress
            : 1 - Math.pow(-2 * progress + 2, 2) / 2;

          // Quadratic Bezier curve
          const t = eased;
          const currentX = (1 - t) ** 2 * startX + 2 * (1 - t) * t * controlX + t ** 2 * endX;
          const currentY = (1 - t) ** 2 * startY + 2 * (1 - t) * t * controlY + t ** 2 * endY;

          circle.style.left = `${currentX}px`;
          circle.style.top = `${currentY}px`;

          if (progress < 1) {
            this.animationFrame = requestAnimationFrame(animate);
          } else {
            this.currentPosition = { x: endX, y: endY };
            resolve();
          }
        };

        // Cancel any ongoing animation
        if (this.animationFrame) {
          cancelAnimationFrame(this.animationFrame);
        }

        this.animationFrame = requestAnimationFrame(animate);
      });
    },

    /**
     * Fade in the circle indicator
     */
    fadeIn() {
      return new Promise((resolve) => {
        this.init();
        const circle = this.elements.circle;

        circle.classList.remove('fade-out', 'pulse', 'shake');
        circle.classList.add('fade-in');

        setTimeout(() => {
          circle.classList.remove('fade-in');
          circle.style.opacity = '1';
          resolve();
        }, CONFIG.fadeInDuration);
      });
    },

    /**
     * Fade out the circle indicator
     */
    fadeOut() {
      return new Promise((resolve) => {
        this.init();
        const circle = this.elements.circle;

        circle.classList.remove('fade-in', 'pulse', 'shake');
        circle.classList.add('fade-out');

        setTimeout(() => {
          circle.classList.remove('fade-out');
          circle.style.opacity = '0';
          resolve();
        }, CONFIG.fadeOutDuration);
      });
    },

    /**
     * Pulse animation for action execution
     */
    pulse(actionType) {
      return new Promise((resolve) => {
        this.init();
        this.setColor(actionType);

        const circle = this.elements.circle;
        circle.classList.remove('fade-in', 'fade-out', 'shake');
        circle.classList.add('pulse');

        setTimeout(() => {
          circle.classList.remove('pulse');
          resolve();
        }, CONFIG.pulseDuration);
      });
    },

    /**
     * Show error animation (red color + shake)
     */
    showError() {
      return new Promise((resolve) => {
        this.init();
        this.setColor('error');

        const circle = this.elements.circle;
        circle.classList.remove('fade-in', 'fade-out', 'pulse');
        circle.classList.add('shake');

        setTimeout(() => {
          circle.classList.remove('shake');
          resolve();
        }, CONFIG.shakeDuration);
      });
    },

    /**
     * Show typing indicator below an element
     */
    showTyping(element) {
      this.init();
      const rect = element.getBoundingClientRect();
      const typing = this.elements.typing;

      typing.style.left = `${rect.left}px`;
      typing.style.top = `${rect.bottom + 8}px`;
      typing.classList.add('visible');
    },

    /**
     * Hide typing indicator
     */
    hideTyping() {
      if (this.elements) {
        this.elements.typing.classList.remove('visible');
      }
    },

    /**
     * Show select preview overlay below element
     * @param {Element} element - The select element
     * @param {string} optionText - The text of the option being selected
     * @param {number} duration - How long to show the preview (ms), default 600
     */
    showSelectPreview(element, optionText, duration = 600) {
      this.init();

      // Remove any existing preview
      const existing = document.querySelector('.inspekt-select-preview');
      if (existing) {
        existing.remove();
      }

      const rect = element.getBoundingClientRect();
      const preview = document.createElement('div');
      preview.className = 'inspekt-select-preview';
      preview.textContent = optionText;

      // Position below the select element
      preview.style.left = `${rect.left}px`;
      preview.style.top = `${rect.bottom + 6}px`;

      // Add to overlay container (or body if not ready)
      if (this.elements && this.elements.overlay) {
        this.elements.overlay.appendChild(preview);
      } else {
        document.body.appendChild(preview);
      }

      // Fade out and remove after duration
      setTimeout(() => {
        preview.classList.add('fade-out');
        setTimeout(() => {
          preview.remove();
        }, 300); // Match the fade-out animation duration
      }, duration);

      return preview;
    },

    /**
     * Hide everything
     */
    hide() {
      if (this.elements) {
        this.elements.circle.style.opacity = '0';
        this.elements.circle.classList.remove('fade-in', 'fade-out', 'pulse', 'shake');
        this.elements.typing.classList.remove('visible');
      }
    },

    /**
     * Clean up and remove overlay
     */
    cleanup() {
      if (this.animationFrame) {
        cancelAnimationFrame(this.animationFrame);
      }
      if (this.elements) {
        this.elements.overlay.remove();
        const styles = document.getElementById('inspekt-visual-styles');
        if (styles) styles.remove();
        this.elements = null;
      }
      // Also clean up interactive overlay, assertion overlay, and target indicator
      InteractiveOverlay.hide();
      AssertionOverlay.remove();
      TargetIndicator.hide();
    }
  };

  // ==========================================================================
  // Audio Feedback Module (Web Audio API Synthesizer)
  // ==========================================================================

  const Audio = {
    ctx: null,
    enabled: true,
    initialized: false,

    // Audio cue recording for video (--include-effects)
    recordingForVideo: false,
    recordingStartTime: 0,

    init() {
      if (this.initialized) return this.enabled;

      try {
        this.ctx = new (window.AudioContext || window.webkitAudioContext)();
        this.initialized = true;
        // Resume immediately if possible
        if (this.ctx.state === 'suspended') {
          this.ctx.resume().catch(() => {});
        }
        // Try to warm up the audio context by playing a silent buffer
        this.warmUp();
      } catch (e) {
        console.warn('Inspekt: Web Audio API not available');
        this.enabled = false;
      }
      return this.enabled;
    },

    /**
     * Try to unlock audio context by playing a silent sound.
     * This helps in contexts where autoplay is restricted.
     */
    warmUp() {
      if (!this.ctx) return;
      try {
        // Create a very short silent buffer
        const buffer = this.ctx.createBuffer(1, 1, this.ctx.sampleRate);
        const source = this.ctx.createBufferSource();
        source.buffer = buffer;
        source.connect(this.ctx.destination);
        source.start(0);
        // Resume again after playing (increases success rate)
        if (this.ctx.state === 'suspended') {
          this.ctx.resume().catch(() => {});
        }
      } catch (e) {
        // Ignore errors - this is a best-effort unlock attempt
      }
    },

    /**
     * Ensure audio context is ready
     */
    ensureReady() {
      if (!this.init()) return false;
      if (this.ctx.state === 'suspended') {
        this.ctx.resume().catch(() => {});
      }
      return true;
    },

    /**
     * Create a gain node with specified volume
     */
    createGain(volume = CONFIG.audioVolume) {
      const gain = this.ctx.createGain();
      gain.gain.value = volume;
      gain.connect(this.ctx.destination);
      return gain;
    },

    /**
     * Play a single tone
     */
    playTone(frequency, duration, type = 'sine', volume = CONFIG.audioVolume, startDelay = 0) {
      if (!this.ensureReady()) return;

      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();

      osc.connect(gain);
      gain.connect(this.ctx.destination);

      osc.frequency.value = frequency;
      osc.type = type;

      const now = this.ctx.currentTime + startDelay;
      gain.gain.setValueAtTime(volume, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + duration);

      osc.start(now);
      osc.stop(now + duration);
    },

    /**
     * Start recording sound - choice 2: Ascending with acceleration
     */
    playStart() {
      if (!this.ensureReady()) return;

      // Ascending with acceleration (300-450-600 Hz)
      this.playTone(300, 0.12, 'triangle', 0.2, 0);
      this.playTone(450, 0.1, 'triangle', 0.22, 0.1);
      this.playTone(600, 0.15, 'sine', 0.25, 0.18);
    },

    /**
     * Stop recording sound - choice 4: Tape stop feel
     */
    playStop() {
      if (!this.ensureReady()) return;

      // Tape stop feel (500-350-200 Hz descending)
      this.playTone(500, 0.15, 'triangle', 0.2, 0);
      this.playTone(350, 0.15, 'triangle', 0.18, 0.12);
      this.playTone(200, 0.2, 'sine', 0.15, 0.24);
    },

    /**
     * Start playback sound - choice 2: Forward motion
     */
    playStartPlayback() {
      if (!this.ensureReady()) return;

      // Forward motion - smooth glide up (350-525-700 Hz)
      this.playTone(350, 0.1, 'triangle', 0.22, 0);
      this.playTone(525, 0.1, 'triangle', 0.24, 0.08);
      this.playTone(700, 0.12, 'sine', 0.26, 0.16);
    },

    /**
     * Stop playback sound - choice 5: Soft done
     */
    playStopPlayback() {
      if (!this.ensureReady()) return;

      // Soft done - gentle wrap-up (500-400-300 Hz descending)
      this.playTone(500, 0.12, 'triangle', 0.2, 0);
      this.playTone(400, 0.12, 'triangle', 0.18, 0.1);
      this.playTone(300, 0.15, 'sine', 0.15, 0.2);
    },

    /**
     * Click sound - sharper click (higher pitched)
     */
    playClick() {
      if (!this.ensureReady()) return;

      const now = this.ctx.currentTime;
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();

      osc.connect(gain);
      gain.connect(this.ctx.destination);

      osc.frequency.setValueAtTime(5000, now);
      osc.frequency.exponentialRampToValueAtTime(1500, now + 0.01);
      osc.type = 'square';

      gain.gain.setValueAtTime(CONFIG.audioVolume * 0.3, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.02);

      osc.start(now);
      osc.stop(now + 0.02);
    },

    /**
     * Right-click sound - choice 5: Menu pop
     */
    playRightClick() {
      if (!this.ensureReady()) return;

      // Menu pop: sharp click + resonant tone
      this.playTone(1200, 0.02, 'square', CONFIG.audioVolume * 0.2, 0);
      this.playTone(500, 0.04, 'triangle', CONFIG.audioVolume * 0.25, 0.015);
    },

    /**
     * Keystroke/Type sound - choice 4: Light laptop key
     */
    playKeystroke() {
      if (!this.ensureReady()) return;

      const now = this.ctx.currentTime;
      const volume = CONFIG.audioVolume * 0.6;
      const pitch = 1.2;

      // Sharp attack (key hitting) - higher pitched for laptop feel
      const attackOsc = this.ctx.createOscillator();
      const attackGain = this.ctx.createGain();
      attackOsc.connect(attackGain);
      attackGain.connect(this.ctx.destination);
      attackOsc.frequency.setValueAtTime(2500 * pitch, now);
      attackOsc.frequency.exponentialRampToValueAtTime(800 * pitch, now + 0.012);
      attackOsc.type = 'square';
      attackGain.gain.setValueAtTime(volume * 0.25, now);
      attackGain.gain.exponentialRampToValueAtTime(0.001, now + 0.02);
      attackOsc.start(now);
      attackOsc.stop(now + 0.02);

      // Body resonance (keycap) - lighter feel
      const bodyOsc = this.ctx.createOscillator();
      const bodyGain = this.ctx.createGain();
      bodyOsc.connect(bodyGain);
      bodyGain.connect(this.ctx.destination);
      bodyOsc.frequency.setValueAtTime(400 * pitch, now + 0.005);
      bodyOsc.frequency.exponentialRampToValueAtTime(200 * pitch, now + 0.04);
      bodyOsc.type = 'triangle';
      bodyGain.gain.setValueAtTime(volume * 0.3, now + 0.005);
      bodyGain.gain.exponentialRampToValueAtTime(0.001, now + 0.05);
      bodyOsc.start(now);
      bodyOsc.stop(now + 0.05);
    },

    /**
     * Keypress sound - choice 5: Spacebar/wide key (for special keys like Enter, Tab)
     */
    playKeypress() {
      if (!this.ensureReady()) return;

      // Spacebar: sharp attack + deep body resonance (wide key)
      this.playTone(800, 0.02, 'square', CONFIG.audioVolume * 0.2, 0);
      this.playTone(200, 0.06, 'triangle', CONFIG.audioVolume * 0.35, 0.015);
    },

    /**
     * Hover sound - gentle wind breeze
     */
    playHover() {
      if (!this.ensureReady()) return;

      const now = this.ctx.currentTime;
      const duration = 0.25;

      // Create filtered noise for soft breeze effect
      const bufferSize = this.ctx.sampleRate * duration;
      const buffer = this.ctx.createBuffer(1, bufferSize, this.ctx.sampleRate);
      const data = buffer.getChannelData(0);

      // Generate smooth noise with gentle amplitude variation
      for (let i = 0; i < bufferSize; i++) {
        const t = i / bufferSize;
        // Soft envelope: slow fade in, gentle fade out
        const envelope = Math.sin(t * Math.PI) * Math.sin(t * Math.PI);
        data[i] = (Math.random() * 2 - 1) * envelope;
      }

      const noise = this.ctx.createBufferSource();
      noise.buffer = buffer;

      // Lowpass filter for soft, warm breeze (not harsh bandpass)
      const filter = this.ctx.createBiquadFilter();
      filter.type = 'lowpass';
      filter.frequency.value = 800;
      filter.Q.value = 0.5;

      // Gentle frequency drift for natural movement
      filter.frequency.setValueAtTime(600, now);
      filter.frequency.linearRampToValueAtTime(1000, now + duration * 0.5);
      filter.frequency.linearRampToValueAtTime(700, now + duration);

      const gain = this.ctx.createGain();

      noise.connect(filter);
      filter.connect(gain);
      gain.connect(this.ctx.destination);

      // Soft volume envelope - gentle rise and fall
      gain.gain.setValueAtTime(0, now);
      gain.gain.linearRampToValueAtTime(CONFIG.audioVolume * 0.2, now + 0.08);
      gain.gain.setValueAtTime(CONFIG.audioVolume * 0.2, now + duration - 0.08);
      gain.gain.linearRampToValueAtTime(0, now + duration);

      noise.start(now);
      noise.stop(now + duration);
    },

    /**
     * Activate sound - choice 2: Soft bell
     */
    playActivate() {
      if (!this.ensureReady()) return;

      // Soft bell - single warm tone
      this.playTone(660, 0.12, 'sine', CONFIG.audioVolume * 0.35, 0);
    },

    /**
     * Navigate sound - choice 2: Quick portal (200-600 Hz sweep)
     */
    playNavigate() {
      if (!this.ensureReady()) return;

      const now = this.ctx.currentTime;
      const duration = 0.2;

      // Quick portal sweep (200 -> 600 Hz)
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();

      osc.connect(gain);
      gain.connect(this.ctx.destination);

      osc.type = 'sine';
      osc.frequency.setValueAtTime(200, now);
      osc.frequency.exponentialRampToValueAtTime(600, now + duration);

      gain.gain.setValueAtTime(0.22, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + duration);

      osc.start(now);
      osc.stop(now + duration);
    },

    /**
     * Error/Failure sound - dissonant buzz (minor second)
     */
    playError() {
      if (!this.ensureReady()) return;

      const now = this.ctx.currentTime;
      const volume = CONFIG.audioVolume * 0.25;

      // Two dissonant tones (minor second interval = harsh)
      const osc1 = this.ctx.createOscillator();
      const gain1 = this.ctx.createGain();
      osc1.connect(gain1);
      gain1.connect(this.ctx.destination);
      osc1.frequency.value = 220;
      osc1.type = 'sawtooth';
      gain1.gain.setValueAtTime(volume, now);
      gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.2);
      osc1.start(now);
      osc1.stop(now + 0.2);

      const osc2 = this.ctx.createOscillator();
      const gain2 = this.ctx.createGain();
      osc2.connect(gain2);
      gain2.connect(this.ctx.destination);
      osc2.frequency.value = 233;
      osc2.type = 'sawtooth';
      gain2.gain.setValueAtTime(volume, now);
      gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.2);
      osc2.start(now);
      osc2.stop(now + 0.2);
    },

    /**
     * Success sound - bright ding
     */
    playSuccess() {
      if (!this.ensureReady()) return;

      // Ascending major chord - quick and bright
      const notes = [523.25, 659.25, 783.99]; // C5, E5, G5
      const noteDuration = 0.08;

      notes.forEach((freq, i) => {
        this.playTone(freq, noteDuration * 2, 'sine', CONFIG.audioVolume * 0.4, i * noteDuration);
      });
    },

    /**
     * Select sound - choice 5: List selection
     */
    playSelect() {
      if (!this.ensureReady()) return;

      // List selection: quick ascending duo
      this.playTone(550, 0.05, 'triangle', CONFIG.audioVolume * 0.3, 0);
      this.playTone(700, 0.06, 'sine', CONFIG.audioVolume * 0.3, 0.04);
    },

    /**
     * Check sound - ascending tick (positive confirmation)
     */
    playCheck() {
      if (!this.ensureReady()) return;

      const volume = CONFIG.audioVolume;
      this.playTone(500, 0.06, 'sine', volume * 0.35, 0);
      this.playTone(750, 0.08, 'sine', volume * 0.4, 0.05);
    },

    /**
     * Uncheck sound - descending tick (reverse of check)
     */
    playUncheck() {
      if (!this.ensureReady()) return;

      const volume = CONFIG.audioVolume;
      this.playTone(750, 0.06, 'sine', volume * 0.35, 0);
      this.playTone(500, 0.08, 'sine', volume * 0.3, 0.05);
    },

    /**
     * Radio button sound - choice 3: Click + confirm
     */
    playRadio() {
      if (!this.ensureReady()) return;

      // Click + confirm: sharp click followed by confirmation tone
      this.playTone(1200, 0.02, 'square', CONFIG.audioVolume * 0.2, 0);
      this.playTone(600, 0.12, 'sine', CONFIG.audioVolume * 0.4, 0.02);
    },

    /**
     * Plugin sound - choice 1: Bloop-bloop (identical double tone)
     */
    playPlugin() {
      if (!this.ensureReady()) return;

      // Bloop-bloop: two identical tones
      this.playTone(500, 0.1, 'sine', CONFIG.audioVolume * 0.4, 0);
      this.playTone(500, 0.1, 'sine', CONFIG.audioVolume * 0.4, 0.15);
    },

    /**
     * Inspekt command sound - choice 3: Analysis beep-beep (identical double tone)
     */
    playInspekt() {
      if (!this.ensureReady()) return;

      // Analysis beep-beep: two identical tones (softer, triangle wave)
      this.playTone(650, 0.1, 'triangle', CONFIG.audioVolume * 0.35, 0);
      this.playTone(650, 0.1, 'triangle', CONFIG.audioVolume * 0.35, 0.14);
    },

    /**
     * Scroll sound - soft swoosh/slide
     */
    playScroll() {
      if (!this.ensureReady()) return;

      const now = this.ctx.currentTime;
      const duration = 0.15;

      // Quick tonal slide for scrolling feel
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();

      osc.connect(gain);
      gain.connect(this.ctx.destination);

      // Pitch slides down slightly for scroll feel
      osc.frequency.setValueAtTime(400, now);
      osc.frequency.exponentialRampToValueAtTime(300, now + duration);
      osc.type = 'sine';

      gain.gain.setValueAtTime(0, now);
      gain.gain.linearRampToValueAtTime(CONFIG.audioVolume * 0.2, now + 0.02);
      gain.gain.linearRampToValueAtTime(CONFIG.audioVolume * 0.2, now + duration - 0.03);
      gain.gain.linearRampToValueAtTime(0, now + duration);

      osc.start(now);
      osc.stop(now + duration);
    },

    /**
     * Pause sound - distinctive attention chime
     * Different from action sounds to indicate "waiting for input"
     */
    playPause() {
      if (!this.ensureReady()) return;

      // Two-note rising chime (A5 → C6) for attention/pause
      this.playTone(880, 0.15, 'sine', CONFIG.audioVolume * 0.4, 0);    // A5 note
      this.playTone(1047, 0.15, 'sine', CONFIG.audioVolume * 0.4, 0.15); // C6 note
    },

    /**
     * Play sound based on action type
     */
    playForAction(actionType) {
      switch (actionType) {
        case 'click':
          this.playClick();
          break;
        case 'rightclick':
          this.playRightClick();
          break;
        case 'activate':
          this.playActivate();
          break;
        case 'type':
          this.playKeystroke();
          break;
        case 'set':
          this.playKeystroke();  // Same sound as type for setting native control values
          break;
        case 'keypress':
          this.playKeypress();
          break;
        case 'navigate':
          this.playNavigate();
          break;
        case 'scroll':
          this.playScroll();
          break;
        case 'select':
          this.playSelect();
          break;
        case 'check':
          this.playCheck();
          break;
        case 'uncheck':
          this.playUncheck();
          break;
        case 'radio':
          this.playRadio();
          break;
        case 'toggle':
          this.playClick();  // Use click sound for toggle actions
          break;
        case 'dialog':
          this.playClick();  // Use click sound for dialog actions
          break;
        case 'jsdialog':
          this.playClick();  // Use click sound for JS dialog actions
          break;
        case 'upload':
          this.playClick();  // Use click sound for upload actions
          break;
        case 'download':
          this.playClick();  // Use click sound for download actions
          break;
        case 'hover':
          this.playHover();
          break;
        case 'plugin':
          this.playPlugin();
          break;
        case 'inspekt':
          this.playInspekt();
          break;
        case 'pause':
          this.playPause();
          break;
        case 'failure':
        case 'error':
          this.playError();
          break;
        default:
          // No sound for unknown actions
          break;
      }

      // If recording audio cues for video, send cue to bridge
      if (this.recordingForVideo && actionType) {
        const timestampMs = Math.round(performance.now() - this.recordingStartTime);
        fetch('http://127.0.0.1:8765/audio/cue', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            timestamp_ms: timestampMs,
            action: actionType
          })
        }).catch(() => {}); // Fire and forget - don't block replay
      }
    },

    /**
     * Start recording audio cues for video
     * Called when replay starts with --video --include-effects
     */
    startRecordingForVideo() {
      this.recordingForVideo = true;
      this.recordingStartTime = performance.now();
    },

    /**
     * Stop recording audio cues for video
     */
    stopRecordingForVideo() {
      this.recordingForVideo = false;
    }
  };

  // ==========================================================================
  // Target Indicator Module (shows arrow pointing to next action target)
  // ==========================================================================

  const TargetIndicator = {
    indicatorElement: null,
    spotlightElement: null,

    /**
     * Actions that should show the target indicator
     */
    shouldShowForAction(action) {
      const showActions = ['click', 'rightclick', 'activate', 'type', 'set', 'check', 'uncheck', 'select', 'radio'];
      return showActions.includes(action);
    },

    /**
     * Actions that should show for keypress (only Tab/Shift+Tab)
     */
    shouldShowForKeypress(step) {
      if (step.action !== 'keypress') return false;
      const key = (step.key || '').toLowerCase();
      return key === 'tab';
    },

    /**
     * Get color for action type
     */
    getColorForAction(action) {
      const colors = {
        click: CONFIG.colors.click,
        rightclick: CONFIG.colors.click,
        activate: CONFIG.colors.activate,
        type: CONFIG.colors.type,
        set: CONFIG.colors.set,
        keypress: CONFIG.colors.keypress,
        check: CONFIG.colors.check,
        uncheck: CONFIG.colors.uncheck,
        select: CONFIG.colors.select,
        radio: CONFIG.colors.radio
      };
      return colors[action] || CONFIG.colors.click;
    },

    /**
     * Show the target indicator for a step
     */
    show(step) {
      // Check if we should show for this action
      const action = step?.action;
      if (!action) {
        this.hide();
        return;
      }

      const shouldShow = this.shouldShowForAction(action) || this.shouldShowForKeypress(step);
      if (!shouldShow) {
        this.hide();
        return;
      }

      // Get the target selector
      const selector = step.target?.selector;
      if (!selector) {
        this.hide();
        return;
      }

      // Find the target element
      let targetElement;
      try {
        targetElement = document.querySelector(selector);
      } catch (e) {
        // Invalid selector
        this.hide();
        return;
      }

      if (!targetElement) {
        this.hide();
        return;
      }

      // Get element position
      const rect = targetElement.getBoundingClientRect();
      const color = this.getColorForAction(action);

      // Calculate spotlight size (add padding around element)
      const padding = 60;
      const spotlightWidth = rect.width + padding * 2;
      const spotlightHeight = rect.height + padding * 2;
      // Use the larger dimension to make it circular, with minimum size
      const spotlightSize = Math.max(spotlightWidth, spotlightHeight, 150);

      // Center of the element
      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height / 2;

      // Create spotlight if it doesn't exist
      if (!this.spotlightElement) {
        this.spotlightElement = document.createElement('div');
        this.spotlightElement.id = 'inspekt-spotlight';
        // Set initial position immediately (no transition for first appearance)
        this.spotlightElement.style.transition = 'none';
        this.spotlightElement.style.opacity = '0';
        document.body.appendChild(this.spotlightElement);
        // Force reflow, then enable transitions and fade in
        this.spotlightElement.offsetHeight;
        this.spotlightElement.style.transition = '';
        this.spotlightElement.style.opacity = '1';
      }

      // Position spotlight centered on the element
      this.spotlightElement.style.width = `${spotlightSize}px`;
      this.spotlightElement.style.height = `${spotlightSize}px`;
      this.spotlightElement.style.left = `${centerX - spotlightSize / 2}px`;
      this.spotlightElement.style.top = `${centerY - spotlightSize / 2}px`;

      // Calculate best position for the arrow (prefer left side of element)
      const viewportWidth = window.innerWidth;
      const viewportHeight = window.innerHeight;
      const arrowSize = 48;
      const gap = 20;

      let arrowX, arrowY, direction;

      // Try left side first
      if (rect.left > arrowSize + gap + 20) {
        arrowX = rect.left - arrowSize - gap;
        arrowY = rect.top + rect.height / 2 - arrowSize / 2;
        direction = 'right';
      }
      // Try right side
      else if (rect.right + arrowSize + gap + 20 < viewportWidth) {
        arrowX = rect.right + gap;
        arrowY = rect.top + rect.height / 2 - arrowSize / 2;
        direction = 'left';
      }
      // Try top
      else if (rect.top > arrowSize + gap + 20) {
        arrowX = rect.left + rect.width / 2 - arrowSize / 2;
        arrowY = rect.top - arrowSize - gap;
        direction = 'down';
      }
      // Try bottom
      else {
        arrowX = rect.left + rect.width / 2 - arrowSize / 2;
        arrowY = rect.bottom + gap;
        direction = 'up';
      }

      // Clamp to viewport
      arrowX = Math.max(10, Math.min(arrowX, viewportWidth - arrowSize - 10));
      arrowY = Math.max(10, Math.min(arrowY, viewportHeight - arrowSize - 10));

      // Create indicator if it doesn't exist
      if (!this.indicatorElement) {
        this.indicatorElement = document.createElement('div');
        this.indicatorElement.id = 'inspekt-target-indicator';
        // Arrow SVG (pointing right by default, rotated via CSS)
        this.indicatorElement.innerHTML = `
          <div class="arrow">
            <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
              <path d="M8.59 16.59L13.17 12 8.59 7.41 10 6l6 6-6 6-1.41-1.41z"/>
            </svg>
          </div>
        `;
        document.body.appendChild(this.indicatorElement);
      }

      // Update position and direction
      this.indicatorElement.setAttribute('data-direction', direction);
      this.indicatorElement.style.left = `${arrowX}px`;
      this.indicatorElement.style.top = `${arrowY}px`;
      this.indicatorElement.style.setProperty('--arrow-color', color);
    },

    /**
     * Hide and remove the target indicator
     */
    hide() {
      if (this.indicatorElement) {
        this.indicatorElement.remove();
        this.indicatorElement = null;
      }
      if (this.spotlightElement) {
        this.spotlightElement.remove();
        this.spotlightElement = null;
      }
    }
  };

  // ==========================================================================
  // Interactive Replay Module (step-by-step execution with user control)
  // ==========================================================================

  const InteractiveOverlay = {
    element: null,
    keyHandler: null,
    resolvePromise: null,
    currentCorner: 'bottom-left',
    isDragging: false,
    dragStartX: 0,
    dragStartY: 0,
    dragOffsetX: 0,
    dragOffsetY: 0,
    initialRect: null,
    boundDragMove: null,
    boundDragEnd: null,
    dragTargets: [],
    positionLoaded: false,

    /**
     * Load saved corner position from extension storage
     */
    async loadPosition() {
      if (this.positionLoaded) return this.currentCorner;

      return new Promise((resolve) => {
        const requestId = `pos-load-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

        const handler = (event) => {
          if (event.data?.type === 'INSPEKT_OVERLAY_POSITION_RESPONSE' &&
              event.data?.source === 'inspekt-extension' &&
              event.data?.requestId === requestId) {
            window.removeEventListener('message', handler);
            this.currentCorner = event.data.corner || 'bottom-left';
            this.positionLoaded = true;
            resolve(this.currentCorner);
          }
        };

        window.addEventListener('message', handler);

        // Request position from extension
        window.postMessage({
          type: 'INSPEKT_GET_OVERLAY_POSITION',
          source: 'inspekt-page',
          requestId: requestId
        }, '*');

        // Timeout after 500ms - use default if extension doesn't respond
        setTimeout(() => {
          window.removeEventListener('message', handler);
          if (!this.positionLoaded) {
            this.positionLoaded = true;
            resolve(this.currentCorner);
          }
        }, 500);
      });
    },

    /**
     * Save corner position to extension storage
     */
    savePosition(corner) {
      window.postMessage({
        type: 'INSPEKT_SAVE_OVERLAY_POSITION',
        source: 'inspekt-page',
        requestId: `pos-save-${Date.now()}`,
        corner: corner
      }, '*');
    },

    /**
     * Get the bounding rect of the target element for a step
     */
    getTargetRect(step) {
      if (!step?.target?.selector) return null;

      try {
        const element = document.querySelector(step.target.selector);
        if (!element) return null;
        return element.getBoundingClientRect();
      } catch (e) {
        return null;
      }
    },

    /**
     * Calculate the overlay rect for a given corner
     */
    getOverlayRectForCorner(corner) {
      const margin = 20;
      // Estimate overlay dimensions (or use actual if available)
      const width = this.element ? this.element.offsetWidth : 380;
      const height = this.element ? this.element.offsetHeight : 180;

      const viewport = {
        width: window.innerWidth,
        height: window.innerHeight
      };

      let left, top;

      switch (corner) {
        case 'top-left':
          left = margin;
          top = margin;
          break;
        case 'top-right':
          left = viewport.width - width - margin;
          top = margin;
          break;
        case 'bottom-left':
          left = margin;
          top = viewport.height - height - margin;
          break;
        case 'bottom-right':
          left = viewport.width - width - margin;
          top = viewport.height - height - margin;
          break;
        default:
          left = margin;
          top = viewport.height - height - margin;
      }

      return { left, top, width, height, right: left + width, bottom: top + height };
    },

    /**
     * Check if two rects overlap (with padding for breathing room)
     */
    rectsOverlap(rect1, rect2, padding = 20) {
      if (!rect1 || !rect2) return false;

      return !(
        rect1.right + padding < rect2.left ||
        rect1.left - padding > rect2.right ||
        rect1.bottom + padding < rect2.top ||
        rect1.top - padding > rect2.bottom
      );
    },

    /**
     * Find the best corner that doesn't overlap with the target element
     * Returns the current corner if no overlap, or the best alternative
     */
    findBestCorner(targetRect) {
      if (!targetRect) return this.currentCorner;

      const corners = ['bottom-left', 'bottom-right', 'top-left', 'top-right'];
      const currentOverlayRect = this.getOverlayRectForCorner(this.currentCorner);

      // If current corner doesn't overlap, keep it
      if (!this.rectsOverlap(currentOverlayRect, targetRect)) {
        return this.currentCorner;
      }

      // Find first corner that doesn't overlap (prefer same side - bottom vs top)
      const isCurrentBottom = this.currentCorner.startsWith('bottom');
      const isCurrentLeft = this.currentCorner.includes('left');

      // Priority: same vertical side first, then opposite
      const priorityOrder = isCurrentBottom
        ? ['bottom-right', 'bottom-left', 'top-left', 'top-right']
        : ['top-right', 'top-left', 'bottom-left', 'bottom-right'];

      // Adjust priority to prefer opposite horizontal side first
      if (isCurrentLeft) {
        // Current is left, prefer right corners
        priorityOrder.sort((a, b) => {
          const aIsRight = a.includes('right') ? 0 : 1;
          const bIsRight = b.includes('right') ? 0 : 1;
          return aIsRight - bIsRight;
        });
      }

      for (const corner of priorityOrder) {
        if (corner === this.currentCorner) continue;
        const overlayRect = this.getOverlayRectForCorner(corner);
        if (!this.rectsOverlap(overlayRect, targetRect)) {
          return corner;
        }
      }

      // All corners overlap - return current (user can drag if needed)
      return this.currentCorner;
    },

    /**
     * Auto-reposition overlay if it would cover the target element
     * Moves to a different corner if needed
     * @param {object} step - The current step data
     * @param {boolean} instant - If true, reposition instantly without animation
     */
    autoRepositionForTarget(step, instant = false) {
      const targetRect = this.getTargetRect(step);
      if (!targetRect) return;

      const bestCorner = this.findBestCorner(targetRect);

      if (bestCorner !== this.currentCorner) {
        if (instant) {
          // Instant repositioning (used on first show)
          this.snapToCorner(bestCorner);
        } else {
          // Animated repositioning
          this.snapToCornerAnimated(bestCorner);
        }
      }
    },

    /**
     * Create drag target zones for other corners
     * Sizes them to match the actual overlay dimensions
     */
    createDragTargets() {
      const corners = ['top-left', 'top-right', 'bottom-left', 'bottom-right'];
      const targets = [];

      // Get actual overlay dimensions to size targets correctly
      const overlayRect = this.element ? this.element.getBoundingClientRect() : null;

      corners.forEach(corner => {
        if (corner === this.currentCorner) return; // Skip current corner

        const target = document.createElement('div');
        target.className = 'inspekt-drag-target';
        target.setAttribute('data-corner', corner);

        // Match overlay dimensions if available
        if (overlayRect) {
          target.style.width = `${overlayRect.width}px`;
          target.style.height = `${overlayRect.height}px`;
        }

        document.body.appendChild(target);
        targets.push(target);
      });

      return targets;
    },

    /**
     * Remove all drag targets
     */
    removeDragTargets() {
      this.dragTargets.forEach(target => target.remove());
      this.dragTargets = [];
    },

    /**
     * Format a step for display in the overlay
     */
    formatStep(step) {
      if (!step) return 'Starting replay...';

      const action = step.action || 'unknown';
      const target = step.target || {};
      const accessibleName = target.accessible_name || target.text || '';
      const tag = target.tag || '';
      const selector = target.selector || '';

      // Action icons (Nerd Font) - matches icons.py ACTION_ICONS exactly
      const icons = {
        navigate: '\u{f059f}',    // 󰖟 nf-md-web
        click: '\u{f0cfd}',       // 󰳽 nf-md-cursor_default_click
        rightclick: '\u{f0cfd}',  // 󰳽 nf-md-cursor_default_click
        activate: '\u{f0311}',    // 󰌑 nf-md-keyboard_return
        type: '\u{f05e7}',        // 󰗧 nf-md-form_textbox
        set: '\u{f05e7}',         // 󰗧 nf-md-form_textbox (default, overridden below)
        keypress: '\uf11c',       //  nf-fa-keyboard_o
        hover: '\u{f0208}',       // 󰈈 nf-md-eye
        scroll: '\u{f0599}',      // 󰖙 nf-md-unfold_more_vertical
        check: '\u{f0c52}',       // 󰱒 nf-md-checkbox_marked_circle
        uncheck: '\uf0c8',        //  nf-fa-square
        select: '\u{f1400}',      // 󱐀 nf-md-form_dropdown
        radio: '\u{f043e}',       // 󰐾 nf-md-radiobox_marked
        jsdialog: '\ue60c',       //  nf-seti-javascript
        inspekt: '\uf002'         //  nf-fa-search
      };

      // Native control icons - matches icons.py NATIVE_CONTROL_ICONS
      const nativeControlIcons = {
        time: '\u{f0589}',           // 󰖉 nf-md-clock_outline
        date: '\u{f00ed}',           // 󰃭 nf-md-calendar
        'datetime-local': '\u{f00f0}', // 󰃰 nf-md-calendar_clock
        month: '\u{f00ed}',          // 󰃭 nf-md-calendar
        week: '\u{f00ed}',           // 󰃭 nf-md-calendar
        range: '\ue690',              //  nf-seti-config
        number: '\uf4f7',            //  nf-oct-number
        color: '\u{f03d8}'           // 󰏘 nf-md-palette
      };

      // Get icon - for 'set' action, use native control-specific icon
      let icon = icons[action] || '\u2022'; // bullet as fallback
      if (action === 'set') {
        const inputType = target.input_type || '';
        icon = nativeControlIcons[inputType] || icons.set;
      }

      // Format based on action type
      if (action === 'navigate') {
        const url = step.url || '';
        const shortUrl = url.length > 40 ? url.substring(0, 40) + '...' : url;
        return `${icon} Navigate to ${shortUrl}`;
      }

      if (action === 'type') {
        const charCount = (step.value || '').length;
        const inputType = target.attributes?.type || 'text';
        if (step.sensitive) {
          return `${icon} Type password (${charCount} chars)`;
        }
        return `${icon} Type ${charCount} chars into ${inputType} field`;
      }

      if (action === 'set') {
        const value = step.value || '';
        const inputType = target.input_type || '';
        const typeNames = {
          time: 'time',
          date: 'date',
          'datetime-local': 'date & time',
          month: 'month',
          week: 'week',
          range: 'range',
          number: 'number',
          color: 'color'
        };
        const typeName = typeNames[inputType] || 'value';
        return `${icon} Set ${typeName} to ${value}`;
      }

      if (action === 'keypress') {
        const key = step.key || '';
        const modifiers = step.modifiers || [];
        const keyStr = modifiers.length > 0 ? modifiers.join('+') + '+' + key : key;
        return `${icon} Press ${keyStr}`;
      }

      if (action === 'select') {
        const optionText = step.option_text || step.value || '';
        return `${icon} Select "${optionText}"`;
      }

      if (action === 'check' || action === 'uncheck') {
        const name = accessibleName || step.value || selector;
        return `${icon} ${action === 'check' ? 'Check' : 'Uncheck'} "${name}"`;
      }

      if (action === 'scroll') {
        const scroll = step.scroll || {};
        const deltaY = scroll.deltaY || 0;
        const direction = deltaY > 0 ? 'down' : 'up';
        return `${icon} Scroll ${direction} ${Math.abs(deltaY)}px`;
      }

      if (action === 'inspekt') {
        return `${icon} Run: inspekt ${step.command || ''}`;
      }

      if (action === 'jsdialog') {
        const dialogType = step.dialog_type || 'alert';
        const message = step.message || '';
        const shortMessage = message.length > 30 ? message.substring(0, 30) + '...' : message;
        const typeLabels = { alert: 'Alert', confirm: 'Confirm', prompt: 'Prompt' };
        const typeLabel = typeLabels[dialogType] || dialogType;
        if (message) {
          return `${icon} ${typeLabel}: "${shortMessage}"`;
        }
        return `${icon} ${typeLabel} dialog`;
      }

      // Default: click, rightclick, activate, hover
      const name = accessibleName || selector.substring(0, 30);
      const tagDisplay = tag ? ` (${tag})` : '';
      return `${icon} ${action} → "${name}"${tagDisplay}`;
    },

    /**
     * Show the interactive overlay
     */
    show(currentStep, previousStep, stepNum, totalSteps) {
      // Track if this is the first show (for instant vs animated repositioning)
      const isFirstShow = !this.element;

      // Create overlay shell if it doesn't exist (with static key hints)
      if (!this.element) {
        const overlay = document.createElement('div');
        overlay.id = 'inspekt-interactive-overlay';
        overlay.className = 'waiting';
        overlay.setAttribute('data-corner', this.currentCorner);
        overlay.innerHTML = `
          <div class="previous-step"></div>
          <div class="step-counter"></div>
          <div class="progress-bar">
            <div class="progress-fill"></div>
          </div>
          <div class="current-step"></div>
          <div class="key-hints">
            <span><kbd>Enter</kbd> Next</span>
            <span><kbd>Space</kbd> Skip</span>
            <span><kbd>Esc</kbd> Stop</span>
          </div>
        `;
        document.body.appendChild(overlay);
        this.element = overlay;
        // Initialize dragging for new overlay
        this.initDrag();
        // Fade in on first show
        requestAnimationFrame(() => {
          this.element.classList.add('visible');
        });
      }

      // Update only the dynamic content (no innerHTML replacement on container)
      const previousEl = this.element.querySelector('.previous-step');
      const counterEl = this.element.querySelector('.step-counter');
      const progressEl = this.element.querySelector('.progress-fill');
      const currentEl = this.element.querySelector('.current-step');

      // Previous step content
      if (previousStep) {
        const prevFormatted = this.formatStep(previousStep);
        previousEl.innerHTML = `<span class="checkmark">✓</span> ${prevFormatted}`;
      } else {
        previousEl.innerHTML = `<span class="checkmark">▶</span> Interactive replay started`;
      }

      // Step counter
      counterEl.textContent = `Step ${stepNum} of ${totalSteps}`;

      // Progress bar
      const progressPercent = (stepNum / totalSteps) * 100;
      progressEl.style.width = `${progressPercent}%`;

      // Current step
      currentEl.innerHTML = this.formatStep(currentStep);

      // Ensure visible class is set
      if (!this.element.classList.contains('visible')) {
        this.element.classList.add('visible');
      }

      // Auto-reposition if overlay would cover the target element
      // Use instant positioning on first show, animated on subsequent shows
      this.autoRepositionForTarget(currentStep, isFirstShow);

      // Show target indicator arrow for the current step
      TargetIndicator.show(currentStep);
    },

    /**
     * Initialize drag-to-corner functionality
     */
    initDrag() {
      if (!this.element) return;

      this.boundDragMove = this.onDragMove.bind(this);
      this.boundDragEnd = this.onDragEnd.bind(this);

      this.element.addEventListener('mousedown', this.onDragStart.bind(this));
    },

    /**
     * Handle drag start
     */
    onDragStart(e) {
      // Don't drag when clicking on kbd elements
      if (e.target.tagName === 'KBD') return;

      this.isDragging = true;
      this.dragStartX = e.clientX;
      this.dragStartY = e.clientY;

      // Capture initial overlay position and offset for free dragging
      const rect = this.element.getBoundingClientRect();
      this.dragOffsetX = e.clientX - rect.left;
      this.dragOffsetY = e.clientY - rect.top;
      this.initialRect = rect;

      // Switch to free-positioning mode
      this.element.classList.add('dragging', 'free-drag');
      this.element.style.left = `${rect.left}px`;
      this.element.style.top = `${rect.top}px`;
      this.element.style.right = 'auto';
      this.element.style.bottom = 'auto';

      // Hide assertion overlay during drag
      AssertionOverlay.hide();

      // Create and show drag targets
      this.dragTargets = this.createDragTargets();
      // Small delay to allow CSS transition
      requestAnimationFrame(() => {
        this.dragTargets.forEach(t => t.classList.add('visible'));
      });

      document.addEventListener('mousemove', this.boundDragMove);
      document.addEventListener('mouseup', this.boundDragEnd);

      e.preventDefault();
    },

    /**
     * Handle drag move - move overlay with cursor and highlight targets
     */
    onDragMove(e) {
      if (!this.isDragging) return;

      // Move overlay with cursor
      this.element.style.left = `${e.clientX - this.dragOffsetX}px`;
      this.element.style.top = `${e.clientY - this.dragOffsetY}px`;

      // Check which drag target (if any) the cursor is over
      this.dragTargets.forEach(target => {
        const rect = target.getBoundingClientRect();
        const isOver = e.clientX >= rect.left && e.clientX <= rect.right &&
                       e.clientY >= rect.top && e.clientY <= rect.bottom;
        target.classList.toggle('hover', isOver);
      });
    },

    /**
     * Handle drag end - snap to nearest corner with animation
     */
    onDragEnd(e) {
      if (!this.isDragging) return;

      this.isDragging = false;
      this.element.classList.remove('dragging');

      document.removeEventListener('mousemove', this.boundDragMove);
      document.removeEventListener('mouseup', this.boundDragEnd);

      // Check if dropped on a specific target
      let droppedCorner = null;
      this.dragTargets.forEach(target => {
        const rect = target.getBoundingClientRect();
        const isOver = e.clientX >= rect.left && e.clientX <= rect.right &&
                       e.clientY >= rect.top && e.clientY <= rect.bottom;
        if (isOver) {
          droppedCorner = target.getAttribute('data-corner');
        }
      });

      // Remove drag targets
      this.removeDragTargets();

      // Determine corner - use dropped target or calculate from position
      let newCorner;
      if (droppedCorner) {
        newCorner = droppedCorner;
      } else {
        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight;
        const isRight = e.clientX > viewportWidth / 2;
        const isBottom = e.clientY > viewportHeight / 2;
        newCorner = `${isBottom ? 'bottom' : 'top'}-${isRight ? 'right' : 'left'}`;
      }

      // Animate snap to corner
      this.snapToCornerAnimated(newCorner);

      // Save position to extension storage
      this.savePosition(newCorner);
    },

    /**
     * Snap overlay to a specific corner with smooth animation
     */
    snapToCornerAnimated(corner) {
      if (!this.element) return;

      // Get current position before changing anything
      const currentRect = this.element.getBoundingClientRect();
      const viewportWidth = window.innerWidth;
      const viewportHeight = window.innerHeight;
      const margin = 20;

      // Calculate target position for the new corner
      let targetLeft, targetTop;

      switch (corner) {
        case 'top-left':
          targetLeft = margin;
          targetTop = margin;
          break;
        case 'top-right':
          targetLeft = viewportWidth - currentRect.width - margin;
          targetTop = margin;
          break;
        case 'bottom-left':
          targetLeft = margin;
          targetTop = viewportHeight - currentRect.height - margin;
          break;
        case 'bottom-right':
          targetLeft = viewportWidth - currentRect.width - margin;
          targetTop = viewportHeight - currentRect.height - margin;
          break;
        default:
          targetLeft = margin;
          targetTop = viewportHeight - currentRect.height - margin;
      }

      // Step 1: Convert current CSS positioning to absolute left/top
      // This ensures we animate FROM the current visual position
      this.element.style.transition = 'none';
      this.element.style.top = `${currentRect.top}px`;
      this.element.style.bottom = 'auto';
      this.element.style.left = `${currentRect.left}px`;
      this.element.style.right = 'auto';
      this.element.classList.add('free-drag');

      // Step 2: Force reflow to apply the position change instantly
      this.element.offsetHeight;

      // Step 3: Re-enable transitions and animate to target
      this.element.style.transition = '';
      this.element.classList.add('snapping');
      this.element.style.left = `${targetLeft}px`;
      this.element.style.top = `${targetTop}px`;

      // Update assertion overlay position
      AssertionOverlay.updatePosition(corner, false);

      // Update current corner
      this.currentCorner = corner;

      // Step 4: After animation completes, switch back to corner-based positioning
      setTimeout(() => {
        this.element.classList.remove('free-drag', 'snapping');
        this.element.style.transition = '';
        this.element.style.left = '';
        this.element.style.top = '';
        this.element.style.right = '';
        this.element.style.bottom = '';
        this.element.setAttribute('data-corner', corner);

        // Show assertion overlay again if it exists (with fade-in animation)
        if (AssertionOverlay.element) {
          AssertionOverlay.element.classList.add('visible');
        }
      }, 260); // Slightly longer than the 250ms transition
    },

    /**
     * Snap overlay to a specific corner (instant, used for initialization)
     */
    snapToCorner(corner) {
      this.currentCorner = corner;
      if (this.element) {
        this.element.setAttribute('data-corner', corner);
      }
      // Also move the assertion overlay to follow (instant)
      AssertionOverlay.updatePosition(corner, false);
    },

    /**
     * Hide the overlay (keeps element in DOM for reuse)
     */
    hide() {
      // Clean up drag listeners if dragging was interrupted
      if (this.boundDragMove) {
        document.removeEventListener('mousemove', this.boundDragMove);
      }
      if (this.boundDragEnd) {
        document.removeEventListener('mouseup', this.boundDragEnd);
      }
      this.isDragging = false;

      // Clean up any drag targets
      this.removeDragTargets();

      // Note: Don't hide TargetIndicator here - it will be updated by the next show() call
      // or explicitly hidden when replay ends

      // Just hide visually, keep element in DOM for smooth transitions
      if (this.element) {
        this.element.classList.remove('visible');
      }
      if (this.keyHandler) {
        document.removeEventListener('keydown', this.keyHandler, true);
        this.keyHandler = null;
      }
      this.resolvePromise = null;
    },

    /**
     * Wait for user input (Enter, Space, or Escape)
     * Returns a promise that resolves with 'next', 'skip', or 'cancel'
     */
    waitForInput() {
      return new Promise((resolve) => {
        this.resolvePromise = resolve;

        // Debounce: ignore keypresses for a short time after overlay appears
        // This prevents the Enter from the previous step from immediately triggering this one
        const startTime = Date.now();
        const debounceMs = 150; // Ignore keypresses in first 150ms

        this.keyHandler = (event) => {
          // Ignore events during debounce period
          const elapsed = Date.now() - startTime;
          if (elapsed < debounceMs) {
            event.preventDefault();
            event.stopPropagation();
            return;
          }

          // Only handle trusted events (real user input)
          if (!event.isTrusted) return;

          if (event.key === 'Enter') {
            event.preventDefault();
            event.stopPropagation();
            event.stopImmediatePropagation();
            document.removeEventListener('keydown', this.keyHandler, true);
            this.keyHandler = null;
            resolve('next');
          } else if (event.key === ' ') {
            event.preventDefault();
            event.stopPropagation();
            event.stopImmediatePropagation();
            document.removeEventListener('keydown', this.keyHandler, true);
            this.keyHandler = null;
            resolve('skip');
          } else if (event.key === 'Escape') {
            event.preventDefault();
            event.stopPropagation();
            event.stopImmediatePropagation();
            document.removeEventListener('keydown', this.keyHandler, true);
            this.keyHandler = null;
            resolve('cancel');
          }
        };

        // Use capture phase to intercept before page handlers
        document.addEventListener('keydown', this.keyHandler, true);
      });
    }
  };

  // ==========================================================================
  // Assertion Overlay Module (shows test results in interactive mode)
  // ==========================================================================

  const AssertionOverlay = {
    element: null,

    /**
     * Generate assertion description from expect object
     */
    generateDescription(expect) {
      if (!expect) return null;

      const parts = [];
      if (expect.visible) parts.push(`visible: ${expect.visible}`);
      if (expect.hidden) parts.push(`hidden: ${expect.hidden}`);
      if (expect.text_contains) parts.push(`text contains: "${expect.text_contains}"`);
      if (expect.url_contains) parts.push(`URL contains: "${expect.url_contains}"`);
      if (expect.focused) parts.push('element has focus');
      if (expect.checked) parts.push(`checked: ${expect.checked}`);
      if (expect.unchecked) parts.push(`unchecked: ${expect.unchecked}`);
      if (expect.value_equals !== undefined) parts.push(`value equals: "${expect.value_equals}"`);
      if (expect.count && expect.count_equals !== undefined) {
        parts.push(`count(${expect.count}) = ${expect.count_equals}`);
      }

      return parts.length > 0 ? parts.join(', ') : null;
    },

    /**
     * Get position relative to main overlay
     * Uses the same corner as the interactive overlay, positioned above/below it
     */
    getPosition(mainCorner) {
      const mainOverlay = InteractiveOverlay.element;
      const corner = mainCorner || InteractiveOverlay.currentCorner || 'bottom-left';
      const margin = 20; // Same margin as interactive overlay
      const gap = 10; // Gap between overlays

      // Get the main overlay's height (or estimate if not available)
      let mainHeight = 180; // Default estimate (interactive overlay is typically ~170-180px)
      if (mainOverlay) {
        const rect = mainOverlay.getBoundingClientRect();
        if (rect.height > 0) {
          mainHeight = rect.height;
        }
      }

      // Position based on corner
      const isTop = corner.startsWith('top');
      const isLeft = corner.includes('left');

      if (isTop) {
        // Main is at top, assertion goes below it
        // top: margin (main's top) + mainHeight + gap
        return {
          top: `${margin + mainHeight + gap}px`,
          bottom: 'auto',
          left: isLeft ? `${margin}px` : 'auto',
          right: isLeft ? 'auto' : `${margin}px`
        };
      } else {
        // Main is at bottom, assertion goes above it
        // We need to position from bottom, accounting for main overlay height + gap
        return {
          top: 'auto',
          bottom: `${margin + mainHeight + gap}px`,
          left: isLeft ? `${margin}px` : 'auto',
          right: isLeft ? 'auto' : `${margin}px`
        };
      }
    },

    /**
     * Show assertion overlay in "checking" state
     */
    showChecking(expect, mainCorner) {
      const message = expect?.message || this.generateDescription(expect) || 'Checking assertions...';
      const details = this.generateDescription(expect);

      this.show({
        status: 'checking',
        message,
        details: details !== message ? details : null
      }, mainCorner);
    },

    /**
     * Show assertion overlay with result
     */
    showResult(expect, passed, failures, mainCorner) {
      const message = expect?.message || this.generateDescription(expect) || (passed ? 'Assertion passed' : 'Assertion failed');
      const details = failures && failures.length > 0 ? failures.join('\n') : null;

      this.show({
        status: passed ? 'pass' : 'fail',
        message,
        details
      }, mainCorner);
    },

    /**
     * Show the assertion overlay
     */
    show(options, mainCorner) {
      const { status, message, details } = options;

      // Create element if needed
      if (!this.element) {
        this.element = document.createElement('div');
        this.element.id = 'inspekt-assertion-overlay';
        document.body.appendChild(this.element);
      }

      // Get icon based on status
      let icon;
      if (status === 'checking') {
        icon = '\u{f0150}'; // 󰅐 nf-md-loading (spinner)
      } else if (status === 'pass') {
        icon = '\u{f012c}'; // 󰄬 nf-md-check (simple checkmark)
      } else {
        icon = '\u{f0156}'; // 󰅖 nf-md-close (simple cross)
      }

      // Build HTML - compact single-line layout
      let html = `
        <div class="assertion-content">
          <span class="assertion-icon">${icon}</span>
          <span class="assertion-message">${this.escapeHtml(message)}</span>
        </div>
      `;

      if (details) {
        html += `<div class="assertion-details">${this.escapeHtml(details)}</div>`;
      }

      this.element.innerHTML = html;

      // Set status class
      this.element.className = status;

      // Position relative to main overlay
      const pos = this.getPosition(mainCorner || InteractiveOverlay.currentCorner || 'bottom-left');
      this.element.style.top = pos.top || 'auto';
      this.element.style.bottom = pos.bottom || 'auto';
      this.element.style.left = pos.left || 'auto';
      this.element.style.right = pos.right || 'auto';

      // Make visible with slight delay for animation
      requestAnimationFrame(() => {
        this.element.classList.add('visible');
      });
    },

    /**
     * Update position to follow the main overlay's corner
     */
    updatePosition(corner, animated = false) {
      if (!this.element) return;

      const pos = this.getPosition(corner);

      if (animated) {
        // Add transition for smooth following
        this.element.style.transition = 'top 0.25s ease-out, bottom 0.25s ease-out, left 0.25s ease-out, right 0.25s ease-out, opacity 0.2s ease-out';
      }

      this.element.style.top = pos.top || 'auto';
      this.element.style.bottom = pos.bottom || 'auto';
      this.element.style.left = pos.left || 'auto';
      this.element.style.right = pos.right || 'auto';

      if (animated) {
        // Reset transition after animation
        setTimeout(() => {
          if (this.element) {
            this.element.style.transition = 'opacity 0.2s ease-out';
          }
        }, 260);
      }
    },

    /**
     * Hide the assertion overlay
     */
    hide() {
      if (this.element) {
        this.element.classList.remove('visible');
      }
    },

    /**
     * Remove the assertion overlay from DOM
     */
    remove() {
      if (this.element) {
        this.element.remove();
        this.element = null;
      }
    },

    /**
     * Escape HTML to prevent XSS
     */
    escapeHtml(str) {
      if (!str) return '';
      return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/\n/g, '<br>');
    }
  };

  // ==========================================================================
  // Input Lock Module (prevent user interference during replay)
  // ==========================================================================

  const InputLock = {
    enabled: false,
    styleElement: null,
    handlers: {},
    previousFocus: null,

    /**
     * Block an event from propagating (only if it's a real user event)
     * event.isTrusted is true for real user actions, false for synthetic/programmatic events
     */
    blockEvent(event) {
      // Only block real user events, not synthetic events from replay scripts
      if (!event.isTrusted) {
        return true; // Allow synthetic events to proceed
      }

      // Check for Ctrl+C - allow it to stop the replay
      if (event.type === 'keydown' && event.key === 'c' && event.ctrlKey && !event.metaKey && !event.altKey) {
        // Set stop flag - Python will detect this
        window.__INSPEKT_REPLAY_STOP_REQUESTED__ = true;
        // Prevent default copy behavior during replay
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
        return false;
      }

      // When interactive overlay is visible, handle events specially
      if (InteractiveOverlay.element) {
        // Allow keyboard events for overlay navigation (Enter, Space, Escape)
        if (event.type === 'keydown' || event.type === 'keyup' || event.type === 'keypress') {
          // ONLY allow Enter, Space, Escape - these control the overlay
          if (event.key === 'Enter' || event.key === ' ' || event.key === 'Escape') {
            return true; // Let the interactive overlay handle these
          }
          // Block ALL other keys: Tab, arrows, Page Up/Down, Home/End, function keys, etc.
          event.preventDefault();
          event.stopPropagation();
          event.stopImmediatePropagation();
          return false;
        }

        // Allow mouse events on the interactive overlay (for dragging)
        if (event.type.startsWith('mouse')) {
          const overlayEl = InteractiveOverlay.element;
          const target = event.target;

          // Check if the event target is the overlay or inside it
          if (overlayEl && (overlayEl === target || overlayEl.contains(target))) {
            return true; // Allow drag interactions on overlay
          }

          // Also allow mouse events when dragging (targets are on body)
          if (InteractiveOverlay.isDragging) {
            return true;
          }
        }
      }

      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
      return false;
    },


    /**
     * Enable input lock - hide cursor and block all user input
     * Uses event blocking only (no inert) to preserve visual focus outlines and hover states
     */
    enable() {
      if (this.enabled) return;
      this.enabled = true;

      // Store the currently focused element to restore later
      this.previousFocus = document.activeElement;

      // Hide cursor with CSS
      this.styleElement = document.createElement('style');
      this.styleElement.id = 'inspekt-input-lock-styles';
      this.styleElement.textContent = `
        *, *::before, *::after {
          cursor: none !important;
        }
        body {
          pointer-events: none !important;
        }
        #inspekt-overlay {
          pointer-events: none !important;
        }
        /* Make interactive overlay and its contents interactive */
        #inspekt-interactive-overlay,
        #inspekt-interactive-overlay * {
          pointer-events: auto !important;
          cursor: grab !important;
        }
        #inspekt-interactive-overlay.dragging,
        #inspekt-interactive-overlay.dragging * {
          cursor: grabbing !important;
        }
      `;
      document.head.appendChild(this.styleElement);

      // Block keyboard events
      this.handlers.keydown = (e) => this.blockEvent(e);
      this.handlers.keyup = (e) => this.blockEvent(e);
      this.handlers.keypress = (e) => this.blockEvent(e);

      // Block mouse events
      this.handlers.mousedown = (e) => this.blockEvent(e);
      this.handlers.mouseup = (e) => this.blockEvent(e);
      this.handlers.click = (e) => this.blockEvent(e);
      this.handlers.dblclick = (e) => this.blockEvent(e);
      this.handlers.contextmenu = (e) => this.blockEvent(e);
      this.handlers.mousemove = (e) => this.blockEvent(e);

      // Block scroll events
      this.handlers.wheel = (e) => this.blockEvent(e);
      this.handlers.scroll = (e) => this.blockEvent(e);

      // Block touch events
      this.handlers.touchstart = (e) => this.blockEvent(e);
      this.handlers.touchmove = (e) => this.blockEvent(e);
      this.handlers.touchend = (e) => this.blockEvent(e);

      // Add all event listeners with capture to intercept before anything else
      const listenerOptions = { capture: true, passive: false };
      for (const [eventType, handler] of Object.entries(this.handlers)) {
        document.addEventListener(eventType, handler, listenerOptions);
        window.addEventListener(eventType, handler, listenerOptions);
      }
    },

    /**
     * Disable input lock - restore normal cursor and input handling
     */
    disable() {
      if (!this.enabled) return;
      this.enabled = false;

      // Remove cursor hiding styles
      if (this.styleElement) {
        this.styleElement.remove();
        this.styleElement = null;
      }

      // Remove all event listeners
      const options = { capture: true, passive: false };
      for (const [eventType, handler] of Object.entries(this.handlers)) {
        document.removeEventListener(eventType, handler, options);
        window.removeEventListener(eventType, handler, options);
      }
      this.handlers = {};

      // Restore previous focus if it still exists in the DOM
      if (this.previousFocus && document.contains(this.previousFocus)) {
        try {
          this.previousFocus.focus();
        } catch (e) {
          // Element might not be focusable anymore
        }
      }
      this.previousFocus = null;
    }
  };

  // ==========================================================================
  // JavaScript Dialog Overlay (for alert, confirm, prompt during replay)
  // ==========================================================================

  const JsDialogOverlay = {
    backdrop: null,
    overlay: null,
    timeout: null,
    typeInterval: null,

    /**
     * Show a Chrome-style dialog overlay
     * @param {string} dialogType - 'alert', 'confirm', or 'prompt'
     * @param {string} message - The dialog message
     * @param {*} result - The recorded result (true/false for confirm, string/null for prompt)
     * @param {number} duration - How long to show overlay in ms (default 1500)
     * @returns {Promise} Resolves after the overlay animation completes
     */
    show: function(dialogType, message, result, duration = 1500) {
      return new Promise((resolve) => {
        // Remove any existing overlay
        this.hide();

        // Inject shared dialog styles if not already present
        if (!document.getElementById('inspekt-dialog-styles')) {
          const styleEl = document.createElement('style');
          styleEl.id = 'inspekt-dialog-styles';
          styleEl.textContent = `DIALOG_STYLES_PLACEHOLDER`;
          document.head.appendChild(styleEl);
        }

        // Get domain for heading (includes port if present)
        const domain = window.location.host || 'This page';

        // Create backdrop (dims the page)
        this.backdrop = document.createElement('div');
        this.backdrop.className = 'inspekt-dialog-backdrop inspekt-fade-in';

        // Create dialog overlay
        this.overlay = document.createElement('div');
        this.overlay.className = 'inspekt-dialog inspekt-fade-in';

        // Build buttons based on dialog type
        let buttonsHtml = '';
        if (dialogType === 'alert') {
          buttonsHtml = `<button class="inspekt-dialog-btn inspekt-dialog-btn-primary">OK</button>`;
        } else {
          // confirm and prompt have Cancel + OK
          buttonsHtml = `
            <button class="inspekt-dialog-btn inspekt-dialog-btn-secondary">Cancel</button>
            <button class="inspekt-dialog-btn inspekt-dialog-btn-primary">OK</button>
          `;
        }

        // Build input for prompt
        let inputHtml = '';
        if (dialogType === 'prompt') {
          inputHtml = `<input class="inspekt-dialog-input" type="text" readonly />`;
        }

        this.overlay.innerHTML = `
          <div class="inspekt-dialog-heading">${this.escapeHtml(domain)} says</div>
          <div class="inspekt-dialog-message">${this.escapeHtml(message) || ''}</div>
          ${inputHtml}
          <div class="inspekt-dialog-buttons">
            ${buttonsHtml}
          </div>
        `;

        document.body.appendChild(this.backdrop);
        document.body.appendChild(this.overlay);

        // For prompt dialogs, animate typing the result
        if (dialogType === 'prompt' && result !== null && result !== undefined) {
          const input = this.overlay.querySelector('.inspekt-dialog-input');
          if (input) {
            const text = String(result);
            let i = 0;
            // Calculate typing speed based on duration (leave 500ms for viewing)
            const availableTime = Math.max(duration - 500, 500);
            const charDelay = Math.min(50, availableTime / text.length);
            this.typeInterval = setInterval(() => {
              if (i < text.length) {
                input.value = text.substring(0, ++i);
              } else {
                clearInterval(this.typeInterval);
                this.typeInterval = null;
              }
            }, charDelay);
          }
        }

        // Auto-hide after recorded duration with fade-out
        // Ensure minimum 500ms visibility for readability
        const showDuration = Math.max(duration - 100, 500);
        this.timeout = setTimeout(() => {
          if (this.overlay) {
            this.overlay.classList.remove('inspekt-fade-in');
            this.overlay.classList.add('inspekt-fade-out');
            if (this.backdrop) {
              this.backdrop.classList.remove('inspekt-fade-in');
              this.backdrop.classList.add('inspekt-fade-out');
            }
            setTimeout(() => {
              this.hide();
              resolve();
            }, 100);
          } else {
            resolve();
          }
        }, showDuration);
      });
    },

    hide: function() {
      if (this.timeout) {
        clearTimeout(this.timeout);
        this.timeout = null;
      }
      if (this.typeInterval) {
        clearInterval(this.typeInterval);
        this.typeInterval = null;
      }
      if (this.backdrop && this.backdrop.parentNode) {
        this.backdrop.parentNode.removeChild(this.backdrop);
      }
      this.backdrop = null;
      if (this.overlay && this.overlay.parentNode) {
        this.overlay.parentNode.removeChild(this.overlay);
      }
      this.overlay = null;
    },

    escapeHtml: function(str) {
      if (!str) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    }
  };

  // ==========================================================================
  // JavaScript Dialog Interception (for replay)
  // ==========================================================================

  const JsDialogInterceptor = {
    enabled: false,
    originals: null,
    pendingResults: [],  // Queue of expected results from jsdialog steps

    /**
     * Enable interception of alert, confirm, prompt during replay
     * Shows synthetic overlay instead of native dialog
     */
    enable: function() {
      if (this.enabled) return;

      // Store originals
      this.originals = {
        alert: window.alert,
        confirm: window.confirm,
        prompt: window.prompt
      };

      const self = this;

      // Replace alert - show synthetic overlay, return undefined
      window.alert = function(message) {
        console.log('[Inspekt Replay] alert() intercepted:', message);
        // Get pending result (for the message match)
        const pending = self.popPendingResult('alert');
        // Show synthetic overlay (non-blocking)
        JsDialogOverlay.show('alert', message, true);
        return undefined;
      };

      // Replace confirm - show synthetic overlay, return queued result
      window.confirm = function(message) {
        console.log('[Inspekt Replay] confirm() intercepted:', message);
        const pending = self.popPendingResult('confirm');
        const result = pending !== undefined ? pending : true;
        // Show synthetic overlay with the result
        JsDialogOverlay.show('confirm', message, result);
        return result;
      };

      // Replace prompt - show synthetic overlay, return queued result
      window.prompt = function(message, defaultValue) {
        console.log('[Inspekt Replay] prompt() intercepted:', message);
        const pending = self.popPendingResult('prompt');
        const result = pending !== undefined ? pending : (defaultValue || '');
        // Show synthetic overlay with the result
        JsDialogOverlay.show('prompt', message, result);
        return result;
      };

      this.enabled = true;
    },

    /**
     * Disable interception and restore original functions
     */
    disable: function() {
      if (!this.enabled || !this.originals) return;

      window.alert = this.originals.alert;
      window.confirm = this.originals.confirm;
      window.prompt = this.originals.prompt;

      this.originals = null;
      this.pendingResults = [];
      this.enabled = false;
    },

    /**
     * Queue an expected result for the next dialog call
     * @param {string} type - 'alert', 'confirm', or 'prompt'
     * @param {*} result - The expected result
     */
    queueResult: function(type, result) {
      this.pendingResults.push({ type, result });
    },

    /**
     * Pop the next pending result for a dialog type
     * @param {string} type - 'alert', 'confirm', or 'prompt'
     * @returns {*} The pending result or undefined
     */
    popPendingResult: function(type) {
      const index = this.pendingResults.findIndex(p => p.type === type);
      if (index >= 0) {
        const item = this.pendingResults.splice(index, 1)[0];
        return item.result;
      }
      return undefined;
    }
  };

  // ==========================================================================
  // Focus Visible Polyfill
  // ==========================================================================

  /**
   * Polyfill for :focus and :focus-visible during replay.
   *
   * Since CDP key events don't trigger Chrome's internal "keyboard mode" flag,
   * :focus-visible styles never apply. Also, when document.hasFocus() is false
   * (terminal has OS focus), :focus styles don't apply either. This module:
   * 1. Scans stylesheets for :focus and :focus-visible rules
   * 2. Creates cloned rules using [data-inspekt-focus-visible] attribute
   * 3. Applies the attribute to focused elements during Tab replay
   *
   * This ensures replay shows the EXACT same focus styles as real keyboard navigation,
   * including skip links that become visible on :focus.
   */
  const FocusVisible = {
    injected: false,
    rulesCount: 0,

    /**
     * Extract a CSS rule as text, handling nested rules (@media, @supports, etc.)
     */
    extractRuleText(rule, parentPrefix = '') {
      // Handle @media rules
      if (rule instanceof CSSMediaRule) {
        const innerRules = [];
        for (const innerRule of rule.cssRules) {
          const extracted = this.extractFocusVisibleRules(innerRule);
          innerRules.push(...extracted);
        }
        if (innerRules.length > 0) {
          return [`@media ${rule.conditionText} {\n${innerRules.join('\n')}\n}`];
        }
        return [];
      }

      // Handle @supports rules
      if (rule instanceof CSSSupportsRule) {
        const innerRules = [];
        for (const innerRule of rule.cssRules) {
          const extracted = this.extractFocusVisibleRules(innerRule);
          innerRules.push(...extracted);
        }
        if (innerRules.length > 0) {
          return [`@supports ${rule.conditionText} {\n${innerRules.join('\n')}\n}`];
        }
        return [];
      }

      // Handle @layer rules (CSS Cascade Layers)
      if (rule instanceof CSSLayerBlockRule) {
        const innerRules = [];
        for (const innerRule of rule.cssRules) {
          const extracted = this.extractFocusVisibleRules(innerRule);
          innerRules.push(...extracted);
        }
        if (innerRules.length > 0) {
          const layerName = rule.name ? ` ${rule.name}` : '';
          return [`@layer${layerName} {\n${innerRules.join('\n')}\n}`];
        }
        return [];
      }

      // Handle regular style rules
      if (rule instanceof CSSStyleRule) {
        // Check for :focus-visible or :focus (but not :focus-within which is different)
        const selectorText = rule.selectorText;
        if (selectorText && (selectorText.includes(':focus-visible') ||
            (selectorText.includes(':focus') && !selectorText.includes(':focus-within')))) {

          // IMPORTANT: Skip rules that REMOVE focus styling (outline: none, box-shadow: none)
          // These "reset" rules would override our fallback due to higher specificity
          // We only want to clone rules that ADD visible focus indicators
          const cssText = rule.style.cssText.toLowerCase();

          // Check if this rule only removes focus styling (no visible indicator)
          const hasOutline = rule.style.outline || rule.style.outlineWidth || rule.style.outlineStyle;
          const hasBoxShadow = rule.style.boxShadow;
          const hasBorder = rule.style.border || rule.style.borderColor || rule.style.borderWidth;

          // Detect "removal" patterns
          const isOutlineRemoval = hasOutline && (
            cssText.includes('outline: none') ||
            cssText.includes('outline: 0') ||
            cssText.includes('outline-style: none') ||
            cssText.includes('outline-width: 0')
          );
          const isBoxShadowRemoval = hasBoxShadow && (
            cssText.includes('box-shadow: none') ||
            cssText.includes('box-shadow: 0')
          );

          // Check if there are ANY visible focus indicators in the rule
          const hasVisibleOutline = hasOutline && !isOutlineRemoval;
          const hasVisibleBoxShadow = hasBoxShadow && !isBoxShadowRemoval;
          const hasBackground = rule.style.background || rule.style.backgroundColor;
          const hasTextDecoration = rule.style.textDecoration;
          const hasTransform = rule.style.transform;
          const hasFilter = rule.style.filter;

          // Skip rules that only contain focus-hiding properties
          if (!hasVisibleOutline && !hasVisibleBoxShadow && !hasBackground &&
              !hasBorder && !hasTextDecoration && !hasTransform && !hasFilter) {
            // This rule only hides focus indicators - skip it
            return [];
          }

          // Replace :focus-visible first (to avoid partial replacement of :focus)
          // Then replace remaining :focus (but not :focus-within)
          let newSelector = selectorText.replace(/:focus-visible/g, '[data-inspekt-focus-visible]');
          // Replace :focus that's not part of :focus-visible or :focus-within
          // Use negative lookahead to avoid matching :focus-visible or :focus-within
          newSelector = newSelector.replace(/:focus(?!-visible)(?!-within)/g, '[data-inspekt-focus-visible]');
          return [`${newSelector} { ${rule.style.cssText} }`];
        }
      }

      return [];
    },

    /**
     * Extract all :focus and :focus-visible rules from a CSSRule (recursive for nested rules)
     */
    extractFocusVisibleRules(rule) {
      return this.extractRuleText(rule);
    },

    /**
     * Scan a stylesheet and extract all :focus and :focus-visible rules
     */
    scanStylesheet(sheet) {
      const rules = [];
      try {
        const cssRules = sheet.cssRules || sheet.rules;
        if (!cssRules) return rules;

        for (const rule of cssRules) {
          const extracted = this.extractFocusVisibleRules(rule);
          rules.push(...extracted);
        }
      } catch (e) {
        // SecurityError for cross-origin stylesheets - skip silently
        if (e.name !== 'SecurityError') {
          console.debug('[Inspekt FocusVisible] Error scanning stylesheet:', e);
        }
      }
      return rules;
    },

    /**
     * Scan Shadow DOM for stylesheets
     */
    scanShadowRoot(shadowRoot, allRules) {
      // Check adopted stylesheets (modern Shadow DOM pattern)
      if (shadowRoot.adoptedStyleSheets) {
        for (const sheet of shadowRoot.adoptedStyleSheets) {
          const rules = this.scanStylesheet(sheet);
          allRules.push(...rules);
        }
      }

      // Check inline <style> elements in shadow root
      const styleElements = shadowRoot.querySelectorAll('style');
      for (const styleEl of styleElements) {
        if (styleEl.sheet) {
          const rules = this.scanStylesheet(styleEl.sheet);
          allRules.push(...rules);
        }
      }

      // Recurse into nested shadow roots
      const elements = shadowRoot.querySelectorAll('*');
      for (const el of elements) {
        if (el.shadowRoot) {
          this.scanShadowRoot(el.shadowRoot, allRules);
        }
      }
    },

    /**
     * Inject :focus-visible polyfill styles into the document
     * Scans all stylesheets and creates cloned rules with [data-inspekt-focus-visible]
     */
    inject() {
      if (this.injected) {
        return this.rulesCount;
      }

      const allRules = [];

      // Scan document stylesheets
      for (const sheet of document.styleSheets) {
        const rules = this.scanStylesheet(sheet);
        allRules.push(...rules);
      }

      // Scan Shadow DOMs
      const allElements = document.querySelectorAll('*');
      for (const el of allElements) {
        if (el.shadowRoot) {
          this.scanShadowRoot(el.shadowRoot, allRules);
        }
      }

      // Always add a universal fallback rule for elements that don't match specific selectors
      // This ensures focus is visible even when we land on container elements
      allRules.push(`
        [data-inspekt-focus-visible] {
          outline: 2px solid #0066ff !important;
          outline-offset: 2px !important;
        }
      `);

      if (allRules.length === 1) {
        // Only the fallback rule - no custom :focus rules found
        console.log('[Inspekt FocusVisible] No custom :focus rules found, using browser default');
      }

      // Save collected rules for on-demand injection into shadow roots
      this._collectedRules = allRules;

      // Inject the cloned rules
      const style = document.createElement('style');
      style.id = 'inspekt-focus-visible-polyfill';
      style.textContent = `/* Inspekt: Cloned :focus and :focus-visible rules for replay */\n${allRules.join('\n')}`;
      document.head.appendChild(style);

      // Also inject into Shadow DOMs that have :focus rules
      this.injectIntoShadowRoots(allRules);

      this.injected = true;
      this.rulesCount = allRules.length;
      console.log(`[Inspekt FocusVisible] Injected ${allRules.length} focus polyfill rules`);

      return this.rulesCount;
    },

    /**
     * Inject polyfill styles into Shadow DOMs
     */
    injectIntoShadowRoots(rules) {
      const allElements = document.querySelectorAll('*');
      for (const el of allElements) {
        if (el.shadowRoot) {
          this.injectIntoShadowRoot(el.shadowRoot, rules);
        }
      }
    },

    /**
     * Inject polyfill into a single Shadow Root (recursive)
     */
    injectIntoShadowRoot(shadowRoot, rules) {
      // Check if already injected
      if (shadowRoot.getElementById('inspekt-focus-visible-polyfill')) {
        return;
      }

      // Create style element for this shadow root
      const style = document.createElement('style');
      style.id = 'inspekt-focus-visible-polyfill';
      style.textContent = rules.join('\n');
      shadowRoot.appendChild(style);

      // Recurse into nested shadow roots
      const elements = shadowRoot.querySelectorAll('*');
      for (const el of elements) {
        if (el.shadowRoot) {
          this.injectIntoShadowRoot(el.shadowRoot, rules);
        }
      }
    },

    /**
     * Show focus-visible styles on an element
     * Removes attribute from any previous element first
     */
    show(element) {
      // Ensure polyfill is injected
      if (!this.injected) {
        this.inject();
      }

      // Remove from any previous elements (light DOM and shadow DOMs)
      this.hide();

      // Apply to the new element
      if (element && element !== document.body && element !== document.documentElement) {
        element.setAttribute('data-inspekt-focus-visible', '');

        // Check if element is in Shadow DOM and ensure polyfill is injected there
        const rootNode = element.getRootNode();

        if (rootNode !== document && rootNode.host) {
          // Check if polyfill styles exist in this shadow root
          if (!rootNode.getElementById('inspekt-focus-visible-polyfill')) {
            // Inject on-demand (element might be in a shadow root we didn't scan earlier)
            const rules = this.getCollectedRules();
            const polyfillStyle = document.createElement('style');
            polyfillStyle.id = 'inspekt-focus-visible-polyfill';
            polyfillStyle.textContent = rules.join('\n');
            rootNode.appendChild(polyfillStyle);
          }
        }
      }
    },

    /**
     * Get collected rules (for on-demand injection into shadow roots)
     */
    getCollectedRules() {
      // If we have collected rules, return them
      if (this._collectedRules && this._collectedRules.length > 0) {
        return this._collectedRules;
      }
      // Otherwise return the default focus style
      return [`
        [data-inspekt-focus-visible] {
          outline: 2px solid #0066ff !important;
          outline-offset: 2px !important;
        }
      `];
    },

    /**
     * Hide focus-visible styles from all elements
     */
    hide() {
      // Remove from light DOM
      const elements = document.querySelectorAll('[data-inspekt-focus-visible]');
      elements.forEach(el => el.removeAttribute('data-inspekt-focus-visible'));

      // Remove from shadow DOMs
      const allElements = document.querySelectorAll('*');
      for (const el of allElements) {
        if (el.shadowRoot) {
          this.hideInShadowRoot(el.shadowRoot);
        }
      }
    },

    /**
     * Hide focus-visible in a shadow root (recursive)
     */
    hideInShadowRoot(shadowRoot) {
      const elements = shadowRoot.querySelectorAll('[data-inspekt-focus-visible]');
      elements.forEach(el => el.removeAttribute('data-inspekt-focus-visible'));

      // Recurse into nested shadow roots
      const allElements = shadowRoot.querySelectorAll('*');
      for (const el of allElements) {
        if (el.shadowRoot) {
          this.hideInShadowRoot(el.shadowRoot);
        }
      }
    },

    /**
     * Clean up - remove injected styles
     */
    cleanup() {
      // Remove from document
      const style = document.getElementById('inspekt-focus-visible-polyfill');
      if (style) {
        style.remove();
      }

      // Remove from shadow DOMs
      const allElements = document.querySelectorAll('*');
      for (const el of allElements) {
        if (el.shadowRoot) {
          const shadowStyle = el.shadowRoot.getElementById('inspekt-focus-visible-polyfill');
          if (shadowStyle) {
            shadowStyle.remove();
          }
        }
      }

      // Remove attribute from all elements
      this.hide();

      this.injected = false;
      this.rulesCount = 0;
    }
  };

  // ==========================================================================
  // Focus Ring Module (Coordinate-Based Overlay Fallback)
  // ==========================================================================

  /**
   * FocusRing - Coordinate-based focus indicator overlay.
   *
   * This is a FALLBACK for when CSS injection doesn't work (closed Shadow DOM,
   * deeply nested shadows, or sites without focus-visible styles).
   *
   * The CSS attribute injection (FocusVisible) is always tried first because
   * it shows the site's actual focus styles. This overlay is only used when
   * CSS injection fails to produce visible styling.
   */
  const FocusRing = {
    element: null,
    currentTarget: null,

    init() {
      this.element = document.getElementById('inspekt-focus-ring');
    },

    /**
     * Show focus ring around an element using coordinates.
     * Works regardless of Shadow DOM, CSS encapsulation, etc.
     * @param {Element} targetElement - The element to show focus ring around
     */
    show(targetElement) {
      if (!this.element) {
        this.init();
      }
      if (!this.element) {
        return; // Overlay not created yet
      }

      if (!targetElement || targetElement === document.body || targetElement === document.documentElement) {
        this.hide();
        return;
      }

      // Store reference for position updates
      this.currentTarget = targetElement;

      // Get element's bounding rect (works for any element, including Shadow DOM)
      const rect = targetElement.getBoundingClientRect();

      // Add padding around the element
      const padding = 3;

      // Position the focus ring overlay
      this.element.style.left = `${rect.left - padding + window.scrollX}px`;
      this.element.style.top = `${rect.top - padding + window.scrollY}px`;
      this.element.style.width = `${rect.width + padding * 2}px`;
      this.element.style.height = `${rect.height + padding * 2}px`;

      // Show it
      this.element.classList.add('visible');
    },

    /**
     * Hide the focus ring
     */
    hide() {
      if (!this.element) this.init();
      this.element?.classList.remove('visible');
      this.currentTarget = null;
    },

    /**
     * Update position (for scrolling or resize)
     */
    updatePosition() {
      if (this.element?.classList.contains('visible') && this.currentTarget) {
        this.show(this.currentTarget);
      }
    }
  };

  /**
   * Check if an element has visible focus styling.
   * Used to determine if CSS injection worked or if we need the overlay fallback.
   * @param {Element} element - The element to check
   * @returns {boolean} - True if the element has visible focus styling
   */
  function hasFocusStyling(element) {
    if (!element) return false;

    const style = getComputedStyle(element);

    // Check for outline (most common focus indicator)
    if (style.outlineWidth !== '0px' && style.outlineStyle !== 'none') {
      return true;
    }

    // Check for box-shadow (another common focus indicator)
    if (style.boxShadow && style.boxShadow !== 'none') {
      return true;
    }

    // Check for border changes (some sites use border for focus)
    // We can't easily detect "changed" borders, but a solid colored border might indicate focus
    // Skip this check as it's too unreliable

    return false;
  }

  // ==========================================================================
  // Public API
  // ==========================================================================

  window.__INSPEKT_VISUAL__ = {
    // Visual feedback
    moveTo: (x, y, curved) => Visual.moveTo(x, y, curved),
    fadeIn: () => Visual.fadeIn(),
    fadeOut: () => Visual.fadeOut(),
    pulse: (actionType) => Visual.pulse(actionType),
    showError: () => Visual.showError(),
    showTyping: (element) => Visual.showTyping(element),
    hideTyping: () => Visual.hideTyping(),
    showSelectPreview: (element, optionText, duration) => Visual.showSelectPreview(element, optionText, duration),
    hide: () => Visual.hide(),
    cleanup: () => Visual.cleanup(),
    setColor: (actionType) => Visual.setColor(actionType),

    // Audio feedback
    audio: {
      init: () => Audio.init(),
      warmUp: () => Audio.warmUp(),
      // Session sounds
      playStart: () => Audio.playStart(),
      playStop: () => Audio.playStop(),
      playStartPlayback: () => Audio.playStartPlayback(),
      playStopPlayback: () => Audio.playStopPlayback(),
      // Action sounds
      playClick: () => Audio.playClick(),
      playRightClick: () => Audio.playRightClick(),
      playActivate: () => Audio.playActivate(),
      playKeystroke: () => Audio.playKeystroke(),
      playKeypress: () => Audio.playKeypress(),
      playHover: () => Audio.playHover(),
      playScroll: () => Audio.playScroll(),
      playNavigate: () => Audio.playNavigate(),
      playCheck: () => Audio.playCheck(),
      playUncheck: () => Audio.playUncheck(),
      playRadio: () => Audio.playRadio(),
      playSelect: () => Audio.playSelect(),
      playPlugin: () => Audio.playPlugin(),
      playInspekt: () => Audio.playInspekt(),
      playPause: () => Audio.playPause(),
      // Feedback sounds
      playError: () => Audio.playError(),
      playSuccess: () => Audio.playSuccess(),
      // Action dispatcher
      playForAction: (actionType) => Audio.playForAction(actionType),
      // Video audio recording
      startRecordingForVideo: () => Audio.startRecordingForVideo(),
      stopRecordingForVideo: () => Audio.stopRecordingForVideo(),
      isRecordingForVideo: () => Audio.recordingForVideo
    },

    // Input lock (prevent user interference during replay)
    // Uses event blocking only - preserves visual focus outlines and hover states
    inputLock: {
      enable: () => InputLock.enable(),
      disable: () => InputLock.disable(),
      isEnabled: () => InputLock.enabled
    },

    // Stop request (Ctrl+C pressed in browser)
    isStopRequested: () => !!window.__INSPEKT_REPLAY_STOP_REQUESTED__,
    clearStopRequest: () => { window.__INSPEKT_REPLAY_STOP_REQUESTED__ = false; },

    // Target indicator (arrow pointing to next action target)
    targetIndicator: {
      show: (step) => TargetIndicator.show(step),
      hide: () => TargetIndicator.hide()
    },

    // Interactive replay (step-by-step execution)
    interactive: {
      show: (currentStep, previousStep, stepNum, totalSteps) =>
        InteractiveOverlay.show(currentStep, previousStep, stepNum, totalSteps),
      hide: () => InteractiveOverlay.hide(),
      waitForInput: () => InteractiveOverlay.waitForInput()
    },

    // Assertion overlay (shows pass/fail for assertions in interactive mode)
    assertion: {
      showChecking: (expect, mainCorner) => AssertionOverlay.showChecking(expect, mainCorner),
      showResult: (expect, passed, failures, mainCorner) => AssertionOverlay.showResult(expect, passed, failures, mainCorner),
      show: (options, mainCorner) => AssertionOverlay.show(options, mainCorner),
      hide: () => AssertionOverlay.hide(),
      remove: () => AssertionOverlay.remove()
    },

    // JavaScript dialog overlay (for alert, confirm, prompt)
    showJsDialogOverlay: (type, message, result) => JsDialogOverlay.show(type, message, result),
    hideJsDialogOverlay: () => JsDialogOverlay.hide(),

    // JavaScript dialog interception (prevents blocking during replay)
    jsDialogInterceptor: {
      enable: () => JsDialogInterceptor.enable(),
      disable: () => JsDialogInterceptor.disable(),
      queueResult: (type, result) => JsDialogInterceptor.queueResult(type, result),
      isEnabled: () => JsDialogInterceptor.enabled
    },

    // Focus visible polyfill (shows site's :focus-visible styles during Tab replay)
    focusVisible: {
      inject: () => FocusVisible.inject(),
      show: (element) => FocusVisible.show(element),
      hide: () => FocusVisible.hide(),
      cleanup: () => FocusVisible.cleanup(),
      isInjected: () => FocusVisible.injected
    },

    // Focus ring overlay (fallback when CSS injection fails)
    focusRing: {
      show: (element) => FocusRing.show(element),
      hide: () => FocusRing.hide(),
      updatePosition: () => FocusRing.updatePosition()
    },

    // Utility to check if element has visible focus styling
    hasFocusStyling: (element) => hasFocusStyling(element),

    // Frame forcer for video recording
    // CDP screencast only generates frames when the compositor renders.
    // For static pages (like Tab navigation), this forces continuous repaints.
    frameForcer: {
      start: () => FrameForcer.start(),
      stop: () => FrameForcer.stop(),
      isActive: () => FrameForcer.active
    },

    // Configuration
    config: CONFIG
  };

  // ==========================================================================
  // FRAME FORCER (for video recording)
  // ==========================================================================

  /**
   * Forces browser to generate frames at a consistent rate for video recording.
   *
   * CDP Page.startScreencast only sends frames when the browser's compositor
   * renders new content. For mostly-static pages (like Tab navigation where
   * only focus indicators change), this can result in very few frames.
   *
   * This module creates a tiny 1x1 pixel element that continuously animates
   * via requestAnimationFrame, forcing the compositor to render and CDP to
   * generate frames.
   */
  const FrameForcer = {
    active: false,
    element: null,
    animationId: null,
    frameCount: 0,

    start() {
      if (this.active) return;

      // Create a tiny pixel in the corner that animates
      this.element = document.createElement('div');
      this.element.id = 'inspekt-frame-forcer';
      this.element.style.cssText = `
        position: fixed !important;
        bottom: 0 !important;
        right: 0 !important;
        width: 1px !important;
        height: 1px !important;
        background: transparent !important;
        pointer-events: none !important;
        z-index: 2147483647 !important;
        opacity: 0.01 !important;
        transform: translateZ(0) !important;
        will-change: opacity !important;
      `;
      document.body.appendChild(this.element);

      this.active = true;
      this.frameCount = 0;

      // Animate continuously to force repaints
      const animate = () => {
        if (!this.active) return;

        // Tiny opacity fluctuation forces compositor to render
        // The change is imperceptible (0.01 to 0.011) but forces a repaint
        this.frameCount++;
        const flicker = 0.01 + (this.frameCount % 2) * 0.001;
        this.element.style.opacity = flicker;

        this.animationId = requestAnimationFrame(animate);
      };

      this.animationId = requestAnimationFrame(animate);
      console.log('[Inspekt] Frame forcer started - ensuring consistent video frame rate');
    },

    stop() {
      if (!this.active) return;

      this.active = false;

      if (this.animationId) {
        cancelAnimationFrame(this.animationId);
        this.animationId = null;
      }

      if (this.element && this.element.parentNode) {
        this.element.parentNode.removeChild(this.element);
        this.element = null;
      }

      console.log('[Inspekt] Frame forcer stopped after', this.frameCount, 'frames');
    }
  };

  // ==========================================================================
  // Font URL Loading (from extension)
  // ==========================================================================

  /**
   * Request font URLs from the Chrome extension
   * Falls back to system fonts if extension doesn't respond
   */
  async function loadFontUrls() {
    return new Promise((resolve) => {
      const requestId = `font-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

      const handler = (event) => {
        if (event.data?.type === 'INSPEKT_FONT_URLS_RESPONSE' &&
            event.data?.source === 'inspekt-extension' &&
            event.data?.requestId === requestId) {
          window.removeEventListener('message', handler);

          if (event.data.fontUrls) {
            fontUrlRegular = event.data.fontUrls.regular;
            fontUrlBold = event.data.fontUrls.bold;
            console.log('[Inspekt Visual] Loaded font URLs from extension');
          }
          resolve(true);
        }
      };

      window.addEventListener('message', handler);

      // Request font URLs from extension
      window.postMessage({
        type: 'INSPEKT_GET_FONT_URLS',
        source: 'inspekt-page',
        requestId: requestId
      }, '*');

      // Timeout after 300ms - use system fonts if extension doesn't respond
      setTimeout(() => {
        window.removeEventListener('message', handler);
        resolve(false);
      }, 300);
    });
  }

  /**
   * Ensure fonts are actually loaded before rendering
   * Uses the CSS Font Loading API to verify font availability
   */
  async function ensureFontsLoaded() {
    if (fontsLoaded || !fontUrlRegular) {
      return;
    }

    try {
      // Try to load the font explicitly
      await document.fonts.load('400 16px "JetBrains Mono NF"');
      fontsLoaded = true;
      console.log('[Inspekt Visual] Nerd Font loaded successfully');
    } catch (e) {
      console.warn('[Inspekt Visual] Font failed to load, using fallback:', e);
    }
  }

  /**
   * Re-inject styles after font URLs are loaded
   * Called when styles need to be updated (e.g., after fonts load)
   */
  function updateStyles() {
    const existingStyle = document.getElementById('inspekt-visual-styles');
    if (existingStyle) {
      existingStyle.textContent = buildStyles();
    }
  }

  // ==========================================================================
  // CDP Dialog Overlay Bridge
  // ==========================================================================

  /**
   * Listen for CDP dialog interception notifications from the extension
   * When CDP intercepts a dialog (Page.javascriptDialogOpening), the extension
   * sends a message to show a visual overlay for user feedback
   */
  window.addEventListener('message', (event) => {
    if (event.data?.type === 'INSPEKT_SHOW_DIALOG_OVERLAY' &&
        event.data?.source === 'inspekt-extension') {
      const { dialogType, message, result, duration } = event.data;
      console.log('[Inspekt Visual] CDP dialog intercepted, showing overlay:', { dialogType, message, result, duration });
      JsDialogOverlay.show(dialogType, message, result, duration);
    }
  });

  // ==========================================================================
  // Initialization
  // ==========================================================================

  // Load font URLs first, then initialize visual overlay
  (async function init() {
    await loadFontUrls();

    // Initialize visual overlay (creates DOM and injects styles)
    Visual.init();

    // If we got font URLs, ensure they're actually loaded
    if (fontUrlRegular) {
      await ensureFontsLoaded();
      // Re-inject styles now that fonts are loaded
      updateStyles();
    }

    // Pre-load position for interactive overlay
    InteractiveOverlay.loadPosition().catch(() => {});

    // IMPORTANT: Always enable JS-level dialog interception during replay
    // This prevents native alert/confirm/prompt from blocking the replay
    // Works as a fallback even if CDP interception fails (e.g., DevTools open)
    JsDialogInterceptor.enable();
    console.log('[Inspekt Visual] JS dialog interceptor enabled (replay mode)');
  })();

})();
