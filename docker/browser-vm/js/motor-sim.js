// =============================================
// Motor Impairment Simulator for Inspekt VM
// =============================================
//
// Simulates motor impairments that affect cursor control. A fake cursor
// overlay replaces the real cursor (hidden via CSS) and adds tremor,
// drift, or other movement artifacts. The VNC stream still receives the
// real mouse coordinates, so the remote browser works normally — but the
// user sees a jittering cursor, experiencing the frustration of imprecise
// motor control when trying to hit small targets.
//
// Architecture:
//   Real cursor → hidden (cursor: none on #vncContainer)
//   Fake cursor → absolutely positioned SVG, follows real mouse + tremor
//   Clicks → land at real position (not jittered), demonstrating the
//            intent-vs-result mismatch that defines motor impairment
//
// Dependencies (globals from control-panel.html):
//   - showToast()    (UI helper)
//   - Simulator HUD  (from vision-sim.js — shared pill/info overlay)

// =============================================
// 1. Motor Profiles
// =============================================

const MOTOR_PROFILES = {
    parkinsons: {
        label: "Parkinson's Tremor",
        group: 'Tremor',
        description: 'Resting tremor with involuntary oscillation — 4-6 Hz',
        tremor: {
            frequency: 5,       // Hz — typical Parkinson's resting tremor
            amplitude: 8,       // px max displacement
            noise: 0.4,         // randomness factor (0 = pure sine, 1 = chaotic)
            drift: 2            // slow baseline drift in px
        }
    },
    'essential-tremor': {
        label: 'Essential Tremor',
        group: 'Tremor',
        description: 'Action tremor — worsens when reaching for targets (6-12 Hz)',
        tremor: {
            frequency: 8,
            amplitude: 5,
            noise: 0.3,
            drift: 1,
            // Note: action tremor (intensifying near targets) is a future enhancement
        }
    },
    'muscle-spasm': {
        label: 'Muscle Spasms',
        group: 'Motor control',
        description: 'Periodic involuntary jerks — sudden large cursor jumps',
        tremor: {
            frequency: 0.3,     // very low base frequency
            amplitude: 3,       // low baseline tremor
            noise: 0.2,
            drift: 1,
            spasms: true,       // enables random large-amplitude jerks
            spasmInterval: 3,   // average seconds between spasms
            spasmAmplitude: 40  // px displacement during a spasm
        }
    },
    'limited-mobility': {
        label: 'Limited Fine Motor',
        group: 'Motor control',
        description: 'Reduced precision — overshoot and correction on small targets',
        tremor: {
            frequency: 2,
            amplitude: 4,
            noise: 0.6,         // high randomness = unpredictable
            drift: 3            // larger drift = imprecise tracking
        }
    }
};


// =============================================
// 1b. Info Content
// =============================================

const MOTOR_INFO = {
    parkinsons: {
        medicalName: "Parkinson's Disease — Resting Tremor",
        category: 'Motor Impairment',
        description: "A progressive neurological disorder that affects movement. The characteristic resting tremor occurs at 4-6 Hz and is most pronounced when the hand is at rest. When reaching for something, the tremor may temporarily decrease (unlike essential tremor), but it makes sustained precision — like holding a cursor over a small button — extremely difficult.",
        prevalence: "Affects approximately 10 million people worldwide. Prevalence increases with age — about 1% of people over 60 and 4% over 80. Men are 1.5x more likely to develop Parkinson's than women.",
        impact: "Small click targets (close buttons, checkboxes, small links) become nearly impossible to hit accurately. Drag-and-drop interactions are extremely frustrating. Hover states that require sustained cursor positioning over an element fail repeatedly. Double-click requirements are a major barrier. Users benefit from large click targets (minimum 44x44px), generous spacing between interactive elements, and alternatives to hover-dependent interactions."
    },
    'essential-tremor': {
        medicalName: 'Essential Tremor — Action/Intention Tremor',
        category: 'Motor Impairment',
        description: "The most common movement disorder. Unlike Parkinson's, essential tremor is an action tremor — it worsens when performing intentional movements like reaching for a target. The tremor frequency is typically 6-12 Hz and intensifies with stress, fatigue, and caffeine. Paradoxically, the tremor may decrease at rest.",
        prevalence: "Affects approximately 1% of the general population and up to 5% of people over 65. Often hereditary — about 50% of cases have a family history. Frequently misdiagnosed as Parkinson's.",
        impact: "The tremor intensifies precisely when trying to click — reaching for a button makes the cursor shake more. Small targets are disproportionately affected because the tremor amplitude exceeds the target size. Form filling is slow and error-prone. Users benefit from large, forgiving click targets, sticky hover states, and autocomplete to reduce typing."
    },
    'muscle-spasm': {
        medicalName: 'Spastic Movement Disorder',
        category: 'Motor Impairment',
        description: "Involuntary muscle contractions that cause sudden, unpredictable movements. Can be caused by cerebral palsy, multiple sclerosis, spinal cord injury, or stroke. Spasms are sudden jerks that displace the hand and cursor far from the intended position, requiring the user to re-acquire the target.",
        prevalence: "Spasticity affects approximately 12 million people worldwide. Common in cerebral palsy (80% of cases), multiple sclerosis (60-80%), and spinal cord injury (65-78%). Severity ranges from mild stiffness to frequent involuntary movements.",
        impact: "Random large cursor jumps cause accidental clicks on wrong elements — potentially triggering navigation, closing dialogs, or submitting forms prematurely. Undo functionality becomes critical. Confirmation dialogs for destructive actions are essential. Users benefit from larger targets, ample spacing between interactive elements (especially between 'save' and 'delete'), and the ability to cancel or undo any action."
    },
    'limited-mobility': {
        medicalName: 'Reduced Fine Motor Control',
        category: 'Motor Impairment',
        description: "A general reduction in hand dexterity and precision, common in many conditions including arthritis, carpal tunnel syndrome, aging, and neurological disorders. The user can move the cursor in the general direction but overshoots targets and requires multiple correction attempts. Fine adjustments are difficult.",
        prevalence: "Affects hundreds of millions of people when all causes are included. Arthritis alone affects over 350 million people worldwide. Age-related decline in fine motor control begins around age 50 and affects virtually everyone by age 75.",
        impact: "Targets smaller than ~20px are consistently overshot. Precision interactions (sliders, drag handles, resize grips) are unreliable. Dense navigation menus where items are close together cause frequent mis-clicks. Text selection is imprecise. Users benefit from generous padding on interactive elements, avoidance of flyout menus that require diagonal mouse movement, and keyboard alternatives for all interactions."
    }
};


