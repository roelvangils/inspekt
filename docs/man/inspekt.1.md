% INSPEKT(1) Inspekt {{ version }} | User Commands
% Roel van Gils
% {{ build_date }}

# NAME

inspekt - browser inspection, accessibility testing, and automation from the command line

# SYNOPSIS

**inspekt** \[*GLOBAL OPTIONS*\] *COMMAND* \[*ARGS*\]...

# DESCRIPTION

{% include "partials/intro.md" %}

# GLOBAL OPTIONS

{{ global_options }}

# COMMANDS

{{ commands_by_category }}

Run **inspekt** *COMMAND* **--help** for full options of any command, or open
the dedicated man page (e.g. **man inspekt-axe**, **man inspekt-storage**).

# CONFIGURATION

{% include "partials/config.md" %}

# FILES

{% include "partials/files.md" %}

# ENVIRONMENT

{% include "partials/environment.md" %}

# EXAMPLES

Open a URL in the connected browser:

    inspekt open https://example.com

Run an axe-core accessibility audit on the current page:

    inspekt axe

Take a full-page screenshot:

    inspekt screenshot --full

Record a sequence of interactions and replay it later:

    inspekt record demo.yaml
    inspekt replay demo.yaml

Ask a natural-language question about the current page:

    inspekt ask "what is this page about?"

# SEE ALSO

{% include "partials/see_also.md" %}

# AUTHORS

Roel van Gils and contributors. See https://github.com/roelvangils/inspekt.

# BUGS

Report issues at https://github.com/roelvangils/inspekt/issues
