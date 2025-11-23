"""
HTML processing utilities for formatting and compacting HTML.

Provides:
- Prettier integration for formatting HTML
- Compact mode that removes classes and truncates long text
"""

import shutil
import subprocess

import click
from bs4 import BeautifulSoup


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

    click.echo("\n📦 Installing prettier via npm...")
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


def format_html_with_prettier(html_content: str) -> str | None:
    """
    Format HTML using prettier.

    Args:
        html_content: Raw HTML string to format

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
                "--tab-width", "2",
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


def compact_html(html_content: str) -> str:
    """
    Compact HTML by removing unnecessary elements for code examples.

    Rules:
    - Remove ALL class attributes
    - Replace text content longer than 20 words with "(…)"
    - Keep all other attributes (id, href, src, etc.)
    - Keep all HTML structure and tags

    Args:
        html_content: HTML string to compact

    Returns:
        Compacted HTML string
    """
    soup = BeautifulSoup(html_content, 'html.parser')

    # Remove all class attributes
    for tag in soup.find_all(class_=True):
        del tag['class']

    # Truncate long text nodes
    for element in soup.find_all(string=True):
        # Skip script and style tags
        if element.parent.name in ['script', 'style']:
            continue

        text = str(element).strip()
        if not text:
            continue

        # Count words
        words = text.split()
        if len(words) > 20:
            # Replace with ellipsis
            element.replace_with('…')

    return str(soup)


def process_html(
    html_content: str,
    prettier: bool = False,
    compact: bool = False
) -> str:
    """
    Process HTML with optional prettier formatting and/or compacting.

    Args:
        html_content: Raw HTML string
        prettier: If True, format with prettier
        compact: If True, remove classes and truncate long text

    Returns:
        Processed HTML string
    """
    result = html_content

    # Apply compact first (before prettier)
    if compact:
        result = compact_html(result)

    # Apply prettier last (for best formatting)
    if prettier:
        formatted = format_html_with_prettier(result)
        if formatted is not None:
            result = formatted
        # If prettier failed, result remains as-is

    return result
