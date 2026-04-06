"""
PDF Test Fixtures.

This module provides fixtures for PDF accessibility testing.
It generates minimal PDF files with known characteristics for testing.
"""

from __future__ import annotations

import pytest
from pathlib import Path


@pytest.fixture(scope="session")
def pdf_fixtures_dir(tmp_path_factory) -> Path:
    """Create a temporary directory for PDF test fixtures."""
    return tmp_path_factory.mktemp("pdf_fixtures")


@pytest.fixture(scope="session")
def accessible_pdf(pdf_fixtures_dir) -> Path:
    """Create an accessible PDF that passes all basic checks."""
    import pikepdf

    pdf_path = pdf_fixtures_dir / "accessible.pdf"

    with pikepdf.new() as pdf:
        # Add a page with text content
        page = pikepdf.Page(pikepdf.Dictionary({
            "/Type": pikepdf.Name("/Page"),
            "/MediaBox": [0, 0, 612, 792],
            "/Contents": pdf.make_stream(b"BT /F1 12 Tf 100 700 Td (Hello World) Tj ET"),
            "/Resources": pikepdf.Dictionary({
                "/Font": pikepdf.Dictionary({
                    "/F1": pikepdf.Dictionary({
                        "/Type": pikepdf.Name("/Font"),
                        "/Subtype": pikepdf.Name("/Type1"),
                        "/BaseFont": pikepdf.Name("/Helvetica"),
                    })
                })
            })
        }))
        pdf.pages.append(page)

        # Make it tagged
        pdf.Root["/MarkInfo"] = pikepdf.Dictionary({
            "/Marked": True
        })
        pdf.Root["/StructTreeRoot"] = pikepdf.Dictionary({
            "/Type": pikepdf.Name("/StructTreeRoot"),
            "/K": pikepdf.Array([])
        })

        # Set title with DisplayDocTitle
        pdf.docinfo["/Title"] = "Accessible Test Document"
        pdf.Root["/ViewerPreferences"] = pikepdf.Dictionary({
            "/DisplayDocTitle": True
        })

        # Set language
        pdf.Root["/Lang"] = "en-US"

        pdf.save(pdf_path)

    return pdf_path


@pytest.fixture(scope="session")
def untagged_pdf(pdf_fixtures_dir) -> Path:
    """Create an untagged PDF (no structure tree)."""
    import pikepdf

    pdf_path = pdf_fixtures_dir / "untagged.pdf"

    with pikepdf.new() as pdf:
        # Add a page with text content
        page = pikepdf.Page(pikepdf.Dictionary({
            "/Type": pikepdf.Name("/Page"),
            "/MediaBox": [0, 0, 612, 792],
            "/Contents": pdf.make_stream(b"BT /F1 12 Tf 100 700 Td (Hello World) Tj ET"),
            "/Resources": pikepdf.Dictionary({
                "/Font": pikepdf.Dictionary({
                    "/F1": pikepdf.Dictionary({
                        "/Type": pikepdf.Name("/Font"),
                        "/Subtype": pikepdf.Name("/Type1"),
                        "/BaseFont": pikepdf.Name("/Helvetica"),
                    })
                })
            })
        }))
        pdf.pages.append(page)

        # No MarkInfo or StructTreeRoot - untagged

        # Set other properties
        pdf.docinfo["/Title"] = "Untagged Test Document"
        pdf.Root["/ViewerPreferences"] = pikepdf.Dictionary({
            "/DisplayDocTitle": True
        })
        pdf.Root["/Lang"] = "en-US"

        pdf.save(pdf_path)

    return pdf_path


@pytest.fixture(scope="session")
def no_title_pdf(pdf_fixtures_dir) -> Path:
    """Create a PDF without a title."""
    import pikepdf

    pdf_path = pdf_fixtures_dir / "no_title.pdf"

    with pikepdf.new() as pdf:
        # Add a page
        page = pikepdf.Page(pikepdf.Dictionary({
            "/Type": pikepdf.Name("/Page"),
            "/MediaBox": [0, 0, 612, 792],
            "/Contents": pdf.make_stream(b"BT /F1 12 Tf 100 700 Td (No Title Document) Tj ET"),
            "/Resources": pikepdf.Dictionary({
                "/Font": pikepdf.Dictionary({
                    "/F1": pikepdf.Dictionary({
                        "/Type": pikepdf.Name("/Font"),
                        "/Subtype": pikepdf.Name("/Type1"),
                        "/BaseFont": pikepdf.Name("/Helvetica"),
                    })
                })
            })
        }))
        pdf.pages.append(page)

        # Make it tagged
        pdf.Root["/MarkInfo"] = pikepdf.Dictionary({"/Marked": True})
        pdf.Root["/StructTreeRoot"] = pikepdf.Dictionary({
            "/Type": pikepdf.Name("/StructTreeRoot"),
            "/K": pikepdf.Array([])
        })

        # No title - docinfo is empty
        pdf.Root["/Lang"] = "en-US"

        pdf.save(pdf_path)

    return pdf_path


