// =============================================
// Accessibility Media-Query Emulation Popout
// =============================================
//
// URL-bar gear icon that lets users override, per tab or per domain, the
// CSS media queries Chromium reports to web content. Applies at runtime
// via CDP (control-server /emulate/<targetId> endpoints).

let emulationPopoverOpen = false;
let emulationState = null;       // { tab_overrides, domain_overrides, host_prefs, effective, domain, target_id }
let emulationScope = 'tab';      // 'tab' | 'domain' — applied to subsequent actions

// Feature catalog: label + ordered list of pin-to choices per section.
const EMULATION_SECTIONS = [
    {
        feature: 'prefers-color-scheme',
        label: 'Appearance',
        choices: [
            { value: 'light', label: 'Light' },
            { value: 'dark', label: 'Dark' },
            { value: 'no-preference', label: 'No preference' },
        ],
    },
    {
        feature: 'prefers-reduced-motion',
        label: 'Motion',
        choices: [
            { value: 'reduce', label: 'Reduce' },
            { value: 'no-preference', label: 'No preference' },
        ],
    },
    {
        feature: 'prefers-contrast',
        label: 'Contrast',
        choices: [
            { value: 'more', label: 'More' },
            { value: 'less', label: 'Less' },
            { value: 'no-preference', label: 'No preference' },
        ],
    },
    {
        feature: 'prefers-reduced-transparency',
        label: 'Transparency',
        choices: [
            { value: 'reduce', label: 'Reduce' },
            { value: 'no-preference', label: 'No preference' },
        ],
    },
    {
        feature: 'forced-colors',
        label: 'Forced colors',
        choices: [
            { value: 'active', label: 'Active' },
            { value: 'none', label: 'None' },
        ],
    },
    {
        feature: 'inverted-colors',
        label: 'Inverted colors',
        choices: [
            { value: 'active', label: 'Active' },
            { value: 'none', label: 'None' },
        ],
    },
];

// Preset profiles. Each lists the features it sets; any feature NOT listed
// is explicitly cleared (sent as null) so applying a preset replaces the
// full set of overrides at the selected scope.
const EMULATION_PRESETS = [
    {
        id: 'vestibular',
        label: 'Vestibular disorder',
        hint: 'Reduce motion + transparency',
        values: {
            'prefers-reduced-motion': 'reduce',
            'prefers-reduced-transparency': 'reduce',
        },
    },
    {
        id: 'low-vision',
        label: 'Low vision',
        hint: 'More contrast + reduce transparency',
        values: {
            'prefers-contrast': 'more',
            'prefers-reduced-transparency': 'reduce',
        },
    },
    {
        id: 'high-contrast',
        label: 'Windows High Contrast',
        hint: 'Forced colors + more contrast',
        values: {
            'forced-colors': 'active',
            'prefers-contrast': 'more',
        },
    },
    {
        id: 'photophobia',
        label: 'Photophobia',
        hint: 'Dark + reduce transparency',
        values: {
            'prefers-color-scheme': 'dark',
            'prefers-reduced-transparency': 'reduce',
        },
    },
];

function formatSystemValue(v) {
    if (v === 'no-preference' || v === 'none') return 'No preference';
    if (!v) return '—';
    return v.charAt(0).toUpperCase() + v.slice(1);
}

// Small question-mark-in-a-circle placed inside chips whose semantics benefit
// from an explanation. The native `title` tooltip on the wrapping span does
// the work.
const EMULATION_HELP_SVG = '<svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>';

const FOLLOW_TOOLTIP = 'Tracks your host OS setting live — changing your OS setting updates the tab immediately.';
const NO_PREFERENCE_TOOLTIP = 'Pins this tab to report "no preference" regardless of host OS. Use to test how a site behaves when the user has explicitly expressed no preference.';
const NONE_TOOLTIP = 'Pins this feature off regardless of host OS. Use to verify the site behaves correctly when the feature is not active.';

// Compute the merged-override dict (domain then tab) for chip "selected" state.
function mergedOverrides(state) {
    if (!state) return {};
    return { ...state.domain_overrides, ...state.tab_overrides };
}

