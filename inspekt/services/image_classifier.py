"""
PDF Image Classifier.

Classifies PDF images into accessibility-relevant categories using:
1. CLIP (fast, local, free) - if transformers/torch installed
2. Vision AI (higher quality) - fallback using existing AI providers

Categories help determine appropriate alt-text strategies:
- Photographs need descriptive context
- Charts/graphs need data descriptions
- Text-as-image needs OCR transcription
- Decorative images can be marked as artifacts
"""

from __future__ import annotations

import base64
import io
import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


class ImageCategory(StrEnum):
    """Categories for PDF images with accessibility implications."""

    PHOTOGRAPH = "photograph"
    ILLUSTRATION = "illustration"
    INFOGRAPHIC = "infographic"
    CHART_OR_GRAPH = "chart_or_graph"
    TABLE_AS_IMAGE = "table_as_image"
    TEXT_AS_IMAGE = "text_as_image"
    LOGO_OR_ICON = "logo_or_icon"
    DECORATIVE = "decorative"
    UNKNOWN = "unknown"

    @property
    def display_name(self) -> str:
        """Human-readable category name."""
        return {
            ImageCategory.PHOTOGRAPH: "Photograph",
            ImageCategory.ILLUSTRATION: "Illustration",
            ImageCategory.INFOGRAPHIC: "Infographic",
            ImageCategory.CHART_OR_GRAPH: "Chart/Graph",
            ImageCategory.TABLE_AS_IMAGE: "Table as Image",
            ImageCategory.TEXT_AS_IMAGE: "Contains Text",  # Renamed for clarity
            ImageCategory.LOGO_OR_ICON: "Logo/Icon",
            ImageCategory.DECORATIVE: "Decorative",
            ImageCategory.UNKNOWN: "Unknown",
        }.get(self, self.value.replace("_", " ").title())

    @property
    def needs_warning(self) -> bool:
        """Whether this category warrants a warning in reports."""
        return self in (ImageCategory.TABLE_AS_IMAGE, ImageCategory.TEXT_AS_IMAGE)

    @property
    def badge_color(self) -> str:
        """CSS color for category badge."""
        return {
            ImageCategory.PHOTOGRAPH: "#3b82f6",  # Blue
            ImageCategory.ILLUSTRATION: "#8b5cf6",  # Violet
            ImageCategory.INFOGRAPHIC: "#ec4899",  # Pink
            ImageCategory.CHART_OR_GRAPH: "#06b6d4",  # Cyan
            ImageCategory.TABLE_AS_IMAGE: "#ef4444",  # Red (warning)
            ImageCategory.TEXT_AS_IMAGE: "#f97316",  # Orange (warning)
            ImageCategory.LOGO_OR_ICON: "#10b981",  # Emerald
            ImageCategory.DECORATIVE: "#6b7280",  # Gray
            ImageCategory.UNKNOWN: "#9ca3af",  # Light gray
        }.get(self, "#9ca3af")


# Alt-text guidance by category
ALT_TEXT_GUIDANCE: dict[ImageCategory, str] = {
    ImageCategory.PHOTOGRAPH: (
        "Describe who/what is shown, the setting, and any relevant actions or emotions. "
        "Include context that's important for understanding the document."
    ),
    ImageCategory.ILLUSTRATION: (
        "Describe the subject and style of the illustration. "
        "Focus on what information it conveys rather than artistic details."
    ),
    ImageCategory.INFOGRAPHIC: (
        "Provide a brief summary of the main message. "
        "Consider linking to a detailed text alternative or providing a long description."
    ),
    ImageCategory.CHART_OR_GRAPH: (
        "Describe the chart type, what data is being visualized, axis labels, "
        "and key trends or values. Include the main takeaway."
    ),
    ImageCategory.TABLE_AS_IMAGE: (
        "⚠️ CONVERT TO REAL TABLE. If kept as image, describe all column headers "
        "and key data. Tables as images are inaccessible to screen readers."
    ),
    ImageCategory.TEXT_AS_IMAGE: (
        "⚠️ USE ACTUAL TEXT. Include verbatim transcription of all visible text. "
        "Text as images cannot be resized or read by assistive technology."
    ),
    ImageCategory.LOGO_OR_ICON: (
        "Use the organization or brand name. Example: 'Acme Corp logo'. "
        "For icons, describe the action they represent."
    ),
    ImageCategory.DECORATIVE: (
        "Mark as artifact (no alt text needed). "
        "Ensure the image truly conveys no meaningful information before marking decorative."
    ),
    ImageCategory.UNKNOWN: (
        "Review the image to determine its category and write appropriate alt text. "
        "Consider the context and what information the image conveys."
    ),
}