@pytest.fixture(scope="session")
def no_language_pdf(pdf_fixtures_dir) -> Path:
    """Create a PDF without a language."""
    import pikepdf

    pdf_path = pdf_fixtures_dir / "no_language.pdf"

    with pikepdf.new() as pdf:
        # Add a page
        page = pikepdf.Page(pikepdf.Dictionary({
            "/Type": pikepdf.Name("/Page"),
            "/MediaBox": [0, 0, 612, 792],
            "/Contents": pdf.make_stream(b"BT /F1 12 Tf 100 700 Td (No Language Document) Tj ET"),
            "/Resources": pikepdf.Dictionary({
                "/Font": pikepdf.Dictionary({
                    "/F1": pikepdf.Dictionary({
                        "/Type": pikepdf.Name("/Font"),
                        "/Subtype": pikepdf.Name("/Type1"),
                        "/BaseFont": pikepdf.Name("/Helvetica"),
                    })
                })
            })
        }))
        pdf.pages.append(page)

        # Make it tagged
        pdf.Root["/MarkInfo"] = pikepdf.Dictionary({"/Marked": True})
        pdf.Root["/StructTreeRoot"] = pikepdf.Dictionary({
            "/Type": pikepdf.Name("/StructTreeRoot"),
            "/K": pikepdf.Array([])
        })

        # Set title
        pdf.docinfo["/Title"] = "No Language Test"
        pdf.Root["/ViewerPreferences"] = pikepdf.Dictionary({"/DisplayDocTitle": True})

        # No language - /Lang not set

        pdf.save(pdf_path)

    return pdf_path


@pytest.fixture(scope="session")
def invalid_language_pdf(pdf_fixtures_dir) -> Path:
    """Create a PDF with an invalid language code."""
    import pikepdf

    pdf_path = pdf_fixtures_dir / "invalid_language.pdf"

    with pikepdf.new() as pdf:
        # Add a page
        page = pikepdf.Page(pikepdf.Dictionary({
            "/Type": pikepdf.Name("/Page"),
            "/MediaBox": [0, 0, 612, 792],
            "/Contents": pdf.make_stream(b"BT /F1 12 Tf 100 700 Td (Invalid Language) Tj ET"),
            "/Resources": pikepdf.Dictionary({
                "/Font": pikepdf.Dictionary({
                    "/F1": pikepdf.Dictionary({
                        "/Type": pikepdf.Name("/Font"),
                        "/Subtype": pikepdf.Name("/Type1"),
                        "/BaseFont": pikepdf.Name("/Helvetica"),
                    })
                })
            })
        }))
        pdf.pages.append(page)

        # Make it tagged
        pdf.Root["/MarkInfo"] = pikepdf.Dictionary({"/Marked": True})
        pdf.Root["/StructTreeRoot"] = pikepdf.Dictionary({
            "/Type": pikepdf.Name("/StructTreeRoot"),
            "/K": pikepdf.Array([])
        })

        # Set title
        pdf.docinfo["/Title"] = "Invalid Language Test"
        pdf.Root["/ViewerPreferences"] = pikepdf.Dictionary({"/DisplayDocTitle": True})

        # Invalid language code
        pdf.Root["/Lang"] = "xyz-123-invalid"

        pdf.save(pdf_path)

    return pdf_path


@pytest.fixture(scope="session")
def with_forms_pdf(pdf_fixtures_dir) -> Path:
    """Create a PDF with AcroForm fields."""
    import pikepdf

    pdf_path = pdf_fixtures_dir / "with_forms.pdf"

    with pikepdf.new() as pdf:
        # Add a page
        page = pikepdf.Page(pikepdf.Dictionary({
            "/Type": pikepdf.Name("/Page"),
            "/MediaBox": [0, 0, 612, 792],
            "/Contents": pdf.make_stream(b"BT /F1 12 Tf 100 700 Td (Form Document) Tj ET"),
            "/Resources": pikepdf.Dictionary({
                "/Font": pikepdf.Dictionary({
                    "/F1": pikepdf.Dictionary({
                        "/Type": pikepdf.Name("/Font"),
                        "/Subtype": pikepdf.Name("/Type1"),
                        "/BaseFont": pikepdf.Name("/Helvetica"),
                    })
                })
            })
        }))
        pdf.pages.append(page)

        # Make it tagged
        pdf.Root["/MarkInfo"] = pikepdf.Dictionary({"/Marked": True})
        pdf.Root["/StructTreeRoot"] = pikepdf.Dictionary({
            "/Type": pikepdf.Name("/StructTreeRoot"),
            "/K": pikepdf.Array([])
        })

        # Set title and language
        pdf.docinfo["/Title"] = "Form Test Document"
        pdf.Root["/ViewerPreferences"] = pikepdf.Dictionary({"/DisplayDocTitle": True})
        pdf.Root["/Lang"] = "en-US"

        # Add AcroForm with fields
        text_field = pikepdf.Dictionary({
            "/Type": pikepdf.Name("/Annot"),
            "/Subtype": pikepdf.Name("/Widget"),
            "/FT": pikepdf.Name("/Tx"),
            "/T": "name_field",
            "/Rect": [100, 600, 300, 620],
        })

        pdf.Root["/AcroForm"] = pikepdf.Dictionary({
            "/Fields": pikepdf.Array([text_field]),
        })

        pdf.save(pdf_path)

    return pdf_path


