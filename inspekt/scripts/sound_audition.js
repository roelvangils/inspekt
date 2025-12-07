/**
 * Sound Audition Script for Inspekt
 *
 * Plays 5 different sound variations for each action type,
 * allowing the user to choose their preferred sounds.
 *
 * Design principles:
 * - Session sounds (start/stop recording/playback): TRITONES (3 notes)
 * - Action sounds: SINGLETONES or DUOTONES only (1-2 notes max)
 * - Realistic sounds where possible (click = mouse click, type = keyboard clack)
 */

(function() {
  'use strict';

  const ctx = new (window.AudioContext || window.webkitAudioContext)();
  const VOLUME = 0.3;

  // ============================================================================
  // SOUND HELPERS
  // ============================================================================

  // Helper to play a single tone
  function playTone(frequency, duration, type = 'sine', volume = VOLUME, startDelay = 0) {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.frequency.value = frequency;
    osc.type = type;
    const now = ctx.currentTime + startDelay;
    gain.gain.setValueAtTime(volume, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + duration);
    osc.start(now);
    osc.stop(now + duration);
  }

  // Helper for frequency sweep
  function playSweep(startFreq, endFreq, duration, type = 'sine', volume = VOLUME, startDelay = 0) {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = type;
    const now = ctx.currentTime + startDelay;
    osc.frequency.setValueAtTime(startFreq, now);
    osc.frequency.exponentialRampToValueAtTime(endFreq, now + duration);
    gain.gain.setValueAtTime(volume, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + duration);
    osc.start(now);
    osc.stop(now + duration);
  }

  // Helper for filtered noise (for whoosh/wind sounds)
  function playNoise(duration, filterType, filterFreq, filterQ = 1, volume = 0.15, startDelay = 0) {
    const now = ctx.currentTime + startDelay;
    const bufferSize = ctx.sampleRate * duration;
    const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
    const data = buffer.getChannelData(0);

    for (let i = 0; i < bufferSize; i++) {
      data[i] = Math.random() * 2 - 1;
    }

    const source = ctx.createBufferSource();
    const filter = ctx.createBiquadFilter();
    const gain = ctx.createGain();

    source.buffer = buffer;
    filter.type = filterType;
    filter.frequency.value = filterFreq;
    filter.Q.value = filterQ;

    source.connect(filter);
    filter.connect(gain);
    gain.connect(ctx.destination);

    // Envelope for smooth fade in/out
    gain.gain.setValueAtTime(0, now);
    gain.gain.linearRampToValueAtTime(volume, now + duration * 0.15);
    gain.gain.setValueAtTime(volume, now + duration * 0.7);
    gain.gain.linearRampToValueAtTime(0, now + duration);

    source.start(now);
    source.stop(now + duration);
  }

  // Helper for realistic mouse click (two-component: tick + thump)
  function playMouseClick(volume = VOLUME) {
    const now = ctx.currentTime;

    // High-frequency "tick" (button contact)
    const clickOsc = ctx.createOscillator();
    const clickGain = ctx.createGain();
    clickOsc.connect(clickGain);
    clickGain.connect(ctx.destination);
    clickOsc.frequency.setValueAtTime(4000, now);
    clickOsc.frequency.exponentialRampToValueAtTime(1000, now + 0.008);
    clickOsc.type = 'square';
    clickGain.gain.setValueAtTime(volume * 0.35, now);
    clickGain.gain.exponentialRampToValueAtTime(0.001, now + 0.015);
    clickOsc.start(now);
    clickOsc.stop(now + 0.015);

    // Low-frequency "thump" (mechanical body)
    const thumpOsc = ctx.createOscillator();
    const thumpGain = ctx.createGain();
    thumpOsc.connect(thumpGain);
    thumpGain.connect(ctx.destination);
    thumpOsc.frequency.setValueAtTime(150, now);
    thumpOsc.frequency.exponentialRampToValueAtTime(80, now + 0.02);
    thumpOsc.type = 'sine';
    thumpGain.gain.setValueAtTime(volume * 0.45, now);
    thumpGain.gain.exponentialRampToValueAtTime(0.001, now + 0.025);
    thumpOsc.start(now);
    thumpOsc.stop(now + 0.025);
  }

  // Helper for keyboard clack sound
  function playKeyboardClack(volume = VOLUME, pitch = 1.0) {
    const now = ctx.currentTime;

    // Sharp attack (key hitting)
    const attackOsc = ctx.createOscillator();
    const attackGain = ctx.createGain();
    attackOsc.connect(attackGain);
    attackGain.connect(ctx.destination);
    attackOsc.frequency.setValueAtTime(2500 * pitch, now);
    attackOsc.frequency.exponentialRampToValueAtTime(800 * pitch, now + 0.012);
    attackOsc.type = 'square';
    attackGain.gain.setValueAtTime(volume * 0.25, now);
    attackGain.gain.exponentialRampToValueAtTime(0.001, now + 0.02);
    attackOsc.start(now);
    attackOsc.stop(now + 0.02);

    // Body resonance (keycap)
    const bodyOsc = ctx.createOscillator();
    const bodyGain = ctx.createGain();
    bodyOsc.connect(bodyGain);
    bodyGain.connect(ctx.destination);
    bodyOsc.frequency.setValueAtTime(400 * pitch, now + 0.005);
    bodyOsc.frequency.exponentialRampToValueAtTime(200 * pitch, now + 0.04);
    bodyOsc.type = 'triangle';
    bodyGain.gain.setValueAtTime(volume * 0.3, now + 0.005);
    bodyGain.gain.exponentialRampToValueAtTime(0.001, now + 0.05);
    bodyOsc.start(now);
    bodyOsc.stop(now + 0.05);
  }

  // Helper for windy whoosh sound
  function playWhoosh(duration, freqStart, freqEnd, volume = 0.2) {
    const now = ctx.currentTime;
    const bufferSize = ctx.sampleRate * duration;
    const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
    const data = buffer.getChannelData(0);

    // Generate noise with smooth envelope
    for (let i = 0; i < bufferSize; i++) {
      const t = i / bufferSize;
      const envelope = Math.sin(t * Math.PI); // Smooth rise and fall
      data[i] = (Math.random() * 2 - 1) * envelope;
    }

    const noise = ctx.createBufferSource();
    noise.buffer = buffer;

    const filter = ctx.createBiquadFilter();
    filter.type = 'bandpass';
    filter.Q.value = 0.8;
    filter.frequency.setValueAtTime(freqStart, now);
    filter.frequency.exponentialRampToValueAtTime(freqEnd, now + duration);

    const gain = ctx.createGain();

    noise.connect(filter);
    filter.connect(gain);
    gain.connect(ctx.destination);

    gain.gain.setValueAtTime(0, now);
    gain.gain.linearRampToValueAtTime(volume, now + duration * 0.2);
    gain.gain.linearRampToValueAtTime(volume * 0.8, now + duration * 0.8);
    gain.gain.linearRampToValueAtTime(0, now + duration);

    noise.start(now);
    noise.stop(now + duration);
  }

  // ============================================================================
  // SOUND VARIATIONS
  // ============================================================================

  const sounds = {

    // ========================================================================
    // SESSION SOUNDS (TRITONES - 3 notes)
    // ========================================================================

    // START_RECORDING - Beginning a recording session
    start_recording: {
      1: () => { // Classic ascending major (C-E-G)
        playTone(261.63, 0.15, 'sine', 0.25);
        playTone(329.63, 0.15, 'sine', 0.25, 0.12);
        playTone(392.00, 0.2, 'sine', 0.3, 0.24);
      },
      2: () => { // Ascending with acceleration
        playTone(300, 0.12, 'triangle', 0.2);
        playTone(450, 0.1, 'triangle', 0.22, 0.1);
        playTone(600, 0.15, 'sine', 0.25, 0.18);
      },
      3: () => { // Bright startup (higher pitched)
        playTone(523, 0.1, 'sine', 0.2);
        playTone(659, 0.1, 'sine', 0.22, 0.08);
        playTone(784, 0.15, 'sine', 0.25, 0.16);
      },
      4: () => { // Warm analog feel
        playTone(220, 0.18, 'triangle', 0.2);
        playTone(330, 0.15, 'triangle', 0.22, 0.15);
        playTone(440, 0.2, 'sine', 0.25, 0.28);
      },
      5: () => { // Tech startup
        playTone(400, 0.08, 'square', 0.15);
        playTone(500, 0.08, 'square', 0.18, 0.1);
        playTone(700, 0.12, 'sine', 0.22, 0.2);
      }
    },

    // STOP_RECORDING - Ending a recording session
    stop_recording: {
      1: () => { // Descending resolution (G-E-C)
        playTone(392.00, 0.15, 'sine', 0.25);
        playTone(329.63, 0.15, 'sine', 0.22, 0.12);
        playTone(261.63, 0.2, 'sine', 0.2, 0.24);
      },
      2: () => { // Soft wind-down
        playTone(600, 0.12, 'triangle', 0.22);
        playTone(450, 0.12, 'triangle', 0.2, 0.1);
        playTone(300, 0.18, 'sine', 0.18, 0.2);
      },
      3: () => { // Completion signal
        playTone(784, 0.1, 'sine', 0.22);
        playTone(659, 0.1, 'sine', 0.2, 0.08);
        playTone(523, 0.15, 'sine', 0.18, 0.16);
      },
      4: () => { // Tape stop feel
        playTone(500, 0.15, 'triangle', 0.2);
        playTone(350, 0.15, 'triangle', 0.18, 0.12);
        playTone(200, 0.2, 'sine', 0.15, 0.24);
      },
      5: () => { // Gentle farewell
        playTone(440, 0.12, 'sine', 0.2);
        playTone(330, 0.12, 'sine', 0.18, 0.1);
        playTone(262, 0.18, 'sine', 0.15, 0.2);
      }
    },

    // START_PLAYBACK - Beginning replay (distinct from recording start)
    start_playback: {
      1: () => { // Play button - bright ascending (A-C#-E)
        playTone(440, 0.1, 'sine', 0.25);
        playTone(554, 0.1, 'sine', 0.27, 0.08);
        playTone(659, 0.15, 'sine', 0.3, 0.16);
      },
      2: () => { // Forward motion - smooth glide up
        playTone(350, 0.1, 'triangle', 0.22);
        playTone(525, 0.1, 'triangle', 0.24, 0.08);
        playTone(700, 0.12, 'sine', 0.26, 0.16);
      },
      3: () => { // Quick launch - fast and bright
        playTone(500, 0.07, 'sine', 0.22);
        playTone(650, 0.07, 'sine', 0.24, 0.05);
        playTone(850, 0.1, 'sine', 0.26, 0.1);
      },
      4: () => { // Gentle start - softer, warmer
        playTone(300, 0.12, 'sine', 0.2);
        playTone(400, 0.12, 'sine', 0.22, 0.1);
        playTone(500, 0.15, 'sine', 0.24, 0.2);
      },
      5: () => { // Tech engage - digital feel
        playTone(400, 0.08, 'square', 0.15);
        playTone(550, 0.08, 'triangle', 0.2, 0.06);
        playTone(750, 0.12, 'sine', 0.22, 0.12);
      }
    },

    // STOP_PLAYBACK - Ending replay (distinct from recording stop)
    stop_playback: {
      1: () => { // Clean stop - smooth descending (E-C#-A)
        playTone(659, 0.1, 'sine', 0.25);
        playTone(554, 0.1, 'sine', 0.22, 0.08);
        playTone(440, 0.15, 'sine', 0.2, 0.16);
      },
      2: () => { // Gentle pause - soft fade
        playTone(600, 0.12, 'sine', 0.22);
        playTone(450, 0.12, 'sine', 0.2, 0.1);
        playTone(350, 0.15, 'sine', 0.17, 0.2);
      },
      3: () => { // Quick end - fast resolution
        playTone(750, 0.07, 'sine', 0.22);
        playTone(550, 0.07, 'sine', 0.2, 0.05);
        playTone(400, 0.1, 'sine', 0.17, 0.1);
      },
      4: () => { // Completion chime - satisfying end
        playTone(800, 0.1, 'sine', 0.22);
        playTone(600, 0.1, 'sine', 0.2, 0.08);
        playTone(500, 0.15, 'sine', 0.18, 0.16);
      },
      5: () => { // Soft done - gentle wrap-up
        playTone(500, 0.12, 'triangle', 0.2);
        playTone(400, 0.12, 'triangle', 0.18, 0.1);
        playTone(300, 0.15, 'sine', 0.15, 0.2);
      }
    },

    // ========================================================================
    // ACTION SOUNDS (SINGLETONES / DUOTONES only)
    // ========================================================================

    // NAVIGATE - Moving to a new page (whoosh sounds)
    navigate: {
      1: () => { // Whoosh sweep with noise (like existing)
        playSweep(150, 500, 0.25, 'sine', 0.2);
        playWhoosh(0.3, 400, 1500, 0.15);
      },
      2: () => { // Quick portal
        playSweep(200, 600, 0.2, 'sine', 0.22);
      },
      3: () => { // Windy transition
        playWhoosh(0.35, 300, 1200, 0.2);
      },
      4: () => { // Space warp
        playSweep(100, 800, 0.25, 'triangle', 0.18);
      },
      5: () => { // Gentle glide
        playSweep(250, 450, 0.2, 'sine', 0.2);
        playNoise(0.25, 'lowpass', 800, 0.5, 0.1);
      }
    },

    // CLICK - Mouse click (realistic)
    click: {
      1: () => { // Realistic mouse click (existing style)
        playMouseClick(VOLUME);
      },
      2: () => { // Softer click
        playMouseClick(VOLUME * 0.7);
      },
      3: () => { // Sharper click (higher pitched)
        const now = ctx.currentTime;
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.frequency.setValueAtTime(5000, now);
        osc.frequency.exponentialRampToValueAtTime(1500, now + 0.01);
        osc.type = 'square';
        gain.gain.setValueAtTime(VOLUME * 0.3, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.02);
        osc.start(now);
        osc.stop(now + 0.02);
      },
      4: () => { // Mechanical click (lower)
        const now = ctx.currentTime;
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.frequency.setValueAtTime(2000, now);
        osc.frequency.exponentialRampToValueAtTime(400, now + 0.015);
        osc.type = 'square';
        gain.gain.setValueAtTime(VOLUME * 0.4, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.03);
        osc.start(now);
        osc.stop(now + 0.03);
      },
      5: () => { // Crisp tap
        playTone(3000, 0.015, 'square', VOLUME * 0.25);
        playTone(800, 0.02, 'triangle', VOLUME * 0.3, 0.01);
      }
    },

    // RIGHTCLICK - Context menu click
    rightclick: {
      1: () => { // Double tick
        playMouseClick(VOLUME * 0.8);
        playTone(600, 0.03, 'triangle', VOLUME * 0.2, 0.04);
      },
      2: () => { // Click + menu hint
        playMouseClick(VOLUME * 0.7);
        playTone(800, 0.04, 'sine', VOLUME * 0.15, 0.03);
      },
      3: () => { // Deeper click
        const now = ctx.currentTime;
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.frequency.setValueAtTime(2500, now);
        osc.frequency.exponentialRampToValueAtTime(600, now + 0.02);
        osc.type = 'square';
        gain.gain.setValueAtTime(VOLUME * 0.35, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.04);
        osc.start(now);
        osc.stop(now + 0.04);
      },
      4: () => { // Hollow click
        playTone(400, 0.04, 'triangle', VOLUME * 0.35);
        playTone(600, 0.03, 'sine', VOLUME * 0.2, 0.02);
      },
      5: () => { // Menu pop
        playTone(1200, 0.02, 'square', VOLUME * 0.2);
        playTone(500, 0.04, 'triangle', VOLUME * 0.25, 0.015);
      }
    },

    // TYPE - Typing text (keyboard clack)
    type: {
      1: () => { // Realistic keyboard clack (like existing)
        playKeyboardClack(VOLUME);
      },
      2: () => { // Softer key
        playKeyboardClack(VOLUME * 0.7, 0.9);
      },
      3: () => { // Mechanical keyboard (louder)
        playKeyboardClack(VOLUME * 1.1, 1.1);
      },
      4: () => { // Light laptop key
        playKeyboardClack(VOLUME * 0.6, 1.2);
      },
      5: () => { // Tactile switch feel
        const now = ctx.currentTime;
        playTone(1800, 0.015, 'square', VOLUME * 0.2);
        playTone(600, 0.025, 'triangle', VOLUME * 0.25, 0.01);
      }
    },

    // KEYPRESS - Keyboard shortcut (special keys)
    keypress: {
      1: () => { // Enter/Space key (deeper)
        playKeyboardClack(VOLUME * 1.2, 0.7);
      },
      2: () => { // Modifier key feel
        playTone(1200, 0.02, 'square', VOLUME * 0.25);
        playTone(300, 0.05, 'triangle', VOLUME * 0.3, 0.015);
      },
      3: () => { // Tab key
        playKeyboardClack(VOLUME, 0.85);
      },
      4: () => { // Function key
        playTone(2000, 0.015, 'square', VOLUME * 0.2);
        playTone(500, 0.04, 'sine', VOLUME * 0.2, 0.01);
      },
      5: () => { // Spacebar (wide key)
        playTone(800, 0.02, 'square', VOLUME * 0.2);
        playTone(200, 0.06, 'triangle', VOLUME * 0.35, 0.015);
      }
    },

    // ACTIVATE - Enter/Space activation
    activate: {
      1: () => { // Confirmation ding (single)
        playTone(880, 0.15, 'sine', VOLUME * 0.4);
      },
      2: () => { // Soft bell
        playTone(660, 0.12, 'sine', VOLUME * 0.35);
      },
      3: () => { // Bright confirm
        playTone(1047, 0.1, 'sine', VOLUME * 0.35);
      },
      4: () => { // Button press + ding
        playTone(600, 0.08, 'sine', VOLUME * 0.3);
        playTone(900, 0.1, 'sine', VOLUME * 0.25, 0.06);
      },
      5: () => { // Warm confirmation
        playTone(523, 0.12, 'triangle', VOLUME * 0.35);
      }
    },

    // HOVER - Mouse hover (windy whoosh)
    hover: {
      1: () => { // Gentle breeze (like existing playHover)
        const now = ctx.currentTime;
        const duration = 0.25;
        const bufferSize = ctx.sampleRate * duration;
        const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
        const data = buffer.getChannelData(0);

        for (let i = 0; i < bufferSize; i++) {
          const t = i / bufferSize;
          const envelope = Math.sin(t * Math.PI) * Math.sin(t * Math.PI);
          data[i] = (Math.random() * 2 - 1) * envelope;
        }

        const noise = ctx.createBufferSource();
        noise.buffer = buffer;

        const filter = ctx.createBiquadFilter();
        filter.type = 'lowpass';
        filter.frequency.value = 800;
        filter.Q.value = 0.5;
        filter.frequency.setValueAtTime(600, now);
        filter.frequency.linearRampToValueAtTime(1000, now + duration * 0.5);
        filter.frequency.linearRampToValueAtTime(700, now + duration);

        const gain = ctx.createGain();
        noise.connect(filter);
        filter.connect(gain);
        gain.connect(ctx.destination);

        gain.gain.setValueAtTime(0, now);
        gain.gain.linearRampToValueAtTime(VOLUME * 0.2, now + 0.08);
        gain.gain.setValueAtTime(VOLUME * 0.2, now + duration - 0.08);
        gain.gain.linearRampToValueAtTime(0, now + duration);

        noise.start(now);
        noise.stop(now + duration);
      },
      2: () => { // Quick air puff
        playWhoosh(0.18, 500, 1000, 0.15);
      },
      3: () => { // Soft whisper
        playNoise(0.2, 'lowpass', 600, 0.5, 0.12);
      },
      4: () => { // Wind brush
        playWhoosh(0.22, 400, 900, 0.18);
      },
      5: () => { // Light breath
        playNoise(0.15, 'bandpass', 700, 0.7, 0.1);
      }
    },

    // CHECK - Checkbox checked
    check: {
      1: () => { // Ascending tick (duo)
        playTone(500, 0.06, 'sine', VOLUME * 0.35);
        playTone(750, 0.08, 'sine', VOLUME * 0.4, 0.05);
      },
      2: () => { // Bright check
        playTone(600, 0.05, 'triangle', VOLUME * 0.3);
        playTone(900, 0.07, 'sine', VOLUME * 0.35, 0.04);
      },
      3: () => { // Positive blip
        playTone(700, 0.05, 'sine', VOLUME * 0.35);
        playTone(1000, 0.06, 'sine', VOLUME * 0.3, 0.04);
      },
      4: () => { // Click + high (mechanical checkbox)
        playTone(2000, 0.015, 'square', VOLUME * 0.2);
        playTone(880, 0.08, 'sine', VOLUME * 0.35, 0.02);
      },
      5: () => { // Soft confirm
        playTone(550, 0.06, 'sine', VOLUME * 0.3);
        playTone(800, 0.08, 'triangle', VOLUME * 0.3, 0.05);
      }
    },

    // UNCHECK - Checkbox unchecked (reverse of check)
    uncheck: {
      1: () => { // Descending tick (duo) - reverse of check
        playTone(750, 0.06, 'sine', VOLUME * 0.35);
        playTone(500, 0.08, 'sine', VOLUME * 0.3, 0.05);
      },
      2: () => { // Lower uncheck
        playTone(900, 0.05, 'triangle', VOLUME * 0.3);
        playTone(600, 0.07, 'sine', VOLUME * 0.25, 0.04);
      },
      3: () => { // Removal blip
        playTone(1000, 0.05, 'sine', VOLUME * 0.3);
        playTone(700, 0.06, 'sine', VOLUME * 0.25, 0.04);
      },
      4: () => { // Click + low
        playTone(2000, 0.015, 'square', VOLUME * 0.2);
        playTone(440, 0.08, 'sine', VOLUME * 0.3, 0.02);
      },
      5: () => { // Soft removal
        playTone(800, 0.06, 'sine', VOLUME * 0.3);
        playTone(550, 0.08, 'triangle', VOLUME * 0.25, 0.05);
      }
    },

    // RADIO - Radio button selection (distinct from checkbox)
    radio: {
      1: () => { // Focused ping (single clear tone)
        playTone(750, 0.15, 'sine', VOLUME * 0.4);
      },
      2: () => { // Selection lock (ascending duo)
        playTone(500, 0.08, 'sine', VOLUME * 0.35);
        playTone(700, 0.1, 'sine', VOLUME * 0.38, 0.07);
      },
      3: () => { // Click + confirm
        playTone(1200, 0.02, 'square', VOLUME * 0.2);
        playTone(600, 0.12, 'sine', VOLUME * 0.4, 0.02);
      },
      4: () => { // Bubble pop (rounder)
        playTone(400, 0.1, 'sine', VOLUME * 0.4);
        playTone(550, 0.08, 'sine', VOLUME * 0.35, 0.08);
      },
      5: () => { // Soft exclusive tone
        playTone(650, 0.12, 'triangle', VOLUME * 0.38);
      }
    },

    // SELECT - Dropdown selection
    select: {
      1: () => { // Selection blip (duo)
        playTone(600, 0.05, 'sine', VOLUME * 0.35);
        playTone(800, 0.06, 'sine', VOLUME * 0.3, 0.04);
      },
      2: () => { // Menu pick
        playTone(700, 0.06, 'triangle', VOLUME * 0.3);
        playTone(850, 0.05, 'sine', VOLUME * 0.25, 0.05);
      },
      3: () => { // Dropdown tick
        playTone(500, 0.04, 'square', VOLUME * 0.2);
        playTone(750, 0.06, 'sine', VOLUME * 0.3, 0.03);
      },
      4: () => { // Choice made
        playTone(650, 0.07, 'sine', VOLUME * 0.35);
        playTone(900, 0.05, 'sine', VOLUME * 0.25, 0.05);
      },
      5: () => { // List selection
        playTone(550, 0.05, 'triangle', VOLUME * 0.3);
        playTone(700, 0.06, 'sine', VOLUME * 0.3, 0.04);
      }
    },

    // SCROLL - Page scroll (like existing)
    scroll: {
      1: () => { // Soft slide (existing style)
        const now = ctx.currentTime;
        const duration = 0.15;
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.frequency.setValueAtTime(400, now);
        osc.frequency.exponentialRampToValueAtTime(300, now + duration);
        osc.type = 'sine';
        gain.gain.setValueAtTime(0, now);
        gain.gain.linearRampToValueAtTime(VOLUME * 0.2, now + 0.02);
        gain.gain.linearRampToValueAtTime(VOLUME * 0.2, now + duration - 0.03);
        gain.gain.linearRampToValueAtTime(0, now + duration);
        osc.start(now);
        osc.stop(now + duration);
      },
      2: () => { // Quick slide
        playSweep(350, 250, 0.1, 'sine', VOLUME * 0.2);
      },
      3: () => { // Gentle roll
        playSweep(300, 220, 0.12, 'triangle', VOLUME * 0.18);
      },
      4: () => { // Smooth glide
        playSweep(380, 280, 0.15, 'sine', VOLUME * 0.18);
      },
      5: () => { // Subtle movement
        playSweep(320, 260, 0.1, 'sine', VOLUME * 0.15);
      }
    },

    // PLUGIN - Running an inspekt plugin (distinctive "bloop" sounds)
    plugin: {
      1: () => { // Bloop-bloop (identical tones)
        playTone(500, 0.1, 'sine', VOLUME * 0.4);
        playTone(500, 0.1, 'sine', VOLUME * 0.4, 0.15);
      },
      2: () => { // Double pop (higher)
        playTone(700, 0.08, 'sine', VOLUME * 0.35);
        playTone(700, 0.08, 'sine', VOLUME * 0.35, 0.12);
      },
      3: () => { // Plop-plop (rounder, lower)
        playTone(350, 0.12, 'sine', VOLUME * 0.4);
        playTone(350, 0.12, 'sine', VOLUME * 0.4, 0.18);
      },
      4: () => { // Quick double beep
        playTone(600, 0.06, 'triangle', VOLUME * 0.35);
        playTone(600, 0.06, 'triangle', VOLUME * 0.35, 0.1);
      },
      5: () => { // Soft double pulse
        playTone(450, 0.1, 'sine', VOLUME * 0.3);
        playTone(450, 0.1, 'sine', VOLUME * 0.3, 0.14);
      }
    },

    // INSPEKT - Running inspekt command (distinctive "bleep" sounds)
    inspekt: {
      1: () => { // Bleep-bleep (identical high tones)
        playTone(800, 0.08, 'sine', VOLUME * 0.35);
        playTone(800, 0.08, 'sine', VOLUME * 0.35, 0.12);
      },
      2: () => { // Scan ping-ping
        playTone(1000, 0.06, 'sine', VOLUME * 0.3);
        playTone(1000, 0.06, 'sine', VOLUME * 0.3, 0.1);
      },
      3: () => { // Analysis beep-beep (softer)
        playTone(650, 0.1, 'triangle', VOLUME * 0.35);
        playTone(650, 0.1, 'triangle', VOLUME * 0.35, 0.14);
      },
      4: () => { // Double chirp
        playTone(900, 0.05, 'sine', VOLUME * 0.35);
        playTone(900, 0.05, 'sine', VOLUME * 0.35, 0.08);
      },
      5: () => { // Soft double ding
        playTone(550, 0.12, 'sine', VOLUME * 0.3);
        playTone(550, 0.12, 'sine', VOLUME * 0.3, 0.16);
      }
    },

    // FAILURE - Action failed (NEW!)
    failure: {
      1: () => { // Dissonant buzz (minor second)
        playTone(220, 0.2, 'sawtooth', VOLUME * 0.25);
        playTone(233, 0.2, 'sawtooth', VOLUME * 0.25);
      },
      2: () => { // Error tone (descending)
        playTone(400, 0.1, 'square', VOLUME * 0.25);
        playTone(280, 0.15, 'square', VOLUME * 0.2, 0.08);
      },
      3: () => { // Warning buzz
        playTone(150, 0.25, 'sawtooth', VOLUME * 0.3);
      },
      4: () => { // Rejected sound
        playTone(300, 0.08, 'square', VOLUME * 0.25);
        playTone(200, 0.12, 'sawtooth', VOLUME * 0.2, 0.06);
      },
      5: () => { // Flat error
        playTone(250, 0.15, 'triangle', VOLUME * 0.3);
        playTone(240, 0.15, 'triangle', VOLUME * 0.25, 0.02);
      }
    }
  };

  // ============================================================================
  // PUBLIC API
  // ============================================================================

  window.__INSPEKT_SOUND_AUDITION__ = {
    sounds: sounds,

    play: function(action, variation) {
      if (sounds[action] && sounds[action][variation]) {
        if (ctx.state === 'suspended') {
          ctx.resume();
        }
        sounds[action][variation]();
        return { ok: true, action, variation };
      }
      return { ok: false, error: `Unknown: ${action}/${variation}` };
    },

    getActions: function() {
      return Object.keys(sounds);
    },

    resume: function() {
      if (ctx.state === 'suspended') {
        ctx.resume();
      }
    }
  };

  return { loaded: true, actions: Object.keys(sounds) };
})();