function toggleEmulationPopout() {
    if (emulationPopoverOpen) {
        closeEmulationPopout();
    } else {
        openEmulationPopout();
    }
}

async function openEmulationPopout() {
    openPopout('emulationPopout', 'urlBarEmulationIcon', closeEmulationPopout);
    emulationPopoverOpen = true;
    await refreshEmulationPopout();
}

function closeEmulationPopout() {
    dismissActivePopout();
    emulationPopoverOpen = false;
}

async function refreshEmulationPopout() {
    const body = document.getElementById('emulationPopoutBody');
    if (!body) return;
    const targetId = activeTabId;
    if (!targetId) {
        body.innerHTML = '<div class="emulation-empty">No active tab.</div>';
        return;
    }
    body.innerHTML = '<div class="emulation-empty">Loading…</div>';
    try {
        const resp = await fetch(
            `http://${VNC_HOST}:${CONTROL_PORT}/emulate/${encodeURIComponent(targetId)}`
        );
        const data = await resp.json();
        if (!data.ok) throw new Error(data.error || 'Failed to load emulation state');
        emulationState = data;
        renderEmulationPopout();
    } catch (e) {
        body.innerHTML = `<div class="emulation-empty">Error: ${e.message}</div>`;
    }
}

function renderEmulationPopout() {
    const body = document.getElementById('emulationPopoutBody');
    if (!body || !emulationState) return;
    const overrides = mergedOverrides(emulationState);
    const { host_prefs, domain } = emulationState;

    const domainAvailable = !!domain;
    const domainLabel = domain || 'internal page';

    const parts = [];

    // --- Scope toggle -------------------------------------------------------
    parts.push(`<div class="emulation-scope" role="radiogroup" aria-label="Apply changes to">
        <span class="emulation-scope-label">Apply to:</span>
        <button class="emulation-scope-btn${emulationScope === 'tab' ? ' selected' : ''}"
                data-scope="tab" role="radio" aria-checked="${emulationScope === 'tab'}">
            This tab
        </button>
        <button class="emulation-scope-btn${emulationScope === 'domain' ? ' selected' : ''}"
                data-scope="domain" role="radio" aria-checked="${emulationScope === 'domain'}"
                ${domainAvailable ? '' : 'disabled title="Current tab has no domain"'}>
            Whole site
        </button>
        <span class="emulation-scope-domain" title="${domainLabel}">${domainLabel}</span>
    </div>`);

    // --- Preset dropdown ----------------------------------------------------
    parts.push(`<div class="emulation-presets">
        <label class="emulation-preset-label" for="emulationPresetSelect">Preset</label>
        <select id="emulationPresetSelect" class="emulation-preset-select">
            <option value="">Choose a profile…</option>
            ${EMULATION_PRESETS.map(p =>
                `<option value="${p.id}" title="${p.hint}">${p.label}</option>`
            ).join('')}
        </select>
    </div>`);

    // --- Feature sections (two-column grid) --------------------------------
    parts.push('<div class="emulation-grid">');
    for (const section of EMULATION_SECTIONS) {
        const overridden = section.feature in overrides;
        const systemValue = host_prefs[section.feature];
        const systemSelected = !overridden;
        const activeValue = overridden ? overrides[section.feature] : null;

        const pinChoiceButtons = section.choices.map(choice => {
            const selected = activeValue === choice.value;
            const classes = ['emulation-chip'];
            if (selected) classes.push('selected');
            // "No preference" / "None" values get an info tooltip so the user
            // understands they're pinning the default rather than unsetting.
            let infoIcon = '';
            if (choice.value === 'no-preference' || choice.value === 'none') {
                const tip = choice.value === 'no-preference'
                    ? NO_PREFERENCE_TOOLTIP
                    : NONE_TOOLTIP;
                infoIcon = `<span class="emulation-chip-info" role="img" aria-label="${tip}" title="${tip}">${EMULATION_HELP_SVG}</span>`;
            }
            return `<button class="${classes.join(' ')}"
                        data-feature="${section.feature}" data-value="${choice.value}">
                    ${choice.label}${infoIcon}
                </button>`;
        }).join('');

        parts.push(`<div class="emulation-section">
            <div class="emulation-section-label">${section.label}</div>
            <div class="emulation-row-system">
                <button class="emulation-chip emulation-chip-system${systemSelected ? ' selected' : ''}"
                        data-feature="${section.feature}" data-value="__system__">
                    Follow system <span class="emulation-chip-hint">(${formatSystemValue(systemValue)})</span>
                    <span class="emulation-chip-info" role="img" aria-label="${FOLLOW_TOOLTIP}" title="${FOLLOW_TOOLTIP}">${EMULATION_HELP_SVG}</span>
                </button>
            </div>
            <div class="emulation-row-pin">
                <span class="emulation-pin-divider" aria-hidden="true">Pin to</span>
                ${pinChoiceButtons}
            </div>
        </div>`);
    }
    parts.push('</div>');

    body.innerHTML = parts.join('');

    // --- Wire up events -----------------------------------------------------
    body.querySelectorAll('.emulation-scope-btn').forEach(btn => {
        btn.addEventListener('click', onScopeChange);
    });
    body.querySelectorAll('.emulation-chip').forEach(btn => {
        btn.addEventListener('click', onEmulationChipClick);
    });
    const presetSelect = body.querySelector('#emulationPresetSelect');
    if (presetSelect) presetSelect.addEventListener('change', onPresetChange);

    // ARIA radiogroup keyboard behaviour for the scope toggle.
    const scopeGroup = body.querySelector('.emulation-scope');
    if (scopeGroup) attachRadiogroupKeys(scopeGroup);
}

