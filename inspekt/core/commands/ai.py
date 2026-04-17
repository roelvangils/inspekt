"""
AI command definitions.

Commands for AI-powered features:
- summarize: Summarize article content using AI
- describe: Generate page description for screen readers
- ask: Answer questions about the page
- do: Execute actions from natural language instructions
- md_link: Get markdown link for current page
- element_describe: AI description of specific element (inspected/focused/selection)
- element_ask: Ask questions about specific element
"""

from inspekt.core.commands.base import Category, CommandDefinition, EmptyParams
from inspekt.core.schemas.ai import (
    AskParams,
    AskResponse,
    DescribeParams,
    DescribeResponse,
    DoParams,
    DoResponse,
    ElementAskParams,
    ElementAskResponse,
    ElementDescribeParams,
    ElementDescribeResponse,
    MdLinkResponse,
    SummarizeParams,
    SummarizeResponse,
)

# === Summarize ===

summarize = CommandDefinition(
    id="summarize",
    name="Summarize Article",
    category=Category.EXTRACTION,
    description="""Summarize the current article using AI.

Extracts article content using Mozilla Readability and generates
a concise summary using the configured AI model (mods).

Perfect for:
- Quickly understanding long articles
- Getting the key points of a news story
- Summarizing blog posts or documentation

The --format option controls output:
- summary: AI-generated summary (default)
- full: Show the full extracted article text""",
    params_schema=SummarizeParams,
    response_schema=SummarizeResponse,
    handler="inspekt.core.handlers.ai.summarize",
    cli_name="summarize",
    api_path="/ai/summarize",
    api_method="POST",
    # URL scheme support
    url_scheme="summarize",
    url_scheme_params={
        "format": "Output format: summary (default) or full",
        "language": "Language for AI output (e.g., en, nl)",
    },
    url_scheme_examples=[
        "inspekt://summarize",
        "inspekt://summarize?language=en",
    ],
    url_scheme_output_mode="dialog",
    url_scheme_timeout=120,
    examples=[
        "inspekt summarize",
        "inspekt summarize --format full",
        "inspekt summarize --language en",
    ],
)

# === Describe ===

describe = CommandDefinition(
    id="describe",
    name="Describe Page",
    category=Category.EXTRACTION,
    description="""Generate an AI-powered description of the page for screen reader users.

Extracts page structure (landmarks, headings, links, images, forms) and
uses AI to create a concise, natural description perfect for blind users
to understand what the page offers at a glance.

Returns a conversational description like:
"This is a news article page with a main navigation menu,
 3 featured stories, and a sidebar with recent posts…"

Ideal for:
- Screen reader users getting page orientation
- Accessibility testing and auditing
- Understanding complex page layouts""",
    params_schema=DescribeParams,
    response_schema=DescribeResponse,
    handler="inspekt.core.handlers.ai.describe",
    cli_name="describe",
    api_path="/ai/describe",
    api_method="POST",
    # URL scheme support
    url_scheme="describe",
    url_scheme_params={
        "language": "Language for AI output (e.g., en, nl)",
    },
    url_scheme_examples=[
        "inspekt://describe",
        "inspekt://describe?language=nl",
    ],
    url_scheme_output_mode="dialog",
    url_scheme_timeout=120,
    examples=[
        "inspekt describe",
        "inspekt describe --language en",
        "inspekt describe --json",
    ],
)

# === Ask ===

ask = CommandDefinition(
    id="ask",
    name="Ask About Page",
    category=Category.EXTRACTION,
    description="""Ask a question about the current page using AI.

Uses the cached page index (from 'inspekt index') to answer questions.
The AI has access to:
- Full semantic structure and text content
- Interactive elements and their accessible names
- Vision AI descriptions of images

Examples of questions you can ask:
- "What is this page about?"
- "What's the price of this product?"
- "Summarize the main article"
- "What accessibility issues might exist?"
- "What's in the main image?"

Tip: Run 'inspekt index' first to cache the page for faster queries.""",
    params_schema=AskParams,
    response_schema=AskResponse,
    handler="inspekt.core.handlers.ai.ask",
    cli_name="ask",
    api_path="/ai/ask",
    api_method="POST",
    # URL scheme support
    url_scheme="ask",
    url_scheme_params={
        "question": "The question to ask about the page",
    },
    url_scheme_examples=[
        "inspekt://ask?question=What%20is%20this%20page%20about",
        "inspekt://ask?question=Summarize%20the%20main%20content",
    ],
    url_scheme_output_mode="dialog",
    url_scheme_timeout=120,
    examples=[
        'inspekt ask "What is this page about?"',
        'inspekt ask "What products are available?"',
        'inspekt ask "Summarize the article"',
    ],
)

# === Do ===

