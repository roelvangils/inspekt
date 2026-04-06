"""
Rich HTML report generator for element analysis.

Generates a self-contained, accessible HTML page with:
- Element screenshot (base64 embedded)
- AI question and answer
- HTML views (compacted and original)
- CSS views (optimized and computed)
- Accessibility details
- Page context
- Element tree
"""

from __future__ import annotations

import html
from dataclasses import dataclass

import markdown


@dataclass
class RichReportData:
    """Data collected for the rich HTML report."""

    question: str
    answer: str
    element_type: str
    screenshot_data_url: str  # base64 data URL
    html_original: str  # prettified original HTML
    html_compacted: str  # compacted + prettified HTML
    css_optimized: str  # with heuristic comments, grouped
    css_computed: str  # raw computed styles
    accessibility: dict  # role, name, aria, focusable
    page_context: dict  # url, title, viewport
    element_tree: list[dict]  # parent chain
    generated_at: str  # timestamp
    audit_results: dict | None = None  # consolidated a11y audit results
    debug_data: dict | None = None  # prompt, API params, cURL (when --debug)


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return html.escape(text) if text else ""


def _markdown_to_html(text: str) -> str:
    """Convert markdown text to HTML.

    Uses the Python markdown library with extensions for:
    - Smart quotes and typography (smarty)
    - Fenced code blocks (fenced_code)
    - Tables (tables)
    - Definition lists (def_list)
    """
    if not text:
        return ""

    md = markdown.Markdown(
        extensions=[
            "smarty",
            "fenced_code",
            "tables",
            "def_list",
            "nl2br",  # Convert newlines to <br> for better formatting
        ],
        output_format="html5",
    )
    return md.convert(text)


def _escape_for_code_block(text: str) -> str:
    """Escape text for display in a <code> block."""
    # Escape HTML entities but preserve structure
    return html.escape(text) if text else ""


def _format_accessibility_details(a11y: dict) -> str:
    """Format accessibility details as HTML definition list items."""
    items = []

    # Role
    role = a11y.get("role", "")
    if role:
        items.append(f'<dt>Role</dt><dd><code>{_escape_html(role)}</code></dd>')
    else:
        items.append('<dt>Role</dt><dd class="empty">None (no explicit role)</dd>')

    # Accessible Name
    name = a11y.get("accessibleName", "")
    source = a11y.get("accessibleNameSource", "")
    if name:
        items.append(f'<dt>Accessible Name</dt><dd>"{_escape_html(name)}"</dd>')
        if source:
            items.append(f'<dt>Name Source</dt><dd><code>{_escape_html(source)}</code></dd>')
    else:
        items.append('<dt>Accessible Name</dt><dd class="warning">Missing accessible name</dd>')

    # ARIA attributes
    aria_attrs = []
    if a11y.get("ariaLabel"):
        aria_attrs.append(f'aria-label="{_escape_html(a11y["ariaLabel"])}"')
    if a11y.get("ariaLabelledBy"):
        aria_attrs.append(f'aria-labelledby="{_escape_html(a11y["ariaLabelledBy"])}"')
    if a11y.get("ariaDescribedBy"):
        aria_attrs.append(f'aria-describedby="{_escape_html(a11y["ariaDescribedBy"])}"')
    if a11y.get("ariaHidden"):
        aria_attrs.append("aria-hidden=true")

    if aria_attrs:
        items.append(f'<dt>ARIA Attributes</dt><dd><code>{", ".join(aria_attrs)}</code></dd>')
    else:
        items.append('<dt>ARIA Attributes</dt><dd class="empty">None</dd>')

    # Focusability
    focusable = a11y.get("focusable", False)
    tab_index = a11y.get("tabIndex")
    focus_info = "Yes" if focusable else "No"
    if tab_index is not None:
        focus_info += f' (tabindex="{tab_index}")'
    items.append(f"<dt>Focusable</dt><dd>{focus_info}</dd>")

    # Disabled state
    if a11y.get("disabled"):
        items.append('<dt>State</dt><dd class="warning">Disabled</dd>')

    return "\n".join(items)


def _format_page_context(context: dict) -> str:
    """Format page context as HTML definition list items."""
    items = []

    url = context.get("url", "")
    if url:
        items.append(f'<dt>URL</dt><dd><a href="{_escape_html(url)}" target="_blank" rel="noopener">{_escape_html(url)}</a></dd>')

    title = context.get("title", "")
    if title:
        items.append(f"<dt>Page Title</dt><dd>{_escape_html(title)}</dd>")

    viewport = context.get("viewport", {})
    if viewport:
        w = viewport.get("width", "?")
        h = viewport.get("height", "?")
        items.append(f"<dt>Viewport</dt><dd>{w} x {h} px</dd>")

    lang = context.get("lang", "")
    if lang:
        items.append(f"<dt>Language</dt><dd><code>{_escape_html(lang)}</code></dd>")

    return "\n".join(items)