// =============================================
// 2. State
// =============================================

let _activeMotorProfile = null;
let _motorPaused = false;
let _motorCursor = null;        // Fake cursor DOM element
let _motorAnimFrame = null;     // RAF for tremor animation
let _motorMouseHandler = null;  // Mousemove handler on container
let _motorRealX = 0;            // Real mouse X (viewport coords)
let _motorRealY = 0;            // Real mouse Y (viewport coords)
let _lastSpasmTime = 0;         // For muscle spasm timing
let _spasmOffsetX = 0;          // Current spasm displacement
let _spasmOffsetY = 0;


// =============================================
// 3. Apply / Remove / Toggle
// =============================================

function setMotorSimulation(profileId) {
    clearMotorSimulation();

    if (!profileId || profileId === 'none') {
        _activeMotorProfile = null;
        return;
    }

    const profile = MOTOR_PROFILES[profileId];
    if (!profile) return;

    _activeMotorProfile = profileId;
    _motorPaused = false;

    const container = document.getElementById('vncContainer');
    if (!container) return;

    _createMotorCursor(container);
    _startMotorTracking(container, profile);

    // Update HUD (reuses the vision simulator HUD)
    _updateMotorHUD();

    showToast(`Motor: ${profile.label}`, 'info');
}

function clearMotorSimulation() {
    _stopMotorTracking();
    _removeMotorCursor();

    _activeMotorProfile = null;
    _motorPaused = false;
    _updateMotorHUD();
}

function toggleMotorSimulation(profileId) {
    if (_activeMotorProfile === profileId) {
        clearMotorSimulation();
        showToast('Motor simulation off', 'info');
    } else {
        setMotorSimulation(profileId);
    }
}


// =============================================
// 4. Fake Cursor
// =============================================

const _CURSOR_SVG = `<svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M3 2L3 17L7.5 12.5L11.5 19L14 17.5L10 11L16 11L3 2Z" fill="white" stroke="black" stroke-width="1.2" stroke-linejoin="round"/>
</svg>`;

function _createMotorCursor(container) {
    _removeMotorCursor();

    const cursor = document.createElement('div');
    cursor.id = 'motorCursor';
    cursor.className = 'motor-cursor';
    cursor.innerHTML = _CURSOR_SVG;
    cursor.setAttribute('aria-hidden', 'true');
    document.body.appendChild(cursor);
    _motorCursor = cursor;

    // Hide real cursor over the VNC container
    container.classList.add('motor-cursor-active');
}

function _removeMotorCursor() {
    if (_motorCursor) {
        _motorCursor.remove();
        _motorCursor = null;
    }
    const container = document.getElementById('vncContainer');
    if (container) container.classList.remove('motor-cursor-active');
}


// =============================================
// 5. Mouse Tracking + Tremor Animation
// =============================================