do = CommandDefinition(
    id="do",
    name="Do Action",
    category=Category.INTERACTION,
    description="""Find and execute actionable elements matching a natural language instruction.

This command analyzes the page for clickable elements (links, buttons, forms)
and uses AI to match them with your instruction. It returns a ranked list
of matches with confidence scores.

Behavior:
- If the top match has confidence >= 75%, executes automatically
- For lower confidence, shows matches for manual selection
- Elements are briefly highlighted before clicking

Great for:
- "Go to the homepage"
- "Click the login button"
- "Submit the form"
- "Open the menu"
- "Search for products"

The command handles different element types and works with modern SPAs.""",
    params_schema=DoParams,
    response_schema=DoResponse,
    handler="inspekt.core.handlers.ai.do",
    cli_name="do",
    api_path="/ai/do",
    api_method="POST",
    # URL scheme support
    url_scheme="do",
    url_scheme_params={
        "instruction": "Natural language instruction for what to do",
    },
    url_scheme_examples=[
        "inspekt://do?instruction=Go%20to%20homepage",
        "inspekt://do?instruction=Click%20login",
    ],
    url_scheme_output_mode="notification",
    url_scheme_allowed_output_modes=["notification", "silent"],
    url_scheme_timeout=120,
    examples=[
        'inspekt do "Go to the homepage"',
        'inspekt do "Click the login button"',
        'inspekt do "Submit the form"',
    ],
)

# === Markdown Link ===

md_link = CommandDefinition(
    id="md_link",
    name="Markdown Link",
    category=Category.EXTRACTION,
    description="""Get a Markdown-formatted link for the current page.

Returns [title](url) format with a cleaned page title.
Automatically strips website name suffixes from titles
(splits on " |", " -", " –", " —").

Example output:
  [Getting Started with Inspekt](https://example.com/docs/getting-started)

Perfect for:
- Adding links to documentation
- Sharing pages in Markdown files
- Creating link lists for research""",
    params_schema=EmptyParams,
    response_schema=MdLinkResponse,
    handler="inspekt.core.handlers.ai.md_link",
    cli_name="md-link",
    api_path="/extraction/md-link",
    api_method="GET",
    # URL scheme support
    url_scheme="md-link",
    url_scheme_examples=["inspekt://md-link"],
    examples=["inspekt md-link", "inspekt md-link --json"],
)

# === Element Describe ===

element_describe = CommandDefinition(
    id="element_describe",
    name="Describe Element",
    category=Category.EXTRACTION,
    description="""Generate an AI-powered accessibility description of a specific element.

Uses vision AI to analyze a screenshot of the element along with its metadata
(accessibility properties, computed styles, HTML attributes) to provide a
concise, accessibility-focused description.

Element sources:
- inspected: The element currently selected in DevTools ($0)
- focused: The element with keyboard focus
- selection: The text selection area

The description focuses on:
- What the element is and its purpose
- Accessible name and how it's computed
- Keyboard accessibility (focusable, operable)
- Visual accessibility (contrast, focus indicators)
- Potential accessibility issues

Perfect for:
- Understanding how screen readers announce elements
- Accessibility auditing and testing
- Debugging focus management""",
    params_schema=ElementDescribeParams,
    response_schema=ElementDescribeResponse,
    handler="inspekt.core.handlers.ai.element_describe",
    cli_name=None,  # Exposed via group subcommands (inspected describe, focused describe, etc.)
    api_path="/ai/element/describe",
    api_method="POST",
    examples=[
        "inspekt inspected describe",
        "inspekt focused describe",
        "inspekt selection describe",
        "inspekt inspected describe --language en",
    ],
)

# === Element Ask ===

element_ask = CommandDefinition(
    id="element_ask",
    name="Ask About Element",
    category=Category.EXTRACTION,
    description="""Ask a question about a specific element using AI.

Uses vision AI to analyze a screenshot of the element along with its metadata
to answer questions about accessibility, design, or functionality.

Element sources:
- inspected: The element currently selected in DevTools ($0)
- focused: The element with keyboard focus
- selection: The text selection area

Example questions:
- "Is this accessible?"
- "Does this have sufficient contrast?"
- "How would a screen reader announce this?"
- "What WCAG issues does this have?"
- "Is this keyboard accessible?"

The AI provides specific, actionable answers and references WCAG guidelines
when discussing accessibility issues.""",
    params_schema=ElementAskParams,
    response_schema=ElementAskResponse,
    handler="inspekt.core.handlers.ai.element_ask",
    cli_name=None,  # Exposed via group subcommands (inspected ask, focused ask, etc.)
    api_path="/ai/element/ask",
    api_method="POST",
    examples=[
        'inspekt inspected ask "Is this accessible?"',
        'inspekt focused ask "Does this have good contrast?"',
        'inspekt inspected ask "What WCAG issues does this have?"',
    ],
)

# All AI commands
AI_COMMANDS = [
    summarize,
    describe,
    ask,
    do,
    md_link,
    element_describe,
    element_ask,
]