# CLIP category labels for zero-shot classification
CLIP_CATEGORY_LABELS = [
    "a photograph of a real scene or people",
    "an illustration, drawing, or clipart",
    "an infographic with data visualization and text",
    "a chart, graph, or diagram showing data",
    "a table or spreadsheet showing rows and columns of data",
    "text, a document, or a scanned page",
    "a logo, icon, or brand symbol",
    "a decorative pattern, border, or background element",
]

# Mapping from CLIP labels to categories
CLIP_LABEL_TO_CATEGORY = {
    "a photograph of a real scene or people": ImageCategory.PHOTOGRAPH,
    "an illustration, drawing, or clipart": ImageCategory.ILLUSTRATION,
    "an infographic with data visualization and text": ImageCategory.INFOGRAPHIC,
    "a chart, graph, or diagram showing data": ImageCategory.CHART_OR_GRAPH,
    "a table or spreadsheet showing rows and columns of data": ImageCategory.TABLE_AS_IMAGE,
    "text, a document, or a scanned page": ImageCategory.TEXT_AS_IMAGE,
    "a logo, icon, or brand symbol": ImageCategory.LOGO_OR_ICON,
    "a decorative pattern, border, or background element": ImageCategory.DECORATIVE,
}


@dataclass
class ClassificationResult:
    """Result of image classification."""

    category: ImageCategory
    confidence: float  # 0.0 to 1.0
    method: str  # "clip", "vision_ai", "heuristic", "clip+ocr"
    ai_suggested_alt: str | None = None
    ai_provider_used: str | None = None
    raw_scores: dict[str, float] | None = None  # For debugging
    ocr_text: str | None = None  # Extracted text from OCR (when --ocr is used)

    @property
    def guidance(self) -> str:
        """Get alt-text writing guidance for this category."""
        return ALT_TEXT_GUIDANCE.get(self.category, ALT_TEXT_GUIDANCE[ImageCategory.UNKNOWN])

    @property
    def is_confident(self) -> bool:
        """Whether the classification is confident enough to trust."""
        return self.confidence >= 0.4

    @property
    def confidence_level(self) -> str:
        """Get confidence level as high/medium/low for display."""
        if self.confidence >= 0.6:
            return "high"
        elif self.confidence >= 0.4:
            return "medium"
        else:
            return "low"

    @property
    def needs_warning(self) -> bool:
        """Whether this classification warrants a warning."""
        return self.category.needs_warning and self.is_confident


