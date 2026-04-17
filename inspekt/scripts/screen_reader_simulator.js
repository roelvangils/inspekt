/**
 * Screen Reader Simulator
 *
 * Simulates JAWS, NVDA, and VoiceOver announcements for any web page.
 * Uses the DOM accessibility API (computedRole, computedName) with fallbacks,
 * and can be enhanced with CDP Accessibility.getFullAXTree when available.
 *
 * Injected data (via placeholders):
 *   __SR_ANNOUNCEMENTS__ — role → announcement templates per SR
 *   __SR_VERBOSITY__     — verbosity level config
 *   __SR_CONFIG__        — { screenReader, verbosity, mode, maxElements }
 */

(function () {
  'use strict';

  // ── Injected data ──────────────────────────────────────────────
  const ANNOUNCEMENTS = __SR_ANNOUNCEMENTS__;
  const VERBOSITY = __SR_VERBOSITY__;
  const KNOWN_BUGS = __SR_KNOWN_BUGS__;
  const CONFIG = __SR_CONFIG__;

  const GLOBAL_STATES = ANNOUNCEMENTS._global_states || {};

  // ── Helpers ────────────────────────────────────────────────────

  /**
   * Normalize whitespace: collapse newlines, tabs, and multiple spaces into single spaces.
   */
  function normalizeWhitespace(text) {
    return text.replace(/\s+/g, ' ').trim();
  }

  /**
   * Get the computed accessible role of an element.
   * Uses computedRole (Chrome 90+), falls back to getAttribute('role'),
   * then to implicit role mapping.
   */
  function getRole(el) {
    // Chrome's computedRole API
    if (typeof el.computedRole === 'string' && el.computedRole) {
      return el.computedRole;
    }

    // Explicit ARIA role
    const explicit = el.getAttribute('role');
    if (explicit) return explicit.split(' ')[0]; // first token

    // Implicit role mapping (common HTML elements)
    return getImplicitRole(el);
  }

  /**
   * Map HTML elements to their implicit ARIA roles.
   */
  function getImplicitRole(el) {
    const tag = el.tagName.toLowerCase();
    const type = el.getAttribute('type');

    const implicitRoles = {
      'a':          el.hasAttribute('href') ? 'link' : null,
      'article':    'article',
      'aside':      'complementary',
      'button':     'button',
      'datalist':   'listbox',
      'details':    'group',
      'dialog':     'dialog',
      'fieldset':   'group',
      'figure':     'figure',
      'footer':     isLandmarkContext(el) ? 'contentinfo' : null,
      'form':       el.hasAttribute('aria-label') || el.hasAttribute('aria-labelledby') ? 'form' : null,
      'h1':         'heading', 'h2': 'heading', 'h3': 'heading',
      'h4':         'heading', 'h5': 'heading', 'h6': 'heading',
      'header':     isLandmarkContext(el) ? 'banner' : null,
      'hr':         'separator',
      'img':        'img',
      'input':      getInputRole(el, type),
      'li':         'listitem',
      'main':       'main',
      'math':       'math',
      'menu':       'list',
      'meter':      'meter',
      'nav':        'navigation',
      'ol':         'list',
      'optgroup':   'group',
      'option':     'option',
      'output':     'status',
      'p':          'paragraph',
      'progress':   'progressbar',
      'search':     'search',
      'section':    el.hasAttribute('aria-label') || el.hasAttribute('aria-labelledby') ? 'region' : null,
      'select':     el.hasAttribute('multiple') || (el.size > 1) ? 'listbox' : 'combobox',
      'summary':    'button',
      'table':      'table',
      'tbody':      'rowgroup',
      'td':         'cell',
      'textarea':   'textbox',
      'tfoot':      'rowgroup',
      'th':         'columnheader',
      'thead':      'rowgroup',
      'tr':         'row',
      'ul':         'list',
    };

    return implicitRoles[tag] || null;
  }

  function getInputRole(el, type) {
    const inputRoles = {
      'button': 'button', 'submit': 'button', 'reset': 'button', 'image': 'button',
      'checkbox': 'checkbox',
      'radio': 'radio',
      'range': 'slider',
      'number': 'spinbutton',
      'search': 'searchbox',
      'email': 'textbox', 'password': 'textbox', 'tel': 'textbox', 'url': 'textbox',
      'text': 'textbox', 'date': 'textbox', 'time': 'textbox',
    };
    return inputRoles[type || 'text'] || 'textbox';
  }

  /**
   * Check if element is a direct child of body (landmark context for header/footer).
   */
  function isLandmarkContext(el) {
    let parent = el.parentElement;
    while (parent) {
      const tag = parent.tagName.toLowerCase();
      if (tag === 'article' || tag === 'aside' || tag === 'main' || tag === 'nav' || tag === 'section') {
        return false; // nested inside a sectioning element → not a landmark
      }
      if (tag === 'body') return true;
      parent = parent.parentElement;
    }
    return true;
  }

  /**
   * Get the computed accessible name of an element.
   * Uses computedName (Chrome), falls back to manual computation.
   */
  function getName(el) {
    if (typeof el.computedName === 'string') {
      return el.computedName;
    }

    // aria-labelledby
    const labelledBy = el.getAttribute('aria-labelledby');
    if (labelledBy) {
      const names = labelledBy.split(/\s+/).map(id => {
        const ref = document.getElementById(id);
        return ref ? normalizeWhitespace(ref.textContent || '') : '';
      }).filter(Boolean);
      if (names.length) return names.join(' ');
    }

    // aria-label
    const label = el.getAttribute('aria-label');
    if (label) return label;

    // <label for="…">
    if (el.id) {
      const labelEl = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (labelEl) return normalizeWhitespace(labelEl.textContent || '');
    }

    // Wrapping label
    const parentLabel = el.closest('label');
    if (parentLabel) {
      // Get label text excluding the input itself
      const clone = parentLabel.cloneNode(true);
      const inputs = clone.querySelectorAll('input, select, textarea');
      inputs.forEach(i => i.remove());
      const text = normalizeWhitespace(clone.textContent || '');
      if (text) return text;
    }

    // alt attribute (images)
    if (el.hasAttribute('alt')) return el.getAttribute('alt');

    // title attribute (last resort)
    if (el.hasAttribute('title')) return el.getAttribute('title');

    // Text content (for elements that derive their name from content).
    // Use getVisibleText() instead of textContent to exclude hidden
    // children (e.g., multi-language spans hidden via CSS :lang()).
    const role = getRole(el);
    if (['button', 'link', 'heading', 'tab', 'menuitem', 'option', 'treeitem', 'listitem',
         'paragraph', 'blockquote', 'cell', 'columnheader', 'rowheader', 'caption',
         'legend', 'term', 'definition', 'status', 'alert', 'note'].includes(role)) {
      return normalizeWhitespace(getVisibleText(el));
    }

    return '';
  }

  /**
   * Get the accessible description (aria-describedby / aria-description).
   */
  function getDescription(el) {
    const describedBy = el.getAttribute('aria-describedby');
    if (describedBy) {
      return describedBy.split(/\s+/).map(id => {
        const ref = document.getElementById(id);
        return ref ? normalizeWhitespace(ref.textContent || '') : '';
      }).filter(Boolean).join(' ');
    }
    return el.getAttribute('aria-description') || '';
  }

  /**
   * Get the title attribute as a tooltip, but only when it's NOT already
   * used as the accessible name (to avoid duplication).
   */
  function getTooltip(el) {
    const title = el.getAttribute('title');
    if (!title) return null;
    const name = getName(el);
    if (title === name) return null;  // Already used as name
    return normalizeWhitespace(title);
  }

  /**
   * Get the associated column header for a table cell.
   * Checks the headers attribute first, then falls back to positional <th>.
   */
  function getColumnHeader(el) {
    const role = getRole(el);
    if (!['cell', 'gridcell', 'columnheader'].includes(role)) return null;
    const td = el.closest('td, th, [role="cell"], [role="gridcell"]');
    if (!td) return null;

    // Check headers attribute first
    const headersAttr = td.getAttribute('headers');
    if (headersAttr) {
      return headersAttr.split(/\s+/).map(id => {
        const th = document.getElementById(id);
        return th ? normalizeWhitespace(th.textContent || '') : '';
      }).filter(Boolean).join(', ');
    }

    // Fall back to positional <th> in <thead>
    const table = td.closest('table');
    if (!table) return null;
    const colIndex = td.cellIndex;
    if (colIndex < 0) return null;
    const thead = table.querySelector('thead');
    if (!thead) return null;
    const headerRow = thead.querySelector('tr');
    if (!headerRow || !headerRow.cells[colIndex]) return null;
    return normalizeWhitespace(headerRow.cells[colIndex].textContent || '');
  }

  /**
   * Get the associated row header for a table cell.
   * Looks for th[scope="row"] or first th in the row.
   */
  function getRowHeader(el) {
    const role = getRole(el);
    if (!['cell', 'gridcell'].includes(role)) return null;
    const tr = el.closest('tr');
    if (!tr) return null;
    const rowHeader = tr.querySelector('th[scope="row"]') || tr.querySelector('th:first-child');
    if (!rowHeader || rowHeader === el) return null;
    return normalizeWhitespace(rowHeader.textContent || '');
  }

  /**
   * Get the heading level for heading elements.
   */
  function getHeadingLevel(el) {
    const ariaLevel = el.getAttribute('aria-level');
    if (ariaLevel) return parseInt(ariaLevel, 10);

    const tag = el.tagName.toLowerCase();
    const match = tag.match(/^h([1-6])$/);
    return match ? parseInt(match[1], 10) : 2;
  }

  /**
   * Detect the language of an element by walking up the DOM.
   */
  function detectLanguage(el) {
    let current = el;
    while (current && current !== document.documentElement) {
      const lang = current.getAttribute('lang') || current.getAttribute('xml:lang');
      if (lang) return lang.split('-')[0].toLowerCase(); // 'en-US' → 'en'
      current = current.parentElement;
    }
    // Fall back to document language
    const htmlLang = document.documentElement.getAttribute('lang') || document.documentElement.getAttribute('xml:lang');
    return htmlLang ? htmlLang.split('-')[0].toLowerCase() : 'en';
  }

  /**
   * Check if an element is hidden from the accessibility tree.
   */
  function isHidden(el) {
    if (el.getAttribute('aria-hidden') === 'true') return true;
    if (el.hidden) return true;

    const style = window.getComputedStyle(el);
    if (style.display === 'none') return true;
    if (style.visibility === 'hidden') return true;

    // Skip empty alt images
    if (el.tagName === 'IMG' && el.getAttribute('alt') === '') return true;

    return false;
  }

  /**
   * Get visible text content from an element, excluding hidden children.
   * Respects display:none, visibility:hidden, and aria-hidden.
   * Mirrors the W3C AccName algorithm's visibility filtering.
   *
   * Use this instead of el.textContent when the element may contain
   * hidden children (e.g., multi-language spans hidden via CSS :lang()).
   */
  function getVisibleText(el) {
    let text = '';
    for (const node of el.childNodes) {
      if (node.nodeType === Node.TEXT_NODE) {
        text += node.textContent;
      } else if (node.nodeType === Node.ELEMENT_NODE) {
        if (!isHidden(node)) {
          text += getVisibleText(node);
        }
      }
    }
    return text;
  }

  /**
   * Check if an element should be a leaf node in the reading order
   * (i.e., announced as a whole, not walked into).
   */
  function isLeafNode(el, role) {
    const leafRoles = new Set([
      'button', 'link', 'checkbox', 'radio', 'switch', 'textbox',
      'searchbox', 'combobox', 'slider', 'spinbutton', 'progressbar',
      'meter', 'scrollbar', 'separator', 'img', 'menuitem',
      'menuitemcheckbox', 'menuitemradio', 'option', 'tab',
    ]);
    return leafRoles.has(role);
  }

  /**
   * Find known bugs that apply to an element for the given screen readers.
   * Matches on role, property (aria-* attributes), and screen reader.
   * @param {Element} el — DOM element
   * @param {string} role — computed ARIA role
   * @param {string[]} screenReaders — which SRs to check
   * @returns {string[]} — array of bug IDs
   */
  function findKnownBugs(el, role, screenReaders) {
    if (!KNOWN_BUGS || !KNOWN_BUGS.bugs) return [];

    const bugs = [];
    for (const bug of KNOWN_BUGS.bugs) {
      // Check if this bug applies to any of the active screen readers
      if (!screenReaders.includes(bug.screen_reader)) continue;

      // Match by role
      if (bug.role && bug.role === role) {
        bugs.push(bug.id);
        continue;
      }

      // Match by property (check if element has the ARIA attribute)
      if (bug.property && el.hasAttribute(bug.property)) {
        bugs.push(bug.id);
      }
    }
    return bugs;
  }

  // ── AnnouncementEngine ─────────────────────────────────────────

  class AnnouncementEngine {
    constructor(screenReader, verbosityLevel) {
      this.sr = screenReader; // 'jaws' | 'nvda' | 'voiceover'
      this.verbosity = VERBOSITY[verbosityLevel] || VERBOSITY.high;
      this.previousLanguage = null;
    }

    /**
     * Generate the announcement text for an element.
     * @param {Element} el — DOM element
     * @returns {{ text: string, role: string, name: string, lang: string, langChanged: boolean }}
     */
    announce(el) {
      const role = getRole(el);
      const name = getName(el);
      const lang = detectLanguage(el);
      const langChanged = this.previousLanguage !== null && this.previousLanguage !== lang;
      this.previousLanguage = lang;

      if (!role) {
        // No role — just read visible text content
        const text = normalizeWhitespace(getVisibleText(el));
        return { text, role: 'generic', name: text, lang, langChanged };
      }

      const template = this._getTemplate(role, el);
      const text = this._interpolate(template, el, role, name);

      // Append states
      const stateText = this._getStateText(el, role);
      const descText = this._getDescriptionText(el);
      const globalStateText = this._getGlobalStateText(el);

      let fullText = [text, stateText, globalStateText, descText]
        .filter(Boolean)
        .join(', ');

      // Language change indicator
      if (langChanged && this.verbosity.announce_language_change) {
        fullText = `[${lang}] ${fullText}`;
      }

      return { text: fullText, role, name, lang, langChanged };
    }

    /**
     * Get the announcement template for a role and screen reader.
     */
    _getTemplate(role, el) {
      const roleData = ANNOUNCEMENTS[role];
      if (!roleData || !roleData[this.sr]) {
        // Fallback: announce name with role
        return '{name}';
      }
      return roleData[this.sr].enter || '{name}';
    }

    /**
     * Interpolate template variables.
     */
    _interpolate(template, el, role, name) {
      const value = el.value || el.getAttribute('aria-valuenow') || el.getAttribute('aria-valuetext') || '';
      const level = getHeadingLevel(el);

      // Position in set
      const position = el.getAttribute('aria-posinset') || '';
      const setsize = el.getAttribute('aria-setsize') || '';

      // List item count (for lists)
      let listItemCount = '';
      if (role === 'list' && this.verbosity.announce_list_item_count) {
        const items = el.querySelectorAll(':scope > li, :scope > [role="listitem"]');
        listItemCount = String(items.length);
      }

      // Table dimensions
      let rowcount = el.getAttribute('aria-rowcount') || '';
      let colcount = el.getAttribute('aria-colcount') || '';
      if (!rowcount && role === 'table') {
        rowcount = String(el.querySelectorAll('tr').length);
      }
      if (!colcount && role === 'table') {
        const firstRow = el.querySelector('tr');
        colcount = firstRow ? String(firstRow.cells.length) : '0';
      }

      // Row/column index
      const rowindex = el.getAttribute('aria-rowindex') || '';
      const colindex = el.getAttribute('aria-colindex') || '';

      // Handle state placeholders like {state:checked}
      let result = template;
      const statePattern = /\{state:(\w+)\}/g;
      result = result.replace(statePattern, (match, stateName) => {
        return this._resolveState(role, stateName, el);
      });

      return result
        .replace(/\{name\}/g, name)
        .replace(/\{value\}/g, value)
        .replace(/\{level\}/g, String(level))
        .replace(/\{position\}/g, position)
        .replace(/\{setsize\}/g, listItemCount || setsize)
        .replace(/\{rowcount\}/g, rowcount)
        .replace(/\{colcount\}/g, colcount)
        .replace(/\{rowindex\}/g, rowindex)
        .replace(/\{colindex\}/g, colindex)
        .replace(/\{min\}/g, el.getAttribute('aria-valuemin') || el.min || '')
        .replace(/\{max\}/g, el.getAttribute('aria-valuemax') || el.max || '')
        .replace(/,\s*,/g, ',')   // Clean up double commas
        .replace(/,\s*$/g, '')    // Remove trailing comma
        .replace(/^\s*,\s*/g, '') // Remove leading comma
        .trim();
    }

    /**
     * Resolve a state value from the role's _states definition.
     */
    _resolveState(role, stateName, el) {
      const roleData = ANNOUNCEMENTS[role];
      if (!roleData?._states?.[stateName]) return '';

      const stateMap = roleData._states[stateName];
      let stateValue;

      switch (stateName) {
        case 'checked':
          stateValue = el.getAttribute('aria-checked') ||
            (el.checked === true ? 'true' : el.checked === false ? 'false' : null) ||
            (el.indeterminate ? 'mixed' : null) || 'false';
          break;
        case 'expanded':
          stateValue = el.getAttribute('aria-expanded') || 'false';
          break;
        case 'selected':
          stateValue = el.getAttribute('aria-selected') || 'false';
          break;
        case 'pressed':
          stateValue = el.getAttribute('aria-pressed') || 'false';
          break;
        default:
          stateValue = el.getAttribute(`aria-${stateName}`) || 'false';
      }

      const srValues = stateMap[stateValue];
      if (!srValues) return '';
      return srValues[this.sr] || '';
    }

    /**
     * Get additional state text (required, invalid, readonly, disabled).
     */
    _getStateText(el, role) {
      const parts = [];

      if (this.verbosity.announce_required_state) {
        if (el.hasAttribute('aria-required') && el.getAttribute('aria-required') === 'true' ||
          el.required) {
          const roleData = ANNOUNCEMENTS[role];
          const stateText = roleData?._states?.required?.true?.[this.sr];
          if (stateText) parts.push(stateText);
          else parts.push(this.sr === 'voiceover' ? 'required' : 'required');
        }
      }

      if (this.verbosity.announce_invalid_state) {
        const invalid = el.getAttribute('aria-invalid');
        if (invalid === 'true' || invalid === 'grammar' || invalid === 'spelling') {
          const roleData = ANNOUNCEMENTS[role];
          const stateText = roleData?._states?.invalid?.true?.[this.sr];
          parts.push(stateText || 'invalid entry');
        }
      }

      if (this.verbosity.announce_readonly_state) {
        if (el.hasAttribute('aria-readonly') && el.getAttribute('aria-readonly') === 'true' ||
          el.readOnly) {
          parts.push(this.sr === 'voiceover' ? 'read only' : 'read-only');
        }
      }

      return parts.join(', ');
    }

    /**
     * Get global ARIA state text (disabled, current, grabbed, haspopup).
     */
    _getGlobalStateText(el) {
      if (!this.verbosity.announce_disabled_state && !this.verbosity.announce_aria_current) {
        return '';
      }

      const parts = [];

      // aria-disabled
      if (this.verbosity.announce_disabled_state) {
        if (el.getAttribute('aria-disabled') === 'true' || el.disabled) {
          const text = GLOBAL_STATES['aria-disabled']?.true?.[this.sr];
          if (text) parts.push(text);
        }
      }

      // aria-current
      if (this.verbosity.announce_aria_current) {
        const current = el.getAttribute('aria-current');
        if (current && current !== 'false') {
          const text = GLOBAL_STATES['aria-current']?.[current]?.[this.sr];
          if (text) parts.push(text);
        }
      }

      // aria-haspopup
      const hasPopup = el.getAttribute('aria-haspopup');
      if (hasPopup && hasPopup !== 'false') {
        const text = GLOBAL_STATES['aria-haspopup']?.[hasPopup]?.[this.sr];
        if (text) parts.push(text);
      }

      return parts.join(', ');
    }

    /**
     * Get description text if verbosity allows.
     */
    _getDescriptionText(el) {
      if (!this.verbosity.announce_description) return '';
      const desc = getDescription(el);
      return desc || '';
    }

    /**
     * Get the secondary announcement (read after a pause by real SRs).
     * This is the aria-describedby/aria-description/title text.
     */
    getSecondaryAnnouncement(el) {
      const desc = getDescription(el);
      const tooltip = getTooltip(el);
      const text = desc || tooltip || '';
      if (!text) return null;

      switch (this.sr) {
        case 'jaws':
          return text;  // JAWS reads description after pause
        case 'nvda':
          return text;  // NVDA reads description after pause
        case 'voiceover':
          return `Help text: ${text}`;  // VoiceOver prefixes with "Help text"
        default:
          return text;
      }
    }
  }

  // ── VirtualCursor ──────────────────────────────────────────────

  class VirtualCursor {
    constructor(announcementEngine) {
      this.engine = announcementEngine;
      this.nodes = [];       // Linearized reading order
      this.position = -1;    // Current index
      this.mode = 'reading'; // 'reading' | 'interaction'
    }

    /**
     * Initialize by linearizing the page into reading order.
     */
    init(rootElement) {
      this.nodes = [];
      this.position = -1;
      this._linearize(rootElement || document.body, 0);
      this._nonExitCount = this.nodes.filter(n => !n.isExit).length;
      return this.nodes.length;
    }

    /**
     * Recursively linearize the DOM into reading order.
     */
    _linearize(el, depth) {
      // Skip non-element nodes
      if (el.nodeType !== Node.ELEMENT_NODE) return;

      // Skip hidden elements
      if (isHidden(el)) return;

      // Skip script, style, noscript, template
      const tag = el.tagName.toLowerCase();
      if (['script', 'style', 'noscript', 'template', 'link', 'meta'].includes(tag)) return;

      const role = getRole(el);

      // Skip presentation/none roles (but process children)
      if (role === 'presentation' || role === 'none') {
        for (const child of el.children) {
          this._linearize(child, depth);
        }
        return;
      }

      // Determine if this element should be announced
      const name = getName(el);
      const shouldAnnounce = this._shouldAnnounce(el, role, name, tag);

      if (shouldAnnounce) {
        this.nodes.push({
          element: el,
          role: role,
          name: name,
          depth: depth,
          isLeaf: isLeafNode(el, role)
        });
      }

      // If it's a leaf node, don't recurse into children
      if (isLeafNode(el, role)) return;

      // Recurse into children
      for (const child of el.children) {
        this._linearize(child, depth + 1);
      }

      // Announce exit for container roles (landmarks, lists, tables)
      if (shouldAnnounce && this._hasExitAnnouncement(role)) {
        this.nodes.push({
          element: el,
          role: role,
          name: name,
          depth: depth,
          isExit: true
        });
      }
    }

    /**
     * Check if an element should be included in the reading order.
     */
    _shouldAnnounce(el, role, name, tag) {
      // Always announce elements with explicit roles
      if (el.hasAttribute('role')) return true;

      // Always announce landmark roles
      const landmarks = new Set([
        'banner', 'complementary', 'contentinfo', 'form', 'main',
        'navigation', 'region', 'search',
      ]);
      if (landmarks.has(role)) return true;

      // Always announce interactive elements
      const interactive = new Set([
        'button', 'link', 'checkbox', 'radio', 'textbox', 'searchbox',
        'combobox', 'slider', 'spinbutton', 'switch', 'tab', 'menuitem',
        'menuitemcheckbox', 'menuitemradio', 'option', 'treeitem',
      ]);
      if (interactive.has(role)) return true;

      // Always announce structural roles
      const structural = new Set([
        'heading', 'img', 'table', 'list', 'listitem', 'row', 'cell',
        'columnheader', 'rowheader', 'separator', 'group', 'figure',
        'dialog', 'alertdialog', 'alert', 'status', 'progressbar',
        'meter', 'toolbar', 'tablist', 'tabpanel', 'tree', 'treegrid',
        'grid', 'gridcell', 'menu', 'menubar', 'feed', 'article',
      ]);
      if (structural.has(role)) return true;

      // Announce text-containing block elements
      const blockTags = new Set(['p', 'blockquote', 'pre', 'address', 'dt', 'dd']);
      if (blockTags.has(tag) && normalizeWhitespace(el.textContent || '')) return true;

      return false;
    }

    /**
     * Check if a role should have an exit announcement.
     */
    _hasExitAnnouncement(role) {
      if (!this.engine.verbosity.announce_landmarks_on_exit) return false;

      const roleData = ANNOUNCEMENTS[role];
      if (!roleData?.[this.engine.sr]?.exit) return false;

      return true;
    }

    // ── Navigation methods ────────────────────────────────────────

    /**
     * Move to the next element in reading order.
     */
    moveNext() {
      if (this.position >= this.nodes.length - 1) return null;
      this.position++;
      return this._currentResult();
    }

    /**
     * Move to the previous element in reading order.
     */
    movePrevious() {
      if (this.position <= 0) return null;
      this.position--;
      return this._currentResult();
    }

    /**
     * Move to the next element with a specific role.
     */
    moveToNextByRole(targetRole) {
      for (let i = this.position + 1; i < this.nodes.length; i++) {
        if (this.nodes[i].role === targetRole && !this.nodes[i].isExit) {
          this.position = i;
          return this._currentResult();
        }
      }
      return null; // Not found — wrap or announce "no more [role]"
    }

    /**
     * Move to the previous element with a specific role.
     */
    moveToPreviousByRole(targetRole) {
      for (let i = this.position - 1; i >= 0; i--) {
        if (this.nodes[i].role === targetRole && !this.nodes[i].isExit) {
          this.position = i;
          return this._currentResult();
        }
      }
      return null;
    }

    /**
     * Move to the next heading of a specific level.
     */
    moveToNextHeadingLevel(level) {
      for (let i = this.position + 1; i < this.nodes.length; i++) {
        const node = this.nodes[i];
        if (node.role === 'heading' && !node.isExit) {
          const headingLevel = getHeadingLevel(node.element);
          if (headingLevel === level) {
            this.position = i;
            return this._currentResult();
          }
        }
      }
      return null;
    }

    /**
     * Move to the next focusable element (Tab behavior).
     * Calls element.focus() to trigger the page's focus management
     * (including focus traps in modal dialogs).
     */
    moveToNextFocusable() {
      SR._srNavigating = true;
      for (let i = this.position + 1; i < this.nodes.length; i++) {
        const node = this.nodes[i];
        if (!node.isExit && this._isFocusable(node.element)) {
          this.position = i;
          node.element.focus({ preventScroll: true });
          SR._srNavigating = false;
          return this._currentResult();
        }
      }
      SR._srNavigating = false;
      // No more focusable elements in our list.
      // Dispatch a real Tab keydown on the current element to trigger
      // any focus traps (their JS listens for keydown, not focus).
      // The focus handler (with _srNavigating = false) will detect
      // where the page's trap sends focus and update our position.
      const current = this.nodes[this.position];
      if (current && current.element) {
        current.element.dispatchEvent(new KeyboardEvent('keydown', {
          key: 'Tab', code: 'Tab', keyCode: 9, bubbles: true, cancelable: true,
        }));
      }
      return null;
    }

    /**
     * Move to the previous focusable element (Shift+Tab behavior).
     * Calls element.focus() to trigger the page's focus management.
     */
    moveToPreviousFocusable() {
      SR._srNavigating = true;
      for (let i = this.position - 1; i >= 0; i--) {
        const node = this.nodes[i];
        if (!node.isExit && this._isFocusable(node.element)) {
          this.position = i;
          node.element.focus({ preventScroll: true });
          SR._srNavigating = false;
          return this._currentResult();
        }
      }
      SR._srNavigating = false;
      // Dispatch Shift+Tab to trigger reverse focus trap
      const current = this.nodes[this.position];
      if (current && current.element) {
        current.element.dispatchEvent(new KeyboardEvent('keydown', {
          key: 'Tab', code: 'Tab', keyCode: 9, shiftKey: true, bubbles: true, cancelable: true,
        }));
      }
      return null;
    }

    /**
     * Move to the top of the page.
     */
    moveToTop() {
      this.position = 0;
      return this._currentResult();
    }

    /**
     * Move to the bottom of the page.
     */
    moveToBottom() {
      this.position = this.nodes.length - 1;
      return this._currentResult();
    }

    /**
     * Activate the current element (click/toggle).
     */
    activate() {
      const node = this.nodes[this.position];
      if (!node || node.isExit) return null;
      node.element.click();
      // Re-announce after activation (state may have changed)
      return this._currentResult();
    }

    /**
     * Get the current position info.
     */
    getPosition() {
      return {
        index: this.position,
        total: this._nonExitCount,
        mode: this.mode
      };
    }

    /**
     * Get the current element.
     */
    getCurrentElement() {
      const node = this.nodes[this.position];
      return node ? node.element : null;
    }

    // ── Private helpers ──────────────────────────────────────────

    /**
     * Build the result object for the current position.
     */
    _currentResult() {
      const node = this.nodes[this.position];
      if (!node) return null;

      // Skip elements that have been removed from the DOM
      if (!node.element.isConnected) {
        // Try to move to the next connected element
        return this.moveNext();
      }

      // Handle exit announcements
      if (node.isExit) {
        const roleData = ANNOUNCEMENTS[node.role];
        const exitText = roleData?.[this.engine.sr]?.exit || '';
        const rect = node.element.getBoundingClientRect();
        return {
          announcement: exitText,
          role: node.role,
          name: node.name,
          isExit: true,
          selector: this._getSelector(node.element),
          rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
          position: this.getPosition(),
          language: detectLanguage(node.element),
          languageChanged: false
        };
      }

      // Normal announcement
      const result = this.engine.announce(node.element);
      const rect = node.element.getBoundingClientRect();

      return {
        announcement: result.text,
        role: result.role,
        name: result.name,
        isExit: false,
        selector: this._getSelector(node.element),
        rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
        position: this.getPosition(),
        language: result.lang,
        languageChanged: result.langChanged
      };
    }

    /**
     * Check if an element is keyboard-focusable.
     */
    _isFocusable(el) {
      if (el.disabled) return false;
      if (el.tabIndex < 0) return false;

      const tag = el.tagName.toLowerCase();

      // <a> without href is not focusable (unless it has tabindex)
      if (tag === 'a' && !el.hasAttribute('href') && !el.hasAttribute('tabindex')) return false;

      const nativelyFocusable = ['a', 'button', 'input', 'select', 'textarea', 'summary', 'details'];
      if (nativelyFocusable.includes(tag) && el.tabIndex >= 0) return true;

      if (el.tabIndex >= 0 && el.hasAttribute('tabindex')) return true;
      if (el.hasAttribute('contenteditable')) return true;

      return false;
    }

    /**
     * Generate a CSS selector for an element (for reporting).
     */
    _getSelector(el) {
      if (el.id) return `#${CSS.escape(el.id)}`;

      const tag = el.tagName.toLowerCase();
      const role = el.getAttribute('role');
      const ariaLabel = el.getAttribute('aria-label');

      if (role) return `${tag}[role="${role}"]`;
      if (ariaLabel) return `${tag}[aria-label="${CSS.escape(ariaLabel)}"]`;

      // Positional selector
      const parent = el.parentElement;
      if (!parent) return tag;
      const siblings = Array.from(parent.children).filter(c => c.tagName === el.tagName);
      if (siblings.length === 1) return `${parent.tagName.toLowerCase()} > ${tag}`;
      const index = siblings.indexOf(el) + 1;
      return `${tag}:nth-of-type(${index})`;
    }
  }

  // ── LiveRegionMonitor ──────────────────────────────────────────

  class LiveRegionMonitor {
    constructor(announcementEngine, onAnnounce) {
      this.engine = announcementEngine;
      this.onAnnounce = onAnnounce;
      this.observer = null;
      this.queue = []; // { text, priority: 'assertive' | 'polite' }
    }

    start() {
      // Find all live regions
      const liveRegions = document.querySelectorAll(
        '[aria-live], [role="alert"], [role="status"], [role="log"], [role="marquee"], [role="timer"]'
      );

      this.observer = new MutationObserver((mutations) => {
        for (const mutation of mutations) {
          const target = mutation.target;
          const liveRegion = target.closest(
            '[aria-live], [role="alert"], [role="status"], [role="log"]'
          );
          if (!liveRegion) continue;

          const ariaLive = liveRegion.getAttribute('aria-live') ||
            (liveRegion.getAttribute('role') === 'alert' ? 'assertive' : 'polite');

          const text = normalizeWhitespace(liveRegion.textContent || '');
          if (!text) continue;

          const announcement = {
            text: text,
            priority: ariaLive,
            role: getRole(liveRegion),
            timestamp: Date.now()
          };

          if (ariaLive === 'assertive') {
            // Interrupt current speech
            this.onAnnounce(announcement);
          } else {
            // Queue for after current speech
            this.queue.push(announcement);
            this._processQueue();
          }
        }
      });

      // Observe each live region
      const observeConfig = { childList: true, characterData: true, subtree: true };
      liveRegions.forEach(region => {
        this.observer.observe(region, observeConfig);
      });

      // Also observe body for dynamically added live regions
      this.observer.observe(document.body, { childList: true, subtree: true });
    }

    stop() {
      if (this.observer) {
        this.observer.disconnect();
        this.observer = null;
      }
      this.queue = [];
    }

    _processQueue() {
      if (this.queue.length === 0) return;
      // Process polite announcements with a small delay
      setTimeout(() => {
        const next = this.queue.shift();
        if (next) this.onAnnounce(next);
      }, 500);
    }
  }

  // ── Headless walk (for CLI/MCP) ────────────────────────────────

  function walkPage(config) {
    const screenReaders = config.screenReader === 'all'
      ? ['jaws', 'nvda', 'voiceover']
      : [config.screenReader];

    const verbosity = config.verbosity || 'high';
    const maxElements = config.maxElements || 500;

    // Use the first SR engine to build reading order (same for all)
    const primaryEngine = new AnnouncementEngine(screenReaders[0], verbosity);
    const cursor = new VirtualCursor(primaryEngine);
    const totalNodes = cursor.init(document.body);

    // Build engines for each SR
    const engines = {};
    for (const sr of screenReaders) {
      engines[sr] = new AnnouncementEngine(sr, verbosity);
    }

    // Walk through all nodes
    const announcements = [];
    let count = 0;

    for (let i = 0; i < cursor.nodes.length && count < maxElements; i++) {
      const node = cursor.nodes[i];
      if (node.isExit) continue; // Skip exit announcements in headless mode

      const el = node.element;
      const entry = {
        index: count,
        selector: cursor._getSelector(el),
        tag: el.tagName.toLowerCase(),
        role: node.role,
        name: node.name,
        language: detectLanguage(el),

        // Secondary info
        description: getDescription(el) || null,
        tooltip: getTooltip(el),
        is_focusable: cursor._isFocusable(el),
        tab_index: el.hasAttribute('tabindex')
          ? parseInt(el.getAttribute('tabindex'), 10) : null,

        // Table context
        table_column_header: getColumnHeader(el),
        table_row_header: getRowHeader(el),

        // Form context
        value: el.value || el.getAttribute('aria-valuenow') || null,
        placeholder: el.getAttribute('placeholder') || null,

        // Link context
        href: (node.role === 'link' && el.href) ? el.href : null,

        // Known bugs
        known_bugs: config.includeBugs !== false
          ? findKnownBugs(el, node.role, screenReaders) : [],
      };

      // Generate announcement for each SR
      for (const sr of screenReaders) {
        const result = engines[sr].announce(el);
        entry[sr] = result.text;

        // Secondary announcement (description/tooltip per SR)
        const secondary = engines[sr].getSecondaryAnnouncement(el);
        if (secondary) {
          entry[sr + '_secondary'] = secondary;
        }
      }

      announcements.push(entry);
      count++;
    }

    // Build summary
    const summary = {
      total_elements: count,
      headings: announcements.filter(a => a.role === 'heading').length,
      links: announcements.filter(a => a.role === 'link').length,
      buttons: announcements.filter(a => a.role === 'button').length,
      form_fields: announcements.filter(a =>
        ['textbox', 'searchbox', 'checkbox', 'radio', 'combobox', 'slider', 'spinbutton'].includes(a.role)
      ).length,
      images: announcements.filter(a => a.role === 'img').length,
      landmarks: announcements.filter(a =>
        ['banner', 'main', 'navigation', 'complementary', 'contentinfo', 'search', 'form', 'region'].includes(a.role)
      ).length,
      tables: announcements.filter(a => a.role === 'table').length,
      lists: announcements.filter(a => a.role === 'list').length,
    };

    // Find differences between SRs
    let differences = [];
    if (screenReaders.length > 1) {
      differences = announcements.filter(a => {
        const texts = screenReaders.map(sr => a[sr]);
        return new Set(texts).size > 1; // At least one SR differs
      }).map(a => ({
        index: a.index,
        selector: a.selector,
        role: a.role,
        name: a.name,
        ...Object.fromEntries(screenReaders.map(sr => [sr, a[sr]]))
      }));
    }

    return {
      ok: true,
      url: location.href,
      title: document.title,
      element_count: count,
      announcements: announcements,
      summary: summary,
      differences: differences,
      difference_count: differences.length
    };
  }

  // ── Interactive mode API (for VM control panel) ────────────────

  // Store simulator state on the window for the control server to access
  if (!window.__inspektSR) {
    window.__inspektSR = {
      active: false,
      engine: null,
      cursor: null,
      liveMonitor: null,
      screenReader: null,
      lastAnnouncement: null,
      options: {},
    };
  }

  const SR = window.__inspektSR;

  /**
   * Start the screen reader simulator.
   * @param {string} screenReader — 'jaws' | 'nvda' | 'voiceover'
   * @param {string} verbosity — 'high' | 'medium' | 'low'
   * @param {object} options — { startFromFocus, syncFocus, syncMouse }
   */
  function startSimulator(screenReader, verbosity, options) {
    SR.screenReader = screenReader;
    SR.options = options || {};
    SR.engine = new AnnouncementEngine(screenReader, verbosity || 'high');
    SR.cursor = new VirtualCursor(SR.engine);
    SR.cursor.init(document.body);
    SR.liveMonitor = new LiveRegionMonitor(SR.engine, (announcement) => {
      SR.lastAnnouncement = announcement;
    });
    SR.liveMonitor.start();
    SR.active = true;

    // Listen for page-driven focus changes (focus traps, skip links, etc.).
    // When the page's JavaScript calls element.focus(), we detect it and
    // move our virtual cursor to match — just like real screen readers do.
    // We use _srNavigating flag to ignore focus events that WE triggered
    // (via element.focus() in moveToNextFocusable) — only follow focus
    // changes from the PAGE's own JavaScript (focus traps, skip links, etc.).
    SR._srNavigating = false;
    SR._focusHandler = function(e) {
      if (!SR.active || !SR.cursor || SR._srNavigating) return;
      const el = e.target;
      const index = SR.cursor.nodes.findIndex(n => n.element === el && !n.isExit);
      if (index !== -1 && index !== SR.cursor.position) {
        SR.cursor.position = index;
        SR.lastAnnouncement = SR.cursor._currentResult();
      }
    };
    document.addEventListener('focus', SR._focusHandler, true);

    // Start from currently focused element if requested
    if (SR.options.startFromFocus) {
      const focused = document.activeElement;
      if (focused && focused !== document.body && focused !== document.documentElement) {
        const index = SR.cursor.nodes.findIndex(n => n.element === focused);
        if (index !== -1) {
          SR.cursor.position = index;
          const result = SR.cursor._currentResult();
          SR.lastAnnouncement = result;
          return result;
        }
      }
    }

    // Default: start from first element
    const first = SR.cursor.moveNext();
    SR.lastAnnouncement = first;
    return first;
  }

  /**
   * Stop the screen reader simulator.
   */
  function stopSimulator() {
    if (SR.liveMonitor) SR.liveMonitor.stop();
    if (SR._focusHandler) {
      document.removeEventListener('focus', SR._focusHandler, true);
      SR._focusHandler = null;
    }
    SR.active = false;
    SR.engine = null;
    SR.cursor = null;
    SR.liveMonitor = null;
    SR.lastAnnouncement = null;
    return { ok: true };
  }

  /**
   * Navigate in the simulator.
   * @param {string} action — navigation action name
   * @param {object} params — optional params (e.g., { level: 2 })
   */
  function navigate(action, params) {
    if (!SR.active || !SR.cursor) {
      return { ok: false, error: 'Simulator not active' };
    }

    let result = null;

    switch (action) {
      case 'next-line':
      case 'next-element':
        result = SR.cursor.moveNext();
        break;
      case 'previous-line':
      case 'previous-element':
        result = SR.cursor.movePrevious();
        break;
      case 'next-heading':
        result = SR.cursor.moveToNextByRole('heading');
        break;
      case 'previous-heading':
        result = SR.cursor.moveToPreviousByRole('heading');
        break;
      case 'next-heading-level':
        result = SR.cursor.moveToNextHeadingLevel(params?.level || 1);
        break;
      case 'next-link':
        result = SR.cursor.moveToNextByRole('link');
        break;
      case 'previous-link':
        result = SR.cursor.moveToPreviousByRole('link');
        break;
      case 'next-button':
        result = SR.cursor.moveToNextByRole('button');
        break;
      case 'previous-button':
        result = SR.cursor.moveToPreviousByRole('button');
        break;
      case 'next-form-field':
        result = SR.cursor.moveToNextByRole('textbox') ||
          SR.cursor.moveToNextByRole('searchbox') ||
          SR.cursor.moveToNextByRole('combobox') ||
          SR.cursor.moveToNextByRole('checkbox') ||
          SR.cursor.moveToNextByRole('radio');
        break;
      case 'previous-form-field':
        result = SR.cursor.moveToPreviousByRole('textbox') ||
          SR.cursor.moveToPreviousByRole('searchbox');
        break;
      case 'next-table':
        result = SR.cursor.moveToNextByRole('table');
        break;
      case 'previous-table':
        result = SR.cursor.moveToPreviousByRole('table');
        break;
      case 'next-list':
        result = SR.cursor.moveToNextByRole('list');
        break;
      case 'previous-list':
        result = SR.cursor.moveToPreviousByRole('list');
        break;
      case 'next-landmark':
        // Try all landmark roles
        for (const role of ['banner', 'main', 'navigation', 'complementary', 'contentinfo', 'search', 'form', 'region']) {
          result = SR.cursor.moveToNextByRole(role);
          if (result) break;
        }
        break;
      case 'previous-landmark':
        for (const role of ['banner', 'main', 'navigation', 'complementary', 'contentinfo', 'search', 'form', 'region']) {
          result = SR.cursor.moveToPreviousByRole(role);
          if (result) break;
        }
        break;
      case 'next-graphic':
        result = SR.cursor.moveToNextByRole('img');
        break;
      case 'previous-graphic':
        result = SR.cursor.moveToPreviousByRole('img');
        break;
      case 'next-focusable':
        result = SR.cursor.moveToNextFocusable();
        if (!result) {
          // Focus trap may have moved us — check current position
          result = SR.cursor._currentResult();
        }
        break;
      case 'previous-focusable':
        result = SR.cursor.moveToPreviousFocusable();
        if (!result) {
          result = SR.cursor._currentResult();
        }
        break;
      case 'top-of-page':
        result = SR.cursor.moveToTop();
        break;
      case 'bottom-of-page':
        result = SR.cursor.moveToBottom();
        break;
      case 'activate':
        result = SR.cursor.activate();
        break;
      case 'point-at': {
        // Move SR cursor to the element at the given coordinates.
        // Walks up the DOM tree to find the nearest ancestor that
        // exists in the virtual cursor's node list.
        const targetEl = document.elementFromPoint(params.x, params.y);
        if (targetEl) {
          let el = targetEl;
          let index = -1;
          while (el && index === -1) {
            index = SR.cursor.nodes.findIndex(n => n.element === el && !n.isExit);
            if (index === -1) el = el.parentElement;
          }
          if (index !== -1 && index !== SR.cursor.position) {
            SR.cursor.position = index;
            result = SR.cursor._currentResult();
          }
        }
        break;
      }
      default:
        return { ok: false, error: `Unknown action: ${action}` };
    }

    if (result) {
      SR.lastAnnouncement = result;

      // Sync browser focus if enabled
      if (SR.options?.syncFocus) {
        const el = SR.cursor.getCurrentElement();
        if (el && typeof el.focus === 'function') {
          el.focus({ preventScroll: true });
        }
      }

      return { ok: true, ...result };
    }

    // Wrap or announce "not found"
    return {
      ok: true,
      announcement: `No more ${action.replace('next-', '').replace('previous-', '')} elements`,
      role: null,
      name: null,
      position: SR.cursor.getPosition()
    };
  }

  /**
   * Get current simulator state.
   */
  function getState() {
    return {
      active: SR.active,
      screenReader: SR.screenReader,
      position: SR.cursor ? SR.cursor.getPosition() : null,
      lastAnnouncement: SR.lastAnnouncement
    };
  }

  // ── Dispatch based on CONFIG mode ──────────────────────────────

  if (CONFIG.mode === 'walk') {
    return walkPage(CONFIG);
  } else if (CONFIG.mode === 'start') {
    return startSimulator(CONFIG.screenReader, CONFIG.verbosity, CONFIG.options);
  } else if (CONFIG.mode === 'stop') {
    return stopSimulator();
  } else if (CONFIG.mode === 'navigate') {
    return navigate(CONFIG.action, CONFIG.params);
  } else if (CONFIG.mode === 'state') {
    return getState();
  } else {
    return { ok: false, error: `Unknown mode: ${CONFIG.mode}` };
  }

})();
