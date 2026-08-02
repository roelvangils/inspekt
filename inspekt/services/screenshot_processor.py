"""
Screenshot file processor.

Handles temp file creation, metadata embedding, optimization, and final save.
"""

import shutil
import tempfile
from pathlib import Path
from typing import Literal

import click

from inspekt.app.cli import icons
from inspekt.services.formatting_utils import format_filesize

# Size thresholds for compression behavior (in bytes)
SIZE_1MB = 1 * 1024 * 1024
SIZE_2MB = 2 * 1024 * 1024
SIZE_5MB = 5 * 1024 * 1024


class ScreenshotProcessor:
    """
    Handles temp file processing, metadata embedding, and optimization for screenshots.

    Usage:
        processor = ScreenshotProcessor(output_path, format="png", compression="auto")
        tmp_path = processor.save_to_temp(image_data)
        try:
            processor.add_metadata(tmp_path, metadata_dict)
            processor.optimize_png(tmp_path)
            processor.finalize(tmp_path)
        finally:
            processor.cleanup(tmp_path)
    """

    def __init__(
        self,
        output_path: Path,
        format: str = "png",
        compression: Literal["auto", "enabled", "disabled"] = "auto",
        metadata: bool = True,
        quiet: bool = False,
        json_output: bool = False,
    ):
        """
        Initialize the screenshot processor.

        Args:
            output_path: Final output file path
            format: Image format (png, jpg, jpeg, webp)
            compression: Compression mode - "auto" (size-based), "enabled" (force), "disabled" (skip)
            metadata: Whether to embed metadata
            quiet: Suppress status messages
            json_output: Suppress status messages (JSON mode)
        """
        self.output_path = Path(output_path)
        self.format = format.lower()
        self.compression = compression
        self.metadata_enabled = metadata
        self.quiet = quiet
        self.json_output = json_output

        # Tracking
        self.original_size = 0
        self.final_size = 0
        self.metadata_added = False
        self.optimized = False
        self.compression_skipped = False

    def _should_output(self) -> bool:
        """Check if we should display output messages."""
        return not self.quiet and not self.json_output

    def save_to_temp(self, image_data: bytes, width: int | None = None, height: int | None = None) -> Path:
        """
        Write image data to a temporary file.

        Args:
            image_data: Raw image bytes
            width: Image width (for display)
            height: Image height (for display)

        Returns:
            Path to the temporary file

        Raises:
            RuntimeError: If temp file creation or write fails
        """
        if len(image_data) == 0:
            raise ValueError("Cannot save empty image data")

        self.original_size = len(image_data)

        # Create output directory if needed
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        # Create temp file with matching extension
        suffix = self.output_path.suffix or f".{self.format}"

        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp_path = Path(tmp.name)
                tmp.write(image_data)
        except OSError as e:
            raise RuntimeError(f"Failed to create temp file: {e}")

        # Display "Received from Chrome" message
        if self._should_output():
            size_str = format_filesize(self.original_size)
            if width and height:
                click.echo(icons.chrome_received(f"Received from Chrome: {width}×{height} ({size_str})"))
            else:
                click.echo(icons.chrome_received(f"Received from Chrome: {size_str}"))

        return tmp_path

    def add_metadata(
        self,
        tmp_path: Path,
        source_url: str | None = None,
        target: Literal["element", "viewport", "page"] = "element",
        selector: str | None = None,
        element_tag: str | None = None,
        dpr: float = 2,
        redacted: bool = False,
        original_width: int | None = None,
        original_height: int | None = None,
        page_title: str | None = None,
        page_language: str | None = None,
        prefers_color_scheme: str | None = None,
        prefers_contrast: str | None = None,
        prefers_reduced_motion: str | None = None,
        prefers_reduced_transparency: str | None = None,
        forced_colors: str | None = None,
        browser_version: str | None = None,
        user_agent: str | None = None,
        window_width: int | None = None,
        window_height: int | None = None,
        viewport_width: int | None = None,
        viewport_height: int | None = None,
    ) -> None:
        """
        Add metadata to the image file.

        Args:
            tmp_path: Path to the temp file
            source_url: URL of the page
            target: Screenshot target type
            selector: CSS selector (for element screenshots)
            element_tag: HTML tag name (for element screenshots)
            dpr: Device pixel ratio
            redacted: Whether sensitive data was redacted
            original_width: Original image width
            original_height: Original image height
            page_title: Page title
            page_language: Page language
            prefers_color_scheme: Color scheme preference
            prefers_contrast: Contrast preference
            prefers_reduced_motion: Reduced motion preference
            prefers_reduced_transparency: Reduced transparency preference
            forced_colors: Forced colors mode
            browser_version: Browser version
            user_agent: User agent string
            window_width: Browser window width
            window_height: Browser window height
            viewport_width: Viewport width
            viewport_height: Viewport height
        """
        if not self.metadata_enabled:
            return

        if self.format not in ("png", "jpg", "jpeg"):
            return

        try:
            from inspekt.services.image_metadata import is_pillow_installed

            if not is_pillow_installed():
                if self._should_output():
                    click.echo("Note: Metadata requires Pillow. Install with: pip install Pillow", err=True)
                return
        except ImportError:
            # Fallback if is_pillow_installed doesn't exist yet
            pass

        try:
            from inspekt.services.image_metadata import add_metadata, create_metadata

            if self._should_output():
                click.echo(icons.metadata("Adding metadata and re-encoding…"))

            current_size = tmp_path.stat().st_size
            compression_ratio = None
            if self.original_size > 0 and current_size > 0:
                compression_ratio = (1 - (current_size / self.original_size)) * 100

            meta = create_metadata(
                source_url=source_url,
                target=target,
                selector=selector,
                element_tag=element_tag,
                dpr=dpr,
                redacted=redacted,
                original_width=original_width,
                original_height=original_height,
                file_size=current_size,
                compression_ratio=compression_ratio,
                page_title=page_title,
                page_language=page_language,
                prefers_color_scheme=prefers_color_scheme,
                prefers_contrast=prefers_contrast,
                prefers_reduced_motion=prefers_reduced_motion,
                prefers_reduced_transparency=prefers_reduced_transparency,
                forced_colors=forced_colors,
                browser_version=browser_version,
                user_agent=user_agent,
                window_width=window_width,
                window_height=window_height,
                viewport_width=viewport_width,
                viewport_height=viewport_height,
            )

            add_metadata(tmp_path, meta)
            self.metadata_added = True

        except Exception as e:
            if self._should_output():
                click.echo(f"Warning: Could not add metadata: {e}", err=True)

    def optimize_png(self, tmp_path: Path) -> None:
        """
        Optimize PNG file with oxipng.

        Compression behavior based on mode and file size:
        - "disabled": Skip compression entirely
        - "enabled": Force compression regardless of size
        - "auto": Size-based behavior:
            - < 1 MB: Compress with standard message
            - 1-2 MB: Compress with "may take a moment" message
            - 2-5 MB: Compress with warning about disabling
            - > 5 MB: Skip compression (suggest --enable-compression)

        Args:
            tmp_path: Path to the temp file
        """
        # Skip if compression is disabled
        if self.compression == "disabled":
            return

        # Only PNG format supports lossless compression
        if self.format != "png":
            return

        # Get current file size for size-based decisions
        file_size = tmp_path.stat().st_size

        # Handle auto mode with size thresholds
        if self.compression == "auto" and file_size > SIZE_5MB:
            # Skip compression for very large files
            if self._should_output():
                click.echo(icons.optimizing(
                    "Skipping lossless compression for files larger than 5 MB "
                    "(force with --enable-compression)…"
                ))
            self.compression_skipped = True
            return

        # Determine appropriate message based on file size
        if file_size > SIZE_2MB:
            message = "Applying lossless compression (slow for larger files; disable with --disable-compression)…"
        elif file_size > SIZE_1MB:
            message = "Applying lossless compression (may take a moment)…"
        else:
            message = "Applying lossless compression…"

        try:
            from inspekt.services.image_optimizer import optimize_png

            if self._should_output():
                click.echo(icons.optimizing(message))

            optimized_size = optimize_png(tmp_path)
            if optimized_size:
                self.final_size = optimized_size
                self.optimized = True

        except Exception as e:
            if self._should_output():
                click.echo(f"Optimization failed: {e}", err=True)

    def finalize(self, tmp_path: Path, auto_generated: bool = False) -> None:
        """
        Move temp file to final output location and display summary.

        Args:
            tmp_path: Path to the temp file
            auto_generated: Whether the filename was auto-generated
        """
        # Move temp file to final output
        shutil.move(str(tmp_path), str(self.output_path))
        self.final_size = self.output_path.stat().st_size

        if self._should_output():
            # Display save message
            filename_display = self.output_path.name
            if auto_generated:
                click.echo(icons.save(f"Screenshot saved: {filename_display} (filename auto-generated)"))
            else:
                click.echo(icons.save(f"Screenshot saved: {filename_display}"))

            # Show optimization summary if optimization was performed
            if self.optimized and self.original_size > 0:
                reduction = ((self.original_size - self.final_size) / self.original_size) * 100
                click.echo(icons.optimized_summary(f"Optimized: {format_filesize(self.original_size)} → {format_filesize(self.final_size)} ({reduction:.1f}% decrease)"))

    def display_source_url(self, url: str | None) -> None:
        """
        Display the source URL.

        Args:
            url: The source URL to display
        """
        if self._should_output() and url:
            click.echo(icons.source_url(f"Source: {url}"))

    def cleanup(self, tmp_path: Path | None) -> None:
        """
        Remove temporary file if it exists.

        Args:
            tmp_path: Path to the temp file (may be None)
        """
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass  # Best effort cleanup