class ImageClassifier:
    """
    Classifies images for accessibility purposes.

    Uses a hybrid approach:
    1. CLIP model (fast, local) if available
    2. Vision AI API fallback
    3. Simple heuristics as last resort
    """

    def __init__(self):
        self._clip_model = None
        self._clip_processor = None
        self._clip_available = None
        self._device = None

    def _check_clip_available(self) -> bool:
        """Check if CLIP dependencies are available."""
        if self._clip_available is not None:
            return self._clip_available

        try:
            import torch  # noqa: F401 -- availability probe only
            from transformers import (  # noqa: F401 -- availability probe only
                CLIPModel,
                CLIPProcessor,
            )

            self._clip_available = True
            logger.debug("CLIP dependencies available")
        except ImportError:
            self._clip_available = False
            logger.debug("CLIP dependencies not available (install with: pip install transformers torch)")

        return self._clip_available

    def _load_clip_model(self) -> bool:
        """Load CLIP model lazily."""
        if self._clip_model is not None:
            return True

        if not self._check_clip_available():
            return False

        try:
            import torch
            from transformers import CLIPModel, CLIPProcessor

            logger.info("Loading CLIP model (first time only)…")

            # Use a smaller, faster CLIP model
            model_name = "openai/clip-vit-base-patch32"
            self._clip_processor = CLIPProcessor.from_pretrained(model_name, use_fast=True)
            self._clip_model = CLIPModel.from_pretrained(model_name)

            # Determine device
            if torch.cuda.is_available():
                self._device = "cuda"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                self._device = "mps"  # Apple Silicon
            else:
                self._device = "cpu"

            self._clip_model = self._clip_model.to(self._device)
            self._clip_model.eval()

            logger.info(f"CLIP model loaded on {self._device}")
            return True

        except Exception as e:
            logger.warning(f"Failed to load CLIP model: {e}")
            self._clip_available = False
            return False

    def classify_with_clip(self, image_bytes: bytes) -> ClassificationResult | None:
        """
        Classify image using CLIP zero-shot classification.

        Args:
            image_bytes: Raw image bytes (PNG, JPEG, etc.)

        Returns:
            ClassificationResult or None if CLIP unavailable
        """
        if not self._load_clip_model():
            return None

        try:
            import torch
            from PIL import Image

            # Load image
            img = Image.open(io.BytesIO(image_bytes))
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            # Process image and text
            inputs = self._clip_processor(
                text=CLIP_CATEGORY_LABELS,
                images=img,
                return_tensors="pt",
                padding=True,
            )

            # Move to device
            inputs = {k: v.to(self._device) for k, v in inputs.items()}

            # Get predictions
            with torch.no_grad():
                outputs = self._clip_model(**inputs)
                logits = outputs.logits_per_image
                probs = logits.softmax(dim=1)

            # Get best prediction
            probs_list = probs[0].cpu().numpy().tolist()
            scores = dict(zip(CLIP_CATEGORY_LABELS, probs_list, strict=False))

            best_label = max(scores, key=scores.get)
            best_score = scores[best_label]

            category = CLIP_LABEL_TO_CATEGORY.get(best_label, ImageCategory.UNKNOWN)

            return ClassificationResult(
                category=category,
                confidence=best_score,
                method="clip",
                raw_scores=scores,
            )

        except Exception as e:
            logger.warning(f"CLIP classification failed: {e}")
            return None

    def classify_with_vision_ai(
        self,
        image_base64: str,
        provider: str | None = None,
    ) -> ClassificationResult | None:
        """
        Classify image using Vision AI API.

        Args:
            image_base64: Base64-encoded image data
            provider: AI provider to use (anthropic, openai, etc.)

        Returns:
            ClassificationResult or None if API unavailable
        """
        try:
            from inspekt.services.ai_integration import AIIntegrationService

            ai_service = AIIntegrationService()

            # Build classification prompt
            prompt = """Classify this image into exactly ONE of these categories:
- photograph: Real-world photo of people, places, or objects
- illustration: Drawing, clipart, or artistic rendering
- infographic: Complex visualization combining data and explanatory text
- chart_or_graph: Bar chart, line graph, pie chart, or similar data visualization
- table_as_image: Tabular data rendered as an image
- text_as_image: Screenshot, scanned document, or text rendered as image
- logo_or_icon: Brand logo, icon, or symbol
- decorative: Background pattern, border, or purely decorative element

Respond with ONLY the category name (e.g., "photograph"), nothing else."""

            # Call vision API
            data_url = f"data:image/png;base64,{image_base64}"
            response = ai_service.call_thoth_vision(prompt, data_url, max_tokens=50)

            if not response:
                return None

            # Parse response
            category_str = response.strip().lower().replace(" ", "_")

            # Map to category
            try:
                category = ImageCategory(category_str)
            except ValueError:
                # Try partial matching
                for cat in ImageCategory:
                    if cat.value in category_str or category_str in cat.value:
                        category = cat
                        break
                else:
                    category = ImageCategory.UNKNOWN

            return ClassificationResult(
                category=category,
                confidence=0.85,  # Vision AI is generally reliable
                method="vision_ai",
                ai_provider_used=provider or "thoth",
            )

        except Exception as e:
            logger.warning(f"Vision AI classification failed: {e}")
            return None

    def classify_with_heuristics(
        self,
        width: float,
        height: float,
        color_space: str | None = None,
        bits_per_component: int | None = None,
    ) -> ClassificationResult:
        """
        Classify image using simple heuristics (fallback).

        Args:
            width: Image width in pixels
            height: Image height in pixels
            color_space: PDF color space (DeviceRGB, DeviceGray, etc.)
            bits_per_component: Bits per color component

        Returns:
            ClassificationResult with low confidence
        """
        aspect_ratio = width / height if height > 0 else 1

        # Very small images are likely icons
        if width < 50 and height < 50:
            return ClassificationResult(
                category=ImageCategory.LOGO_OR_ICON,
                confidence=0.4,
                method="heuristic",
            )

        # Very wide/narrow images might be decorative borders
        if aspect_ratio > 10 or aspect_ratio < 0.1:
            return ClassificationResult(
                category=ImageCategory.DECORATIVE,
                confidence=0.3,
                method="heuristic",
            )

        # Grayscale might be scanned documents
        if color_space and "Gray" in color_space:
            return ClassificationResult(
                category=ImageCategory.TEXT_AS_IMAGE,
                confidence=0.3,
                method="heuristic",
            )

        # Default to unknown
        return ClassificationResult(
            category=ImageCategory.UNKNOWN,
            confidence=0.1,
            method="heuristic",
        )

    def classify(
        self,
        image_bytes: bytes | None = None,
        image_base64: str | None = None,
        width: float = 0,
        height: float = 0,
        color_space: str | None = None,
        bits_per_component: int | None = None,
        use_clip: bool = True,
        use_vision_ai: bool = False,
        ai_provider: str | None = None,
        use_cache: bool = True,
    ) -> ClassificationResult:
        """
        Classify an image using the best available method.

        Args:
            image_bytes: Raw image bytes (preferred for CLIP)
            image_base64: Base64-encoded image (for Vision AI)
            width: Image width (for heuristics fallback)
            height: Image height (for heuristics fallback)
            color_space: PDF color space (for heuristics)
            bits_per_component: Bits per component (for heuristics)
            use_clip: Whether to try CLIP first (default True)
            use_vision_ai: Whether to try Vision AI (default False)
            ai_provider: AI provider for Vision AI
            use_cache: Whether to use cached results (default True)

        Returns:
            ClassificationResult
        """
        # Check cache first for bytes-based classification
        if use_cache and image_bytes:
            from inspekt.services.classification_cache import get_classification_cache

            cache = get_classification_cache()
            cached_result = cache.get_by_bytes(image_bytes)
            if cached_result is not None:
                logger.debug("Using cached classification result")
                return cached_result

        # Try CLIP first (fast, local) - always return CLIP's best guess
        if use_clip and image_bytes:
            result = self.classify_with_clip(image_bytes)
            if result:
                # Cache the result
                if use_cache:
                    from inspekt.services.classification_cache import get_classification_cache

                    cache = get_classification_cache()
                    cache.set_by_bytes(image_bytes, result)
                return result  # Return CLIP result regardless of confidence

        # Try Vision AI (higher quality but slower/costs money)
        if use_vision_ai and image_base64:
            result = self.classify_with_vision_ai(image_base64, ai_provider)
            if result:
                # Cache the result using bytes if available
                if use_cache and image_bytes:
                    from inspekt.services.classification_cache import get_classification_cache

                    cache = get_classification_cache()
                    cache.set_by_bytes(image_bytes, result)
                return result

        # Fall back to heuristics only if CLIP unavailable
        return self.classify_with_heuristics(
            width, height, color_space, bits_per_component
        )

    def classify_from_file(
        self,
        file_path: Path | str,
        use_clip: bool = True,
        use_vision_ai: bool = False,
        ai_provider: str | None = None,
        use_ocr: bool = False,
        ocr_language: str = "eng",
        use_cache: bool = True,
    ) -> ClassificationResult:
        """
        Classify an image from a file path.

        This is a convenience method for classifying images that are already
        saved to disk (e.g., downloaded gallery images).

        SVG files are automatically rendered to PNG before classification,
        since CLIP works with raster images only.

        Results are cached by default to avoid reprocessing the same images.
        The cache is based on file content hash, so renamed/moved files still
        get cache hits.

        Args:
            file_path: Path to the image file
            use_clip: Whether to try CLIP first (default True)
            use_vision_ai: Whether to try Vision AI (default False)
            ai_provider: AI provider for Vision AI
            use_ocr: Whether to run OCR to extract/confirm text content (default False)
            ocr_language: Tesseract language code for OCR (default "eng")
            use_cache: Whether to use cached results (default True)

        Returns:
            ClassificationResult
        """
        from pathlib import Path

        from PIL import Image

        path = Path(file_path)

        # Check cache first (unless disabled or using vision AI which may vary)
        if use_cache and not use_vision_ai:
            from inspekt.services.classification_cache import get_classification_cache

            cache = get_classification_cache()
            cached_result = cache.get(path)
            if cached_result is not None:
                # If OCR was requested but cached result has no OCR text,
                # we need to re-run with OCR
                if use_ocr and cached_result.ocr_text is None:
                    # Check if original method included OCR
                    if "+ocr" not in cached_result.method.lower():
                        logger.debug(f"Cache hit but OCR requested, re-classifying {path.name}")
                    else:
                        return cached_result
                else:
                    return cached_result

        # Handle SVG files by rendering to PNG first
        if path.suffix.lower() == ".svg":
            image_bytes, width, height = self._render_svg_to_png(path)
            if image_bytes is None:
                # SVG rendering failed, fall back to heuristics
                logger.debug(f"SVG rendering failed for {path.name}, using heuristics")
                return self.classify_with_heuristics(width or 100, height or 100)
        else:
            image_bytes = path.read_bytes()
            # Get dimensions for heuristics fallback
            width, height = 0, 0
            try:
                with Image.open(path) as img:
                    width, height = img.size
            except Exception:
                pass

        # Use OCR-enhanced classification if requested
        if use_ocr:
            result = self.classify_with_ocr_enhancement(
                image_bytes=image_bytes,
                width=width,
                height=height,
                use_clip=use_clip,
                ocr_language=ocr_language,
            )
        else:
            result = self.classify(
                image_bytes=image_bytes,
                width=width,
                height=height,
                use_clip=use_clip,
                use_vision_ai=use_vision_ai,
                ai_provider=ai_provider,
            )

        # Store in cache (unless disabled or using vision AI)
        if use_cache and not use_vision_ai:
            from inspekt.services.classification_cache import get_classification_cache

            cache = get_classification_cache()
            cache.set(path, result)

        return result

    def classify_with_ocr_enhancement(
        self,
        image_bytes: bytes,
        width: float = 0,
        height: float = 0,
        use_clip: bool = True,
        ocr_language: str = "eng",
    ) -> ClassificationResult:
        """
        Classify an image using CLIP enhanced with OCR.

        Strategy:
        1. Run CLIP first (fast)
        2. If CLIP says "contains text" OR confidence < 50%: run OCR
        3. If OCR finds meaningful text: boost confidence, store text
        4. If CLIP says text but OCR finds nothing: lower confidence

        Args:
            image_bytes: Raw image bytes
            width: Image width (for heuristics fallback)
            height: Image height (for heuristics fallback)
            use_clip: Whether to use CLIP (default True)
            ocr_language: Tesseract language code for OCR (default "eng")

        Returns:
            ClassificationResult with optional ocr_text
        """
        # Step 1: Run CLIP first
        clip_result = None
        if use_clip:
            clip_result = self.classify_with_clip(image_bytes)

        if clip_result is None:
            # CLIP unavailable, fall back to heuristics + OCR
            clip_result = self.classify_with_heuristics(width, height)

        # Step 2: Determine if we should run OCR
        should_run_ocr = False
        if clip_result.category == ImageCategory.TEXT_AS_IMAGE:
            # CLIP thinks it's text - confirm with OCR
            should_run_ocr = True
        elif clip_result.confidence < 0.5:
            # Low confidence - use OCR as tie-breaker
            should_run_ocr = True

        if not should_run_ocr:
            # High-confidence non-text classification, skip OCR
            return clip_result

        # Step 3: Run OCR
        ocr_text = None
        ocr_has_text = False

        try:
            from inspekt.services.ocr_service import get_ocr_availability, get_ocr_service

            available, _ = get_ocr_availability()
            if available:
                ocr_service = get_ocr_service(language=ocr_language)
                ocr_result = ocr_service.ocr_image_bytes(image_bytes)
                if ocr_result.has_meaningful_text:
                    ocr_has_text = True
                    ocr_text = ocr_result.cleaned_text
        except Exception as e:
            logger.debug(f"OCR failed: {e}")

        # Step 4: Adjust classification based on OCR results
        final_category = clip_result.category
        final_confidence = clip_result.confidence
        method = "clip+ocr" if use_clip else "heuristic+ocr"

        if ocr_has_text:
            # OCR found meaningful text
            if clip_result.category == ImageCategory.TEXT_AS_IMAGE:
                # CLIP and OCR agree - boost confidence
                final_confidence = min(0.95, clip_result.confidence + 0.2)
            else:
                # CLIP missed text - switch to text category
                final_category = ImageCategory.TEXT_AS_IMAGE
                final_confidence = 0.75  # Medium-high confidence
        else:
            # OCR found no meaningful text
            if clip_result.category == ImageCategory.TEXT_AS_IMAGE:
                # CLIP said text but OCR disagrees - lower confidence
                final_confidence = max(0.2, clip_result.confidence - 0.3)

        return ClassificationResult(
            category=final_category,
            confidence=final_confidence,
            method=method,
            raw_scores=clip_result.raw_scores,
            ocr_text=ocr_text,
        )

    def _render_svg_to_png(
        self, svg_path: Path, target_size: int = 512
    ) -> tuple[bytes | None, int, int]:
        """
        Render an SVG file to PNG bytes for classification.

        Args:
            svg_path: Path to the SVG file
            target_size: Target size for the larger dimension (default 512px)

        Returns:
            Tuple of (png_bytes, width, height) or (None, 0, 0) if rendering fails
        """
        # Try cairosvg first (best quality)
        try:
            import cairosvg

            png_bytes = cairosvg.svg2png(
                url=str(svg_path),
                output_width=target_size,
                output_height=target_size,
            )
            # Get actual dimensions from rendered PNG
            from PIL import Image

            img = Image.open(io.BytesIO(png_bytes))
            width, height = img.size
            img.close()
            return png_bytes, width, height
        except ImportError:
            logger.debug("cairosvg not available, trying alternative SVG renderers")
        except Exception as e:
            logger.debug(f"cairosvg failed: {e}")

        # Try svglib + reportlab as fallback
        try:
            from reportlab.graphics import renderPM
            from svglib.svglib import svg2rlg

            drawing = svg2rlg(str(svg_path))
            if drawing:
                # Scale to target size
                scale = target_size / max(drawing.width, drawing.height)
                drawing.width *= scale
                drawing.height *= scale
                drawing.scale(scale, scale)

                png_bytes = renderPM.drawToString(drawing, fmt="PNG")
                return png_bytes, int(drawing.width), int(drawing.height)
        except ImportError:
            logger.debug("svglib not available")
        except Exception as e:
            logger.debug(f"svglib failed: {e}")

        # Try Pillow with svg support (requires pillow-heif or similar)
        try:
            from PIL import Image

            with Image.open(svg_path) as img:
                # Convert to RGB if needed
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGB")
                # Resize if larger than target
                if max(img.size) > target_size:
                    img.thumbnail((target_size, target_size))
                # Save to bytes
                output = io.BytesIO()
                img.save(output, format="PNG")
                return output.getvalue(), img.width, img.height
        except Exception as e:
            logger.debug(f"PIL SVG loading failed: {e}")

        return None, 0, 0


