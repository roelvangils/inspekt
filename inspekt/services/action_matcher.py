"""
Action matching service for finding elements without AI.

This module provides multiple strategies for matching user actions to page elements:
1. Literal text matching
2. Common actions dictionary
3. URL pattern matching
4. Fuzzy text matching
5. Synonym matching
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ActionMatcher:
    """Intelligent action matcher that finds elements without AI."""

    # Legacy common actions - kept for reference, now loaded from JSON
    COMMON_ACTIONS_LEGACY = {
        "home": {
            "href_patterns": ["/", "/home", "/index", "/homepage"],
            "texts": ["home", "homepage", "main page"],
        },
        "login": {
            "href_patterns": ["/login", "/signin", "/sign-in", "/auth"],
            "texts": ["login", "sign in", "signin", "log in"],
        },
        "logout": {
            "href_patterns": ["/logout", "/signout", "/sign-out"],
            "texts": ["logout", "sign out", "signout", "log out"],
        },
        "signup": {
            "href_patterns": ["/signup", "/register", "/join"],
            "texts": ["sign up", "signup", "register", "join", "create account"],
        },
        "search": {
            "types": ["search", "input-search"],
            "texts": ["search", "find"],
            "aria_labels": ["search"],
        },
        "contact": {
            "href_patterns": ["/contact", "/support", "/help"],
            "texts": ["contact", "contact us", "get in touch", "support"],
        },
        "about": {
            "href_patterns": ["/about", "/about-us"],
            "texts": ["about", "about us", "who we are"],
        },
        "products": {
            "href_patterns": ["/products", "/shop", "/store", "/catalog"],
            "texts": ["products", "shop", "store", "catalog"],
        },
        "pricing": {
            "href_patterns": ["/pricing", "/plans", "/pricing-plans"],
            "texts": ["pricing", "plans", "pricing plans", "cost"],
        },
        "blog": {
            "href_patterns": ["/blog", "/news", "/articles"],
            "texts": ["blog", "news", "articles", "posts"],
        },
        "cart": {
            "href_patterns": ["/cart", "/basket", "/shopping-cart"],
            "texts": ["cart", "basket", "shopping cart", "bag"],
        },
        "checkout": {
            "href_patterns": ["/checkout", "/cart/checkout"],
            "texts": ["checkout", "proceed to checkout", "complete order"],
        },
        "settings": {
            "href_patterns": ["/settings", "/preferences", "/account/settings"],
            "texts": ["settings", "preferences", "configuration"],
        },
        "profile": {
            "href_patterns": ["/profile", "/account", "/user", "/me"],
            "texts": ["profile", "account", "my account", "user profile"],
        },
        "help": {
            "href_patterns": ["/help", "/support", "/faq"],
            "texts": ["help", "support", "faq", "faqs"],
        },
    }

    # Synonyms for better matching
    SYNONYMS = {
        "home": ["homepage", "main", "index", "start"],
        "login": ["signin", "sign in", "log in", "authenticate"],
        "logout": ["signout", "sign out", "log out"],
        "search": ["find", "lookup", "query"],
        "contact": ["reach us", "get in touch", "support"],
        "products": ["catalog", "shop", "store", "items"],
        "about": ["about us", "who we are", "our story"],
        "pricing": ["price", "cost", "plans"],
        "cart": ["basket", "bag", "shopping cart"],
        "settings": ["preferences", "config", "configuration", "options"],
        "profile": ["account", "user", "me"],
    }

    def __init__(self, config: dict[str, Any] | None = None):
        """Initialize action matcher with configuration."""
        self.config = config or {}
        self.common_actions = self._load_common_actions()

    def _load_common_actions(self) -> dict[str, Any]:
        """Load common actions from i18n JSON file."""
        try:
            i18n_path = Path(__file__).parent.parent / "i18n" / "common_actions.json"
            if not i18n_path.exists():
                return {}

            with open(i18n_path, encoding="utf-8") as f:
                data = json.load(f)

            # Filter out JSON schema fields
            return {k: v for k, v in data.items() if not k.startswith("$")}
        except Exception:
            return {}

    def find_literal_match(
        self, action_normalized: str, actionable_elements: list[dict]
    ) -> dict | None:
        """
        Find element whose text literally matches the action.

        Returns best match with score, or None if no good match found.
        """
        action_words = set(action_normalized.split())

        if not action_words:
            return None

        matches = []

        for element in actionable_elements:
            # Normalize element text
            element_text = self._normalize_text(element.get("text", ""))
            element_words = set(element_text.split())

            if not element_words:
                continue

            # Calculate word overlap
            overlap = action_words & element_words
            overlap_ratio = len(overlap) / len(action_words) if action_words else 0

            # Also check href for links
            href_score = 0
            if element.get("href"):
                href_normalized = self._normalize_text(element["href"])
                href_words = set(href_normalized.split("/"))
                href_overlap = action_words & href_words
                href_score = len(href_overlap) / len(action_words) if action_words else 0

            # Take best score
            score = max(overlap_ratio, href_score)

            if score > 0:
                matches.append({"element": element, "score": score, "matched_words": overlap})

        # Sort by score with prominence tie-breaking
        matches.sort(key=lambda x: x["score"], reverse=True)
        matches = self._apply_prominence_bonus(matches)

        threshold = self.config.get("literal_match_threshold", 0.8)

        # Return best match if it meets threshold
        if matches and matches[0]["score"] >= threshold:
            return matches[0]

        return None

    def find_common_action_match(
        self, action_normalized: str, actionable_elements: list[dict], languages: list[str] | None = None
    ) -> dict | None:
        """
        Find element using common action patterns.

        Checks if action matches a known pattern (like "login", "home", etc.)
        and looks for elements matching those patterns. Supports multiple languages.

        Args:
            action_normalized: The normalized action text
            actionable_elements: List of actionable elements
            languages: List of language codes to check (e.g., ['nl', 'en'])
        """
        if not self.common_actions:
            return None

        # Default: try common European languages + English
        if languages is None:
            languages = ["en", "nl", "fr", "de", "es"]

        # Check if action matches a common pattern
        for pattern_name, patterns in self.common_actions.items():
            # Check if pattern name matches action
            if pattern_name in action_normalized or action_normalized in pattern_name:
                return self._find_by_pattern(patterns, actionable_elements, languages)

            # Check if any text in any language matches the action
            if "texts" in patterns:
                for lang in languages:
                    if lang in patterns["texts"]:
                        for text in patterns["texts"][lang]:
                            if text.lower() in action_normalized or action_normalized in text.lower():
                                return self._find_by_pattern(patterns, actionable_elements, languages)

        return None

    def _find_by_pattern(self, patterns: dict, actionable_elements: list[dict], languages: list[str] | None = None) -> dict | None:
        """Find element matching a common action pattern. Supports multilingual text patterns."""
        if languages is None:
            languages = ["en", "nl", "fr", "de", "es"]

        matches = []

        for element in actionable_elements:
            score = 0

            # Check href patterns
            if "href_patterns" in patterns and element.get("href"):
                href = element["href"].lower()
                for pattern in patterns["href_patterns"]:
                    if pattern in href:
                        score = 1.0
                        break

            # Check text patterns (now multilingual)
            if "texts" in patterns:
                element_text = self._normalize_text(element.get("text", ""))

                # Handle both old format (list) and new format (dict with language keys)
                if isinstance(patterns["texts"], dict):
                    # New multilingual format
                    for lang in languages:
                        if lang in patterns["texts"]:
                            for text_pattern in patterns["texts"][lang]:
                                if text_pattern.lower() in element_text or element_text in text_pattern.lower():
                                    score = max(score, 0.9)
                                    break
                            if score >= 0.9:
                                break
                else:
                    # Legacy format (simple list)
                    for text_pattern in patterns["texts"]:
                        if text_pattern in element_text or element_text in text_pattern:
                            score = max(score, 0.9)

            # Check types
            if "types" in patterns and element.get("type"):
                if element["type"] in patterns["types"]:
                    score = max(score, 0.9)

            # Check aria labels
            if "aria_labels" in patterns and element.get("ariaLabel"):
                aria = self._normalize_text(element["ariaLabel"])
                for aria_pattern in patterns["aria_labels"]:
                    if aria_pattern in aria:
                        score = max(score, 0.9)

            if score > 0:
                matches.append({"element": element, "score": score})

        # Sort by score with prominence tie-breaking
        matches.sort(key=lambda x: x["score"], reverse=True)
        matches = self._apply_prominence_bonus(matches)
        if matches:
            return matches[0]

        return None

    def find_substring_match(
        self, action_normalized: str, actionable_elements: list[dict]
    ) -> dict | None:
        """
        Find element whose text contains the action as a substring, or vice versa.

        Handles cases like "bewijs" matching "Bewijsstukken" or "nederlands" matching
        "Nederlands". Returns best match with score and match_type, or None.
        """
        if not action_normalized:
            return None

        matches = []

        for element in actionable_elements:
            element_text = self._normalize_text(element.get("text", ""))
            if not element_text:
                continue

            match_type = None
            score = 0.0

            if action_normalized in element_text:
                # Action is a substring of element text
                match_type = "action_in_element"
                score = len(action_normalized) / len(element_text)
            elif element_text in action_normalized:
                # Element text is a substring of action
                match_type = "element_in_action"
                score = len(element_text) / len(action_normalized)

            # Also check href
            if not match_type and element.get("href"):
                href_normalized = self._normalize_text(element["href"])
                if action_normalized in href_normalized:
                    match_type = "action_in_href"
                    score = len(action_normalized) / len(href_normalized)

            if match_type and score >= 0.4:
                matches.append({
                    "element": element,
                    "score": score,
                    "match_type": match_type,
                })

        matches.sort(key=lambda x: x["score"], reverse=True)
        matches = self._apply_prominence_bonus(matches)

        if matches:
            return matches[0]

        return None

    def find_fuzzy_match(
        self, action_normalized: str, actionable_elements: list[dict]
    ) -> dict | None:
        """
        Find element using fuzzy text matching.

        Handles typos and slight variations in text.
        """
        if not self.config.get("use_fuzzy_matching", True):
            return None

        max_distance = self.config.get("max_fuzzy_distance", 2)

        matches = []

        for element in actionable_elements:
            element_text = self._normalize_text(element.get("text", ""))

            # Calculate Levenshtein distance
            distance = self._levenshtein_distance(action_normalized, element_text)

            # If distance is small relative to text length, it's a match
            if distance <= max_distance:
                score = 1.0 - (distance / max(len(action_normalized), 1))
                matches.append({"element": element, "score": score})

        matches.sort(key=lambda x: x["score"], reverse=True)
        matches = self._apply_prominence_bonus(matches)

        threshold = 0.8

        if matches and matches[0]["score"] >= threshold:
            return matches[0]

        return None

    def find_synonym_match(
        self, action_normalized: str, actionable_elements: list[dict]
    ) -> dict | None:
        """
        Find element using synonym expansion.

        Expands action with synonyms and searches for matches.
        """
        # Find synonyms for action words
        action_words = action_normalized.split()
        expanded_words = set(action_words)

        for word in action_words:
            if word in self.SYNONYMS:
                expanded_words.update(self.SYNONYMS[word])

        # Now search with expanded words
        matches = []

        for element in actionable_elements:
            element_text = self._normalize_text(element.get("text", ""))
            element_words = set(element_text.split())

            # Check overlap with expanded words
            overlap = expanded_words & element_words
            if overlap:
                score = len(overlap) / len(action_words) if action_words else 0
                matches.append({"element": element, "score": score})

        matches.sort(key=lambda x: x["score"], reverse=True)
        matches = self._apply_prominence_bonus(matches)

        threshold = 0.8

        if matches and matches[0]["score"] >= threshold:
            return matches[0]

        return None

    def _apply_prominence_bonus(self, matches: list[dict]) -> list[dict]:
        """
        Apply tiny tie-breaking bonuses based on element prominence.

        Bonuses are small enough (max +0.05) to only matter when scores are
        tied or nearly tied. They never override a genuinely better match.
        """
        for match in matches:
            el = match["element"]
            bonus = 0.0

            # Size bonus: larger clickable area (capped at +0.02)
            pos = el.get("position", {})
            area = pos.get("width", 0) * pos.get("height", 0)
            if area > 0:
                bonus += min(area / 50000, 0.02)

            # Position bonus: higher on page
            if pos.get("y", 9999) < 500:
                bonus += 0.01

            # Element type bonus: buttons over links
            if el.get("type") == "button":
                bonus += 0.01

            # Landmark bonus: nav or main over footer
            context = el.get("context", {})
            if isinstance(context, dict):
                landmark = context.get("role") or context.get("tag", "")
                if landmark in ("navigation", "nav", "main"):
                    bonus += 0.01

            match["score"] = min(match["score"] + bonus, 1.0)

        matches.sort(key=lambda x: x["score"], reverse=True)
        return matches

    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison (lowercase, remove special chars)."""
        import string

        text = text.lower()
        text = text.translate(str.maketrans("", "", string.punctuation))
        return " ".join(text.split())  # Normalize whitespace

    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Calculate Levenshtein distance between two strings."""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                # Cost of insertions, deletions, or substitutions
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]
