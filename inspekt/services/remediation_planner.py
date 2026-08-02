"""
PDF Remediation Planner.

Generates prioritized, actionable remediation tasks based on
PDF accessibility violations. Each task includes:
- Priority level (critical, high, medium, low)
- Step-by-step remediation instructions
- Recommended tools
- WCAG criteria affected
- Estimated effort

This helps accessibility remediators efficiently fix PDF issues
in the order of greatest impact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from inspekt.services.pdf_checker import PDFBasicResult, PDFFullResult, VeraPDFViolation
    from inspekt.services.pdf_content_auditor import ContentAuditResult
    from inspekt.services.pdf_structure_extractor import StructureExtractionResult


class RemediationPriority(Enum):
    """Priority levels for remediation tasks."""

    CRITICAL = 1  # Blocking - must fix for basic accessibility
    HIGH = 2  # Serious usability impact
    MEDIUM = 3  # Moderate impact
    LOW = 4  # Minor/cosmetic improvements

    @property
    def label(self) -> str:
        """Human-readable label."""
        return {
            RemediationPriority.CRITICAL: "Critical",
            RemediationPriority.HIGH: "High",
            RemediationPriority.MEDIUM: "Medium",
            RemediationPriority.LOW: "Low",
        }[self]

    @property
    def color(self) -> str:
        """CSS color for the priority."""
        return {
            RemediationPriority.CRITICAL: "#dc2626",  # Red
            RemediationPriority.HIGH: "#f97316",  # Orange
            RemediationPriority.MEDIUM: "#eab308",  # Yellow
            RemediationPriority.LOW: "#3b82f6",  # Blue
        }[self]

    @property
    def icon(self) -> str:
        """Emoji icon for the priority."""
        return {
            RemediationPriority.CRITICAL: "🔴",
            RemediationPriority.HIGH: "🟠",
            RemediationPriority.MEDIUM: "🟡",
            RemediationPriority.LOW: "🔵",
        }[self]


class RemediationTool(Enum):
    """Recommended tools for remediation."""

    ACROBAT_PRO = "Adobe Acrobat Pro"
    PAC = "PDF Accessibility Checker"
    AXES_PDF = "axesPDF"
    COMMONLOOK = "CommonLook"
    SOURCE = "Source Document (Word/InDesign)"
    WORD = "Microsoft Word"
    INDESIGN = "Adobe InDesign"
    LIBRE_OFFICE = "LibreOffice"
    PDF24 = "PDF24 Tools"
    MANUAL = "Manual editing"

    @property
    def is_free(self) -> bool:
        """Check if tool is free/open source."""
        return self in {
            RemediationTool.PAC,
            RemediationTool.LIBRE_OFFICE,
            RemediationTool.PDF24,
        }


class EffortLevel(Enum):
    """Estimated effort for remediation."""

    QUICK = "Quick fix"  # 5-15 minutes
    MODERATE = "Moderate"  # 30-60 minutes
    SIGNIFICANT = "Significant"  # 1-4 hours
    EXTENSIVE = "Extensive"  # 4+ hours / full document recreation

    @property
    def time_estimate(self) -> str:
        """Time estimate string."""
        return {
            EffortLevel.QUICK: "5-15 minutes",
            EffortLevel.MODERATE: "30-60 minutes",
            EffortLevel.SIGNIFICANT: "1-4 hours",
            EffortLevel.EXTENSIVE: "4+ hours",
        }[self]


@dataclass
class RemediationTask:
    """A single remediation task."""

    task_id: str  # Unique identifier
    priority: RemediationPriority
    category: str  # Structure, Alt Text, Forms, etc.
    title: str  # Brief task title
    description: str  # What needs to be fixed
    affected_pages: list[int] = field(default_factory=list)  # 1-indexed
    affected_count: int = 1  # Number of issues this fixes
    tools: list[RemediationTool] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)  # Step-by-step instructions
    wcag_criteria: list[str] = field(default_factory=list)  # e.g., ["1.1.1", "4.1.2"]
    effort: EffortLevel = EffortLevel.MODERATE
    notes: str | None = None

    @property
    def pages_summary(self) -> str:
        """Summarize affected pages."""
        if not self.affected_pages:
            return "All pages"
        if len(self.affected_pages) <= 3:
            return ", ".join(str(p) for p in self.affected_pages)
        return f"{self.affected_pages[0]}, {self.affected_pages[1]}, ... ({len(self.affected_pages)} pages)"


@dataclass
class RemediationPlan:
    """Complete remediation plan with prioritized tasks."""

    tasks: list[RemediationTask] = field(default_factory=list)
    total_issues: int = 0

    # Counts by priority
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0

    @property
    def task_count(self) -> int:
        """Total number of tasks."""
        return len(self.tasks)

    def get_tasks_by_priority(
        self, priority: RemediationPriority
    ) -> list[RemediationTask]:
        """Get tasks for a specific priority level."""
        return [t for t in self.tasks if t.priority == priority]

    @property
    def critical_tasks(self) -> list[RemediationTask]:
        """Get critical priority tasks."""
        return self.get_tasks_by_priority(RemediationPriority.CRITICAL)

    @property
    def high_tasks(self) -> list[RemediationTask]:
        """Get high priority tasks."""
        return self.get_tasks_by_priority(RemediationPriority.HIGH)

    @property
    def estimated_total_effort(self) -> str:
        """Estimate total remediation effort."""
        effort_minutes = 0
        for task in self.tasks:
            if task.effort == EffortLevel.QUICK:
                effort_minutes += 10 * task.affected_count
            elif task.effort == EffortLevel.MODERATE:
                effort_minutes += 45 * task.affected_count
            elif task.effort == EffortLevel.SIGNIFICANT:
                effort_minutes += 150 * task.affected_count
            else:
                effort_minutes += 300 * task.affected_count

        if effort_minutes < 60:
            return f"~{effort_minutes} minutes"
        elif effort_minutes < 480:
            return f"~{effort_minutes // 60} hours"
        else:
            return f"~{effort_minutes // 480} days"


# Remediation templates for common issues
REMEDIATION_TEMPLATES = {
    "tagged": {
        "title": "Add document tagging",
        "category": "Structure",
        "priority": RemediationPriority.CRITICAL,
        "effort": EffortLevel.EXTENSIVE,
        "tools": [RemediationTool.ACROBAT_PRO, RemediationTool.SOURCE],
        "wcag_criteria": ["1.3.1", "4.1.2"],
        "steps": [
            "Open the PDF in Adobe Acrobat Pro",
            "Go to Tools > Accessibility > Autotag Document",
            "Review the automatically generated tags",
            "Use the Tags panel to correct any incorrect tag assignments",
            "Verify reading order in View > Show/Hide > Navigation Panes > Order",
            "For best results, re-export from the source document with accessibility settings enabled",
        ],
    },
    "title": {
        "title": "Set document title and enable display",
        "category": "Metadata",
        "priority": RemediationPriority.HIGH,
        "effort": EffortLevel.QUICK,
        "tools": [RemediationTool.ACROBAT_PRO],
        "wcag_criteria": ["2.4.2"],
        "steps": [
            "Open the PDF in Adobe Acrobat Pro",
            "Go to File > Properties (Ctrl+D / Cmd+D)",
            "In the Description tab, enter a meaningful Title",
            "Go to the Initial View tab",
            "Under Window Options, set 'Show' to 'Document Title'",
            "Click OK and save the document",
        ],
    },
    "language": {
        "title": "Set document language",
        "category": "Metadata",
        "priority": RemediationPriority.HIGH,
        "effort": EffortLevel.QUICK,
        "tools": [RemediationTool.ACROBAT_PRO],
        "wcag_criteria": ["3.1.1"],
        "steps": [
            "Open the PDF in Adobe Acrobat Pro",
            "Go to File > Properties (Ctrl+D / Cmd+D)",
            "Go to the Advanced tab",
            "Under Reading Options, select the appropriate Language from the dropdown",
            "Common codes: English (en), Dutch (nl), French (fr), German (de)",
            "Click OK and save the document",
        ],
    },
    "protected": {
        "title": "Remove accessibility restrictions",
        "category": "Security",
        "priority": RemediationPriority.CRITICAL,
        "effort": EffortLevel.QUICK,
        "tools": [RemediationTool.ACROBAT_PRO],
        "wcag_criteria": ["1.1.1"],
        "steps": [
            "Open the PDF in Adobe Acrobat Pro",
            "Go to File > Properties > Security",
            "Change Security Method to 'No Security' or adjust permissions",
            "Ensure 'Enable copying of text, images, and other content' is checked",
            "Or ensure 'Enable text access for screen reader devices for the visually impaired' is checked",
            "Click OK and save the document",
        ],
    },
    "bookmarks": {
        "title": "Add navigation bookmarks",
        "category": "Navigation",
        "priority": RemediationPriority.MEDIUM,
        "effort": EffortLevel.MODERATE,
        "tools": [RemediationTool.ACROBAT_PRO],
        "wcag_criteria": ["2.4.5"],
        "steps": [
            "Open the PDF in Adobe Acrobat Pro",
            "Go to View > Show/Hide > Navigation Panes > Bookmarks",
            "Select the text for the first heading",
            "Right-click and choose 'Add Bookmark'",
            "Repeat for all major sections/headings",
            "Alternatively, go to Tools > Accessibility > Add Tags to Document, then use 'New Bookmarks from Structure'",
        ],
    },
    "scanned": {
        "title": "Run OCR on scanned document",
        "category": "Text Layer",
        "priority": RemediationPriority.CRITICAL,
        "effort": EffortLevel.SIGNIFICANT,
        "tools": [RemediationTool.ACROBAT_PRO],
        "wcag_criteria": ["1.1.1", "1.4.5"],
        "steps": [
            "Open the PDF in Adobe Acrobat Pro",
            "Go to Tools > Scan & OCR",
            "Click 'Recognize Text' > 'In This File'",
            "Choose appropriate settings for language and output",
            "For 'Output', select 'Searchable Image (Exact)' for best quality",
            "Click 'Recognize Text' and wait for processing",
            "Review and correct any OCR errors",
            "Consider re-creating the document from the original source if available",
        ],
    },
    "alt_text": {
        "title": "Add alternative text to images",
        "category": "Alternative Text",
        "priority": RemediationPriority.CRITICAL,
        "effort": EffortLevel.MODERATE,
        "tools": [RemediationTool.ACROBAT_PRO],
        "wcag_criteria": ["1.1.1"],
        "steps": [
            "Open the PDF in Adobe Acrobat Pro",
            "Go to Tools > Accessibility > Set Alternate Text",
            "Acrobat will show each image requiring alt text",
            "For meaningful images: Enter a description that conveys the image's purpose",
            "For decorative images: Check 'Decorative figure'",
            "For complex images (charts, diagrams): Provide a long description or link to data",
            "Click 'Save & Close' when done",
        ],
    },
    "table_headers": {
        "title": "Mark table header cells",
        "category": "Tables",
        "priority": RemediationPriority.HIGH,
        "effort": EffortLevel.MODERATE,
        "tools": [RemediationTool.ACROBAT_PRO],
        "wcag_criteria": ["1.3.1"],
        "steps": [
            "Open the PDF in Adobe Acrobat Pro",
            "Go to View > Show/Hide > Navigation Panes > Tags",
            "Navigate to the Table element in the tag tree",
            "Find header cells (typically in the first row or column)",
            "Right-click each header cell and choose Properties",
            "Change 'Type' from 'Table Data Cell' to 'Table Header Cell'",
            "Set 'Scope' attribute: Row, Column, or Both",
            "For complex tables, use 'ID' and 'Headers' attributes",
        ],
    },
    "form_labels": {
        "title": "Add labels to form fields",
        "category": "Forms",
        "priority": RemediationPriority.HIGH,
        "effort": EffortLevel.MODERATE,
        "tools": [RemediationTool.ACROBAT_PRO],
        "wcag_criteria": ["1.3.1", "4.1.2"],
        "steps": [
            "Open the PDF in Adobe Acrobat Pro",
            "Go to Tools > Prepare Form",
            "Click on each form field to select it",
            "In the right panel, find 'Tooltip' field",
            "Enter a descriptive label that explains what information to enter",
            "For checkboxes/radios: The tooltip should describe the option",
            "Set logical tab order: Tools > Accessibility > Reading Order",
            "Save the document",
        ],
    },
    "link_text": {
        "title": "Add descriptive link text",
        "category": "Links",
        "priority": RemediationPriority.MEDIUM,
        "effort": EffortLevel.MODERATE,
        "tools": [RemediationTool.ACROBAT_PRO],
        "wcag_criteria": ["2.4.4"],
        "steps": [
            "Open the PDF in Adobe Acrobat Pro",
            "Go to Tools > Edit PDF",
            "Select each non-descriptive link (e.g., 'click here', 'read more')",
            "Change the visible text to be descriptive of the destination",
            "Alternatively, go to View > Show/Hide > Navigation Panes > Tags",
            "Find the Link tag and add a Contents key with descriptive text",
            "Ensure link text makes sense out of context",
        ],
    },
    "heading_order": {
        "title": "Fix heading hierarchy",
        "category": "Structure",
        "priority": RemediationPriority.HIGH,
        "effort": EffortLevel.MODERATE,
        "tools": [RemediationTool.ACROBAT_PRO],
        "wcag_criteria": ["1.3.1"],
        "steps": [
            "Open the PDF in Adobe Acrobat Pro",
            "Go to View > Show/Hide > Navigation Panes > Tags",
            "Review the heading structure (H1, H2, H3, etc.)",
            "Ensure headings follow a logical hierarchy (H1 → H2 → H3)",
            "Do not skip levels (e.g., H1 directly to H3)",
            "To change heading level: Right-click the tag > Properties > Type",
            "Use only one H1 per document",
        ],
    },
    "reading_order": {
        "title": "Fix reading order",
        "category": "Reading Order",
        "priority": RemediationPriority.HIGH,
        "effort": EffortLevel.SIGNIFICANT,
        "tools": [RemediationTool.ACROBAT_PRO],
        "wcag_criteria": ["1.3.2"],
        "steps": [
            "Open the PDF in Adobe Acrobat Pro",
            "Go to View > Show/Hide > Navigation Panes > Order",
            "The Order panel shows the current reading order",
            "Drag items to rearrange them in logical reading sequence",
            "Headers should come before content, captions near figures",
            "Alternatively, use Tools > Accessibility > Reading Order",
            "Draw rectangles around content blocks and assign types",
            "Use 'Show Order Panel' to verify the sequence",
        ],
    },
    "list_structure": {
        "title": "Fix list structure",
        "category": "Structure",
        "priority": RemediationPriority.HIGH,
        "effort": EffortLevel.MODERATE,
        "tools": [RemediationTool.ACROBAT_PRO],
        "wcag_criteria": ["1.3.1"],
        "steps": [
            "Open the PDF in Adobe Acrobat Pro",
            "Go to View > Show/Hide > Navigation Panes > Tags",
            "Locate the List (L) elements in the tag tree",
            "Ensure each L contains only LI (List Item) children",
            "Each LI should contain Lbl (label) and/or LBody (content)",
            "For ordered lists, Lbl should contain the number/bullet",
            "LBody should contain the actual list item content",
            "Nested lists should be inside an LI's LBody, not directly under L",
        ],
    },
    "annotation_accessibility": {
        "title": "Add descriptions to annotations",
        "category": "Annotations",
        "priority": RemediationPriority.MEDIUM,
        "effort": EffortLevel.MODERATE,
        "tools": [RemediationTool.ACROBAT_PRO],
        "wcag_criteria": ["1.1.1", "4.1.2"],
        "steps": [
            "Open the PDF in Adobe Acrobat Pro",
            "Go to Tools > Comment",
            "Click on each annotation that needs a description",
            "Right-click and select 'Properties'",
            "In the General tab, add descriptive text to the Description field",
            "For file attachments, explain what the file contains",
            "For stamps, add text explaining the stamp's meaning",
            "For highlights/underlines, add a note explaining why text was marked",
        ],
    },
}


def generate_remediation_plan(
    result: PDFFullResult,
    structure: StructureExtractionResult | None = None,
    content_audit: ContentAuditResult | None = None,
) -> RemediationPlan:
    """
    Generate a prioritized remediation plan from check results.

    Args:
        result: PDFFullResult from PDF checker
        structure: Optional structure extraction result
        content_audit: Optional content audit result

    Returns:
        RemediationPlan with prioritized tasks
    """
    tasks: list[RemediationTask] = []
    task_id = 0

    def next_task_id() -> str:
        nonlocal task_id
        task_id += 1
        return f"task-{task_id}"

    # Process basic check results
    for check in result.basic.checks:
        if check.status in ("fail", "warn"):
            template = REMEDIATION_TEMPLATES.get(check.check_id)
            if template:
                task = RemediationTask(
                    task_id=next_task_id(),
                    priority=template["priority"],
                    category=template["category"],
                    title=template["title"],
                    description=check.message,
                    tools=template["tools"],
                    steps=template["steps"],
                    wcag_criteria=template["wcag_criteria"],
                    effort=template["effort"],
                )
                tasks.append(task)

    # Process simple check results if available
    if result.simple:
        for check in result.simple.checks:
            if check.status in ("fail", "warn") and check.check_id not in REMEDIATION_TEMPLATES:
                # Generic task for checks without templates
                tasks.append(RemediationTask(
                    task_id=next_task_id(),
                    priority=_severity_to_priority(check.severity),
                    category="General",
                    title=f"Fix: {check.name}",
                    description=check.message,
                    wcag_criteria=[check.wcag_sc] if check.wcag_sc else [],
                    effort=EffortLevel.MODERATE,
                ))

    # Process veraPDF violations if available
    if result.verapdf:
        # Group violations by rule for consolidated tasks
        violations_by_rule: dict[str, list[VeraPDFViolation]] = {}
        for v in result.verapdf.violations:
            if v.rule_id not in violations_by_rule:
                violations_by_rule[v.rule_id] = []
            violations_by_rule[v.rule_id].append(v)

        for rule_id, violations in violations_by_rule.items():
            # Get WCAG mapping
            from inspekt.services.wcag_mapper import get_wcag_mapper

            mapper = get_wcag_mapper()
            mapping = mapper.get_mapping(rule_id)

            wcag_ids = [c.id for c in mapping.wcag_criteria] if mapping else []
            category = mapping.category.replace("_", " ").title() if mapping else "Structure"

            pages = sorted(set(v.page_number + 1 for v in violations if v.page_number is not None))

            tasks.append(RemediationTask(
                task_id=next_task_id(),
                priority=_severity_to_priority(violations[0].severity),
                category=category,
                title=f"Fix: {rule_id}",
                description=violations[0].description,
                affected_pages=pages,
                affected_count=len(violations),
                wcag_criteria=wcag_ids,
                effort=EffortLevel.MODERATE,
                notes=mapping.remediation_hint if mapping else None,
            ))

    # Process content audit results if available
    if content_audit:
        # Images without alt text
        if content_audit.images_without_alt > 0:
            pages = sorted(set(
                img.page + 1 for img in content_audit.images
                if not img.has_alt_text and not img.is_decorative
            ))
            template = REMEDIATION_TEMPLATES["alt_text"]
            tasks.append(RemediationTask(
                task_id=next_task_id(),
                priority=template["priority"],
                category=template["category"],
                title=f"Add alt text to {content_audit.images_without_alt} image(s)",
                description="Images are missing alternative text descriptions",
                affected_pages=pages,
                affected_count=content_audit.images_without_alt,
                tools=template["tools"],
                steps=template["steps"],
                wcag_criteria=template["wcag_criteria"],
                effort=EffortLevel.MODERATE,
            ))

        # Tables without headers
        if content_audit.tables_without_headers > 0:
            pages = sorted(set(
                tbl.page + 1 for tbl in content_audit.tables
                if not tbl.has_headers
            ))
            template = REMEDIATION_TEMPLATES["table_headers"]
            tasks.append(RemediationTask(
                task_id=next_task_id(),
                priority=template["priority"],
                category=template["category"],
                title=f"Add headers to {content_audit.tables_without_headers} table(s)",
                description="Tables are missing header cell markup",
                affected_pages=pages,
                affected_count=content_audit.tables_without_headers,
                tools=template["tools"],
                steps=template["steps"],
                wcag_criteria=template["wcag_criteria"],
                effort=EffortLevel.MODERATE,
            ))

        # Form fields without labels
        if content_audit.fields_without_labels > 0:
            pages = sorted(set(
                f.page + 1 for f in content_audit.forms
                if not f.has_tooltip and not f.has_label
            ))
            template = REMEDIATION_TEMPLATES["form_labels"]
            tasks.append(RemediationTask(
                task_id=next_task_id(),
                priority=template["priority"],
                category=template["category"],
                title=f"Add labels to {content_audit.fields_without_labels} form field(s)",
                description="Form fields are missing accessible labels/tooltips",
                affected_pages=pages,
                affected_count=content_audit.fields_without_labels,
                tools=template["tools"],
                steps=template["steps"],
                wcag_criteria=template["wcag_criteria"],
                effort=EffortLevel.MODERATE,
            ))

        # Non-descriptive links
        if content_audit.links_non_descriptive > 0:
            pages = sorted(set(
                link.page + 1 for link in content_audit.links
                if not link.is_descriptive
            ))
            template = REMEDIATION_TEMPLATES["link_text"]
            tasks.append(RemediationTask(
                task_id=next_task_id(),
                priority=template["priority"],
                category=template["category"],
                title=f"Improve {content_audit.links_non_descriptive} link text(s)",
                description="Links have non-descriptive text like 'click here' or 'read more'",
                affected_pages=pages,
                affected_count=content_audit.links_non_descriptive,
                tools=template["tools"],
                steps=template["steps"],
                wcag_criteria=template["wcag_criteria"],
                effort=EffortLevel.MODERATE,
            ))

        # Lists with structure issues
        if content_audit.lists_with_issues > 0:
            pages = sorted(set(
                lst.page + 1 for lst in content_audit.lists
                if lst.status != "pass"
            ))
            template = REMEDIATION_TEMPLATES["list_structure"]
            tasks.append(RemediationTask(
                task_id=next_task_id(),
                priority=template["priority"],
                category=template["category"],
                title=f"Fix structure of {content_audit.lists_with_issues} list(s)",
                description="Lists have improper L/LI/Lbl/LBody structure",
                affected_pages=pages,
                affected_count=content_audit.lists_with_issues,
                tools=template["tools"],
                steps=template["steps"],
                wcag_criteria=template["wcag_criteria"],
                effort=template["effort"],
            ))

        # Annotations without descriptions
        if content_audit.annotations_without_description > 0:
            pages = sorted(set(
                ann.page + 1 for ann in content_audit.annotations
                if ann.status in ("fail", "warn")
            ))
            template = REMEDIATION_TEMPLATES["annotation_accessibility"]
            tasks.append(RemediationTask(
                task_id=next_task_id(),
                priority=template["priority"],
                category=template["category"],
                title=f"Add descriptions to {content_audit.annotations_without_description} annotation(s)",
                description="Annotations (notes, highlights, stamps, etc.) are missing accessible descriptions",
                affected_pages=pages,
                affected_count=content_audit.annotations_without_description,
                tools=template["tools"],
                steps=template["steps"],
                wcag_criteria=template["wcag_criteria"],
                effort=template["effort"],
            ))

    # Process structure validation results if available
    if structure and structure.validation:
        if not structure.validation.heading_order_valid:
            template = REMEDIATION_TEMPLATES["heading_order"]
            tasks.append(RemediationTask(
                task_id=next_task_id(),
                priority=template["priority"],
                category=template["category"],
                title=template["title"],
                description="Heading levels are skipped or out of order",
                tools=template["tools"],
                steps=template["steps"],
                wcag_criteria=template["wcag_criteria"],
                effort=template["effort"],
            ))

    # Sort tasks by priority
    tasks.sort(key=lambda t: t.priority.value)

    # Remove duplicate tasks (same title and category)
    seen = set()
    unique_tasks = []
    for task in tasks:
        key = (task.title, task.category)
        if key not in seen:
            seen.add(key)
            unique_tasks.append(task)

    # Calculate totals
    total_issues = sum(t.affected_count for t in unique_tasks)
    critical_count = sum(1 for t in unique_tasks if t.priority == RemediationPriority.CRITICAL)
    high_count = sum(1 for t in unique_tasks if t.priority == RemediationPriority.HIGH)
    medium_count = sum(1 for t in unique_tasks if t.priority == RemediationPriority.MEDIUM)
    low_count = sum(1 for t in unique_tasks if t.priority == RemediationPriority.LOW)

    return RemediationPlan(
        tasks=unique_tasks,
        total_issues=total_issues,
        critical_count=critical_count,
        high_count=high_count,
        medium_count=medium_count,
        low_count=low_count,
    )


def _severity_to_priority(severity: str) -> RemediationPriority:
    """Convert severity string to priority level."""
    severity_map = {
        "critical": RemediationPriority.CRITICAL,
        "serious": RemediationPriority.HIGH,
        "moderate": RemediationPriority.MEDIUM,
        "minor": RemediationPriority.LOW,
    }
    return severity_map.get(severity.lower(), RemediationPriority.MEDIUM)


def get_remediation_summary(plan: RemediationPlan) -> str:
    """
    Generate a human-readable summary of the remediation plan.

    Args:
        plan: RemediationPlan to summarize

    Returns:
        Multi-line string summary
    """
    lines = [
        "Remediation Roadmap",
        "=" * 40,
        f"Total tasks: {plan.task_count}",
        f"Total issues: {plan.total_issues}",
        f"Estimated effort: {plan.estimated_total_effort}",
        "",
    ]

    if plan.critical_count > 0:
        lines.append(f"🔴 Critical: {plan.critical_count} task(s)")
    if plan.high_count > 0:
        lines.append(f"🟠 High: {plan.high_count} task(s)")
    if plan.medium_count > 0:
        lines.append(f"🟡 Medium: {plan.medium_count} task(s)")
    if plan.low_count > 0:
        lines.append(f"🔵 Low: {plan.low_count} task(s)")

    if plan.critical_tasks:
        lines.append("")
        lines.append("Critical Tasks (Must Fix):")
        for task in plan.critical_tasks:
            lines.append(f"  • {task.title}")
            if task.affected_count > 1:
                lines.append(f"    ({task.affected_count} issues, pages: {task.pages_summary})")

    return "\n".join(lines)