function onScopeChange(e) {
    const next = e.currentTarget.dataset.scope;
    if (!next || next === emulationScope) return;
    emulationScope = next;
    renderEmulationPopout();
    // Re-render replaces the scope buttons; restore focus to the equivalent
    // one so keyboard users don't lose their place.
    const restored = document.querySelector(`.emulation-scope-btn[data-scope="${next}"]`);
    if (restored) restored.focus();
}

async function onEmulationChipClick(e) {
    const btn = e.currentTarget;
    const feature = btn.dataset.feature;
    const value = btn.dataset.value;
    const targetId = emulationState && emulationState.target_id;
    if (!targetId) return;

    const delta = {
        scope: emulationScope,
        [feature]: value === '__system__' ? null : value,
    };
    await postEmulationDelta(targetId, delta);
}

async function onPresetChange(e) {
    const presetId = e.target.value;
    if (!presetId) return;
    const preset = EMULATION_PRESETS.find(p => p.id === presetId);
    if (!preset) return;
    const targetId = emulationState && emulationState.target_id;
    if (!targetId) return;

    // Reset the select so the same preset can be re-applied later.
    e.target.value = '';

    // Build a full override payload: set the preset's features, explicitly
    // clear everything else so the scope's overrides match the preset exactly.
    const delta = { scope: emulationScope };
    for (const section of EMULATION_SECTIONS) {
        delta[section.feature] = preset.values[section.feature] ?? null;
    }
    await postEmulationDelta(targetId, delta);
}

async function postEmulationDelta(targetId, delta) {
    try {
        const resp = await fetch(
            `http://${VNC_HOST}:${CONTROL_PORT}/emulate/${encodeURIComponent(targetId)}`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(delta),
            }
        );
        const data = await resp.json();
        if (!data.ok) throw new Error(data.error || 'Failed to update');
        emulationState = { ...emulationState, ...data };
        renderEmulationPopout();
    } catch (err) {
        console.warn('[Emulation] Update failed:', err);
    }
}

async function resetEmulationForActiveTab() {
    const targetId = emulationState && emulationState.target_id;
    if (!targetId) return;
    try {
        const resp = await fetch(
            `http://${VNC_HOST}:${CONTROL_PORT}/emulate/${encodeURIComponent(targetId)}/reset`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ scope: emulationScope }),
            }
        );
        const data = await resp.json();
        if (!data.ok) throw new Error(data.error || 'Failed to reset');
        emulationState = { ...emulationState, ...data };
        renderEmulationPopout();
    } catch (err) {
        console.warn('[Emulation] Reset failed:', err);
    }
}

// Re-fetch state when the user switches tabs while the popout is open.
document.addEventListener('tabactivated', () => {
    if (emulationPopoverOpen) refreshEmulationPopout();
});