function _startMotorTracking(container, profile) {
    _stopMotorTracking();
    const tremor = profile.tremor;
    const startTime = performance.now() / 1000;
    _lastSpasmTime = startTime;
    _spasmOffsetX = 0;
    _spasmOffsetY = 0;

    // Track real mouse position (capture phase to get it before noVNC)
    _motorMouseHandler = (e) => {
        _motorRealX = e.clientX;
        _motorRealY = e.clientY;
        // Show cursor when mouse is inside the container
        if (_motorCursor) _motorCursor.style.display = '';
    };
    container.addEventListener('mousemove', _motorMouseHandler, true);

    // Hide fake cursor when mouse leaves the VNC container
    container.addEventListener('mouseleave', () => {
        if (_motorCursor) _motorCursor.style.display = 'none';
    });

    // Animation loop: compute tremor offset and position fake cursor
    function animate(now) {
        if (!_motorCursor) return;
        const t = now / 1000 - startTime;

        // Base tremor: sine waves with slight phase offset between X and Y
        const baseX = Math.sin(t * tremor.frequency * Math.PI * 2) * tremor.amplitude;
        const baseY = Math.cos(t * tremor.frequency * Math.PI * 2 * 1.1 + 0.7) * tremor.amplitude * 0.7;

        // Noise component: Perlin-like randomness
        const noiseX = (Math.sin(t * 13.7) * 0.5 + Math.sin(t * 29.3) * 0.3 + Math.sin(t * 53.1) * 0.2) * tremor.amplitude * tremor.noise;
        const noiseY = (Math.cos(t * 17.1) * 0.5 + Math.cos(t * 31.7) * 0.3 + Math.cos(t * 47.9) * 0.2) * tremor.amplitude * tremor.noise;

        // Slow drift (simulates involuntary hand drift)
        const driftX = Math.sin(t * 0.3) * tremor.drift;
        const driftY = Math.cos(t * 0.25 + 1.0) * tremor.drift;

        // Muscle spasm: occasional large jerks
        if (tremor.spasms) {
            const timeSinceSpasm = t - (_lastSpasmTime - startTime);
            if (timeSinceSpasm > tremor.spasmInterval + (Math.random() - 0.5) * 2) {
                // Trigger a spasm
                const angle = Math.random() * Math.PI * 2;
                _spasmOffsetX = Math.cos(angle) * tremor.spasmAmplitude;
                _spasmOffsetY = Math.sin(angle) * tremor.spasmAmplitude;
                _lastSpasmTime = now / 1000;
            }
            // Decay spasm offset
            _spasmOffsetX *= 0.92;
            _spasmOffsetY *= 0.92;
        }

        // Combine all components
        const totalX = baseX + noiseX + driftX + _spasmOffsetX;
        const totalY = baseY + noiseY + driftY + _spasmOffsetY;

        // Position the fake cursor
        _motorCursor.style.left = (_motorRealX + totalX) + 'px';
        _motorCursor.style.top = (_motorRealY + totalY) + 'px';

        _motorAnimFrame = requestAnimationFrame(animate);
    }
    _motorAnimFrame = requestAnimationFrame(animate);
}

function _stopMotorTracking() {
    if (_motorMouseHandler) {
        const container = document.getElementById('vncContainer');
        if (container) container.removeEventListener('mousemove', _motorMouseHandler, true);
        _motorMouseHandler = null;
    }
    if (_motorAnimFrame) {
        cancelAnimationFrame(_motorAnimFrame);
        _motorAnimFrame = null;
    }
}


// =============================================
// 6. HUD Integration
// =============================================
// Reuses the simulator HUD created by vision-sim.js. The HUD toggle and
// info buttons in vision-sim.js delegate to these functions when a motor
// simulation is active (checked via typeof guards).

function _updateMotorHUD() {
    const hud = document.getElementById('simulatorHud');
    if (!hud) return;

    if (_activeMotorProfile && !_motorPaused) {
        const profile = MOTOR_PROFILES[_activeMotorProfile];
        hud.querySelector('.simulator-hud-label').textContent = profile.label;
        hud.querySelector('.simulator-hud-toggle').classList.add('on');
        hud.classList.remove('paused');
        requestAnimationFrame(() => hud.classList.add('visible'));
    } else if (_activeMotorProfile && _motorPaused) {
        hud.querySelector('.simulator-hud-toggle').classList.remove('on');
        hud.classList.add('paused');
    } else {
        // Only hide if no vision simulation is active either
        const visionActive = typeof _activeVisionProfile !== 'undefined' && _activeVisionProfile;
        if (!visionActive) {
            hud.classList.remove('visible');
        }
    }
}

/**
 * Called by vision-sim.js _onHudToggleClick when a motor sim is active.
 * Pauses/resumes the motor simulation without losing the selection.
 */
function _onMotorHudToggle() {
    if (!_activeMotorProfile) return;

    _motorPaused = !_motorPaused;
    const container = document.getElementById('vncContainer');

    if (_motorPaused) {
        _stopMotorTracking();
        if (_motorCursor) _motorCursor.style.display = 'none';
        container.classList.remove('motor-cursor-active');
    } else {
        const profile = MOTOR_PROFILES[_activeMotorProfile];
        container.classList.add('motor-cursor-active');
        if (_motorCursor) _motorCursor.style.display = '';
        _startMotorTracking(container, profile);
    }

    _updateMotorHUD();
}


// =============================================
// 7. Initialization
// =============================================

function initMotorSimulator() {
    // Nothing to initialize — no SVG filters or DOM elements needed.
    // The fake cursor is created on-demand when a simulation starts.
}
