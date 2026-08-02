"""
Autocomplete Check Service

Provides autocomplete attribute checking functionality for form fields
based on the Autocomplete-Check extension logic.

https://github.com/PhilippRecke/Autocomplete-Check
"""

import json
import logging
from pathlib import Path
from typing import Any

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
            with open(self.vendor_dir / "autocomplete-dict.json", encoding="utf-8") as f:
                self.autocomplete_dict = json.load(f)

            with open(self.vendor_dir / "autocomplete-values.json", encoding="utf-8") as f:
                self.autocomplete_values = json.load(f)

            with open(self.vendor_dir / "matchingClassesInfluence.json", encoding="utf-8") as f:
                self.matching_influence = json.load(f)

            # Load JavaScript source files
            with open(self.vendor_dir / "matchingclasses.js", encoding="utf-8") as f:
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

            with open(self.vendor_dir / "matching.js", encoding="utf-8") as f:
                matching_content = f.read()
                # Remove duplicate variable declaration (conflicts with wrapper)
                matching_content = matching_content.replace("let classesInfluence = null;", "")
                self.matching_js = matching_content

            # Note: We don't load autocomplete_check.js anymore - it's inlined in _compile_script
            self.wrapper_js = None  # Not used

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
            "(async function() {",
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
            "  // === Main Check Function ===",
            "  function checkAutocomplete(options) {",
            "    options = options || {};",
            "    const config = {",
            "      confidenceThreshold: options.confidenceThreshold || 0.5,",
            "      includeHidden: options.includeHidden || false,",
            "      includeDisabled: options.includeDisabled || false",
            "    };",
            "",
            "    // Initialize dependencies for matching functions",
            "    if (typeof setDependencies === 'function') {",
            "      setDependencies(AUTOCOMPLETE_DICT, MATCHING_INFLUENCE, getIdOfAcName);",
            "    }",
            "",
            "    const results = {",
            "      summary: {",
            "        total: 0,",
            "        needsAutocomplete: 0,",
            "        hasAutocomplete: 0,",
            "        hasCorrectAutocomplete: 0,",
            "        violations: 0,",
            "        warnings: 0,",
            "        analyzed: 0",
            "      },",
            "      fields: [],",
            "      config: config",
            "    };",
            "",
            "    // Find all form fields",
            "    const allFields = document.querySelectorAll('input, textarea, select');",
            "    let posInFields = 0;",
            "    let processedCount = 0;",
            "    const MAX_FIELDS = 50; // Limit to prevent timeouts",
            "",
            "    for (const field of allFields) {",
            "      if (field.className && field.className.includes('inspekt')) continue;",
            "      results.summary.total++;",
            "      if (processedCount >= MAX_FIELDS) break; // Stop after MAX_FIELDS",
            "",
            "      // Skip if configured",
            "      if (!config.includeHidden && field.type === 'hidden') continue;",
            "      if (!config.includeDisabled && field.disabled) continue;",
            "",
            "      results.summary.analyzed++;",
            "",
            "      // Get parent form info",
            "      let formId = null;",
            "      let posInForm = 0;",
            "      if (field.form) {",
            "        formId = field.form.id || null;",
            "        const formFields = field.form.querySelectorAll('input, textarea, select');",
            "        posInForm = Array.from(formFields).indexOf(field);",
            "      }",
            "",
            "      // Generate matching item with full metadata",
            "      const matchingItem = generateMatchingItem(field, document, posInFields, posInForm, formId);",
            "",
            "      // Define matching functions object",
            "      const matchingFunctions = {",
            "        matchByLabel: matchByLabel,",
            "        matchByPlaceholder: matchByPlaceholder,",
            "        matchByFieldType: matchByFieldType,",
            "        matchByInputType: matchByInputType,",
            "        matchByFormType: matchByFormType,",
            "        matchByName: matchByName,",
            "        matchById: matchById",
            "      };",
            "",
            "      // Run analysis",
            "      const predictions = analyzeField(matchingItem, matchingFunctions);",
            "      const topPrediction = predictions[0] || {acValue: null, confidenceScore: 0};",
            "      const currentAutocomplete = field.getAttribute('autocomplete') || '';",
            "",
            "      // Determine status",
            "      let status = 'unknown';",
            "      let level = 'pass';",
            "      let message = '';",
            "",
            "      if (topPrediction.confidenceScore >= config.confidenceThreshold) {",
            "        results.summary.needsAutocomplete++;",
            "        if (currentAutocomplete && currentAutocomplete !== 'off') {",
            "          results.summary.hasAutocomplete++;",
            "          if (currentAutocomplete === topPrediction.acValue) {",
            "            results.summary.hasCorrectAutocomplete++;",
            "            status = 'correct';",
            "            level = 'pass';",
            "            message = 'Autocomplete attribute is correct';",
            "          } else {",
            "            results.summary.violations++;",
            "            status = 'incorrect';",
            "            level = 'violation';",
            "            message = `Should be '${topPrediction.acValue}' but is '${currentAutocomplete}'`;",
            "          }",
            "        } else {",
            "          results.summary.violations++;",
            "          status = 'missing';",
            "          level = 'violation';",
            "          message = `Missing autocomplete attribute, should be '${topPrediction.acValue}' (confidence: ${Math.round(topPrediction.confidenceScore * 100)}%)`;",
            "        }",
            "      } else {",
            "        if (currentAutocomplete && currentAutocomplete !== 'off') {",
            "          results.summary.warnings++;",
            "          status = 'present';",
            "          level = 'warning';",
            "          message = `Autocomplete '${currentAutocomplete}' present but confidence is low (${Math.round(topPrediction.confidenceScore * 100)}%)`;",
            "        } else {",
            "          status = 'not-applicable';",
            "          level = 'pass';",
            "          message = `Autocomplete not required (confidence: ${Math.round(topPrediction.confidenceScore * 100)}%)`;",
            "        }",
            "      }",
            "",
            "      // Build field result",
            "      const selector = field.id ? '#' + field.id : (field.name ? field.tagName.toLowerCase() + '[name=\"' + field.name + '\"]' : 'field-' + posInFields);",
            "      const fieldResult = {",
            "        selector: selector,",
            "        tagName: field.tagName.toLowerCase(),",
            "        type: field.type || null,",
            "        id: field.id || null,",
            "        name: field.name || null,",
            "        label: matchingItem.label,",
            "        placeholder: matchingItem.placeholder,",
            "        formId: formId,",
            "        positionInForm: posInForm,",
            "        positionInPage: posInFields,",
            "        currentAutocomplete: currentAutocomplete || null,",
            "        predictedAutocomplete: topPrediction.acValue,",
            "        confidence: topPrediction.confidenceScore,",
            "        allPredictions: predictions.slice(0, 5).map(p => ({value: p.acValue, confidence: p.confidenceScore})),",
            "        status: status,",
            "        level: level,",
            "        message: message,",
            "        wcagCompliant: level !== 'violation'",
            "      };",
            "",
            "      results.fields.push(fieldResult);",
            "      posInFields++;",
            "      processedCount++;",
            "    }",
            "",
            "    return results;",
            "  }",
            "",
            "  // === Execute Check ===",
            "  const options = {",
            f"    confidenceThreshold: {confidence_threshold},",
            f"    includeHidden: {str(include_hidden).lower()},",
            f"    includeDisabled: {str(include_disabled).lower()}",
            "  };",
            "",
            "  const result = checkAutocomplete(options);",
            "  return result;",
            "",
            "})()",
        ]

        return "\n".join(script_parts)

    async def check_autocomplete(
        self,
        bridge_executor,
        confidence_threshold: float = 0.5,
        include_hidden: bool = False,
        include_disabled: bool = False,
    ) -> dict[str, Any]:
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
                        "message": "Missing autocomplete attribute…",
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

            exec_result = await asyncio.to_thread(bridge_executor.execute, script, 30.0)

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
