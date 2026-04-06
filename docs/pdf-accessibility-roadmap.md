# PDF Accessibility Roadmap

Research documentation for expanding Inspekt's PDF accessibility auditing capabilities.

---

## Executive Summary

### Top 3 Insights

1. **Strong Foundation with Gaps**: Inspekt covers 70% of PDF accessibility requirements through its two-tier checking system (basic pikepdf checks + veraPDF integration), but lacks native checks for color contrast, reflow behavior, and advanced infographic analysis.

2. **Matterhorn Protocol Advantage**: With 40+ Matterhorn Protocol checkpoints already mapped to WCAG criteria in `pdfua_wcag_mapping.json`, Inspekt can provide excellent compliance reporting. The gap lies in user-friendly remediation guidance for complex violations.

3. **Quick Wins Available**: Three features (list semantics checking, heading hierarchy visualization, and annotation accessibility) can be implemented with low effort by extending existing patterns in `pdf_content_auditor.py` and `pdf_structure_extractor.py`.

### Current Coverage Assessment

| Coverage Level | Count | Categories |
|----------------|-------|------------|
| **Fully Covered** | 8 | Tagged content, alt text, form fields, language, bookmarks, structural elements, logical headings, annotations (partial) |
| **Partially Covered** | 6 | Reading order, tables, infographics, TOC, interactivity, artifact usage, list semantics |
| **Not Covered** | 4 | Reflow, color contrast, color usage, comprehensive infographic detection |

### Recommended Priority Investments

1. **High Priority**: Color contrast analysis for text in PDFs (WCAG 1.4.3, 1.4.6)
2. **Medium Priority**: Enhanced reading order visualization with export capabilities
3. **Low Priority**: Reflow validation (requires complex rendering analysis)

### Quick Wins for Immediate Implementation

1. List semantics checking - extend `pdf_structure_extractor.py`
2. Heading hierarchy visualization - build on existing validation in `pdf_structure_extractor.py`
3. Basic annotation accessibility - extend `pdf_content_auditor.py` link audit pattern

---

## PDF Accessibility Failure Catalogue

### 1. Reading Order

**Description of Accessibility Harm**
When reading order doesn't match visual layout, screen readers present content in a confusing sequence. Multi-column layouts, sidebars, and floating elements frequently cause reading order problems.