def _format_element_tree(tree: list[dict], current_tag: str) -> str:
    """Format element tree as an indented visualization."""
    if not tree:
        return f"<code>&lt;{_escape_html(current_tag)}&gt;</code> (no parent chain available)"

    lines = []
    for i, el in enumerate(tree):
        indent = "  " * i
        tag = el.get("tag", "?")
        el_id = el.get("id", "")
        classes = el.get("classes", [])

        selector = f"&lt;{_escape_html(tag)}&gt;"
        if el_id:
            selector += f'<span class="tree-id">#{_escape_html(el_id)}</span>'
        if classes:
            class_str = ".".join(classes[:3])  # Show first 3 classes
            if len(classes) > 3:
                class_str += f"... (+{len(classes) - 3})"
            selector += f'<span class="tree-class">.{_escape_html(class_str)}</span>'

        lines.append(f"{indent}{selector}")

    # Add current element
    current_indent = "  " * len(tree)
    lines.append(f'{current_indent}<strong>&lt;{_escape_html(current_tag)}&gt;</strong> <span class="tree-current">(inspected)</span>')

    return "\n".join(lines)


def _format_audit_section(audit_results: dict | None) -> str:
    """Format accessibility audit results as HTML with tabs for violations/warnings/passes."""
    if not audit_results:
        return ""

    summary = audit_results.get("summary", {})
    engines_used = summary.get("engines_used", [])

    if not engines_used:
        error = summary.get("error", "")
        if error:
            return f'''
            <section class="audit-section audit-error" aria-labelledby="audit-heading">
                <h2 id="audit-heading">Accessibility Audit</h2>
                <p class="audit-error-message">Unable to run accessibility audit: {_escape_html(error)}</p>
            </section>
            '''
        return ""

    violations = audit_results.get("violations", [])
    warnings = audit_results.get("warnings", [])
    passes = audit_results.get("passes", [])

    v_count = len(violations)
    w_count = len(warnings)
    p_count = len(passes)

    # Format violations
    violations_html = _format_issues_list(violations, "violation")
    if not violations_html:
        violations_html = '<p class="audit-empty">No violations found ✓</p>'

    # Format warnings
    warnings_html = _format_issues_list(warnings, "warning")
    if not warnings_html:
        warnings_html = '<p class="audit-empty">No warnings or incomplete checks</p>'

    # Format passes
    passes_html = _format_passes_list(passes)
    if not passes_html:
        passes_html = '<p class="audit-empty">No passing rules recorded</p>'

    # Engine badges
    engine_badges = " ".join([f'<span class="badge badge-{e}">{e.upper()}</span>' for e in engines_used])

    return f'''
    <section class="audit-section" aria-labelledby="audit-heading">
        <h2 id="audit-heading">Accessibility Audit</h2>

        <div class="audit-meta">
            <span class="audit-engines">Engines: {engine_badges}</span>
        </div>

        <div class="audit-info" role="note">
            <span class="info-icon" aria-hidden="true">ℹ</span>
            <p>Audit scoped to selected element. Some cross-page rules (heading order, duplicate IDs, landmarks) may require full-page analysis for complete results.</p>
        </div>

        <div class="tabs audit-tabs" role="tablist" aria-label="Audit results by status">
            <button role="tab" id="tab-violations" aria-selected="true" aria-controls="panel-violations" tabindex="0" class="tab tab-violations">
                <span aria-hidden="true">⛔</span>
                Violations
                <span class="count count-violations">{v_count}</span>
            </button>
            <button role="tab" id="tab-warnings" aria-selected="false" aria-controls="panel-warnings" tabindex="-1" class="tab tab-warnings">
                <span aria-hidden="true">⚠</span>
                Warnings
                <span class="count count-warnings">{w_count}</span>
            </button>
            <button role="tab" id="tab-passes" aria-selected="false" aria-controls="panel-passes" tabindex="-1" class="tab tab-passes">
                <span aria-hidden="true">✓</span>
                Passes
                <span class="count count-passes">{p_count}</span>
            </button>
        </div>

        <div role="tabpanel" id="panel-violations" aria-labelledby="tab-violations" class="tab-panel audit-panel">
            {violations_html}
        </div>

        <div role="tabpanel" id="panel-warnings" aria-labelledby="tab-warnings" class="tab-panel audit-panel" hidden>
            {warnings_html}
        </div>

        <div role="tabpanel" id="panel-passes" aria-labelledby="tab-passes" class="tab-panel audit-panel" hidden>
            {passes_html}
        </div>
    </section>
    '''


def _format_issues_list(issues: list, issue_type: str) -> str:
    """Format a list of violations or warnings as issue cards."""
    if not issues:
        return ""

    cards = []
    for issue in issues:
        rule_id = issue.get("rule_id", "unknown")
        description = issue.get("description", "")
        wcag = issue.get("wcag", [])
        impact = issue.get("impact", "moderate")
        engines = issue.get("engines", [])
        instances = issue.get("instances", [])

        # Engine badges
        engine_badges = " ".join([f'<span class="badge badge-{e}">{e.upper()}</span>' for e in engines])

        # Impact badge
        impact_badge = f'<span class="badge badge-impact badge-{impact}">{impact}</span>'

        # WCAG links
        wcag_links = ""
        if wcag:
            wcag_parts = []
            for sc in wcag[:2]:  # Limit to 2 SCs
                if sc:
                    anchor = sc.replace(".", "")
                    wcag_parts.append(f'<a href="https://www.w3.org/WAI/WCAG21/quickref/#{anchor}" class="wcag-link" target="_blank" rel="noopener">WCAG {_escape_html(sc)}</a>')
            wcag_links = " ".join(wcag_parts)

        # Instances
        instances_html = ""
        if instances:
            instance_items = []
            for inst in instances[:3]:  # Limit to 3 instances
                inst_html = inst.get("html", "")
                inst_msg = inst.get("message", "")
                help_url = inst.get("help_url", "")

                item = f'''
                <li class="instance">
                    <code class="instance-html">{_escape_for_code_block(inst_html[:500])}</code>
                    <p class="instance-message">{_escape_html(inst_msg)}</p>
                    {f'<a href="{_escape_html(help_url)}" class="help-link" target="_blank" rel="noopener">Learn more →</a>' if help_url else ''}
                </li>
                '''
                instance_items.append(item)

            instances_html = f'''
            <div class="issue-instances">
                <details{"" if len(instances) == 1 else ""}>
                    <summary>{len(instances)} instance{"s" if len(instances) != 1 else ""}</summary>
                    <ul class="instance-list">
                        {"".join(instance_items)}
                    </ul>
                </details>
            </div>
            '''

        card = f'''
        <article class="issue-card impact-{impact}">
            <header class="issue-header">
                <h3 class="issue-title">{_escape_html(description) or _escape_html(rule_id)}</h3>
                <div class="issue-meta">
                    {engine_badges}
                    {impact_badge}
                    {wcag_links}
                </div>
            </header>
            {instances_html}
        </article>
        '''
        cards.append(card)

    return "\n".join(cards)