def generate_alt_text_suggestion(
    image_base64: str,
    category: ImageCategory,
    document_context: str | None = None,
    provider: str | None = None,
    image_bytes: bytes | None = None,
    use_cache: bool = True,
) -> str | None:
    """
    Generate an AI-suggested alt text for an image.

    Args:
        image_base64: Base64-encoded image
        category: Classified image category
        document_context: Optional context about the document
        provider: AI provider to use
        image_bytes: Raw image bytes (for caching, derived from base64 if not provided)
        use_cache: Whether to use cached results (default True)

    Returns:
        Suggested alt text or None if unavailable
    """
    # Get image bytes for caching (decode from base64 if not provided)
    if image_bytes is None and use_cache:
        try:
            image_bytes = base64.b64decode(image_base64)
        except Exception:
            # Can't decode, disable caching for this call
            use_cache = False

    # Check cache first
    if use_cache and image_bytes:
        from inspekt.services.classification_cache import get_alt_text_cache

        cache = get_alt_text_cache()
        cached_alt = cache.get(image_bytes, category.value)
        if cached_alt is not None:
            logger.debug(f"Using cached alt-text for {category.value}")
            return cached_alt

    try:
        from inspekt.services.ai_integration import AIIntegrationService

        ai_service = AIIntegrationService()

        # Load the prompt template
        try:
            base_prompt = ai_service.load_prompt("pdf-alt-text.prompt")
        except SystemExit:
            # Prompt file not found, use inline prompt
            base_prompt = _get_default_alt_text_prompt()

        # Format prompt with context
        prompt = base_prompt.format(
            category=category.display_name,
            guidance=ALT_TEXT_GUIDANCE.get(category, ""),
            context=document_context or "No additional context available.",
        )

        # Call vision API
        data_url = f"data:image/png;base64,{image_base64}"
        response = ai_service.call_thoth_vision(prompt, data_url, max_tokens=200)

        if response:
            # Clean up response
            alt_text = response.strip()
            # Remove quotes if present
            if alt_text.startswith('"') and alt_text.endswith('"'):
                alt_text = alt_text[1:-1]

            # Cache the result
            if use_cache and image_bytes:
                from inspekt.services.classification_cache import get_alt_text_cache

                cache = get_alt_text_cache()
                cache.set(image_bytes, category.value, alt_text)

            return alt_text

        return None

    except Exception as e:
        logger.warning(f"Failed to generate alt text suggestion: {e}")
        return None


def _get_default_alt_text_prompt() -> str:
    """Get the default alt text generation prompt."""
    return """You are an accessibility expert writing alternative text for a PDF image.

IMAGE CATEGORY: {category}

GUIDANCE FOR THIS CATEGORY:
{guidance}

DOCUMENT CONTEXT:
{context}

RULES:
1. Be concise but descriptive (aim for 125 characters or less for simple images)
2. Focus on conveying the information the image provides
3. Don't start with "Image of" or "Picture of" - describe directly
4. For charts: describe type, data visualized, and key trends
5. For text images: transcribe all visible text
6. If decorative: respond with exactly "DECORATIVE"

Respond with ONLY the alt text, no explanations or quotes."""


# Singleton instance for reuse
_classifier_instance: ImageClassifier | None = None


def get_classifier() -> ImageClassifier:
    """Get the shared classifier instance."""
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = ImageClassifier()
    return _classifier_instance
