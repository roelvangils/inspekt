// =============================================
// Editor Panel
// =============================================

/** Check for unsaved editor changes before navigating away */
function confirmEditorClose() {
    if (editorIsDirty && activePanel === 'editor') {
        return confirm('You have unsaved changes. Discard them?');
    }
    return true;
}

/** Switch between Terminal and Editor tabs */
function switchPanel(panel) {
    if (panel === 'terminal' && !confirmEditorClose()) return;
    activePanel = panel;
    const termContainer = document.getElementById('terminalContainer');
    const editorContainer = document.getElementById('editorContainer');
    const termTab = document.getElementById('tabTerminal');
    const editorTab = document.getElementById('tabEditor');
    const termSettings = document.getElementById('terminalSettings');
    const editorToolbar = document.getElementById('editorToolbar');

    if (panel === 'terminal') {
        termContainer.style.display = '';
        editorContainer.style.display = 'none';
        termTab.classList.add('active');
        editorTab.classList.remove('active');
        if (termSettings) termSettings.style.display = 'flex';
        if (editorToolbar) editorToolbar.style.display = 'none';
        if (terminal && fitAddon) {
            requestAnimationFrame(() => { fitAddon.fit(); sendTerminalSize(); });
            terminal.focus();
        }
    } else {
        termContainer.style.display = 'none';
        editorContainer.style.display = 'flex';
        termTab.classList.remove('active');
        editorTab.classList.add('active');
        if (termSettings) termSettings.style.display = 'none';
        if (editorToolbar) editorToolbar.style.display = 'flex';
        if (editorView) editorView.focus();
    }
}

/**
 * Build a CodeMirror 6 theme from an xterm.js terminal theme.
 * Maps the terminal's ANSI color palette to syntax highlighting roles:
 *   red → keywords/errors, green → strings, yellow → types,
 *   blue → functions, cyan → constants, magenta → tags/regex
 * Returns an array of CM6 extensions: [editorTheme, syntaxHighlighting]
 */