def _format_passes_list(passes: list) -> str:
    """Format a list of passing rules as a compact grid."""
    if not passes:
        return ""

    items = []
    for p in passes[:20]:  # Limit to 20 passes
        rule_id = p.get("rule_id", "unknown")
        engines = p.get("engines", [])
        engine_badges = " ".join([f'<span class="badge badge-{e} badge-sm">{e.upper()}</span>' for e in engines])

        items.append(f'''
        <div class="pass-card">
            <span class="pass-icon" aria-hidden="true">✓</span>
            <span class="pass-rule">{_escape_html(rule_id)}</span>
            <span class="pass-engines">{engine_badges}</span>
        </div>
        ''')

    more_text = ""
    if len(passes) > 20:
        more_text = f'<p class="passes-more">And {len(passes) - 20} more passing rules...</p>'

    return f'<div class="pass-grid">{"".join(items)}</div>{more_text}'


def _format_qa_section(
    question: str,
    answer_html: str,
    debug_data: dict | None = None
) -> str:
    """Format the Q&A section, with debug tabs if debug_data is present."""

    question_escaped = _escape_html(question)

    if not debug_data:
        # Simple Q&A without tabs
        return f'''
            <section class="qa-section" aria-labelledby="qa-heading">
                <h2 id="qa-heading" class="visually-hidden">Question and Analysis</h2>
                <div class="question">
                    <span class="question-label">Question</span>
                    {question_escaped}
                </div>
                <div class="answer">
                    <span class="answer-label">AI Analysis</span>
                    <div class="answer-content">{answer_html}</div>
                </div>
            </section>
'''

    # With debug tabs: Q&A | AI Prompt | cURL
    prompt_escaped = _escape_for_code_block(debug_data.get("prompt", ""))
    curl_escaped = _escape_for_code_block(debug_data.get("curl_command", ""))
    api_params = debug_data.get("api_params", {})

    # Format API params as readable text
    params_lines = [
        f"Provider: {api_params.get('provider', 'unknown')}",
        f"Model: {api_params.get('model', 'unknown')}",
        f"Max Tokens: {api_params.get('max_tokens', 'N/A')}",
        f"Image Size: ~{api_params.get('image_size_kb', 0)} KB",
    ]
    params_text = "\n".join(params_lines)

    return f'''
            <section class="qa-section" aria-labelledby="qa-heading">
                <h2 id="qa-heading" class="visually-hidden">Question and Analysis</h2>

                <div class="tabs qa-tabs" role="tablist" aria-label="Analysis views">
                    <button role="tab" id="tab-qa" aria-selected="true" aria-controls="panel-qa" tabindex="0" class="tab">
                        Q&amp;A
                    </button>
                    <button role="tab" id="tab-prompt" aria-selected="false" aria-controls="panel-prompt" tabindex="-1" class="tab">
                        AI Prompt
                    </button>
                    <button role="tab" id="tab-curl" aria-selected="false" aria-controls="panel-curl" tabindex="-1" class="tab">
                        cURL
                    </button>
                </div>

                <div role="tabpanel" id="panel-qa" aria-labelledby="tab-qa" class="tabpanel">
                    <div class="question">
                        <span class="question-label">Question</span>
                        {question_escaped}
                    </div>
                    <div class="answer">
                        <span class="answer-label">AI Analysis</span>
                        <div class="answer-content">{answer_html}</div>
                    </div>
                </div>

                <div role="tabpanel" id="panel-prompt" aria-labelledby="tab-prompt" class="tabpanel" hidden>
                    <div class="debug-section">
                        <h3>API Parameters</h3>
                        <pre class="debug-params"><code>{_escape_html(params_text)}</code></pre>

                        <h3>Full Prompt</h3>
                        <pre class="debug-prompt"><code class="language-text">{prompt_escaped}</code></pre>
                    </div>
                </div>

                <div role="tabpanel" id="panel-curl" aria-labelledby="tab-curl" class="tabpanel" hidden>
                    <div class="debug-section">
                        <p class="debug-note">
                            <strong>Note:</strong> This is a representative cURL command.
                            The actual API call is made via the SDK. Image data is replaced with a placeholder.
                        </p>
                        <pre class="debug-curl"><code class="language-bash">{curl_escaped}</code></pre>
                    </div>
                </div>
            </section>
'''


