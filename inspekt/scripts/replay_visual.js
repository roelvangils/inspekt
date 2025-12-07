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

  const STYLES = `
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

    /* Interactive replay overlay */
    #inspekt-interactive-overlay {
      position: fixed;
      bottom: 20px;
      left: 20px;
      background: rgba(0, 0, 0, 0.9);
      color: #fff;
      padding: 16px 20px;
      border-radius: 8px;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace;
      font-size: 13px;
      z-index: 2147483647;
      min-width: 320px;
      max-width: 450px;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
      border: 1px solid rgba(255, 255, 255, 0.1);
      animation: inspekt-interactive-in 0.3s ease-out;
    }

    @keyframes inspekt-interactive-in {
      from {
        opacity: 0;
        transform: translateY(20px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }

    #inspekt-interactive-overlay .previous-step {
      color: #888;
      font-size: 12px;
      margin-bottom: 8px;
      padding-bottom: 8px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    }

    #inspekt-interactive-overlay .previous-step .checkmark {
      color: ${CONFIG.colors.success};
      margin-right: 4px;
    }

    #inspekt-interactive-overlay .step-counter {
      color: #888;
      font-size: 11px;
      margin-bottom: 6px;
    }

    #inspekt-interactive-overlay .current-step {
      font-size: 14px;
      font-weight: 500;
      margin-bottom: 12px;
      line-height: 1.4;
    }

    #inspekt-interactive-overlay .current-step .action-icon {
      margin-right: 6px;
    }

    #inspekt-interactive-overlay .current-step .action-name {
      color: ${CONFIG.colors.click};
    }

    #inspekt-interactive-overlay .current-step .target-name {
      color: #fff;
    }

    #inspekt-interactive-overlay .current-step .target-tag {
      color: #888;
      font-size: 12px;
    }

    #inspekt-interactive-overlay .key-hints {
      display: flex;
      gap: 12px;
      font-size: 11px;
      color: #666;
      padding-top: 10px;
      border-top: 1px solid rgba(255, 255, 255, 0.1);
    }

    #inspekt-interactive-overlay .key-hints kbd {
      background: rgba(255, 255, 255, 0.1);
      padding: 2px 6px;
      border-radius: 3px;
      font-family: inherit;
      font-size: 10px;
      margin-right: 4px;
    }

    #inspekt-interactive-overlay.waiting {
      border-color: ${CONFIG.colors.click};
    }
  `;

  // ==========================================================================
  // DOM Setup
  // ==========================================================================

  function createOverlay() {
    // Inject styles
    const styleEl = document.createElement('style');
    styleEl.id = 'inspekt-visual-styles';
    styleEl.textContent = STYLES;
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

    document.body.appendChild(overlay);

    return { overlay, circle, typing };
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

        // If no previous position, just set directly
        if (startX === 0 && startY === 0) {
          this.elements.circle.style.left = `${endX}px`;
          this.elements.circle.style.top = `${endY}px`;
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

        const animate = (currentTime) => {
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

          this.elements.circle.style.left = `${currentX}px`;
          this.elements.circle.style.top = `${currentY}px`;

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
    }
  };

  // ==========================================================================
  // Audio Feedback Module (Web Audio API Synthesizer)
  // ==========================================================================

  const Audio = {
    ctx: null,
    enabled: true,
    initialized: false,

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
        case 'hover':
          this.playHover();
          break;
        case 'plugin':
          this.playPlugin();
          break;
        case 'inspekt':
          this.playInspekt();
          break;
        case 'failure':
        case 'error':
          this.playError();
          break;
        default:
          // No sound for unknown actions
          break;
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

      // Action icons (Nerd Font)
      const icons = {
        navigate: '󰖟',
        click: '󰍽',
        rightclick: '󰍽',
        activate: '󰍽',
        type: '󰌌',
        keypress: '󰌌',
        hover: '󰍽',
        check: '󰄵',
        uncheck: '󰄱',
        select: '󱕅',
        scroll: '󰍽',
        inspekt: '󰍉'
      };

      const icon = icons[action] || '●';

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

      // Default: click, rightclick, activate, hover
      const name = accessibleName || selector.substring(0, 30);
      const tagDisplay = tag ? ` (${tag})` : '';
      return `${icon} ${action} → "${name}"${tagDisplay}`;
    },

    /**
     * Show the interactive overlay
     */
    show(currentStep, previousStep, stepNum, totalSteps) {
      // Remove existing overlay
      this.hide();

      const overlay = document.createElement('div');
      overlay.id = 'inspekt-interactive-overlay';
      overlay.className = 'waiting';

      // Previous step (if any)
      let previousHtml = '';
      if (previousStep) {
        const prevFormatted = this.formatStep(previousStep);
        previousHtml = `
          <div class="previous-step">
            <span class="checkmark">✓</span> ${prevFormatted}
          </div>
        `;
      } else {
        previousHtml = `
          <div class="previous-step">
            <span class="checkmark">▶</span> Interactive replay started
          </div>
        `;
      }

      // Current step
      const currentFormatted = this.formatStep(currentStep);

      overlay.innerHTML = `
        ${previousHtml}
        <div class="step-counter">Step ${stepNum} of ${totalSteps}</div>
        <div class="current-step">${currentFormatted}</div>
        <div class="key-hints">
          <span><kbd>Enter</kbd> Next</span>
          <span><kbd>Space</kbd> Skip</span>
          <span><kbd>Esc</kbd> Stop</span>
        </div>
      `;

      document.body.appendChild(overlay);
      this.element = overlay;
    },

    /**
     * Hide the overlay and clean up
     */
    hide() {
      if (this.element) {
        this.element.remove();
        this.element = null;
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

        this.keyHandler = (event) => {
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
  // Input Lock Module (prevent user interference during replay)
  // ==========================================================================

  const InputLock = {
    enabled: false,
    styleElement: null,
    handlers: {},

    /**
     * Block an event from propagating (only if it's a real user event)
     * event.isTrusted is true for real user actions, false for synthetic/programmatic events
     */
    blockEvent(event) {
      // Only block real user events, not synthetic events from replay scripts
      if (!event.isTrusted) {
        return true; // Allow synthetic events to proceed
      }
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
      return false;
    },

    /**
     * Enable input lock - hide cursor and block all user input
     */
    enable() {
      if (this.enabled) return;
      this.enabled = true;

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
      const options = { capture: true, passive: false };
      for (const [eventType, handler] of Object.entries(this.handlers)) {
        document.addEventListener(eventType, handler, options);
        window.addEventListener(eventType, handler, options);
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
    }
  };

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
      // Feedback sounds
      playError: () => Audio.playError(),
      playSuccess: () => Audio.playSuccess(),
      // Action dispatcher
      playForAction: (actionType) => Audio.playForAction(actionType)
    },

    // Input lock (prevent user interference during replay)
    inputLock: {
      enable: () => InputLock.enable(),
      disable: () => InputLock.disable(),
      isEnabled: () => InputLock.enabled
    },

    // Interactive replay (step-by-step execution)
    interactive: {
      show: (currentStep, previousStep, stepNum, totalSteps) =>
        InteractiveOverlay.show(currentStep, previousStep, stepNum, totalSteps),
      hide: () => InteractiveOverlay.hide(),
      waitForInput: () => InteractiveOverlay.waitForInput()
    },

    // Configuration
    config: CONFIG
  };

  // Initialize overlay on load
  Visual.init();

})();