function buildEditorTheme(xtermTheme) {
    if (typeof CM === 'undefined') return [];
    if (!xtermTheme) return [CM.oneDark];

    // Strip alpha from rgba backgrounds — CM6 needs opaque backgrounds
    const bg = (xtermTheme.background || '#1a1b26').replace(/rgba?\((\d+),\s*(\d+),\s*(\d+)[\s,]*[\d.]*\)/, 'rgb($1,$2,$3)');
    const fg = xtermTheme.foreground || '#c0caf5';
    const sel = xtermTheme.selectionBackground || 'rgba(102,126,234,0.4)';
    const cursor = xtermTheme.cursor || fg;
    const isDark = isThemeDark(xtermTheme);

    // Slightly lighter/darker variant for gutters and active lines
    const gutterBg = isDark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.03)';
    const activeLine = isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.04)';
    const lineNum = isDark ? 'rgba(255,255,255,0.25)' : 'rgba(0,0,0,0.3)';
    const lineNumActive = isDark ? 'rgba(255,255,255,0.6)' : 'rgba(0,0,0,0.7)';

    const editorTheme = CM.EditorView.theme({
        '&': { color: fg, backgroundColor: bg },
        '.cm-content': { caretColor: cursor },
        '.cm-cursor, .cm-dropCursor': { borderLeftColor: cursor },
        '&.cm-focused > .cm-scroller > .cm-selectionLayer .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection': { backgroundColor: sel },
        '.cm-gutters': { backgroundColor: gutterBg, color: lineNum, borderRight: 'none' },
        '.cm-activeLineGutter': { color: lineNumActive, backgroundColor: 'transparent' },
        '.cm-activeLine': { backgroundColor: activeLine },
        '.cm-foldPlaceholder': { backgroundColor: 'transparent', border: 'none', color: xtermTheme.brightBlack || '#666' },
        '.cm-tooltip': { backgroundColor: bg, color: fg, border: `1px solid ${isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.15)'}` },
        '.cm-tooltip-autocomplete > ul > li[aria-selected]': { backgroundColor: sel },
        '.cm-searchMatch': { backgroundColor: isDark ? 'rgba(255,200,0,0.25)' : 'rgba(255,200,0,0.4)', borderRadius: '2px' },
        '.cm-searchMatch.cm-searchMatch-selected': { backgroundColor: isDark ? 'rgba(255,200,0,0.45)' : 'rgba(255,200,0,0.6)' },
    }, { dark: isDark });

    // Map ANSI colors to syntax roles
    const t = CM.tags;
    const syntaxHL = CM.syntaxHighlighting(CM.HighlightStyle.define([
        { tag: [t.keyword, t.operatorKeyword, t.modifier, t.controlKeyword],
          color: xtermTheme.red || '#f7768e' },
        { tag: [t.string, t.special(t.string), t.character],
          color: xtermTheme.green || '#9ece6a' },
        { tag: [t.typeName, t.className, t.changed, t.annotation, t.self, t.namespace],
          color: xtermTheme.yellow || '#e0af68' },
        { tag: [t.function(t.variableName), t.function(t.propertyName), t.labelName],
          color: xtermTheme.blue || '#7aa2f7' },
        { tag: [t.number, t.bool, t.null, t.atom, t.unit],
          color: xtermTheme.cyan || '#7dcfff' },
        { tag: [t.tagName, t.regexp, t.special(t.brace)],
          color: xtermTheme.magenta || '#bb9af7' },
        { tag: [t.propertyName],
          color: xtermTheme.brightBlue || xtermTheme.blue || '#7aa2f7' },
        { tag: [t.attributeName],
          color: xtermTheme.brightCyan || xtermTheme.cyan || '#7dcfff' },
        { tag: [t.attributeValue],
          color: xtermTheme.green || '#9ece6a' },
        { tag: [t.comment, t.lineComment, t.blockComment],
          color: xtermTheme.brightBlack || '#666', fontStyle: 'italic' },
        { tag: [t.meta, t.documentMeta],
          color: xtermTheme.brightBlack || '#666' },
        { tag: [t.definition(t.variableName)],
          color: fg },
        { tag: t.strong, fontWeight: 'bold' },
        { tag: t.emphasis, fontStyle: 'italic' },
        { tag: t.link, textDecoration: 'underline', color: xtermTheme.blue || '#7aa2f7' },
        { tag: t.heading, fontWeight: 'bold', color: xtermTheme.red || '#f7768e' },
        { tag: t.invalid, color: xtermTheme.brightRed || '#ff0000', textDecoration: 'line-through' },
    ]));

    return [editorTheme, syntaxHL];
}

/** Check if a terminal theme is dark (based on background luminance) */
function isThemeDark(xtermTheme) {
    const bg = xtermTheme.background || '';
    // Parse rgba(r,g,b,a) or rgb(r,g,b) or #hex
    let r = 0, g = 0, b = 0;
    const rgbMatch = bg.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
    if (rgbMatch) {
        r = parseInt(rgbMatch[1]); g = parseInt(rgbMatch[2]); b = parseInt(rgbMatch[3]);
    } else {
        const hex = bg.replace('#', '');
        if (hex.length >= 6) {
            r = parseInt(hex.substr(0, 2), 16);
            g = parseInt(hex.substr(2, 2), 16);
            b = parseInt(hex.substr(4, 2), 16);
        }
    }
    // Relative luminance (simplified)
    return (r * 0.299 + g * 0.587 + b * 0.114) < 128;
}

/** Apply the current terminal theme to the editor (called on theme change) */
function syncEditorTheme() {
    if (!editorView || !editorThemeCompartment) return;
    const themeName = localStorage.getItem('terminalTheme') || 'tokyo-night';
    const xtermTheme = TERMINAL_THEMES[themeName];
    if (!xtermTheme) return;
    const cmTheme = buildEditorTheme(xtermTheme);
    editorView.dispatch({
        effects: editorThemeCompartment.reconfigure(cmTheme)
    });
}