def generate_rich_report_html(data: RichReportData) -> str:
    """
    Generate a complete self-contained HTML page for the element analysis report.

    The generated page is:
    - Accessible (WCAG compliant structure, keyboard navigation, ARIA)
    - Portable (base64 images, CDN for Prism.js with graceful degradation)
    - Themed (auto-detects system preference, manual toggle)
    """
    # Escape user-provided content
    element_type_escaped = _escape_html(data.element_type)

    # Convert markdown answer to HTML
    answer_html = _markdown_to_html(data.answer)

    # Format sections
    qa_section = _format_qa_section(data.question, answer_html, data.debug_data)
    a11y_details = _format_accessibility_details(data.accessibility)
    page_context = _format_page_context(data.page_context)
    element_tree = _format_element_tree(data.element_tree, data.element_type)
    audit_section = _format_audit_section(data.audit_results)

    # Escape code blocks
    html_compacted_escaped = _escape_for_code_block(data.html_compacted)
    html_original_escaped = _escape_for_code_block(data.html_original)
    css_optimized_escaped = _escape_for_code_block(data.css_optimized)
    css_computed_escaped = _escape_for_code_block(data.css_computed)

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Element Analysis: &lt;{element_type_escaped}&gt; | Inspekt</title>

    <!-- Prism.js for syntax highlighting (CDN with graceful degradation) -->
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/prismjs@1.29.0/themes/prism-tomorrow.min.css" crossorigin="anonymous">

    <style>
        /* CSS Custom Properties for theming */
        :root {{
            color-scheme: light dark;

            /* Light mode (default) */
            --bg-primary: #ffffff;
            --bg-secondary: #f6f8fa;
            --bg-code: #f6f8fa;
            --text-primary: #1f2328;
            --text-secondary: #656d76;
            --text-tertiary: #8b949e;
            --border-color: #d0d7de;
            --accent: #0969da;
            --accent-hover: #0550ae;
            --success: #1a7f37;
            --warning: #9a6700;
            --error: #cf222e;
            --shadow: 0 1px 3px rgba(0,0,0,0.12);
            --radius: 8px;
        }}

        /* Dark mode */
        [data-theme="dark"] {{
            --bg-primary: #0d1117;
            --bg-secondary: #161b22;
            --bg-code: #161b22;
            --text-primary: #e6edf3;
            --text-secondary: #8b949e;
            --text-tertiary: #6e7681;
            --border-color: #30363d;
            --accent: #58a6ff;
            --accent-hover: #79c0ff;
            --success: #3fb950;
            --warning: #d29922;
            --error: #f85149;
            --shadow: 0 1px 3px rgba(0,0,0,0.3);
        }}

        /* Auto-detect system preference */
        @media (prefers-color-scheme: dark) {{
            :root:not([data-theme="light"]) {{
                --bg-primary: #0d1117;
                --bg-secondary: #161b22;
                --bg-code: #161b22;
                --text-primary: #e6edf3;
                --text-secondary: #8b949e;
                --text-tertiary: #6e7681;
                --border-color: #30363d;
                --accent: #58a6ff;
                --accent-hover: #79c0ff;
                --success: #3fb950;
                --warning: #d29922;
                --error: #f85149;
                --shadow: 0 1px 3px rgba(0,0,0,0.3);
            }}
        }}

        /* Base styles */
        *, *::before, *::after {{
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif;
            font-size: 16px;
            line-height: 1.6;
            color: var(--text-primary);
            background: var(--bg-primary);
            margin: 0;
            padding: 0;
        }}

        /* Skip link for accessibility */
        .skip-link {{
            position: absolute;
            top: -40px;
            left: 0;
            background: var(--accent);
            color: white;
            padding: 8px 16px;
            z-index: 100;
            text-decoration: none;
            border-radius: 0 0 var(--radius) 0;
        }}

        .skip-link:focus {{
            top: 0;
        }}

        /* Layout */
        .container {{
            width: 100%;
            max-width: 100%;
            padding: 24px;
            box-sizing: border-box;
        }}

        /* Header */
        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 24px;
            border-bottom: 1px solid var(--border-color);
            margin-bottom: 32px;
        }}

        header h1 {{
            margin: 0;
            font-size: 1.75rem;
            font-weight: 600;
        }}

        header h1 code {{
            background: var(--bg-secondary);
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.9em;
        }}

        .header-meta {{
            color: var(--text-secondary);
            font-size: 0.875rem;
            margin-top: 4px;
        }}

        /* Theme toggle button */
        .theme-toggle {{
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: var(--radius);
            padding: 8px 12px;
            cursor: pointer;
            color: var(--text-primary);
            font-size: 1.25rem;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: background 0.2s, border-color 0.2s;
        }}

        .theme-toggle:hover {{
            background: var(--bg-code);
            border-color: var(--accent);
        }}

        .theme-toggle:focus {{
            outline: 2px solid var(--accent);
            outline-offset: 2px;
        }}

        .theme-toggle .icon-sun,
        .theme-toggle .icon-moon {{
            display: none;
        }}

        [data-theme="dark"] .theme-toggle .icon-sun {{
            display: inline;
        }}

        [data-theme="light"] .theme-toggle .icon-moon,
        :root:not([data-theme]) .theme-toggle .icon-moon {{
            display: inline;
        }}

        @media (prefers-color-scheme: dark) {{
            :root:not([data-theme="light"]) .theme-toggle .icon-sun {{
                display: inline;
            }}
            :root:not([data-theme="light"]) .theme-toggle .icon-moon {{
                display: none;
            }}
        }}

        /* Sections */
        section {{
            margin-bottom: 32px;
        }}

        section h2 {{
            font-size: 1.25rem;
            font-weight: 600;
            margin: 0 0 16px 0;
            color: var(--text-primary);
        }}

        /* Screenshot section */
        .screenshot-section {{
            text-align: center;
        }}

        .screenshot-section img {{
            max-width: 100%;
            height: auto;
            border: 1px solid var(--border-color);
            border-radius: var(--radius);
            box-shadow: var(--shadow);
        }}

        /* Q&A section */
        .qa-section {{
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: var(--radius);
            padding: 20px;
        }}

        .question {{
            font-weight: 600;
            margin-bottom: 16px;
            padding-bottom: 16px;
            border-bottom: 1px solid var(--border-color);
        }}

        .question-label {{
            color: var(--accent);
            font-size: 0.875rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            display: block;
            margin-bottom: 4px;
        }}

        .answer-label {{
            color: var(--success);
            font-size: 0.875rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            display: block;
            margin-bottom: 8px;
        }}

        /* Markdown-rendered answer content */
        .answer-content {{
            line-height: 1.6;
        }}

        .answer-content p {{
            margin: 0 0 1em 0;
        }}

        .answer-content p:last-child {{
            margin-bottom: 0;
        }}

        .answer-content ul,
        .answer-content ol {{
            margin: 0 0 1em 0;
            padding-left: 1.5em;
        }}

        .answer-content li {{
            margin-bottom: 0.25em;
        }}

        .answer-content strong {{
            font-weight: 600;
        }}

        .answer-content code {{
            background: var(--bg-code);
            padding: 0.125em 0.375em;
            border-radius: 4px;
            font-family: var(--font-mono);
            font-size: 0.875em;
        }}

        .answer-content pre {{
            background: var(--bg-code);
            padding: 1em;
            border-radius: var(--radius);
            overflow-x: auto;
            margin: 0 0 1em 0;
        }}

        .answer-content pre code {{
            background: none;
            padding: 0;
        }}

        .answer-content table {{
            width: 100%;
            border-collapse: collapse;
            margin: 0 0 1em 0;
        }}

        .answer-content th,
        .answer-content td {{
            border: 1px solid var(--border-color);
            padding: 0.5em;
            text-align: left;
        }}

        .answer-content th {{
            background: var(--bg-secondary);
            font-weight: 600;
        }}

        /* Debug sections (visible when --debug is used) */
        .debug-section {{
            padding: 16px 0;
        }}

        .debug-section h3 {{
            font-size: 1rem;
            margin: 0 0 8px 0;
            color: var(--text-secondary);
        }}

        .debug-section h3:not(:first-child) {{
            margin-top: 24px;
        }}

        .debug-params,
        .debug-prompt,
        .debug-curl {{
            background: var(--bg-code);
            border: 1px solid var(--border-color);
            border-radius: var(--radius);
            padding: 16px;
            margin: 0;
            overflow-x: auto;
            font-size: 0.875rem;
            white-space: pre-wrap;
            word-break: break-word;
        }}

        .debug-note {{
            background: var(--bg-secondary);
            border-left: 3px solid var(--accent);
            padding: 12px 16px;
            margin: 0 0 16px 0;
            font-size: 0.875rem;
            color: var(--text-secondary);
        }}

        .debug-note strong {{
            color: var(--text-primary);
        }}

        /* Q&A tabs styling */
        .qa-tabs {{
            margin-bottom: 16px;
        }}

        .qa-section .tabpanel {{
            padding-top: 0;
        }}

        /* Tabs */
        .tabs {{
            display: flex;
            gap: 4px;
            margin-bottom: 0;
            border-bottom: 1px solid var(--border-color);
        }}

        .tab {{
            background: transparent;
            border: none;
            border-bottom: 2px solid transparent;
            padding: 12px 16px;
            cursor: pointer;
            color: var(--text-secondary);
            font-size: 0.875rem;
            font-weight: 500;
            transition: color 0.2s, border-color 0.2s;
            margin-bottom: -1px;
        }}

        .tab:hover {{
            color: var(--text-primary);
        }}

        .tab:focus {{
            outline: 2px solid var(--accent);
            outline-offset: -2px;
        }}

        .tab[aria-selected="true"] {{
            color: var(--accent);
            border-bottom-color: var(--accent);
        }}

        .tab-panel {{
            background: var(--bg-code);
            border: 1px solid var(--border-color);
            border-top: none;
            border-radius: 0 0 var(--radius) var(--radius);
            overflow: hidden;
        }}

        .tab-panel[hidden] {{
            display: none;
        }}

        /* Code blocks */
        pre {{
            margin: 0;
            padding: 16px;
            overflow-x: auto;
            font-family: "JetBrains Mono", "SF Mono", "Fira Code", Consolas, monospace;
            font-size: 13px;
            line-height: 1.5;
        }}

        pre code {{
            background: none;
            padding: 0;
        }}

        /* Details/Summary (collapsible sections) */
        details {{
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: var(--radius);
            margin-bottom: 16px;
        }}

        details summary {{
            padding: 16px;
            cursor: pointer;
            font-weight: 600;
            color: var(--text-primary);
            list-style: none;
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        details summary::-webkit-details-marker {{
            display: none;
        }}

        details summary::before {{
            content: "\\25B6";
            font-size: 0.75rem;
            transition: transform 0.2s;
        }}

        details[open] summary::before {{
            transform: rotate(90deg);
        }}

        details summary:focus {{
            outline: 2px solid var(--accent);
            outline-offset: -2px;
        }}

        details summary h2 {{
            margin: 0;
            font-size: 1rem;
            display: inline;
        }}

        details > div {{
            padding: 0 16px 16px 16px;
        }}

        /* Definition lists */
        dl {{
            display: grid;
            grid-template-columns: auto 1fr;
            gap: 8px 16px;
            margin: 0;
        }}

        dt {{
            font-weight: 500;
            color: var(--text-secondary);
        }}

        dd {{
            margin: 0;
        }}

        dd code {{
            background: var(--bg-code);
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 0.875em;
        }}

        dd.empty {{
            color: var(--text-tertiary);
            font-style: italic;
        }}

        dd.warning {{
            color: var(--warning);
        }}

        dd a {{
            color: var(--accent);
            text-decoration: none;
            word-break: break-all;
        }}

        dd a:hover {{
            text-decoration: underline;
        }}

        /* Audit Section */
        .audit-section {{
            margin-bottom: 32px;
        }}

        .audit-meta {{
            margin-bottom: 12px;
            font-size: 0.875rem;
            color: var(--text-secondary);
        }}

        .audit-info {{
            display: flex;
            gap: 8px;
            padding: 12px 16px;
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: var(--radius);
            margin-bottom: 16px;
            font-size: 0.875rem;
            color: var(--text-secondary);
        }}

        .audit-info .info-icon {{
            flex-shrink: 0;
            color: var(--accent);
        }}

        .audit-info p {{
            margin: 0;
        }}

        .audit-panel {{
            padding: 16px;
        }}

        .audit-empty {{
            color: var(--text-tertiary);
            font-style: italic;
            margin: 0;
        }}

        .audit-error-message {{
            color: var(--error);
            padding: 16px;
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: var(--radius);
        }}

        /* Engine badges */
        .badge {{
            display: inline-flex;
            align-items: center;
            padding: 2px 8px;
            border-radius: 9999px;
            font-size: 0.7rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.025em;
        }}

        .badge-sm {{
            padding: 1px 6px;
            font-size: 0.6rem;
        }}

        .badge-axe {{ background: #4a90d9; color: white; }}
        .badge-ibm {{ background: #0f62fe; color: white; }}
        .badge-hcs {{ background: #6929c4; color: white; }}

        /* Impact levels */
        .badge-critical {{ background: #d93025; color: white; }}
        .badge-serious  {{ background: #f9ab00; color: #1a1a1a; }}
        .badge-moderate {{ background: #fbbc04; color: #1a1a1a; }}
        .badge-minor    {{ background: #34a853; color: white; }}

        /* Issue cards */
        .issue-card {{
            border: 1px solid var(--border-color);
            border-radius: var(--radius);
            margin-bottom: 16px;
            overflow: hidden;
        }}

        .issue-card.impact-critical {{ border-left: 4px solid #d93025; }}
        .issue-card.impact-serious  {{ border-left: 4px solid #f9ab00; }}
        .issue-card.impact-moderate {{ border-left: 4px solid #fbbc04; }}
        .issue-card.impact-minor    {{ border-left: 4px solid #34a853; }}

        .issue-header {{
            padding: 16px;
            background: var(--bg-secondary);
        }}

        .issue-title {{
            font-size: 1rem;
            font-weight: 600;
            margin: 0 0 8px 0;
        }}

        .issue-meta {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            align-items: center;
        }}

        .issue-instances {{
            padding: 16px;
        }}

        .issue-instances details {{
            background: transparent;
            border: none;
            margin: 0;
        }}

        .issue-instances summary {{
            padding: 0 0 8px 0;
            font-weight: 500;
            color: var(--text-secondary);
        }}

        .instance-list {{
            list-style: none;
            padding: 0;
            margin: 0;
        }}

        .instance {{
            margin-bottom: 16px;
            padding-bottom: 16px;
            border-bottom: 1px solid var(--border-color);
        }}

        .instance:last-child {{
            margin-bottom: 0;
            padding-bottom: 0;
            border-bottom: none;
        }}

        .instance-html {{
            display: block;
            padding: 8px 12px;
            background: var(--bg-code);
            border-radius: 4px;
            font-size: 0.8rem;
            overflow-x: auto;
            white-space: pre-wrap;
            word-break: break-word;
            margin-bottom: 8px;
        }}

        .instance-message {{
            margin: 8px 0;
            color: var(--text-secondary);
            font-size: 0.875rem;
        }}

        .help-link {{
            color: var(--accent);
            text-decoration: none;
            font-size: 0.875rem;
        }}

        .help-link:hover {{
            text-decoration: underline;
        }}

        /* Tabs with counts */
        .tab .count {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 1.25rem;
            height: 1.25rem;
            padding: 0 6px;
            margin-left: 6px;
            border-radius: 9999px;
            font-size: 0.7rem;
            font-weight: 600;
        }}

        .count-violations {{ background: #fecaca; color: #991b1b; }}
        .count-warnings   {{ background: #fef3c7; color: #92400e; }}
        .count-passes     {{ background: #d1fae5; color: #065f46; }}

        [data-theme="dark"] .count-violations {{ background: #7f1d1d; color: #fecaca; }}
        [data-theme="dark"] .count-warnings   {{ background: #78350f; color: #fef3c7; }}
        [data-theme="dark"] .count-passes     {{ background: #064e3b; color: #d1fae5; }}

        @media (prefers-color-scheme: dark) {{
            :root:not([data-theme="light"]) .count-violations {{ background: #7f1d1d; color: #fecaca; }}
            :root:not([data-theme="light"]) .count-warnings   {{ background: #78350f; color: #fef3c7; }}
            :root:not([data-theme="light"]) .count-passes     {{ background: #064e3b; color: #d1fae5; }}
        }}

        /* Pass cards (compact grid) */
        .pass-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
            gap: 8px;
        }}

        .pass-card {{
            display: flex;
            align-items: center;
            gap: 6px;
            padding: 8px 12px;
            background: var(--bg-secondary);
            border-radius: 4px;
            font-size: 0.8rem;
        }}

        .pass-icon {{ color: var(--success); }}

        .pass-rule {{
            flex: 1;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}

        .passes-more {{
            margin-top: 12px;
            color: var(--text-tertiary);
            font-size: 0.875rem;
            text-align: center;
        }}

        /* WCAG links */
        .wcag-link {{
            color: var(--accent);
            text-decoration: none;
            font-size: 0.8rem;
        }}

        .wcag-link:hover {{
            text-decoration: underline;
        }}

        /* Element tree */
        .element-tree {{
            font-family: "JetBrains Mono", "SF Mono", "Fira Code", Consolas, monospace;
            font-size: 13px;
            line-height: 1.8;
            white-space: pre;
            background: var(--bg-code);
            padding: 16px;
            border-radius: var(--radius);
            overflow-x: auto;
        }}

        .tree-id {{
            color: var(--accent);
        }}

        .tree-class {{
            color: var(--success);
        }}

        .tree-current {{
            color: var(--warning);
            font-style: italic;
        }}

        /* Footer */
        footer {{
            margin-top: 48px;
            padding-top: 24px;
            border-top: 1px solid var(--border-color);
            text-align: center;
            color: var(--text-tertiary);
            font-size: 0.875rem;
        }}

        footer a {{
            color: var(--accent);
            text-decoration: none;
        }}

        footer a:hover {{
            text-decoration: underline;
        }}

        /* Responsive */
        @media (max-width: 768px) {{
            .container {{
                padding: 16px;
            }}

            header {{
                flex-direction: column;
                align-items: flex-start;
                gap: 16px;
            }}

            header h1 {{
                font-size: 1.5rem;
            }}

            dl {{
                grid-template-columns: 1fr;
            }}

            dt {{
                margin-top: 8px;
            }}
        }}

        /* Print styles */
        @media print {{
            .theme-toggle,
            .skip-link {{
                display: none;
            }}

            body {{
                background: white;
                color: black;
            }}

            details {{
                display: block;
            }}

            details[open] summary::before {{
                content: "";
            }}
        }}

        /* Fallback if Prism.js doesn't load */
        pre code.language-html,
        pre code.language-css {{
            white-space: pre-wrap;
            word-break: break-word;
        }}
    </style>
    <noscript>
        <style>
            .tabs {{ display: none; }}
            .tab-panel {{ display: block !important; border-top: 1px solid var(--border-color); border-radius: var(--radius); }}
            .tab-panel + .tab-panel {{ margin-top: 16px; }}
            .theme-toggle {{ display: none; }}
        </style>
    </noscript>
</head>
<body>
    <a href="#main-content" class="skip-link">Skip to main content</a>

    <div class="container">
        <header>
            <div>
                <h1>Element Analysis: <code>&lt;{element_type_escaped}&gt;</code></h1>
                <p class="header-meta">Generated {data.generated_at}</p>
            </div>
            <button class="theme-toggle" id="theme-toggle" type="button" aria-label="Toggle dark/light mode">
                <span class="icon-sun" aria-hidden="true">&#9728;</span>
                <span class="icon-moon" aria-hidden="true">&#9790;</span>
                <span>Theme</span>
            </button>
        </header>

        <main id="main-content">
            <!-- Screenshot Section -->
            <section class="screenshot-section" aria-labelledby="screenshot-heading">
                <h2 id="screenshot-heading">Element Screenshot</h2>
                <img src="{data.screenshot_data_url}" alt="Screenshot of the inspected {element_type_escaped} element">
            </section>

            <!-- Q&A Section (with debug tabs if --debug is used) -->
            {qa_section}

            <!-- Accessibility Audit Section -->
            {audit_section}

            <!-- HTML Section -->
            <section aria-labelledby="html-heading">
                <h2 id="html-heading">HTML</h2>
                <div class="tabs" role="tablist" aria-label="HTML code views">
                    <button role="tab" id="tab-html-compacted" aria-selected="true" aria-controls="panel-html-compacted" tabindex="0" class="tab">
                        Compacted
                    </button>
                    <button role="tab" id="tab-html-original" aria-selected="false" aria-controls="panel-html-original" tabindex="-1" class="tab">
                        Original
                    </button>
                </div>
                <div role="tabpanel" id="panel-html-compacted" aria-labelledby="tab-html-compacted" class="tab-panel">
                    <pre><code class="language-html">{html_compacted_escaped}</code></pre>
                </div>
                <div role="tabpanel" id="panel-html-original" aria-labelledby="tab-html-original" class="tab-panel" hidden>
                    <pre><code class="language-html">{html_original_escaped}</code></pre>
                </div>
            </section>

            <!-- CSS Section -->
            <section aria-labelledby="css-heading">
                <h2 id="css-heading">CSS</h2>
                <div class="tabs" role="tablist" aria-label="CSS code views">
                    <button role="tab" id="tab-css-optimized" aria-selected="true" aria-controls="panel-css-optimized" tabindex="0" class="tab">
                        Optimized
                    </button>
                    <button role="tab" id="tab-css-computed" aria-selected="false" aria-controls="panel-css-computed" tabindex="-1" class="tab">
                        Computed
                    </button>
                </div>
                <div role="tabpanel" id="panel-css-optimized" aria-labelledby="tab-css-optimized" class="tab-panel">
                    <pre><code class="language-css">{css_optimized_escaped}</code></pre>
                </div>
                <div role="tabpanel" id="panel-css-computed" aria-labelledby="tab-css-computed" class="tab-panel" hidden>
                    <pre><code class="language-css">{css_computed_escaped}</code></pre>
                </div>
            </section>

            <!-- Accessibility Details -->
            <details>
                <summary><h2>Accessibility Details</h2></summary>
                <div>
                    <dl>
                        {a11y_details}
                    </dl>
                </div>
            </details>

            <!-- Page Context -->
            <details>
                <summary><h2>Page Context</h2></summary>
                <div>
                    <dl>
                        {page_context}
                    </dl>
                </div>
            </details>

            <!-- Element Tree -->
            <details>
                <summary><h2>Element Tree</h2></summary>
                <div>
                    <div class="element-tree">{element_tree}</div>
                </div>
            </details>
        </main>

        <footer>
            <p>Generated by <a href="https://github.com/anthropics/inspekt" target="_blank" rel="noopener">Inspekt</a></p>
        </footer>
    </div>

    <!-- Prism.js for syntax highlighting -->
    <script src="https://cdn.jsdelivr.net/npm/prismjs@1.29.0/prism.min.js" crossorigin="anonymous"></script>
    <script src="https://cdn.jsdelivr.net/npm/prismjs@1.29.0/components/prism-markup.min.js" crossorigin="anonymous"></script>
    <script src="https://cdn.jsdelivr.net/npm/prismjs@1.29.0/components/prism-css.min.js" crossorigin="anonymous"></script>

    <script>
        // Theme toggle functionality
        (function() {{
            const toggle = document.getElementById('theme-toggle');
            const html = document.documentElement;

            // Get initial theme
            function getPreferredTheme() {{
                const stored = localStorage.getItem('inspekt-theme');
                if (stored) return stored;
                return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
            }}

            function setTheme(theme) {{
                html.setAttribute('data-theme', theme);
                localStorage.setItem('inspekt-theme', theme);
            }}

            // Apply initial theme
            setTheme(getPreferredTheme());

            // Toggle handler
            toggle.addEventListener('click', function() {{
                const current = html.getAttribute('data-theme') || getPreferredTheme();
                setTheme(current === 'dark' ? 'light' : 'dark');
            }});

            // Listen for system preference changes
            window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function(e) {{
                if (!localStorage.getItem('inspekt-theme')) {{
                    setTheme(e.matches ? 'dark' : 'light');
                }}
            }});
        }})();

        // Accessible tab functionality
        (function() {{
            const tabLists = document.querySelectorAll('[role="tablist"]');

            tabLists.forEach(function(tabList) {{
                const tabs = tabList.querySelectorAll('[role="tab"]');
                const panels = [];

                tabs.forEach(function(tab) {{
                    const panelId = tab.getAttribute('aria-controls');
                    const panel = document.getElementById(panelId);
                    if (panel) panels.push(panel);
                }});

                function selectTab(tab) {{
                    // Deselect all tabs
                    tabs.forEach(function(t) {{
                        t.setAttribute('aria-selected', 'false');
                        t.setAttribute('tabindex', '-1');
                    }});

                    // Hide all panels
                    panels.forEach(function(p) {{
                        p.hidden = true;
                    }});

                    // Select clicked tab
                    tab.setAttribute('aria-selected', 'true');
                    tab.setAttribute('tabindex', '0');
                    tab.focus();

                    // Show corresponding panel
                    const panelId = tab.getAttribute('aria-controls');
                    const panel = document.getElementById(panelId);
                    if (panel) {{
                        panel.hidden = false;
                        // Re-highlight code if Prism is available
                        if (window.Prism) {{
                            Prism.highlightAllUnder(panel);
                        }}
                    }}
                }}

                tabs.forEach(function(tab) {{
                    // Click handler
                    tab.addEventListener('click', function() {{
                        selectTab(tab);
                    }});

                    // Keyboard navigation
                    tab.addEventListener('keydown', function(e) {{
                        const index = Array.from(tabs).indexOf(tab);
                        let newIndex;

                        if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {{
                            newIndex = (index + 1) % tabs.length;
                            e.preventDefault();
                        }} else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {{
                            newIndex = (index - 1 + tabs.length) % tabs.length;
                            e.preventDefault();
                        }} else if (e.key === 'Home') {{
                            newIndex = 0;
                            e.preventDefault();
                        }} else if (e.key === 'End') {{
                            newIndex = tabs.length - 1;
                            e.preventDefault();
                        }}

                        if (newIndex !== undefined) {{
                            selectTab(tabs[newIndex]);
                        }}
                    }});
                }});
            }});
        }})();

        // Highlight code on load (if Prism loaded successfully)
        if (window.Prism) {{
            Prism.highlightAll();
        }}
    </script>
</body>
</html>'''