**Standards References**
| Standard | Reference |
|----------|-----------|
| WCAG 2.x | [1.3.2 Meaningful Sequence (Level A)](https://www.w3.org/WAI/WCAG21/Understanding/meaningful-sequence) |
| EN 301 549 | 10.1.3.2 Meaningful Sequence |
| PDF/UA-1 | Clause 7.1 (General), 7.10 (Optional content) |
| Matterhorn | 19-001, 19-002, 19-003 |

**Current Inspekt Coverage**: Partially covered
- `pdf_structure_extractor.py:100-114` - `ReadingOrderItem` class extracts reading sequence
- `pdf_structure_extractor.py:368-377` - Reading order list generation
- Validation: Basic presence check, no visual alignment comparison

**Detection Methods**
- Automated: Compare tag order vs visual layout coordinates (not yet implemented)
- Manual: Screen reader testing, reading order panel in Acrobat
- PDF/UA validation: veraPDF checks via Matterhorn 19-001, 19-002

**Remediation Guidance**
Use Adobe Acrobat's Reading Order tool (Tools > Accessibility > Reading Order) or reorder tags in the Tags panel. For complex layouts, recreate from source with proper accessibility settings.

---

### 2. Tables

**Description of Accessibility Harm**
Data tables without proper header cells and scope attributes are incomprehensible to screen reader users who cannot see the visual relationship between headers and data cells.

**Standards References**
| Standard | Reference |
|----------|-----------|
| WCAG 2.x | [1.3.1 Info and Relationships (Level A)](https://www.w3.org/WAI/WCAG21/Understanding/info-and-relationships) |
| EN 301 549 | 10.1.3.1 Info and Relationships |
| PDF/UA-1 | Clause 7.5 (Tables) |
| Matterhorn | 12-001, 12-002 |

**Current Inspekt Coverage**: Fully covered
- `pdf_content_auditor.py:77-114` - `TableAudit` class
- `pdf_content_auditor.py:588-718` - `_audit_tables()` and `_analyze_table()`
- veraPDF: Full table structure validation via PDF/UA profile

**Detection Methods**
- Automated: Structure tree analysis for TH/TD tags, scope attributes
- Automated: veraPDF validates Matterhorn 12-001, 12-002
- Manual: Screen reader testing with JAWS/NVDA

**Remediation Guidance**
Mark header cells with TH tags in the Tags panel. For complex tables, add scope (Row/Column/Both) or use ID/Headers attributes. Documented in `remediation_planner.py:313-326`.

---

### 3. Reflow

**Description of Accessibility Harm**
PDFs that don't reflow properly force users with low vision to scroll horizontally at high zoom levels, causing significant usability barriers.

**Standards References**
| Standard | Reference |
|----------|-----------|
| WCAG 2.x | [1.4.10 Reflow (Level AA)](https://www.w3.org/WAI/WCAG21/Understanding/reflow) |
| EN 301 549 | 10.1.4.10 Reflow |
| PDF/UA-1 | Not directly addressed (viewer responsibility) |
| Matterhorn | N/A |

**Current Inspekt Coverage**: **Not covered**
- Reflow is a rendering behavior, not a static document property
- Would require PDF viewer integration or rendering simulation

**Detection Methods**
- Manual: Test reflow behavior in Adobe Reader with View > Zoom > Reflow
- Automated: No reliable automated detection exists; would require rendering engine

**Remediation Guidance**
Ensure proper tag structure with logical reading order. Avoid fixed positioning. Use accessible authoring tools that support reflow. Consider providing alternative HTML version.

---

### 4. Color Contrast

**Description of Accessibility Harm**
Text with insufficient contrast against its background is difficult or impossible to read for users with low vision, color blindness, or in poor lighting conditions.

**Standards References**
| Standard | Reference |
|----------|-----------|
| WCAG 2.x | [1.4.3 Contrast (Minimum) (Level AA)](https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum), [1.4.6 Contrast (Enhanced) (Level AAA)](https://www.w3.org/WAI/WCAG21/Understanding/contrast-enhanced) |
| EN 301 549 | 10.1.4.3 Contrast (Minimum), 10.1.4.6 Contrast (Enhanced) |
| PDF/UA-1 | Not directly addressed |
| Matterhorn | N/A |

**Current Inspekt Coverage**: **Not covered**
- Would require extracting text foreground colors and background colors
- Complex due to transparency, images as backgrounds, gradients

**Detection Methods**
- Automated: Extract text color and underlying background, calculate contrast ratio
- Semi-automated: Tools like [PAC (PDF Accessibility Checker)](https://pac.pdf-accessibility.org/) provide some contrast checking
- Manual: Visual inspection, color picker tools

**Remediation Guidance**
Ensure text meets 4.5:1 contrast ratio (3:1 for large text). Use solid backgrounds behind text. Avoid text over images without contrast overlay.

---

### 5. Infographics

**Description of Accessibility Harm**
Complex infographics, charts, and diagrams without adequate text alternatives exclude users who cannot perceive visual information.

**Standards References**
| Standard | Reference |
|----------|-----------|
| WCAG 2.x | [1.1.1 Non-text Content (Level A)](https://www.w3.org/WAI/WCAG21/Understanding/non-text-content) |
| EN 301 549 | 10.1.1.1 Non-text Content |
| PDF/UA-1 | Clause 7.3 (Graphics) |
| Matterhorn | 06-001, 06-002, 06-003 |

**Current Inspekt Coverage**: Partially covered
- `pdf_content_auditor.py:42-74` - `ImageAudit` class checks for alt text
- `pdf_content_auditor.py:478-533` - `_audit_images()` detects images without alt
- Gap: No detection of whether image is simple vs complex infographic

**Detection Methods**
- Automated: Detect images lacking alt text (implemented)
- Automated: Image complexity heuristics (not implemented)
- Manual: Review whether alt text adequately describes complex graphics

**Remediation Guidance**
Provide concise alt text for simple images. For complex infographics, provide both brief alt text and long description (adjacent text or linked document). Documented in `remediation_planner.py:293-308`.

---

### 6. Table of Contents

**Description of Accessibility Harm**
Long documents without a navigable table of contents force users to scroll through entire documents to find specific sections, creating significant barriers for keyboard and screen reader users.

**Standards References**
| Standard | Reference |
|----------|-----------|
| WCAG 2.x | [2.4.5 Multiple Ways (Level AA)](https://www.w3.org/WAI/WCAG21/Understanding/multiple-ways) |
| EN 301 549 | 10.2.4.5 Multiple Ways |
| PDF/UA-1 | Clause 7.17 (Navigation) |
| Matterhorn | 17-001, 17-002, 17-003 |

**Current Inspekt Coverage**: Partially covered (bookmarks only)
- `pdf_checker.py:693-745` - `_check_bookmarks()` checks for outline presence
- Gap: No TOC tag structure validation (TOCI elements)
- Gap: No verification that TOC links work correctly

**Detection Methods**
- Automated: Check for bookmarks (implemented)
- Automated: Check for TOC/TOCI structure elements (not implemented)
- Manual: Verify TOC links navigate correctly

**Remediation Guidance**
Create bookmarks from heading structure. For formal TOC, use TOC and TOCI tags. Ensure internal links point to correct destinations.

---

### 7. Interactivity (JavaScript/Actions)

**Description of Accessibility Harm**
Automatic actions, JavaScript that modifies content without user consent, and actions without keyboard alternatives create barriers for assistive technology users.

**Standards References**
| Standard | Reference |
|----------|-----------|
| WCAG 2.x | [3.2.5 Change on Request (Level AAA)](https://www.w3.org/WAI/WCAG21/Understanding/change-on-request) |
| EN 301 549 | 10.3.2.5 Change on Request |
| PDF/UA-1 | Clause 7.19 (Actions) |
| Matterhorn | N/A (machine-testable aspects limited) |

**Current Inspekt Coverage**: Partially covered
- `pdf_checker.py:98-110` - XFA form detection (forms check)
- veraPDF: Some action validation via PDF/UA profile
- Gap: No JavaScript analysis or action impact assessment

**Detection Methods**
- Automated: Detect presence of JavaScript (not implemented)
- Automated: Detect automatic page/document actions (not implemented)
- Manual: Test document behavior with JavaScript disabled

**Remediation Guidance**
Avoid automatic actions. Provide user controls for any dynamic content. Ensure all functionality available via keyboard. Document any JavaScript dependencies.

---

### 8. Tagged Content

**Description of Accessibility Harm**
Untagged PDFs are completely inaccessible to screen readers, which rely on the tag structure to understand document content and hierarchy.

**Standards References**
| Standard | Reference |
|----------|-----------|
| WCAG 2.x | [1.3.1 Info and Relationships (Level A)](https://www.w3.org/WAI/WCAG21/Understanding/info-and-relationships), [4.1.2 Name, Role, Value (Level A)](https://www.w3.org/WAI/WCAG21/Understanding/name-role-value) |
| EN 301 549 | 10.1.3.1 Info and Relationships, 10.4.1.2 Name, Role, Value |
| PDF/UA-1 | Clause 7.1 (General) |
| Matterhorn | 01-001 through 01-007 |

**Current Inspekt Coverage**: Fully covered
- `pdf_checker.py:530-571` - `_check_tagged()` validates MarkInfo/Marked and StructTreeRoot
- `pdf_structure_extractor.py` - Complete structure tree extraction
- veraPDF: Full tagged PDF validation

**Detection Methods**
- Automated: Check for MarkInfo/Marked and StructTreeRoot (implemented)
- Automated: veraPDF validates all Matterhorn 01-xxx checkpoints

**Remediation Guidance**
Re-export from source with accessibility settings enabled, or use Adobe Acrobat's Autotag feature. Documented in `remediation_planner.py:195-210`.

---

### 9. Alternative Text

**Description of Accessibility Harm**
Images without alternative text convey no information to screen reader users, excluding them from understanding visual content.

**Standards References**
| Standard | Reference |
|----------|-----------|
| WCAG 2.x | [1.1.1 Non-text Content (Level A)](https://www.w3.org/WAI/WCAG21/Understanding/non-text-content) |
| EN 301 549 | 10.1.1.1 Non-text Content |
| PDF/UA-1 | Clause 7.3 (Graphics) |
| Matterhorn | 06-001, 06-002, 06-003 |

**Current Inspekt Coverage**: Fully covered
- `pdf_content_auditor.py:478-533` - `_audit_images()` checks alt text
- `pdf_content_auditor.py:535-586` - `_extract_figure_alt_texts()` from structure tree
- `pdf_structure_extractor.py:473-492` - Validates Figure elements have alt text
- veraPDF: Validates Matterhorn 06-001, 06-002, 06-003

**Detection Methods**
- Automated: Check Figure tags for /Alt attribute (implemented)
- Automated: veraPDF validates alt text requirements
- Manual: Review alt text quality and appropriateness

**Remediation Guidance**
Use Set Alternate Text tool in Acrobat (Tools > Accessibility > Set Alternate Text). Mark decorative images as artifacts. Documented in `remediation_planner.py:293-308`.

---

### 10. Form Fields

**Description of Accessibility Harm**
Form fields without accessible names prevent screen reader users from understanding what information to enter, making forms unusable.

**Standards References**
| Standard | Reference |
|----------|-----------|
| WCAG 2.x | [1.3.1 Info and Relationships (Level A)](https://www.w3.org/WAI/WCAG21/Understanding/info-and-relationships), [4.1.2 Name, Role, Value (Level A)](https://www.w3.org/WAI/WCAG21/Understanding/name-role-value) |
| EN 301 549 | 10.1.3.1 Info and Relationships, 10.4.1.2 Name, Role, Value |
| PDF/UA-1 | Clause 7.6 (Lists), 7.13-7.15 (Forms) |
| Matterhorn | 14-001 through 14-007 |

**Current Inspekt Coverage**: Fully covered
- `pdf_content_auditor.py:117-152` - `FormFieldAudit` class
- `pdf_content_auditor.py:719-826` - `_audit_forms()` checks labels, tooltips
- `pdf_checker.py:86-110` - AcroForm and XFA detection in `pdf_checks.json`
- veraPDF: Validates Matterhorn 14-xxx checkpoints

**Detection Methods**
- Automated: Check for /TU (tooltip) entry (implemented)
- Automated: Check field name and label association (implemented)
- Automated: veraPDF validates form accessibility

**Remediation Guidance**
Add tooltip (TU entry) to each form field. Set logical tab order. Documented in `remediation_planner.py:328-345`.

---

### 11. Annotations

**Description of Accessibility Harm**
Link annotations and other annotations without accessible descriptions are not perceivable to screen reader users.

**Standards References**
| Standard | Reference |
|----------|-----------|
| WCAG 2.x | [1.1.1 Non-text Content (Level A)](https://www.w3.org/WAI/WCAG21/Understanding/non-text-content), [2.4.4 Link Purpose (Level A)](https://www.w3.org/WAI/WCAG21/Understanding/link-purpose-in-context) |
| EN 301 549 | 10.1.1.1 Non-text Content, 10.2.4.4 Link Purpose |
| PDF/UA-1 | Clause 7.18 (Annotations) |
| Matterhorn | 11-001 through 11-006 |

**Current Inspekt Coverage**: Partially covered (links only)
- `pdf_content_auditor.py:155-191` - `LinkAudit` class
- `pdf_content_auditor.py:828-900` - `_audit_links()` checks link text
- Gap: Other annotation types (notes, highlights, stamps) not audited

**Detection Methods**
- Automated: Check link text and Contents entry (partially implemented)
- Automated: veraPDF validates Matterhorn 11-xxx checkpoints
- Manual: Test link navigation with screen reader

**Remediation Guidance**
Add Contents or Alt entry to link annotations. Ensure visible link text is descriptive. Wrap annotations in appropriate Link structure elements.

---

### 12. Language Settings

**Description of Accessibility Harm**
Missing document language causes screen readers to use wrong pronunciation, making content incomprehensible. Unmarked language changes within content cause similar issues.

**Standards References**
| Standard | Reference |
|----------|-----------|
| WCAG 2.x | [3.1.1 Language of Page (Level A)](https://www.w3.org/WAI/WCAG21/Understanding/language-of-page), [3.1.2 Language of Parts (Level AA)](https://www.w3.org/WAI/WCAG21/Understanding/language-of-parts) |
| EN 301 549 | 10.3.1.1 Language of Page, 10.3.1.2 Language of Parts |
| PDF/UA-1 | Clause 7.2 (Text) |
| Matterhorn | 02-001, 02-002, 02-003 |

**Current Inspekt Coverage**: Fully covered
- `pdf_checker.py:625-656` - `_check_language()` validates /Lang in catalog
- `pdfua_wcag_mapping.json:298-321` - Matterhorn mappings for language checks
- veraPDF: Validates Matterhorn 02-001, 02-002, 02-003

**Detection Methods**
- Automated: Check /Lang entry in document catalog (implemented)
- Automated: veraPDF validates language requirements
- Manual: Verify language changes within content have /Lang attribute

**Remediation Guidance**
Set document language in File > Properties > Advanced. Add /Lang attribute to structure elements containing different language text. Documented in `remediation_planner.py:227-241`.

---

### 13. Bookmarks

**Description of Accessibility Harm**
Long documents without bookmarks require users to navigate page-by-page, creating significant barriers for efficient document navigation.

**Standards References**
| Standard | Reference |
|----------|-----------|
| WCAG 2.x | [2.4.5 Multiple Ways (Level AA)](https://www.w3.org/WAI/WCAG21/Understanding/multiple-ways) |
| EN 301 549 | 10.2.4.5 Multiple Ways |
| PDF/UA-1 | Clause 7.17 (Navigation) |
| Matterhorn | 17-001, 17-002, 17-003 |

**Current Inspekt Coverage**: Fully covered
- `pdf_checker.py:693-745` - `_check_bookmarks()` validates /Outlines
- `pdf_checks.json:59-71` - Check definition with 20-page threshold
- veraPDF: Validates bookmark structure

**Detection Methods**
- Automated: Check for /Outlines entry and bookmark count (implemented)
- Automated: veraPDF validates Matterhorn 17-xxx checkpoints

**Remediation Guidance**
Create bookmarks from heading structure using Acrobat's New Bookmarks from Structure feature. Documented in `remediation_planner.py:259-273`.

---

### 14. Structural Elements

**Description of Accessibility Harm**
Missing or incorrect structural elements (paragraphs, sections, articles) prevent assistive technologies from conveying document organization.

**Standards References**
| Standard | Reference |
|----------|-----------|
| WCAG 2.x | [1.3.1 Info and Relationships (Level A)](https://www.w3.org/WAI/WCAG21/Understanding/info-and-relationships) |
| EN 301 549 | 10.1.3.1 Info and Relationships |
| PDF/UA-1 | Clause 7.1 (General) |
| Matterhorn | 01-001 through 01-007, ISO-32000-1-14.7 |

**Current Inspekt Coverage**: Fully covered
- `pdf_structure_extractor.py:26-44` - Standard tag definitions
- `pdf_structure_extractor.py:160-280` - Complete structure extraction
- `pdf_structure_extractor.py:494-543` - Statistics calculation
- veraPDF: Full structure validation

**Detection Methods**
- Automated: Extract and validate structure tree (implemented)
- Automated: veraPDF validates structure requirements

**Remediation Guidance**
Use proper structure tags for all content. Map custom tags to standard roles via RoleMap. Ensure Document is root element.

---

### 15. Artifact Usage

**Description of Accessibility Harm**
Decorative content not marked as artifacts is announced by screen readers, creating noise and confusion. Meaningful content incorrectly marked as artifacts is completely hidden.

**Standards References**
| Standard | Reference |
|----------|-----------|
| WCAG 2.x | [1.3.1 Info and Relationships (Level A)](https://www.w3.org/WAI/WCAG21/Understanding/info-and-relationships) |
| EN 301 549 | 10.1.3.1 Info and Relationships |
| PDF/UA-1 | Clause 7.1 (General) |
| Matterhorn | 01-001 |

**Current Inspekt Coverage**: Partially covered
- `pdf_content_auditor.py:513` - Small images assumed decorative
- veraPDF: Validates artifact usage via Matterhorn 01-001
- Gap: No comprehensive artifact audit across all content types

**Detection Methods**
- Automated: veraPDF checks artifact requirements
- Manual: Review headers, footers, watermarks, background images

**Remediation Guidance**
Mark page numbers, headers/footers, watermarks, and decorative elements as artifacts. Ensure all meaningful content is tagged.

---

### 16. Logical Heading Hierarchy

**Description of Accessibility Harm**
Skipped heading levels or improper heading use prevents screen reader users from understanding document structure and navigating by headings.

**Standards References**
| Standard | Reference |
|----------|-----------|
| WCAG 2.x | [1.3.1 Info and Relationships (Level A)](https://www.w3.org/WAI/WCAG21/Understanding/info-and-relationships), [2.4.6 Headings and Labels (Level AA)](https://www.w3.org/WAI/WCAG21/Understanding/headings-and-labels) |
| EN 301 549 | 10.1.3.1 Info and Relationships, 10.2.4.6 Headings and Labels |
| PDF/UA-1 | Clause 7.4 (Headings) |
| Matterhorn | 09-001, 09-002, 09-003, 09-004 |

**Current Inspekt Coverage**: Fully covered
- `pdf_structure_extractor.py:44` - Heading tag definitions
- `pdf_structure_extractor.py:76-91` - `heading_level` property
- `pdf_structure_extractor.py:564-581` - Heading order validation
- veraPDF: Validates Matterhorn 09-xxx checkpoints

**Detection Methods**
- Automated: Check heading sequence for skipped levels (implemented)
- Automated: veraPDF validates heading structure

**Remediation Guidance**
Use H1-H6 tags in logical order. Do not skip levels. Use only one H1 per document. Documented in `remediation_planner.py:365-378`.

---

### 17. List Semantics

**Description of Accessibility Harm**
Content that visually appears as a list but is not tagged as a list prevents screen readers from announcing list structure and item counts.

**Standards References**
| Standard | Reference |
|----------|-----------|
| WCAG 2.x | [1.3.1 Info and Relationships (Level A)](https://www.w3.org/WAI/WCAG21/Understanding/info-and-relationships) |
| EN 301 549 | 10.1.3.1 Info and Relationships |
| PDF/UA-1 | Clause 7.6 (Lists) |
| Matterhorn | 13-001, 13-002 |

**Current Inspekt Coverage**: Partially covered
- `pdf_structure_extractor.py:531-532` - List count in statistics
- `pdfua_wcag_mapping.json:459-474` - Matterhorn 13-001, 13-002 mappings
- veraPDF: Validates list structure
- Gap: No dedicated list audit in content auditor

**Detection Methods**
- Automated: veraPDF validates Matterhorn 13-xxx checkpoints
- Automated: Check L/LI/Lbl/LBody structure (not implemented in content auditor)
- Manual: Compare visual lists with tag structure

**Remediation Guidance**
Use L, LI, Lbl, and LBody tags for all lists. Ensure proper nesting for multi-level lists. Each LI must contain at least Lbl or LBody.

---

### 18. Color Usage

**Description of Accessibility Harm**
Information conveyed only through color is inaccessible to users who are colorblind or cannot perceive color differences.

**Standards References**
| Standard | Reference |
|----------|-----------|
| WCAG 2.x | [1.4.1 Use of Color (Level A)](https://www.w3.org/WAI/WCAG21/Understanding/use-of-color) |
| EN 301 549 | 10.1.4.1 Use of Color |
| PDF/UA-1 | Not directly addressed |
| Matterhorn | N/A |

**Current Inspekt Coverage**: **Not covered**
- Would require semantic analysis of color usage patterns
- Complex to detect programmatically

**Detection Methods**
- Manual: Review charts, forms, and UI elements for color-only indicators
- Semi-automated: Could flag colored text without other indicators (not implemented)

**Remediation Guidance**
Never use color alone to convey information. Add text labels, patterns, or symbols. For form errors, include text explanation alongside red highlighting.

---

## External Tools Inventory

### Open-Source Tools

| Tool | Purpose | Licensing | Integration Notes | Pros | Cons |
|------|---------|-----------|-------------------|------|------|
| [veraPDF](https://verapdf.org/) | PDF/UA-1, PDF/UA-2 validation | Apache 2.0 | **Already integrated** via `pdf_checker.py:837-1295` | Industry standard, comprehensive Matterhorn coverage, actively maintained | Java dependency, slow startup, large output |
| [PAC (PDF Accessibility Checker)](https://pac.pdf-accessibility.org/) | PDF/UA validation with preview | Free (closed source) | Windows executable, would need wrapper | Excellent visual preview, free | Windows only, no API, closed source |
| [axesCheck](https://www.axes4.com/axescheck-cli-overview-en.html) | PDF/UA validation | Commercial with free tier | REST API or CLI available | Fast, cloud-based option | Limited free tier, commercial product |

### Commercial APIs

| Tool | Purpose | Licensing | Integration Notes | Pros | Cons |
|------|---------|-----------|-------------------|------|------|
| [Adobe PDF Services API](https://developer.adobe.com/document-services/apis/pdf-services/) | PDF operations, accessibility tagging | Pay-per-use (~€0,05/transaction) | REST API, good Python SDK | Industry leader, autotag feature | Cost scales with volume, cloud dependency |
| [Apryse SDK](https://apryse.com/) (formerly PDFTron) | Full PDF manipulation | Commercial license | Python bindings available | Comprehensive, fast, no Java | Expensive licensing, vendor lock-in |
| [CommonLook](https://commonlook.com/) | PDF remediation, validation | Commercial license | Desktop application, API available | Best-in-class remediation | High cost, Windows-focused |
| [axesSense](https://www.axes4.com/axessense-overview-en.html) | AI-powered PDF accessibility | Commercial license | REST API | AI-enhanced detection | Commercial, newer product |
| [PDFix](https://pdfix.net/) | PDF repair and accessibility | Commercial license | SDK available | Automated remediation | Commercial licensing |

### Python Libraries

| Tool | Purpose | Licensing | Integration Notes | Pros | Cons |
|------|---------|-----------|-------------------|------|------|
| [pikepdf](https://pikepdf.readthedocs.io/) | Low-level PDF access | MPL 2.0 | **Already integrated** via `pdf_checker.py:404-829` | Fast, comprehensive PDF access, actively maintained | Requires understanding PDF internals |
| [pdfminer.six](https://pdfminersix.readthedocs.io/) | Text extraction | MIT | Could supplement text analysis | Good text extraction | Limited structure access |
| [PyMuPDF (fitz)](https://pymupdf.readthedocs.io/) | PDF rendering, extraction | AGPL-3.0 | **Already integrated** via `pdf_content_auditor.py:258-263` | Fast, good image/link extraction | AGPL license considerations |
| [pypdf](https://pypdf.readthedocs.io/) | PDF manipulation | BSD | Simpler alternative to pikepdf | Easy to use | Less comprehensive than pikepdf |
| [reportlab](https://www.reportlab.com/) | PDF generation | BSD | Could generate accessible PDFs | PDF creation | Not for accessibility checking |

### AI/ML Tools

| Tool | Purpose | Licensing | Integration Notes | Pros | Cons |
|------|---------|-----------|-------------------|------|------|
| Adobe Sensei | AI-powered document analysis | Part of Adobe services | Via PDF Services API | Integrated with Adobe ecosystem | Requires Adobe subscription |
| [Grackle PDF AI](https://grackledocs.com/) | AI-assisted remediation | Commercial | Web-based, API available | Automated alt text generation | Commercial, newer product |
| [Equidox AI](https://equidox.co/) | AI-powered PDF remediation | Commercial | Desktop and cloud | Strong AI remediation features | Expensive licensing |

### Supporting Tools

| Tool | Purpose | Licensing | Integration Notes | Pros | Cons |
|------|---------|-----------|-------------------|------|------|
| [BBC Color Contrast Checker](https://www.bbc.co.uk/accessibility/tools/web-accessibility-toolkit/colour-contrast-checker/) | Color contrast calculation | Open | JavaScript library available | Simple, accurate | Web-focused |
| [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) | OCR for scanned PDFs | Apache 2.0 | **Already integrated** via `pdf_ocr.py` | Best open-source OCR, many languages | Accuracy varies with quality |

---

## Feature Backlog

| Priority | Feature | Problem Addressed | Detection Approach | Remediation Strategy | Complexity | Dependencies | Quick Win |
|----------|---------|-------------------|-------------------|---------------------|------------|--------------|-----------|
| 1 | List semantics checking | Lists not recognized by AT | Check L/LI/Lbl/LBody structure in tag tree | Show list hierarchy, flag invalid structure | Low - Extend `pdf_structure_extractor.py` pattern | None | **Yes** |
| 2 | Heading hierarchy visualization | Hard to spot heading order issues | Generate visual/text outline from headings | Export as tree diagram or markdown outline | Low - Build on existing validation | None | **Yes** |
| 3 | Annotation accessibility audit | Non-link annotations ignored | Audit all annotation types (Note, Highlight, Stamp) | Report annotations lacking accessible names | Low - Extend `pdf_content_auditor.py` pattern | None | **Yes** |
| 4 | TOC structure validation | TOC links may not work | Check TOCI tag structure, verify destinations | Report broken TOC links and structure issues | Medium - Requires destination resolution | pikepdf | No |
| 5 | Form tab order validation | Tab order may be illogical | Extract tab order, compare to visual layout | Visualize tab sequence on page | Medium - Requires coordinate analysis | PyMuPDF | No |
| 6 | Artifact usage validation | Decorative content not marked | Identify headers/footers/watermarks, check artifact status | Report content that should be artifacts | Medium - Requires heuristics for common patterns | pikepdf | No |
| 7 | Enhanced reading order visualization | Hard to verify reading order | Extract reading order, overlay on page rendering | Generate visual reading order diagram | Medium - Requires rendering integration | PyMuPDF | No |
| 8 | Reflow validation | Content doesn't reflow | Simulate reflow rendering, check for horizontal scroll | Report fixed-width elements that break reflow | High - Requires rendering engine or viewer integration | External tool | No |
| 9 | Color contrast analysis | Low contrast text undetected | Extract text colors and backgrounds, calculate ratios | Report text failing 4.5:1 or 3:1 thresholds | High - Complex due to transparency, images, gradients | PyMuPDF, color analysis | No |
| 10 | Infographic complexity detection | Simple alt text for complex graphics | Analyze image content, detect charts/diagrams | Flag complex images needing long descriptions | High - Requires ML/image classification | ML library (optional) | No |

---

## Quick Wins Section

### 1. List Semantics Checking

**Implementation Effort**: Low (2-4 hours)

**Current State**: `pdf_structure_extractor.py` already tracks list count (`stats.list_count`) but doesn't validate list structure.

**Proposed Implementation**:
1. Add `ListAudit` class to `pdf_content_auditor.py` following `TableAudit` pattern
2. Extend `_audit_lists()` method to traverse L/LI/Lbl/LBody structure
3. Validate: LI contains Lbl or LBody, L contains only LI children
4. Add to remediation templates in `remediation_planner.py`

**Files to Modify**:
- `inspekt/services/pdf_content_auditor.py` - Add `ListAudit` class and `_audit_lists()` method
- `inspekt/services/remediation_planner.py` - Add `list_structure` remediation template
- `inspekt/data/pdf_checks.json` - Add `list_structure` check definition

**Value**: Catches Matterhorn 13-001, 13-002 violations locally without veraPDF dependency.

---

### 2. Heading Hierarchy Visualization

**Implementation Effort**: Low (2-4 hours)

**Current State**: `pdf_structure_extractor.py:564-581` validates heading order but doesn't provide visualization.

**Proposed Implementation**:
1. Add `get_heading_outline()` method to `PDFStructureExtractor`
2. Return headings as nested data structure with levels and text
3. Add CLI output option: `inspekt pdf structure --headings`
4. Export formats: indented text, markdown, or JSON

**Files to Modify**:
- `inspekt/services/pdf_structure_extractor.py` - Add `get_heading_outline()` method
- `inspekt/app/cli/pdf.py` - Add `--headings` flag to structure command

**Value**: Provides immediate insight into document structure; useful for both auditing and remediation planning.

---

### 3. Basic Annotation Accessibility

**Implementation Effort**: Low (3-5 hours)

**Current State**: `pdf_content_auditor.py:828-900` audits links only; other annotation types ignored.

**Proposed Implementation**:
1. Add `AnnotationAudit` class for non-link annotations
2. Extend `_audit_annotations()` to check Note, Highlight, Stamp, FileAttachment types
3. Check for Contents, Alt, or T (title) entries
4. Flag annotations lacking accessible descriptions

**Files to Modify**:
- `inspekt/services/pdf_content_auditor.py` - Add `AnnotationAudit` class and `_audit_annotations()` method
- `inspekt/services/remediation_planner.py` - Add annotation remediation template

**Value**: Completes annotation accessibility coverage; addresses Matterhorn 11-xxx violations for all annotation types.

---

## References

### Standards

- **WCAG 2.1/2.2**: [https://www.w3.org/WAI/WCAG21/quickref/](https://www.w3.org/WAI/WCAG21/quickref/)
- **EN 301 549 v3.2.1**: [https://www.etsi.org/deliver/etsi_en/301500_301599/301549/](https://www.etsi.org/deliver/etsi_en/301500_301599/301549/)
- **PDF/UA-1 (ISO 14289-1:2014)**: Available from ISO
- **Matterhorn Protocol 1.1**: [https://www.pdfa.org/resource/the-matterhorn-protocol/](https://www.pdfa.org/resource/the-matterhorn-protocol/)
- **PDF/UA-2 (ISO 14289-2:2024)**: Available from ISO

### Tools Documentation

- **veraPDF**: [https://docs.verapdf.org/](https://docs.verapdf.org/)
- **Adobe PDF Services API**: [https://developer.adobe.com/document-services/docs/overview/](https://developer.adobe.com/document-services/docs/overview/)
- **PAC User Guide**: [https://pac.pdf-accessibility.org/en/pac-user-guide](https://pac.pdf-accessibility.org/en/pac-user-guide)
- **pikepdf Documentation**: [https://pikepdf.readthedocs.io/](https://pikepdf.readthedocs.io/)

### Inspekt Implementation References

- Basic checker: `inspekt/services/pdf_checker.py`
- Content auditor: `inspekt/services/pdf_content_auditor.py`
- Structure extractor: `inspekt/services/pdf_structure_extractor.py`
- Remediation planner: `inspekt/services/remediation_planner.py`
- WCAG mapper: `inspekt/services/wcag_mapper.py`
- Check definitions: `inspekt/data/pdf_checks.json`
- WCAG mappings: `inspekt/data/pdfua_wcag_mapping.json`
