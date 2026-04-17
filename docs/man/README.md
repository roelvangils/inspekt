# Inspekt man-page sources

This directory holds the Markdown sources for `man inspekt` and the
per-command pages (`man inspekt-axe`, `man inspekt-storage`, ...). The
generator at `scripts/build_man.py` walks the live Click CLI and the
`CommandRegistry`, splices in the templates here, and writes roff output to
`inspekt/man/` via pandoc.

## Layout

| File | Purpose |
|---|---|
| `inspekt.1.md` | Main page template. The generator fills `{{ global_options }}` and `{{ commands_by_category }}`. Other sections are hand-authored. |
| `_command.1.md.j2` | Default template for every per-command page. Receives `synopsis`, `description`, `arguments_section`, `options_section`, `subcommands_section`, `examples_section`, and an optional `override` block. |
| `inspekt-plugins.7.md` | Hand-authored overview of the plugin system. The generator can splice an "INSTALLED PLUGINS" section in via `inspekt man rebuild`. |
| `partials/*.md` | Reusable Markdown fragments included with `{% include "partials/foo.md" %}`. |
| `overrides/<name>.md` | Optional add-on content for a specific command. Spliced into the auto-generated page after the auto sections. Use this for NOTES, BUGS, additional EXAMPLES, etc. |

## Authoring

* Write plain Markdown. Pandoc converts it to roff with the
  `markdown+pipe_tables+definition_lists` extension, so use a definition list
  (`term\n: description`) for option/file/env tables.
* Wrap long literal strings in backticks; surround command names in
  `**bold**` and option flags in `**--bold**` for proper man-page emphasis.
* For section headers, use a single `#` so pandoc emits `.SH` (section).
  Nested `##` becomes `.SS` (subsection).
* You **cannot** override SYNOPSIS / OPTIONS / SUBCOMMANDS - those are
  derived from the live CLI to prevent drift. To add prose around them,
  drop a Markdown file into `overrides/`.

## Override example

Adding `docs/man/overrides/axe.md`:

```markdown
# NOTES

The axe analyzer caches rule definitions for 24 hours.

# ADDITIONAL EXAMPLES

Run only WCAG 2.0 AA rules:

    inspekt axe --tag wcag2aa
```

The generator splices this *after* the auto-generated sections and *before*
the SEE ALSO footer.

## Building

```bash
make build-man               # regenerate everything (needs pandoc)
inspekt man build            # same, via the CLI
inspekt man install --user   # copy generated pages into ~/.local/share/man
inspekt man rebuild          # re-write inspekt-plugins(7) with current plugins
```

The generated `*.1` and `*.7` files are checked into `inspekt/man/` so that
wheels can be built without pandoc.
