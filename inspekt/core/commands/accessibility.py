"""
Accessibility command definitions.

Commands for accessibility testing:
- run_axe_audit: Run axe-core accessibility audit
- run_autocomplete_check: Check autocomplete attributes on form fields
"""

from inspekt.core.commands.base import Category, CommandDefinition
from inspekt.core.schemas.accessibility import (
    AxeParams,
    AxeResponse,
    AutocompleteParams,
    AutocompleteResponse,
)

# === Run Axe Audit ===

run_axe_audit = CommandDefinition(
    id="run_axe_audit",
    name="Run Axe Audit",
    category=Category.ACCESSIBILITY,
    description="""Run axe-core accessibility audit on the current page.

Analyzes the page for WCAG conformance violations using the industry-standard
axe-core library. By default, tests against WCAG 2 Level AA standards.

The audit runs in the current browser tab, testing the actual rendered page
state including any JavaScript-generated content and authentication state.

Supported WCAG levels:
- 2a: WCAG 2.0 Level A
- 2aa: WCAG 2.0 Level AA (default)
- 2aaa: WCAG 2.0 Level AAA
- 21a: WCAG 2.1 Level A
- 21aa: WCAG 2.1 Level AA
- 22aa: WCAG 2.2 Level AA

Additional tags like 'best-practice' or 'experimental' can be included.""",
    params_schema=AxeParams,
    response_schema=AxeResponse,
    handler="inspekt.core.handlers.accessibility.run_axe_audit",
    cli_name="axe",
    cli_aliases=["a11y", "accessibility"],
    api_path="/accessibility/axe",
    api_method="POST",
    examples=[
        "inspekt axe",
        "inspekt axe --level 21aa",
        "inspekt axe --level 22aa --tags best-practice",
        "inspekt axe --include-passes --include-incomplete",
    ],
)

# === Run Autocomplete Check ===

run_autocomplete_check = CommandDefinition(
    id="run_autocomplete_check",
    name="Check Autocomplete",
    category=Category.ACCESSIBILITY,
    description="""Check autocomplete attributes on form fields per WCAG 2.1 SC 1.3.5.

Analyzes all form fields (input, textarea, select) on the current page and
predicts appropriate autocomplete attributes using multi-language heuristics.

The check uses 7 matching strategies with weighted confidence scoring:
- Label text (weight: 5) - highest reliability
- Placeholder text (weight: 4)
- Name attribute (weight: 2)
- ID attribute (weight: 2)
- Field type (weight: 1)
- Input type (weight: 1)
- Form type (weight: 1) - login vs signup detection

Supports multi-language keyword matching (English, German, Dutch) with
fuzzy substring matching for robust field identification.

Fields are classified as:
- violation: Missing or incorrect autocomplete (WCAG failure)
- warning: Autocomplete might be needed but uncertain
- pass: Correct autocomplete or not applicable""",
    params_schema=AutocompleteParams,
    response_schema=AutocompleteResponse,
    handler="inspekt.core.handlers.accessibility.run_autocomplete_check",
    cli_name="autocomplete",
    cli_aliases=["ac-check", "wcag-135"],
    api_path="/accessibility/autocomplete-check",
    api_method="POST",
    examples=[
        "inspekt autocomplete",
        "inspekt autocomplete --confidence-threshold 0.7",
        "inspekt autocomplete --include-hidden --include-disabled",
    ],
)

# All accessibility commands
ACCESSIBILITY_COMMANDS = [
    run_axe_audit,
    run_autocomplete_check,
]
