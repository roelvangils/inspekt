"""
HTML processing utilities for formatting and compacting HTML.

Provides:
- Prettier integration for formatting HTML
- Compact mode for documentation-friendly output (strips noise, preserves structure)
"""

import re
import shutil
import subprocess
from urllib.parse import urlparse, urlunparse

import click
from bs4 import BeautifulSoup, Comment, Tag


def strip_empty_comments(html: str) -> str:
    """Remove empty or whitespace-only HTML comments (<!-- -->, <!---->)."""
    return re.sub(r'<!--\s*-->', '', html)


def is_prettier_installed() -> bool:
    """Check if prettier is installed and available."""
    return shutil.which("prettier") is not None


def prompt_install_prettier() -> bool:
    """Prompt user to install prettier."""
    click.echo("\n📦 prettier is not installed.")
    click.echo("Prettier is a code formatter that makes HTML/CSS/JS code beautiful and consistent.")
    click.echo("\nInstallation options:")
    click.echo("  • npm:  npm install -g prettier")
    click.echo("  • yarn: yarn global add prettier")
    click.echo("  • pnpm: pnpm add -g prettier")
    click.echo("\nOr download from: https://prettier.io/docs/en/install.html")
    return click.confirm("\nWould you like to install prettier now via npm?", default=False)