/** Detect CM6 language extension from file extension */
function getLanguageExtension(ext) {
    if (typeof CM === 'undefined') return null;
    const map = {
        'js': CM.javascript, 'mjs': CM.javascript, 'ts': CM.javascript,
        'jsx': CM.javascript, 'tsx': CM.javascript,
        'html': CM.html, 'htm': CM.html, 'svg': CM.html,
        'css': CM.css, 'scss': CM.css,
        'json': CM.json,
        'py': CM.python,
        'md': CM.markdown, 'markdown': CM.markdown,
    };
    return map[ext] ? map[ext]() : null;
}

/** Open a file in the editor panel */
async function openFileInEditor(filePath) {
    // Route image files to the preview modal instead of the editor
    if (isImageFile(filePath)) {
        previewImage(filePath);
        return;
    }

    if (typeof CM === 'undefined') {
        showToast('Editor not available (CodeMirror failed to load)', 'error');
        return;
    }

    // If path is a directory, open file browser at that location
    // (detected by trailing / or by the control server returning 'Not a file')
    // For now, try to open as file — server will return appropriate error

    // Ensure the panel is visible and in split mode
    if (!isTerminalOpen) {
        toggleTerminal();
        // Wait a tick for the panel to render
        await new Promise(r => requestAnimationFrame(r));
    }
    // Force split mode if floating
    if (terminalMode !== 'split') {
        enterSplitMode();
        await new Promise(r => requestAnimationFrame(r));
    }

    // Switch to editor tab
    switchPanel('editor');

    // Fetch file content
    try {
        const resp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/file/read?path=${encodeURIComponent(filePath)}`);
        if (!resp.ok && resp.status >= 500) {
            showToast(`Server error (HTTP ${resp.status})`, 'error');
            return;
        }
        const data = await resp.json();
        if (!data.ok) {
            // If it's a directory, open file browser instead
            if (data.error === 'Not a file' || data.error === 'File not found') {
                toggleFileBrowser(filePath);
                return;
            }
            showToast(`Cannot open: ${data.error}`, 'error');
            return;
        }

        editorCurrentPath = data.path;
        editorIsReadOnly = !data.writable;
        editorIsDirty = false;

        // Update toolbar
        document.getElementById('editorFilePath').textContent = data.path;
        document.getElementById('editorFilePath').title = data.path;
        document.getElementById('editorReadonlyBadge').style.display = editorIsReadOnly ? '' : 'none';
        document.getElementById('editorSaveBtn').disabled = editorIsReadOnly;
        document.getElementById('editorSaveBtn').style.opacity = editorIsReadOnly ? '0.3' : '';
        document.getElementById('editorDirtyDot').style.display = 'none';

        // Detect language from extension
        const ext = (data.filename.split('.').pop() || '').toLowerCase();
        const langExtension = getLanguageExtension(ext);

        // Destroy previous editor
        if (editorView) {
            editorView.destroy();
            editorView = null;
        }
        document.getElementById('editorInstance').innerHTML = '';

        // Build extensions
        const extensions = [
            CM.lineNumbers(),
            CM.highlightActiveLineGutter(),
            CM.highlightSpecialChars(),
            CM.history(),
            CM.foldGutter(),
            CM.drawSelection(),
            CM.dropCursor(),
            CM.indentOnInput(),
            CM.syntaxHighlighting(CM.defaultHighlightStyle, { fallback: true }),
            CM.bracketMatching(),
            CM.closeBrackets(),
            CM.autocompletion(),
            CM.rectangularSelection(),
            CM.crosshairCursor(),
            CM.highlightActiveLine(),
            CM.highlightSelectionMatches(),
            CM.keymap.of([
                ...CM.closeBracketsKeymap,
                ...CM.defaultKeymap,
                ...CM.searchKeymap,
                ...CM.historyKeymap,
                ...CM.foldKeymap,
                ...CM.completionKeymap,
                CM.indentWithTab,
                { key: 'Mod-s', run: () => { saveEditorFile(); return true; } },
            ]),
            CM.EditorView.updateListener.of((update) => {
                if (update.docChanged && !editorIsDirty) {
                    editorIsDirty = true;
                    document.getElementById('editorDirtyDot').style.display = '';
                }
            }),
            editorThemeCompartment.of(buildEditorTheme(TERMINAL_THEMES[localStorage.getItem('terminalTheme') || 'tokyo-night'])),
        ];
        if (langExtension) extensions.push(langExtension);
        if (editorIsReadOnly) extensions.push(CM.EditorState.readOnly.of(true));

        editorView = new CM.EditorView({
            doc: data.content,
            extensions,
            parent: document.getElementById('editorInstance'),
        });

        editorView.focus();
    } catch (err) {
        showToast(`Error opening file: ${err.message}`, 'error');
    }
}

/** Save the current editor file back to the container */
let _editorSaving = false;
async function saveEditorFile() {
    if (!editorView || !editorCurrentPath || editorIsReadOnly || _editorSaving) return;
    _editorSaving = true;
    const content = editorView.state.doc.toString();
    try {
        const resp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/file/write`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: editorCurrentPath, content })
        });
        const data = await resp.json();
        if (data.ok) {
            editorIsDirty = false;
            document.getElementById('editorDirtyDot').style.display = 'none';
            showToast(`Saved ${editorCurrentPath.split('/').pop()}`, 'success');
        } else {
            showToast(`Save failed: ${data.error}`, 'error');
        }
    } catch (err) {
        showToast(`Save failed: ${err.message}`, 'error');
    } finally {
        _editorSaving = false;
    }
}

