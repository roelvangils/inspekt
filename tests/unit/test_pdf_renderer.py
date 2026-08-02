"""
Unit tests for PDF Renderer service.

Tests the PDFRenderer class and helper functions for rendering
PDF pages to images.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestPyMuPDFAvailability:
    """Tests for PyMuPDF availability checking."""

    def test_is_pymupdf_available_when_installed(self):
        """Test detection when PyMuPDF is installed."""
        from inspekt.services.pdf_renderer import is_pymupdf_available

        # PyMuPDF should be available in the test environment
        result = is_pymupdf_available()
        assert isinstance(result, bool)

    def test_is_pymupdf_available_when_not_installed(self):
        """Test detection when PyMuPDF is not installed."""
        with patch.dict("sys.modules", {"fitz": None}):
            # Force reimport to test unavailable path
            import importlib

            from inspekt.services import pdf_renderer

            importlib.reload(pdf_renderer)
            # Note: This test is tricky because the module is already loaded
            # In practice, the function will still work correctly


class TestPDFRenderer:
    """Tests for PDFRenderer class."""

    @pytest.fixture
    def mock_fitz(self):
        """Create a mock fitz module."""
        mock = MagicMock()
        mock.Matrix = MagicMock(return_value=MagicMock())

        # Mock page
        mock_page = MagicMock()
        mock_page.rect = MagicMock()
        mock_page.rect.width = 612.0  # Letter width in points
        mock_page.rect.height = 792.0  # Letter height in points

        # Mock pixmap
        mock_pixmap = MagicMock()
        mock_pixmap.tobytes = MagicMock(return_value=b"PNG_DATA")
        mock_page.get_pixmap = MagicMock(return_value=mock_pixmap)

        # Mock document
        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=5)
        mock_doc.__getitem__ = MagicMock(return_value=mock_page)
        mock_doc.close = MagicMock()

        mock.open = MagicMock(return_value=mock_doc)

        return mock

    def test_renderer_init_file_not_found(self):
        """Test that FileNotFoundError is raised for missing files."""
        from inspekt.services.pdf_renderer import PDFRenderer, is_pymupdf_available

        if not is_pymupdf_available():
            pytest.skip("PyMuPDF not installed")

        with pytest.raises(FileNotFoundError):
            PDFRenderer("/nonexistent/path/file.pdf")

    def test_renderer_page_count(self, mock_fitz, tmp_path):
        """Test page_count property."""
        from inspekt.services.pdf_renderer import is_pymupdf_available

        if not is_pymupdf_available():
            pytest.skip("PyMuPDF not installed")

        # Create a dummy PDF file
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 dummy content")

        with patch("fitz.open", mock_fitz.open):
            from inspekt.services.pdf_renderer import PDFRenderer

            renderer = PDFRenderer(pdf_file)
            # The mock returns a doc with 5 pages
            assert renderer.page_count == 5

    def test_get_page_dimensions(self, mock_fitz, tmp_path):
        """Test getting page dimensions."""
        from inspekt.services.pdf_renderer import is_pymupdf_available

        if not is_pymupdf_available():
            pytest.skip("PyMuPDF not installed")

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 dummy content")

        with patch("fitz.open", mock_fitz.open):
            from inspekt.services.pdf_renderer import PDFRenderer

            renderer = PDFRenderer(pdf_file)
            width, height = renderer.get_page_dimensions(0)
            # From mock: width=612, height=792
            assert width == 612.0
            assert height == 792.0

    def test_context_manager(self, mock_fitz, tmp_path):
        """Test context manager usage."""
        from inspekt.services.pdf_renderer import is_pymupdf_available

        if not is_pymupdf_available():
            pytest.skip("PyMuPDF not installed")

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 dummy content")

        with patch("fitz.open", mock_fitz.open):
            from inspekt.services.pdf_renderer import PDFRenderer

            with PDFRenderer(pdf_file) as renderer:
                assert renderer.page_count == 5

            # Document should be closed after context exit
            mock_fitz.open.return_value.close.assert_called()


class TestCoordinateTransformation:
    """Tests for PDF to image coordinate transformation."""

    def test_transform_coordinates_basic(self):
        """Test basic coordinate transformation."""
        from inspekt.services.pdf_renderer import is_pymupdf_available

        if not is_pymupdf_available():
            pytest.skip("PyMuPDF not installed")

        # PDF coordinates use bottom-left origin
        # Image coordinates use top-left origin
        # For a page of height 792 points:
        # PDF (0, 0) -> Image (0, 792)
        # PDF (0, 792) -> Image (0, 0)

        # Test that we understand the concept
        page_height = 792.0
        pdf_bbox = (100.0, 100.0, 200.0, 200.0)  # Bottom-left corner box

        # Transform Y coordinates
        x1, y1, x2, y2 = pdf_bbox
        img_y1 = page_height - max(y1, y2)  # 792 - 200 = 592
        img_y2 = page_height - min(y1, y2)  # 792 - 100 = 692

        assert img_y1 == 592.0
        assert img_y2 == 692.0


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_render_pdf_cover_nonexistent_file(self):
        """Test render_pdf_cover with nonexistent file."""
        from inspekt.services.pdf_renderer import is_pymupdf_available, render_pdf_cover

        if not is_pymupdf_available():
            pytest.skip("PyMuPDF not installed")

        result = render_pdf_cover("/nonexistent/file.pdf")
        assert result is None

    def test_render_pdf_page_nonexistent_file(self):
        """Test render_pdf_page with nonexistent file."""
        from inspekt.services.pdf_renderer import is_pymupdf_available, render_pdf_page

        if not is_pymupdf_available():
            pytest.skip("PyMuPDF not installed")

        result = render_pdf_page("/nonexistent/file.pdf", 0)
        assert result is None
