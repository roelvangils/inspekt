"""
AI Integration Service - Language detection and Thoth API integration.

This service handles:
- Language detection from page content and configuration
- Prompt file loading and formatting
- Direct integration with Thoth API for text and vision AI
- Image processing for vision AI
"""

from __future__ import annotations

import base64
import io
import re
import sys
from pathlib import Path
from typing import Any

import click
import requests
from PIL import Image

from inspekt import config as inspekt_config


class AIIntegrationService:
    """Service for AI-powered content analysis and language handling."""

    def __init__(self, prompts_dir: Path | None = None):
        """
        Initialize the AI integration service.

        Args:
            prompts_dir: Directory containing prompt files (default: inspekt/data/prompts/)
        """
        if prompts_dir is None:
            # Default to inspekt/data/prompts/
            current_file = Path(__file__)
            self.prompts_dir = current_file.parent.parent / "data" / "prompts"
        else:
            self.prompts_dir = Path(prompts_dir)

        # Load AI configuration
        self.ai_config = inspekt_config.get_ai_config()

    def get_target_language(
        self,
        language_override: str | None = None,
        page_lang: str | None = None,
    ) -> str | None:
        """
        Determine the language for AI operations.

        Priority:
        1. language_override (from --language flag)
        2. config.json ai-language setting
        3. If "auto", detect from page_lang
        4. Default to None (let AI decide)

        Args:
            language_override: Language code from CLI flag (e.g., "en", "nl", "fr")
            page_lang: Detected page language

        Returns:
            Language code or None to let AI decide
        """
        # Priority 1: CLI flag override
        if language_override:
            return language_override

        # Priority 2: Config file
        config = inspekt_config.load_config()
        config_lang = config.get("ai-language", "auto")

        # If config specifies a language (not "auto"), use it
        if config_lang and config_lang != "auto":
            return config_lang

        # Priority 3: Auto-detect from page
        if page_lang:
            return page_lang

        # Default: let AI decide
        return None

    def extract_page_language(self, content: str) -> str | None:
        """
        Extract page language from content string.

        Looks for patterns like:
        - "**Language:** xx"
        - "lang": "xx"

        Args:
            content: Content string (markdown or JSON)

        Returns:
            Language code or None if not found
        """
        # Try markdown pattern first
        match = re.search(r"\*\*Language:\*\*\s*(\w+)", content)
        if match:
            return match.group(1)

        # Try JSON pattern
        match = re.search(r'"lang"\s*:\s*"(\w+)"', content)
        if match:
            return match.group(1)

        return None

    def load_prompt(self, prompt_name: str) -> str:
        """
        Load a prompt file from the prompts directory.

        Args:
            prompt_name: Name of prompt file (e.g., "describe.prompt", "summary.prompt")

        Returns:
            Prompt content as string

        Raises:
            SystemExit: If prompt file not found
        """
        prompt_path = self.prompts_dir / prompt_name
        if not prompt_path.exists():
            click.echo(f"Error: Prompt file not found: {prompt_path}", err=True)
            sys.exit(1)

        try:
            with open(prompt_path, encoding="utf-8") as f:
                return f.read().strip()
        except IOError as e:
            click.echo(f"Error reading prompt file: {e}", err=True)
            sys.exit(1)

    def format_prompt(
        self,
        base_prompt: str,
        content: str,
        target_lang: str | None = None,
        extra_instructions: str | None = None,
    ) -> str:
        """
        Format a complete prompt with language instructions and content.

        Args:
            base_prompt: Base prompt template
            content: Content to analyze
            target_lang: Target language code (optional)
            extra_instructions: Additional instructions to append (optional)

        Returns:
            Formatted prompt ready for AI tool
        """
        prompt_parts = [base_prompt]

        # Add language instruction if specified
        if target_lang:
            prompt_parts.append(
                f"\n\nIMPORTANT: Provide your response in {target_lang} language."
            )

        # Add extra instructions if provided
        if extra_instructions:
            prompt_parts.append(f"\n\n{extra_instructions}")

        # Add content separator
        prompt_parts.append("\n\n---\n\n")

        # Add content
        prompt_parts.append(content)

        return "".join(prompt_parts)

    def call_thoth_text(
        self,
        prompt: str,
        model: str | None = None,
        timeout: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """
        Call Thoth API for text completion.

        Args:
            prompt: Complete prompt to send to Thoth
            model: Model name (default from config)
            timeout: Request timeout in seconds (default from config)
            max_tokens: Maximum tokens to generate (default from config)

        Returns:
            AI response text

        Raises:
            SystemExit: If API call fails
        """
        # Check for API key
        api_key = self.ai_config.get("api-key", "")
        if not api_key:
            click.echo("Error: THOTH_API_KEY environment variable not set", err=True)
            click.echo("Please set your Thoth API key to use AI features", err=True)
            sys.exit(1)

        # Use config defaults if not specified
        model = model or self.ai_config.get("text-model", "gpt-4o-mini")
        timeout = timeout or self.ai_config.get("timeout", 30)
        max_tokens = max_tokens or self.ai_config.get("max-tokens", 500)
        endpoint = self.ai_config.get("endpoint", "https://thoth.elevenways.be/v1/chat/completions")

        try:
            response = requests.post(
                endpoint,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                },
                timeout=timeout,
            )

            if response.status_code == 200:
                result = response.json()
                if "choices" in result and len(result["choices"]) > 0:
                    return result["choices"][0]["message"]["content"].strip()
                else:
                    click.echo(f"Error: Unexpected API response format: {result}", err=True)
                    sys.exit(1)
            else:
                click.echo(f"Error: Thoth API returned status {response.status_code}", err=True)
                try:
                    error_body = response.json()
                    click.echo(f"Error details: {error_body}", err=True)
                except:
                    click.echo(f"Response text: {response.text[:200]}", err=True)
                sys.exit(1)

        except requests.Timeout:
            click.echo(f"Error: API request timed out after {timeout} seconds", err=True)
            sys.exit(1)
        except requests.RequestException as e:
            click.echo(f"Error calling Thoth API: {e}", err=True)
            sys.exit(1)

    def call_thoth_vision(
        self,
        prompt: str,
        image_data_url: str,
        model: str | None = None,
        timeout: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """
        Call Thoth API for vision completion.

        Args:
            prompt: Text prompt for the vision request
            image_data_url: Base64-encoded image data URL
            model: Model name (default from config)
            timeout: Request timeout in seconds (default from config)
            max_tokens: Maximum tokens to generate (default from config)

        Returns:
            AI response text

        Raises:
            SystemExit: If API call fails
        """
        # Check for API key
        api_key = self.ai_config.get("api-key", "")
        if not api_key:
            click.echo("Warning: THOTH_API_KEY not set, skipping vision analysis", err=True)
            return ""

        # Use config defaults if not specified
        model = model or self.ai_config.get("vision-model", "gpt-4o-mini")
        timeout = timeout or self.ai_config.get("timeout", 30)
        max_tokens = max_tokens or self.ai_config.get("max-tokens", 150)
        endpoint = self.ai_config.get("endpoint", "https://thoth.elevenways.be/v1/chat/completions")

        try:
            # Extract base64 data from data URL
            if ';base64,' in image_data_url:
                base64_data = image_data_url.split(';base64,')[1]
            else:
                click.echo("Error: Invalid image data URL format", err=True)
                return ""

            response = requests.post(
                endpoint,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{base64_data}",
                                        "detail": "low",
                                    },
                                },
                            ],
                        }
                    ],
                    "max_tokens": max_tokens,
                },
                timeout=timeout,
            )

            if response.status_code == 200:
                result = response.json()
                if "choices" in result and len(result["choices"]) > 0:
                    description = result["choices"][0]["message"]["content"].strip()
                    click.echo(f"✓ Got vision description ({len(description)} chars)", err=True)
                    return description
                else:
                    click.echo(f"Warning: No choices in API response: {result}", err=True)
                    return ""
            else:
                click.echo(f"Warning: Vision API returned status {response.status_code}", err=True)
                try:
                    error_body = response.json()
                    click.echo(f"Error details: {error_body}", err=True)
                except:
                    click.echo(f"Response text: {response.text[:200]}", err=True)
                return ""

        except requests.Timeout:
            click.echo(f"Warning: Vision API timed out after {timeout} seconds", err=True)
            return ""
        except requests.RequestException as e:
            click.echo(f"Warning: Failed to call vision API: {e}", err=True)
            return ""
        except Exception as e:
            click.echo(f"Warning: Unexpected error in vision API: {e}", err=True)
            return ""

    def download_and_convert_image(
        self, image_url: str, max_size: int = 800, quality: int = 60
    ) -> str:
        """
        Download an image from a URL and convert it to a base64 data URL.

        Args:
            image_url: URL of the image to download
            max_size: Maximum width/height in pixels (image will be resized if larger)
            quality: JPEG quality (1-100)

        Returns:
            Base64-encoded data URL (data:image/jpeg;base64,...)
        """
        try:
            # Download the image
            click.echo(f"Downloading image from {image_url[:80]}...", err=True)
            response = requests.get(image_url, timeout=10)
            response.raise_for_status()

            # Open image with PIL
            img = Image.open(io.BytesIO(response.content))

            # Convert to RGB if necessary (e.g., RGBA or palette mode)
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')

            # Resize if too large
            width, height = img.size
            if width > max_size or height > max_size:
                # Calculate new size maintaining aspect ratio
                if width > height:
                    new_width = max_size
                    new_height = int(height * (max_size / width))
                else:
                    new_height = max_size
                    new_width = int(width * (max_size / height))

                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                click.echo(
                    f"Resized image from {width}x{height} to {new_width}x{new_height}", err=True
                )

            # Convert to JPEG in memory
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=quality, optimize=True)
            buffer.seek(0)

            # Encode to base64
            img_base64 = base64.b64encode(buffer.read()).decode('utf-8')
            data_url = f"data:image/jpeg;base64,{img_base64}"

            click.echo(f"✓ Image converted to base64 ({len(img_base64)} bytes)", err=True)
            return data_url

        except requests.RequestException as e:
            click.echo(f"Error downloading image: {e}", err=True)
            return ""
        except Exception as e:
            click.echo(f"Error processing image: {e}", err=True)
            return ""

    def get_image_description(
        self, image_data_url: str, prompt: str | None = None
    ) -> str:
        """
        Get a vision AI description of an image.

        Args:
            image_data_url: Base64-encoded image data URL
            prompt: Custom prompt for vision analysis (default: accessibility description)

        Returns:
            Description of the image
        """
        if not prompt:
            prompt = "Describe this image for users who cannot see it in max. 100 words."

        return self.call_thoth_vision(prompt, image_data_url, max_tokens=150)

    def show_debug_prompt(self, prompt: str) -> None:
        """
        Display a formatted debug view of the prompt.

        Args:
            prompt: The prompt to display
        """
        click.echo("=" * 80)
        click.echo("DEBUG: Full prompt that would be sent to AI")
        click.echo("=" * 80)
        click.echo()
        click.echo(prompt)
        click.echo()
        click.echo("=" * 80)

    def generate_description(
        self,
        page_structure: str,
        language_override: str | None = None,
        debug: bool = False,
    ) -> str | None:
        """
        Generate an AI-powered page description.

        Args:
            page_structure: Extracted page structure (markdown format)
            language_override: Optional language override
            debug: If True, show prompt instead of calling AI

        Returns:
            AI-generated description or None if debug mode
        """
        # Extract page language
        page_lang = self.extract_page_language(page_structure)

        # Determine target language
        target_lang = self.get_target_language(
            language_override=language_override,
            page_lang=page_lang,
        )

        # Load and format prompt
        base_prompt = self.load_prompt("describe.prompt")
        full_prompt = self.format_prompt(
            base_prompt=base_prompt,
            content=f"PAGE STRUCTURE:\n\n{page_structure}",
            target_lang=target_lang,
        )

        # Debug mode: show prompt
        if debug:
            self.show_debug_prompt(full_prompt)
            return None

        # Call AI
        click.echo("Generating description...", err=True)
        return self.call_thoth_text(full_prompt)

    def generate_summary(
        self,
        article: dict[str, Any],
        language_override: str | None = None,
        debug: bool = False,
    ) -> str | None:
        """
        Generate an AI-powered article summary.

        Args:
            article: Extracted article data (title, content, byline, lang)
            language_override: Optional language override
            debug: If True, show prompt instead of calling AI

        Returns:
            AI-generated summary or None if debug mode
        """
        title = article.get("title", "Untitled")
        content = article.get("content", "")
        page_lang = article.get("lang")

        # Determine target language
        target_lang = self.get_target_language(
            language_override=language_override,
            page_lang=page_lang,
        )

        # Load and format prompt
        base_prompt = self.load_prompt("summary.prompt")
        full_prompt = self.format_prompt(
            base_prompt=base_prompt,
            content=f"Title: {title}\n\n{content}",
            target_lang=target_lang,
        )

        # Debug mode: show prompt
        if debug:
            self.show_debug_prompt(full_prompt)
            return None

        # Call AI
        click.echo(f"Generating summary for: {title}", err=True)
        return self.call_thoth_text(full_prompt)


# Global service instance (lazy-initialized)
_default_service: AIIntegrationService | None = None


def get_ai_service(prompts_dir: Path | None = None) -> AIIntegrationService:
    """
    Get the default AI integration service instance (singleton pattern).

    Args:
        prompts_dir: Optional custom prompts directory

    Returns:
        Shared AIIntegrationService instance
    """
    global _default_service
    if _default_service is None:
        _default_service = AIIntegrationService(prompts_dir=prompts_dir)
    return _default_service
