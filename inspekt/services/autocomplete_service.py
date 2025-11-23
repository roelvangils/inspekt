"""
Autocomplete Check Service

Provides autocomplete attribute checking functionality for form fields
based on the Autocomplete-Check extension logic.

https://github.com/PhilippRecke/Autocomplete-Check
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class AutocompleteService:
    """Service for checking autocomplete attributes on form fields"""

    def __init__(self):
        self.script_dir = Path(__file__).parent.parent / "scripts"
        self.vendor_dir = self.script_dir / "vendor" / "autocomplete-check"
        self._compiled_script = None
        self._load_resources()

    def _load_resources(self):
        """Load JSON configuration files and JavaScript source"""
        try:
            # Load JSON configurations
            with open(self.vendor_dir / "autocomplete-dict.json", "r", encoding="utf-8") as f:
                self.autocomplete_dict = json.load(f)

            with open(self.vendor_dir / "autocomplete-values.json", "r", encoding="utf-8") as f:
                self.autocomplete_values = json.load(f)

            with open(
                self.vendor_dir / "matchingClassesInfluence.json", "r", encoding="utf-8"
            ) as f:
                self.matching_influence = json.load(f)

            # Load JavaScript source files
            with open(self.vendor_dir / "matchingclasses.js", "r", encoding="utf-8") as f:
                matchingclasses_content = f.read()
                # Remove duplicate variable declarations (they conflict with matching.js)
                # Remove lines: let autocompleteDict = null; let matchingClassesInfluence = null; let getIdOfAcName = null;
                lines_to_remove = [
                    "let autocompleteDict = null;",
                    "let matchingClassesInfluence = null;",
                    "let getIdOfAcName = null;",
                ]
                for line in lines_to_remove:
                    matchingclasses_content = matchingclasses_content.replace(line, "")
                self.matchingclasses_js = matchingclasses_content

            with open(self.vendor_dir / "matching.js", "r", encoding="utf-8") as f:
                self.matching_js = f.read()

            with open(self.script_dir / "autocomplete_check.js", "r", encoding="utf-8") as f:
                self.wrapper_js = f.read()

            logger.info("Autocomplete check resources loaded successfully")

        except Exception as e:
            logger.error(f"Failed to load autocomplete check resources: {e}")
            raise

    def _compile_script(
        self,
        confidence_threshold: float = 0.5,
        include_hidden: bool = False,
        include_disabled: bool = False,
    ) -> str:
        """
        Compile the complete JavaScript that will be injected into the page.

        Args:
            confidence_threshold: Minimum confidence (0-1) to consider autocomplete required
            include_hidden: Include hidden input fields
            include_disabled: Include disabled input fields

        Returns:
            Complete JavaScript code ready for injection
        """
        # Serialize JSON data for injection
        dict_json = json.dumps(self.autocomplete_dict, ensure_ascii=False)
        values_json = json.dumps(self.autocomplete_values, ensure_ascii=False)
        influence_json = json.dumps(self.matching_influence, ensure_ascii=False)

        # Build the complete script
        script_parts = [
            "// Autocomplete Check - Compiled Script for Inspekt",
            "// Based on: https://github.com/PhilippRecke/Autocomplete-Check",
            "",
            "(function() {",
            "  'use strict';",
            "",
            "  // === JSON Configuration Data ===",
            f"  const AUTOCOMPLETE_DICT = {dict_json};",
            f"  const AUTOCOMPLETE_VALUES = {values_json};",
            f"  const MATCHING_INFLUENCE = {influence_json};",
            "",
            "  // === Declare shared variables (used by both files) ===",
            "  let autocompleteDict = AUTOCOMPLETE_DICT;",
            "  let matchingClassesInfluence = MATCHING_INFLUENCE;",
            "  let classesInfluence = MATCHING_INFLUENCE;",
            "",
            "  // === Matching Classes (7 Strategies) ===",
            "  // Inject matchingclasses.js code (variable declarations removed to avoid conflicts)",
            self.matchingclasses_js,
            "",
            "  // === Main Matching Logic ===",
            "  // Inject matching.js code (defines getIdOfAcName function)",
            self.matching_js,
            "",
            "  // === Wrapper Script ===",
            "  // Replace injection placeholders",
            self.wrapper_js.replace("INJECTED_AUTOCOMPLETE_DICT", "AUTOCOMPLETE_DICT")
            .replace("INJECTED_AUTOCOMPLETE_VALUES", "AUTOCOMPLETE_VALUES")
            .replace("INJECTED_MATCHING_INFLUENCE", "MATCHING_INFLUENCE"),
            "",
            "  // === Execute Check ===",
            f"  const options = {{",
            f"    confidenceThreshold: {confidence_threshold},",
            f"    includeHidden: {str(include_hidden).lower()},",
            f"    includeDisabled: {str(include_disabled).lower()}",
            f"  }};",
            "",
            "  const result = checkAutocomplete(options);",
            "  return result;",
            "",
            "})();",
        ]

        return "\n".join(script_parts)

    async def check_autocomplete(
        self,
        bridge_executor,
        confidence_threshold: float = 0.5,
        include_hidden: bool = False,
        include_disabled: bool = False,
    ) -> Dict[str, Any]:
        """
        Check autocomplete attributes on the current page.

        Args:
            bridge_executor: Bridge executor instance for running JavaScript
            confidence_threshold: Minimum confidence (0-1) to consider autocomplete required (default: 0.5)
            include_hidden: Include hidden input fields (default: False)
            include_disabled: Include disabled input fields (default: False)

        Returns:
            Dict containing:
                - summary: Statistics (total, violations, warnings, etc.)
                - fields: List of field analyses with predictions
                - config: Configuration used for the check

        Example result:
            {
                "summary": {
                    "total": 10,
                    "analyzed": 8,
                    "needsAutocomplete": 5,
                    "hasAutocomplete": 3,
                    "hasCorrectAutocomplete": 2,
                    "violations": 3,
                    "warnings": 1
                },
                "fields": [
                    {
                        "selector": "#email",
                        "tagName": "input",
                        "type": "email",
                        "label": "Email Address",
                        "currentAutocomplete": null,
                        "predictedAutocomplete": "email",
                        "confidence": 0.85,
                        "status": "missing",
                        "level": "violation",
                        "message": "Missing autocomplete attribute...",
                        "wcagCompliant": false
                    },
                    ...
                ]
            }
        """
        try:
            # Compile the script with options
            script = self._compile_script(
                confidence_threshold=confidence_threshold,
                include_hidden=include_hidden,
                include_disabled=include_disabled,
            )

            # Execute the script in the browser (using asyncio.to_thread for sync executor)
            import asyncio

            exec_result = await asyncio.to_thread(
                bridge_executor.execute, script, 30.0
            )

            if not exec_result.get("ok"):
                logger.error(f"Script execution failed: {exec_result.get('error')}")
                return {
                    "error": exec_result.get("error", "Failed to execute autocomplete check"),
                    "summary": {
                        "total": 0,
                        "analyzed": 0,
                        "needsAutocomplete": 0,
                        "hasAutocomplete": 0,
                        "hasCorrectAutocomplete": 0,
                        "violations": 0,
                        "warnings": 0,
                    },
                    "fields": [],
                }

            result = exec_result.get("result")

            if not result or not isinstance(result, dict):
                logger.error(f"Invalid autocomplete check result: {result}")
                return {
                    "error": "Failed to analyze autocomplete attributes",
                    "summary": {
                        "total": 0,
                        "analyzed": 0,
                        "needsAutocomplete": 0,
                        "hasAutocomplete": 0,
                        "hasCorrectAutocomplete": 0,
                        "violations": 0,
                        "warnings": 0,
                    },
                    "fields": [],
                }

            logger.info(
                f"Autocomplete check completed: {result['summary']['analyzed']} fields analyzed, "
                f"{result['summary']['violations']} violations, "
                f"{result['summary']['warnings']} warnings"
            )

            return result

        except Exception as e:
            logger.error(f"Error running autocomplete check: {e}")
            return {
                "error": str(e),
                "summary": {
                    "total": 0,
                    "analyzed": 0,
                    "needsAutocomplete": 0,
                    "hasAutocomplete": 0,
                    "hasCorrectAutocomplete": 0,
                    "violations": 0,
                    "warnings": 0,
                },
                "fields": [],
            }


# Global service instance
_autocomplete_service = None


def get_autocomplete_service() -> AutocompleteService:
    """Get or create the global AutocompleteService instance"""
    global _autocomplete_service
    if _autocomplete_service is None:
        _autocomplete_service = AutocompleteService()
    return _autocomplete_service