def install_prettier_via_npm() -> bool:
    """Attempt to install prettier using npm."""
    if not shutil.which("npm"):
        click.echo("\n❌ Error: npm is not installed.", err=True)
        click.echo("Please install Node.js and npm first: https://nodejs.org/", err=True)
        return False

    click.echo("\n📦 Installing prettier via npm…")
    try:
        result = subprocess.run(
            ["npm", "install", "-g", "prettier"],
            check=True,
            capture_output=True,
            text=True
        )
        click.echo("✓ prettier installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        click.echo(f"\n❌ Error installing prettier: {e.stderr}", err=True)
        return False


def format_html_with_prettier(html_content: str, indent: int = 2) -> str | None:
    """
    Format HTML using prettier.

    Args:
        html_content: Raw HTML string to format
        indent: Number of spaces for indentation (default 2)

    Returns:
        Formatted HTML string, or None if prettier not available
    """
    if not is_prettier_installed():
        if prompt_install_prettier():
            if install_prettier_via_npm():
                # Verify installation
                if not is_prettier_installed():
                    return None
            else:
                return None
        else:
            click.echo("Skipping prettier formatting", err=True)
            return None

    try:
        # Run prettier with stdin input
        result = subprocess.run(
            [
                "prettier",
                "--stdin-filepath", "index.html",
                "--print-width", "80",
                "--tab-width", str(indent),
                "--html-whitespace-sensitivity", "ignore",
            ],
            input=html_content,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        click.echo(f"Error running prettier: {e.stderr}", err=True)
        return None


def _truncate_url(url: str, max_segments: int = 3) -> str:
    """Shorten a URL by collapsing middle path segments, preserving query and fragment."""
    if len(url) < 60:
        return url
    try:
        parsed = urlparse(url)
    except Exception:
        return url
    if not parsed.scheme or not parsed.netloc:
        return url
    parts = [p for p in parsed.path.split('/') if p]
    if len(parts) <= max_segments:
        return url
    shortened_path = '/' + parts[0] + '/…/' + parts[-1]
    return urlunparse((parsed.scheme, parsed.netloc, shortened_path, '', parsed.query, parsed.fragment))


def _is_hash_like(s: str) -> bool:
    """Check if a string looks like a hash/random ID (20+ hex-like chars)."""
    if len(s) < 20:
        return False
    alnum_count = sum(1 for c in s if c.isalnum())
    return alnum_count >= 20 and alnum_count / max(len(s), 1) > 0.8


def _replace_hashes_in_url(url: str) -> str:
    """Replace hash-like segments in a URL path with [STRING]."""
    try:
        parsed = urlparse(url)
    except Exception:
        return url
    if not parsed.path:
        return url
    parts = parsed.path.split('/')
    new_parts = []
    for part in parts:
        # Split off file extension
        if '.' in part and not part.startswith('.'):
            name, ext = part.rsplit('.', 1)
            if _is_hash_like(name):
                new_parts.append(f'[STRING].{ext}')
                continue
        if _is_hash_like(part):
            new_parts.append('[STRING]')
            continue
        new_parts.append(part)
    new_path = '/'.join(new_parts)
    return urlunparse((parsed.scheme, parsed.netloc, new_path, '', parsed.query, parsed.fragment))


_EVENT_ATTRS = {
    'onclick', 'ondblclick', 'onmousedown', 'onmouseup', 'onmouseover',
    'onmouseout', 'onmousemove', 'onmouseenter', 'onmouseleave',
    'onkeydown', 'onkeyup', 'onkeypress', 'onfocus', 'onblur',
    'onchange', 'oninput', 'onsubmit', 'onreset', 'onload', 'onerror',
    'onscroll', 'onresize', 'ontouchstart', 'ontouchend', 'ontouchmove',
}

_URL_ATTRS = {'href', 'src', 'action', 'poster', 'formaction', 'cite'}

# src/poster are simplified to filename only; href keeps path for navigation context
_FILENAME_ONLY_ATTRS = {'src', 'poster'}

_MAX_ATTR_LEN = 30  # Truncate long id/for/name/aria-* values


def _get_tag_skeleton(tag) -> str:
    """Return a structural fingerprint of a tag: its name + recursive child tag names.

    Used to detect repeated siblings with the same structure (ignoring text/attributes).
    Example: <li><a><img><span></span></a></li> → "li>a>img+span"
    """
    children = [c for c in tag.children if isinstance(c, Tag)]
    if not children:
        return tag.name
    child_skeletons = '+'.join(_get_tag_skeleton(c) for c in children)
    return f'{tag.name}>{child_skeletons}'


def _collapse_repeated_siblings(soup) -> None:
    """Replace 3+ consecutive siblings with the same tag skeleton with a comment.

    Keeps the first 2 siblings so the reader sees the pattern, then adds
    <!-- … and N more <tag> --> in place of the rest.
    """
    for parent in soup.find_all(True):
        children = [c for c in parent.children if isinstance(c, Tag)]
        if len(children) < 3:
            continue

        # Compute skeletons once per child
        skeletons = [_get_tag_skeleton(c) for c in children]

        # Group consecutive siblings by skeleton
        i = 0
        while i < len(children):
            run_start = i
            while i < len(children) and skeletons[i] == skeletons[run_start]:
                i += 1

            if i - run_start >= 3:
                tag_name = children[run_start].name
                to_remove = children[run_start + 2:i]
                comment = Comment(f' … and {len(to_remove)} more <{tag_name}> ')
                to_remove[0].insert_before(comment)
                for el in to_remove:
                    el.decompose()


def _unwrap_purposeless_wrappers(soup) -> None:
    """Remove <div> and <span> wrappers that have no attributes and a single child element.

    Runs in a loop since unwrapping may expose new single-child wrappers.
    """
    for _ in range(10):  # Max iterations to prevent infinite loops
        found = False
        for tag in soup.find_all(['div', 'span']):
            if tag.attrs:  # Has meaningful attributes (id, aria-*, etc.)
                continue
            element_children = [c for c in tag.children if isinstance(c, Tag)]
            # Only unwrap if there's exactly one child element and no significant text
            if len(element_children) != 1:
                continue
            non_element_text = ''.join(
                str(c).strip() for c in tag.children if not isinstance(c, Tag)
            )
            if non_element_text:  # Has text content alongside the child — div provides grouping
                continue
            tag.unwrap()
            found = True
        if not found:
            break


def compact_html(html_content: str) -> str:
    """
    Compact HTML for documentation — strips noise while preserving semantic structure.

    Transformations (in order):
    1. Remove class, style, and data-* attributes
    2. Replace event handlers, integrity hashes, nonces
    3. Shorten URLs, replace hashes, simplify src to filename
    4. Truncate long id/for/name/aria-* values
    5. Collapse inline <script>/<style> content to /* … */
    6. Replace SVG path/polygon data
    7. Truncate text nodes longer than 20 words
    8. Remove purposeless wrapper <div>/<span> elements
    9. Collapse 3+ repeated siblings into <!-- … and N more -->
    """
    soup = BeautifulSoup(html_content, 'html.parser')

    for tag in soup.find_all(True):
        attrs_to_delete = []

        for attr_name in list(tag.attrs.keys()):
            attr_val = tag[attr_name]
            # Normalize list attributes (class, etc.) to string
            if isinstance(attr_val, list):
                attr_val = ' '.join(attr_val)

            # Remove class, style, data-* attributes
            if attr_name == 'class' or attr_name == 'style' or attr_name.startswith('data-'):
                attrs_to_delete.append(attr_name)
                continue

            # Replace event handlers with [JAVASCRIPT]
            if attr_name.lower() in _EVENT_ATTRS:
                tag[attr_name] = '[JAVASCRIPT]'
                continue

            # Replace integrity hashes
            if attr_name == 'integrity':
                tag[attr_name] = '[HASH]'
                continue

            # Replace nonces
            if attr_name == 'nonce':
                tag[attr_name] = '[NONCE]'
                continue

            # Handle srcset (multiple URLs with descriptors)
            if attr_name == 'srcset':
                entries = [e.strip() for e in attr_val.split(',') if e.strip()]
                new_entries = []
                for entry in entries:
                    parts = entry.split()
                    if parts:
                        url = _replace_hashes_in_url(parts[0])
                        url = _truncate_url(url)
                        descriptor = ' '.join(parts[1:]) if len(parts) > 1 else ''
                        new_entries.append(f'{url} {descriptor}'.strip())
                tag[attr_name] = ', '.join(new_entries)
                continue

            # Shorten URLs and replace hashes in URL attributes
            if attr_name.lower() in _URL_ATTRS and isinstance(attr_val, str):
                if attr_val.startswith('data:'):
                    # Base64 data URI → keep MIME type, replace data
                    semi = attr_val.find(';')
                    if semi > 0:
                        tag[attr_name] = attr_val[:semi + 1] + 'base64,[DATA]'
                    else:
                        tag[attr_name] = '[DATA]'
                    continue
                attr_val = _replace_hashes_in_url(attr_val)
                # src/poster: simplify to filename only; href: keep path for context
                if attr_name.lower() in _FILENAME_ONLY_ATTRS:
                    try:
                        path = urlparse(attr_val).path
                        filename = path.rsplit('/', 1)[-1] if '/' in path else path
                        if filename:
                            attr_val = filename
                    except Exception:
                        pass
                else:
                    attr_val = _truncate_url(attr_val)
                tag[attr_name] = attr_val
                continue

            # Truncate long id, for, name, aria-* values
            if attr_name in ('id', 'for', 'name') or attr_name.startswith('aria-'):
                if isinstance(attr_val, str) and len(attr_val) > _MAX_ATTR_LEN:
                    tag[attr_name] = attr_val[:_MAX_ATTR_LEN] + '…'
                continue

        for attr_name in attrs_to_delete:
            del tag[attr_name]

        # Collapse inline <script>/<style> content — keep the tag, replace body with /* … */
        if tag.name in ('script', 'style') and not tag.get('src'):
            if tag.string and tag.string.strip():
                tag.string = '/* … */'

        # SVG: replace path d="" with [PATH DATA]
        if tag.name == 'path' and tag.get('d'):
            tag['d'] = '[PATH DATA]'

        # SVG: replace polygon/polyline points with [POINTS]
        if tag.name in ('polygon', 'polyline') and tag.get('points'):
            tag['points'] = '[POINTS]'

    # Truncate long text nodes
    for element in soup.find_all(string=True):
        if element.parent.name in ('script', 'style'):
            continue
        text = str(element).strip()
        if not text:
            continue
        words = text.split()
        if len(words) > 20:
            element.replace_with('…')

    # Structural cleanup (runs after content cleanup for accurate analysis)
    _unwrap_purposeless_wrappers(soup)
    _collapse_repeated_siblings(soup)

    return str(soup)


def process_html(
    html_content: str,
    format: bool = False,
    compact: bool = False,
    remove_comments: bool = False,
    indent: int = 2,
) -> str:
    """
    Process HTML with optional formatting, compacting, and comment removal.

    Args:
        html_content: Raw HTML string
        format: If True, format with prettier
        compact: If True, remove classes and truncate long text
        remove_comments: If True, strip all HTML comments
        indent: Indentation width for prettier (default 2)

    Returns:
        Processed HTML string
    """
    result = html_content

    # Always strip empty comments
    result = strip_empty_comments(result)

    # Remove all comments if requested
    if remove_comments:
        result = re.sub(r'<!--[\s\S]*?-->', '', result)

    # Apply compact (before prettier)
    if compact:
        result = compact_html(result)

    # Apply prettier last (for best formatting)
    if format:
        formatted = format_html_with_prettier(result, indent=indent)
        if formatted is not None:
            result = formatted

    return result