@pytest.fixture(scope="session")
def with_xmp_pdf(pdf_fixtures_dir) -> Path:
    """Create a PDF with XMP metadata."""
    import pikepdf

    pdf_path = pdf_fixtures_dir / "with_xmp.pdf"

    with pikepdf.new() as pdf:
        # Add a page
        page = pikepdf.Page(pikepdf.Dictionary({
            "/Type": pikepdf.Name("/Page"),
            "/MediaBox": [0, 0, 612, 792],
            "/Contents": pdf.make_stream(b"BT /F1 12 Tf 100 700 Td (XMP Metadata Document) Tj ET"),
            "/Resources": pikepdf.Dictionary({
                "/Font": pikepdf.Dictionary({
                    "/F1": pikepdf.Dictionary({
                        "/Type": pikepdf.Name("/Font"),
                        "/Subtype": pikepdf.Name("/Type1"),
                        "/BaseFont": pikepdf.Name("/Helvetica"),
                    })
                })
            })
        }))
        pdf.pages.append(page)

        # Make it tagged
        pdf.Root["/MarkInfo"] = pikepdf.Dictionary({"/Marked": True})
        pdf.Root["/StructTreeRoot"] = pikepdf.Dictionary({
            "/Type": pikepdf.Name("/StructTreeRoot"),
            "/K": pikepdf.Array([])
        })

        # Set title and language
        pdf.docinfo["/Title"] = "XMP Test Document"
        pdf.Root["/ViewerPreferences"] = pikepdf.Dictionary({"/DisplayDocTitle": True})
        pdf.Root["/Lang"] = "en-US"

        # Add XMP metadata
        xmp_content = b'''<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:Description rdf:about=""
      xmlns:dc="http://purl.org/dc/elements/1.1/"
      xmlns:xmp="http://ns.adobe.com/xap/1.0/">
      <dc:title><rdf:Alt><rdf:li xml:lang="x-default">XMP Test Document</rdf:li></rdf:Alt></dc:title>
      <dc:creator><rdf:Seq><rdf:li>Test Author</rdf:li></rdf:Seq></dc:creator>
      <dc:description><rdf:Alt><rdf:li xml:lang="x-default">A test document with XMP metadata</rdf:li></rdf:Alt></dc:description>
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>'''

        xmp_stream = pdf.make_stream(xmp_content)
        xmp_stream["/Type"] = pikepdf.Name("/Metadata")
        xmp_stream["/Subtype"] = pikepdf.Name("/XML")
        pdf.Root["/Metadata"] = xmp_stream

        pdf.save(pdf_path)

    return pdf_path


@pytest.fixture(scope="session")
def long_no_bookmarks_pdf(pdf_fixtures_dir) -> Path:
    """Create a 25-page PDF without bookmarks."""
    import pikepdf

    pdf_path = pdf_fixtures_dir / "long_no_bookmarks.pdf"

    with pikepdf.new() as pdf:
        # Add 25 pages
        for i in range(25):
            page = pikepdf.Page(pikepdf.Dictionary({
                "/Type": pikepdf.Name("/Page"),
                "/MediaBox": [0, 0, 612, 792],
                "/Contents": pdf.make_stream(f"BT /F1 12 Tf 100 700 Td (Page {i + 1}) Tj ET".encode()),
                "/Resources": pikepdf.Dictionary({
                    "/Font": pikepdf.Dictionary({
                        "/F1": pikepdf.Dictionary({
                            "/Type": pikepdf.Name("/Font"),
                            "/Subtype": pikepdf.Name("/Type1"),
                            "/BaseFont": pikepdf.Name("/Helvetica"),
                        })
                    })
                })
            }))
            pdf.pages.append(page)

        # Make it tagged
        pdf.Root["/MarkInfo"] = pikepdf.Dictionary({"/Marked": True})
        pdf.Root["/StructTreeRoot"] = pikepdf.Dictionary({
            "/Type": pikepdf.Name("/StructTreeRoot"),
            "/K": pikepdf.Array([])
        })

        # Set title and language
        pdf.docinfo["/Title"] = "Long Document Without Bookmarks"
        pdf.Root["/ViewerPreferences"] = pikepdf.Dictionary({"/DisplayDocTitle": True})
        pdf.Root["/Lang"] = "en-US"

        # No bookmarks (/Outlines not set)

        pdf.save(pdf_path)

    return pdf_path


@pytest.fixture(scope="session")
def all_pdf_fixtures(
    accessible_pdf,
    untagged_pdf,
    no_title_pdf,
    no_language_pdf,
    invalid_language_pdf,
    with_forms_pdf,
    with_xmp_pdf,
    long_no_bookmarks_pdf,
) -> list[Path]:
    """Return a list of all PDF test fixtures."""
    return [
        accessible_pdf,
        untagged_pdf,
        no_title_pdf,
        no_language_pdf,
        invalid_language_pdf,
        with_forms_pdf,
        with_xmp_pdf,
        long_no_bookmarks_pdf,
    ]
