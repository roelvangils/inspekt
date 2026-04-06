# The clever CSS trick that makes cookie banners speak your language

*While testing a client's website for accessibility, we stumbled upon something genuinely interesting — a CSS technique that elegantly solves the problem of multilingual UI elements. Here's what we found and why it matters.*

## What we noticed

We were running an accessibility audit on a Flemish government website when we noticed something curious about their cookie consent dialog. The button text read "Stel je voorkeuren in" — correct Dutch, matching the page language. Nothing unusual there.

But when we looked at the HTML, we found this:

```html
<button>
    <span class="trans" lang="en">Set your preferences</span>
    <span class="trans" lang="nl">Stel je voorkeuren in</span>
    <span class="trans" lang="fr">Configurez vos préférences</span>
    <span class="trans" lang="de">Präferenzen eingeben</span>
    <span class="trans" lang="es">Configure sus preferencias</span>
</button>
```

Five languages, all embedded in the same button. Yet only the Dutch text was visible. No JavaScript switching. No AJAX call to fetch the right translation. Just... CSS.

## How it works

The trick uses two standard CSS features that work beautifully together:

**1. The `lang` attribute on HTML elements**

Every well-built multilingual page sets a language on the `<html>` tag: `<html lang="nl">` for Dutch, `<html lang="fr">` for French, and so on. Individual elements can override this with their own `lang` attribute.

**2. The `:lang()` CSS pseudo-class**

The `:lang()` selector matches elements based on the document's language context. Here's the CSS that makes the magic happen:

```css
.trans {
    display: none;
}

.trans:lang(nl) {
    display: inline;
}
```

When the page is in Dutch (`<html lang="nl">`), only the `<span lang="nl">` matches the `:lang(nl)` selector. All other spans stay hidden with `display: none`.

That's it. No JavaScript. No server-side rendering. Pure CSS.

## Why this matters for accessibility

Here's where it gets really interesting. The browser's accessibility engine respects `display: none`. When it calculates the "accessible name" of the button — the text that a screen reader would announce — it only includes visible content.

So a screen reader user hears: *"Stel je voorkeuren in, button"* — exactly what a sighted user sees. Not the concatenated mess of five languages.

This is precisely what the [W3C Accessible Name computation algorithm](https://www.w3.org/TR/accname-1.2/) specifies: hidden elements are excluded from name calculation. The CSS technique works *with* the accessibility layer, not against it.

## The benefits

**Zero JavaScript overhead.** The language switching happens in pure CSS. No script needs to run, no DOM manipulation happens after page load. The correct language is displayed from the very first render.

**Server-side simplicity.** The server doesn't need to know which language to render. It can output all translations at once and let CSS handle the display. This is particularly useful for third-party widgets (like cookie consent tools) that are embedded across sites in different languages.

**Graceful degradation.** If CSS fails to load, all translations are visible. Not ideal, but the content is still accessible — just in multiple languages.

**Cache-friendly.** Since the HTML contains all translations, the same HTML can be cached regardless of language. The CSS handles the presentation layer.

## The downsides

**Performance with many translations.** The HTML payload includes all language variants, even though only one is displayed. For a few buttons this is negligible, but for a content-heavy page with 20 languages, the markup could balloon significantly.

**SEO considerations.** Hidden text in the DOM can confuse search engines. While modern crawlers are smart enough to understand `display: none`, having multiple languages in the same element could affect content language signals.

**Not suitable for long content.** This pattern works well for short UI strings — button labels, navigation items, form labels. For paragraphs of content, you'd still want proper i18n with language-specific pages or server-side rendering.

**The `textContent` trap.** If you're building tools that read the DOM (browser extensions, testing tools, scrapers), `element.textContent` returns *all* text including hidden children. You need to walk the DOM tree and check computed styles to get only the visible text. We discovered this the hard way when our own accessibility tool was concatenating all five translations into one string.

## Where we've seen this in the wild

The technique is used by [CookieBot](https://www.cookiebot.com/), one of the most popular cookie consent management platforms. Their widget is embedded on millions of websites across Europe, and this CSS pattern lets a single widget work in any language without server-side configuration.

It's a clever solution to a real problem: how do you ship a third-party widget that works in dozens of languages without requiring the host site to configure anything? The answer: embed everything and let CSS sort it out.

## Try it yourself

Here's a minimal example you can paste into any HTML file:

```html
<!DOCTYPE html>
<html lang="nl">
<head>
    <style>
        .i18n { display: none; }
        .i18n:lang(nl) { display: inline; }
        .i18n:lang(en) { display: inline; }
        .i18n:lang(fr) { display: inline; }
    </style>
</head>
<body>
    <button>
        <span class="i18n" lang="en">Accept cookies</span>
        <span class="i18n" lang="nl">Cookies accepteren</span>
        <span class="i18n" lang="fr">Accepter les cookies</span>
    </button>
</body>
</html>
```

Change `<html lang="nl">` to `<html lang="fr">` and reload — the button text switches to French. No JavaScript involved.

## What we learned

Sometimes the most elegant solutions are the simplest ones. Two standard CSS features — `lang` attributes and the `:lang()` pseudo-class — combine to solve a real-world internationalisation challenge. It's not perfect for every use case, but for UI strings in embedded widgets, it's hard to beat.

And if you're building accessibility tools (like we are), remember: always check visibility before reading text content. The DOM tells you what's *there*, not what's *seen*.

---

*This article was written by the team at [Eleven Ways](https://www.elevenways.be), an accessibility consultancy based in Belgium. We discovered this technique while building [Inspekt](https://inspekt.dev), our browser inspection and accessibility testing tool.*
