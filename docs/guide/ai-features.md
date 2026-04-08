# AI Features

Master AI-powered features in Inspekt. Learn how to generate article summaries, create page descriptions for accessibility, and configure AI integration with mods.

## Overview

Inspekt integrates with AI through [mods](https://github.com/charmbracelet/mods) to provide two powerful features:

- `inspekt summarize` - Generate concise article summaries
- `inspekt describe` - Create accessible page descriptions for screen readers

Both commands extract page content and use AI to generate natural-language output.

## Prerequisites

### Install mods

AI features require [mods](https://github.com/charmbracelet/mods) to be installed:

```bash
# macOS/Linux
brew install charmbracelet/tap/mods

# Or with go
go install github.com/charmbracelet/mods@latest
```

### Configure mods

On first run, mods will prompt you to configure an AI provider:

```bash
mods
```

Supported providers:
- **OpenAI** (GPT-3.5, GPT-4)
- **Anthropic** (Claude)
- **Ollama** (local models)
- **Azure OpenAI**
- And more...

Set your API key:

```bash
# OpenAI
export OPENAI_API_KEY="your-key-here"

# Anthropic
export ANTHROPIC_API_KEY="your-key-here"

# Or configure via mods
mods --settings
```

---

## Article Summarization

The `inspekt summarize` command extracts article content and generates a concise summary.

### Basic Usage

```bash
inspekt summarize
```

**Example output:**
```
This article discusses the importance of web accessibility and provides
practical techniques for making websites more inclusive. Key points include
semantic HTML, ARIA labels, keyboard navigation, and screen reader compatibility.
The author emphasizes that accessibility benefits all users, not just those with
disabilities, by improving usability and SEO.
```

### How It Works

1. **Extract Article** - Uses [Mozilla Readability](https://github.com/mozilla/readability) to extract main content
2. **Detect Language** - Automatically detects page language
3. **Generate Summary** - Sends content to AI via mods
4. **Return Result** - Displays concise summary

### Show Full Article

```bash
inspekt summarize --format full
```

Displays the extracted article content without summarizing:

```
Title: Web Accessibility Best Practices
Author: John Doe
Published: 2024-01-15

Web accessibility is crucial for creating inclusive digital experiences...
[Full extracted article text]
```

### Language Control

Override the output language:

```bash
# Summarize in French
inspekt summarize --language fr
inspekt summarize --lang fr

# Summarize in Spanish
inspekt summarize --language es

# Summarize in German
inspekt summarize --lang de
```

### Language Detection Flow

1. **CLI flag** (`--language`) - Highest priority
2. **Config file** (`ai-language` setting) - Second priority
3. **Page language** (HTML `lang` attribute) - Third priority
4. **Let AI decide** - Default behavior

### Debug Mode

See the full prompt sent to AI:

```bash
inspekt summarize --debug
```

**Output:**
```
=== PROMPT ===
Please summarize the following article in 2-3 sentences.
Respond in English.

Title: Web Accessibility Best Practices
Content: [article content]
=== END PROMPT ===
```

Useful for:
- Understanding what's sent to AI
- Debugging language issues
- Customizing prompts

### Custom Prompts

Edit the summarization prompt:

```bash
# Edit prompt file
nano ~/inspekt_bridge/prompts/summary.prompt
```

**Default prompt:**
```
Please summarize the following article in 2-3 concise sentences.
Focus on the main points and key takeaways.

{LANGUAGE_INSTRUCTION}

Title: {TITLE}
Content: {CONTENT}
```

Variables:
- `{LANGUAGE_INSTRUCTION}` - Injected when `--language` is used
- `{TITLE}` - Article title
- `{CONTENT}` - Extracted article text

---

## Page Descriptions for Screen Readers

The `inspekt describe` command generates natural-language page descriptions perfect for blind users.

### Basic Usage

```bash
inspekt describe
```

**Example output:**
```
This webpage is in Dutch, but is also available in English and French.
At the top you can navigate to services, articles, careers, about us
and contact us. The main part contains a rather long article about an
empathy lab with five headings. The footer contains standard links
such as a sitemap and privacy statement.
```

### What It Analyzes

The `describe` command extracts:

- **Available languages** - Alternate language versions
- **Navigation menus** - Main navigation structure
- **Page landmarks** - Headers, main content, footer, etc.
- **Heading structure** - H1-H6 hierarchy and count
- **Main content type** - Article, form, list, etc.
- **Content length** - Approximate reading time
- **Significant images** - Alt text and image count
- **Forms** - Input fields and their purposes
- **Footer utilities** - Links like privacy policy, sitemap

### Language Control

```bash
# Describe in French
inspekt describe --language fr

# Describe in Spanish
inspekt describe --lang es
```

### Debug Mode

```bash
inspekt describe --debug
```

See the extracted page structure and full prompt.

### Custom Prompts

Edit the description prompt:

```bash
nano ~/inspekt_bridge/prompts/describe.prompt
```

**Default prompt:**
```
Create a concise description of this webpage for a blind user using a screen reader.
Focus on:
- Available languages
- Navigation structure
- Main content type and purpose
- Interactive elements
- Overall page organization

Keep it natural and conversational.

{LANGUAGE_INSTRUCTION}

Page Structure:
{PAGE_STRUCTURE}
```

---

## Configuration

### Language Settings

Set default AI output language in `config.json`:

```json
{
  "ai-language": "en"
}
```

Supported languages:
- `en` - English
- `es` - Spanish
- `fr` - French
- `de` - German
- `nl` - Dutch
- `it` - Italian
- `pt` - Portuguese
- `ja` - Japanese
- `zh` - Chinese
- And more...

### Customize mods Settings

Configure mods behavior:

```bash
# Set default AI model
mods --settings

# Use specific model
mods --model gpt-4

# Use local model with Ollama
mods --model ollama:llama2
```

---

## Practical Use Cases

### Content Research

```bash
# Quickly understand article
inspekt summarize

# Compare summaries
inspekt summarize > summary1.txt
# Navigate to another article
inspekt summarize > summary2.txt
```

### Accessibility Testing

```bash
# Generate page description
inspekt describe

# Test with actual screen reader
inspekt describe | say  # macOS text-to-speech
```

### Multi-language Content

```bash
# Summarize in original language
inspekt summarize

# Translate summary
inspekt summarize --language es
inspekt summarize --language fr
```

### Content Curation

```bash
#!/bin/bash
# Batch summarize articles

URLS=(
  "https://example.com/article1"
  "https://example.com/article2"
  "https://example.com/article3"
)

for url in "${URLS[@]}"; do
  echo "=== $url ===" >> summaries.txt
  inspekt open "$url" --wait
  inspekt summarize >> summaries.txt
  echo "" >> summaries.txt
done
```

### Documentation Assistant

```bash
# Summarize documentation page
inspekt summarize

# Get page overview
inspekt describe

# Extract key sections
inspekt outline
```

---

## Advanced Examples

### Multilingual Research Workflow

```bash
#!/bin/bash
# Research workflow with translations

# Navigate to French article
inspekt open "https://example.fr/article"

# Get English summary
inspekt summarize --language en > summary-en.txt

# Get French summary
inspekt summarize --language fr > summary-fr.txt

# Compare
diff summary-en.txt summary-fr.txt
```

### Accessibility Audit

```bash
#!/bin/bash
# Audit multiple pages

PAGES=(
  "https://example.com/"
  "https://example.com/about"
  "https://example.com/contact"
)

for page in "${PAGES[@]}"; do
  echo "Auditing: $page"
  inspekt open "$page" --wait

  # Get description
  echo "Description:" >> audit.txt
  inspekt describe >> audit.txt

  # Get outline
  echo "Outline:" >> audit.txt
  inspekt outline >> audit.txt

  # Get link analysis
  echo "Links:" >> audit.txt
  inspekt links --only-internal >> audit.txt

  echo "---" >> audit.txt
done
```

### Content Monitoring

```bash
#!/bin/bash
# Monitor article changes

URL="https://example.com/article"

while true; do
  inspekt open "$URL" --wait
  SUMMARY=$(inspekt summarize)

  if [[ "$SUMMARY" != "$LAST_SUMMARY" ]]; then
    echo "Article updated: $URL"
    echo "$SUMMARY"
    LAST_SUMMARY="$SUMMARY"
  fi

  sleep 3600  # Check every hour
done
```

---

## Troubleshooting

### mods Not Found

**Error:**
```
Error: mods command not found
```

**Solution:**
```bash
# Install mods
brew install charmbracelet/tap/mods

# Or check PATH
which mods
```

### API Key Not Set

**Error:**
```
Error: OPENAI_API_KEY not set
```

**Solution:**
```bash
# Set API key
export OPENAI_API_KEY="your-key-here"

# Or configure mods
mods --settings
```

### No Article Content Found

**Error:**
```
Error: Could not extract article content
```

**Possible causes:**
- Page is not an article (try a blog post or news article)
- Content is behind login
- Page uses non-standard structure

**Solution:**
Use `inspekt eval` to extract manually:
```bash
inspekt eval "document.querySelector('article')?.textContent"
```

### Rate Limiting

**Error:**
```
Error: Rate limit exceeded
```

**Solution:**
- Wait and retry
- Use a different AI provider
- Use local models with Ollama

---

## Cost Considerations

### Token Usage

AI features consume tokens:

**Typical usage:**
- `inspekt summarize` - 500-2000 tokens (depending on article length)
- `inspekt describe` - 300-800 tokens (depending on page complexity)

**Cost estimates (OpenAI GPT-3.5-Turbo):**
- ~$0.001 per summary
- ~$0.0005 per description

**Cost estimates (Claude Sonnet):**
- ~$0.003 per summary
- ~$0.001 per description

### Optimization Tips

1. **Use cheaper models** for simple tasks
2. **Batch operations** instead of repeated calls
3. **Use local models** (Ollama) for free inference
4. **Cache results** for frequently accessed pages

### Using Local Models

Free alternative with Ollama:

```bash
# Install Ollama
curl https://ollama.ai/install.sh | sh

# Download model
ollama pull llama2

# Configure mods to use Ollama
mods --model ollama:llama2

# Use normally
inspekt summarize
inspekt describe
```

---

## Best Practices

### 1. Verify AI Output

Always review AI-generated content:

```bash
# Compare with full article
inspekt summarize
inspekt summarize --format full
```

### 2. Use Appropriate Languages

Match output language to use case:

```bash
# English summary for English-speaking users
inspekt summarize --language en

# Native language for accessibility
inspekt describe --language fr  # For French site
```

### 3. Customize Prompts

Tailor prompts to your needs:

```bash
# Edit prompts
nano ~/inspekt_bridge/prompts/summary.prompt
nano ~/inspekt_bridge/prompts/describe.prompt
```

### 4. Monitor Costs

Track API usage:

```bash
# Check mods usage
mods --usage

# Use local models for development
mods --model ollama:llama2
```

---

## Next Steps

- **[Control Mode](control-mode.md)** - Keyboard-only navigation
- **[Advanced Usage](advanced.md)** - Complex patterns and scripting

---

## Quick Reference

| Command | Purpose | Example |
|---------|---------|---------|
| `inspekt summarize` | Summarize article | `inspekt summarize` |
| `inspekt summarize --format full` | Show full article | `inspekt summarize --format full` |
| `inspekt summarize --language es` | Summarize in Spanish | `inspekt summarize --lang es` |
| `inspekt summarize --debug` | Show AI prompt | `inspekt summarize --debug` |
| `inspekt describe` | Describe page for screen readers | `inspekt describe` |
| `inspekt describe --language fr` | Describe in French | `inspekt describe --lang fr` |
| `inspekt describe --debug` | Show extracted structure | `inspekt describe --debug` |

---

## Further Reading

- [mods documentation](https://github.com/charmbracelet/mods)
- [Mozilla Readability](https://github.com/mozilla/readability)
- [OpenAI API](https://platform.openai.com/docs)
- [Anthropic Claude](https://www.anthropic.com/claude)
- [Ollama](https://ollama.ai/)
