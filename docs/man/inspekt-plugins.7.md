% INSPEKT-PLUGINS(7) Inspekt {{ version }} | Miscellaneous
% Roel van Gils
% {{ build_date }}

# NAME

inspekt-plugins - overview of the Inspekt plugin system

# DESCRIPTION

Inspekt plugins are small JavaScript snippets - typically imported from
bookmarklets - that you can run inside the connected browser tab. They are
managed locally and never leave your machine.

Each plugin has a slug-style ID (e.g. **text-spacing**), an optional category
and tags, and metadata controlling how it is invoked: whether it returns
structured data, whether it auto-runs on certain domains, whether it is exposed
as an MCP tool, and how long it may run before timing out.

Plugins live in a SQLite database in the Inspekt data directory; see *FILES*
below.

# COMMANDS

The **inspekt plugin** command group manages plugins. Common operations:

**inspekt plugin list**
:   Show every installed plugin, its category and tags.

**inspekt plugin add** *NAME*
:   Add a new plugin from a bookmarklet URL or pasted JavaScript.

**inspekt plugin run** *ID*
:   Execute a plugin in the active tab.

**inspekt plugin export** / **import**
:   Move plugins between machines as JSON.

Run **inspekt plugin --help** for the full list, and **man inspekt-plugin** for
detailed flags.

# AUTORUN

A plugin marked **autorun** executes automatically whenever the page URL
matches one of its **autorun_domains** patterns. Inspekt debounces repeated
triggers within a 3-second window so that a single page load only fires the
plugin once.

# MCP EXPOSURE

A plugin with **mcp_exposed = true** is registered as an MCP tool when the
Inspekt MCP server starts, allowing AI agents to call it like any other
inspekt command. Plugins that return structured JSON should also set
**returns_data = true** so that the MCP wrapper exposes the result.

{% if installed_plugins %}
# INSTALLED PLUGINS

The following plugins are currently installed on this machine:

{{ installed_plugins }}

This list reflects the contents of your local plugin database at the time
**inspekt man rebuild** was last run. Run it again after adding or removing
plugins to refresh.
{% else %}
# INSTALLED PLUGINS

This system man page does not list your installed plugins. Run
**inspekt plugin list** to see them, or **inspekt man rebuild** to regenerate
this page with an embedded "INSTALLED PLUGINS" section under
*~/.local/share/man/man7/*.
{% endif %}

# FILES

*~/.inspekt/data.db*
:   SQLite database holding plugin definitions, autorun state, and run counts.

*~/.local/share/man/man7/inspekt-plugins.7*
:   Personalized version of this page written by **inspekt man rebuild**.
    Shadows the system page when present.

# SEE ALSO

**inspekt**(1), **inspekt-plugin**(1), **inspekt-mcp**(1), https://inspekt.dev