/** Download the current editor file to the host machine */
function downloadEditorFile() {
    if (!editorCurrentPath) return;
    triggerFileDownload(editorCurrentPath);
}

/** Toggle file browser sidebar */
async function toggleFileBrowser(dirPath) {
    const sidebar = document.getElementById('fileBrowserSidebar');
    if (sidebar.style.display === 'none' || dirPath) {
        sidebar.style.display = '';
        await loadFileTree(dirPath || '/home/inspekt');
    } else {
        sidebar.style.display = 'none';
    }
}

/** Load directory listing into file browser */
async function loadFileTree(dirPath) {
    const tree = document.getElementById('fileBrowserTree');
    try {
        const resp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/file/list?path=${encodeURIComponent(dirPath)}`);
        const data = await resp.json();
        if (!data.ok) {
            tree.innerHTML = `<div class="file-entry" style="color:#f66">${_esc(data.error)}</div>`;
            return;
        }

        // Build breadcrumb for current path
        let breadcrumb = '';
        if (data.path !== '/home/inspekt') {
            const parentPath = _esc(data.path.replace(/\/[^/]+$/, '') || '/home/inspekt');
            breadcrumb = `<div class="file-entry dir" data-path="${parentPath}" onclick="loadFileTree(this.dataset.path)"><span class="file-icon">..</span> <span>← Back</span></div>`;
        }

        const entries = data.entries.map(e => {
            const full = _esc(data.path + '/' + e.name);
            const name = _esc(e.name);
            if (e.type === 'dir') {
                return `<div class="file-entry dir" data-path="${full}" onclick="loadFileTree(this.dataset.path)"><span class="file-icon">📁</span> <span>${name}</span></div>`;
            }
            const sizeStr = e.size > 1024 ? `${(e.size / 1024).toFixed(1)}K` : `${e.size}B`;
            const active = editorCurrentPath === (data.path + '/' + e.name) ? ' active' : '';
            return `<div class="file-entry${active}" data-path="${full}" onclick="openFileInEditor(this.dataset.path)"><span class="file-icon">📄</span> <span>${name}</span> <span style="margin-left:auto;font-size:10px;color:#666">${sizeStr}</span></div>`;
        }).join('');

        tree.innerHTML = breadcrumb + entries;
    } catch (err) {
        tree.innerHTML = `<div class="file-entry" style="color:#f66">Error: ${_esc(err.message)}</div>`;
    }
}

// Intercept Cmd+S globally when editor is active to prevent browser save dialog.
// The actual save is handled by the CM6 keymap — this only does preventDefault().
document.addEventListener('keydown', function(e) {
    if ((e.metaKey || e.ctrlKey) && e.key === 's' && activePanel === 'editor') {
        e.preventDefault();
        // Don't call saveEditorFile() here — CM6's keymap already handles it.
        // This handler only prevents the browser's "Save Page" dialog.
    }
});

