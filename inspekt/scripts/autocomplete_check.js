/**
 * Autocomplete Check - Inspekt Integration
 * Based on: https://github.com/PhilippRecke/Autocomplete-Check
 *
 * This script analyzes form fields on the current page and predicts appropriate
 * autocomplete attributes according to WCAG 2.1 SC 1.3.5 (Identify Input Purpose).
 *
 * Usage:
 *   const result = await checkAutocomplete(options);
 *
 * Options:
 *   - confidenceThreshold: Minimum confidence (0-1) to consider autocomplete required (default: 0.5)
 *   - includeHidden: Include hidden input fields (default: false)
 *   - includeDisabled: Include disabled input fields (default: false)
 *
 * Returns:
 *   {
 *     summary: { total, needsAutocomplete, hasAutocomplete, violations, warnings },
 *     fields: [ { element, prediction, status, ... } ]
 *   }
 */

// INJECTED_AUTOCOMPLETE_DICT - Will be replaced by Python service
const AUTOCOMPLETE_DICT = INJECTED_AUTOCOMPLETE_DICT;

// INJECTED_AUTOCOMPLETE_VALUES - Will be replaced by Python service
const AUTOCOMPLETE_VALUES = INJECTED_AUTOCOMPLETE_VALUES;

// INJECTED_MATCHING_INFLUENCE - Will be replaced by Python service
const MATCHING_INFLUENCE = INJECTED_MATCHING_INFLUENCE;

// INJECTED_MATCHING_CLASSES - Will be replaced by Python service
// This should contain the matchingclasses.js code

// INJECTED_MATCHING - Will be replaced by Python service
// This should contain the matching.js code

/**
 * Main autocomplete check function
 */
function checkAutocomplete(options = {}) {
    const config = {
        confidenceThreshold: options.confidenceThreshold || 0.5,
        includeHidden: options.includeHidden || false,
        includeDisabled: options.includeDisabled || false
    };

    // Initialize dependencies for matching functions
    if (typeof setDependencies === 'function') {
        // For matchingclasses.js
        setDependencies(AUTOCOMPLETE_DICT, MATCHING_INFLUENCE, getIdOfAcName);
    }

    const results = {
        summary: {
            total: 0,
            needsAutocomplete: 0,
            hasAutocomplete: 0,
            hasCorrectAutocomplete: 0,
            violations: 0,
            warnings: 0,
            analyzed: 0
        },
        fields: [],
        config: config
    };

    // Find all form fields (input, textarea, select)
    const allFields = document.querySelectorAll('input, textarea, select');

    let posInFields = 0;

    for (const field of allFields) {
        // Skip internal/generated fields
        if (field.className && field.className.includes('inspekt')) {
            continue;
        }

        results.summary.total++;

        // Filter based on options
        const fieldType = field.getAttribute('type');
        if (!config.includeHidden && fieldType === 'hidden') {
            continue;
        }
        if (!config.includeDisabled && field.disabled) {
            continue;
        }

        // Get parent form if exists
        let formId = null;
        let posInForm = 0;
        const parentForm = field.closest('form');
        if (parentForm) {
            formId = parentForm.id || null;
            // Calculate position within form
            const formFields = parentForm.querySelectorAll('input, textarea, select');
            posInForm = Array.from(formFields).indexOf(field);
        }

        // Generate matching item with metadata
        const matchingItem = generateMatchingItem(field, document, posInFields, posInForm, formId);

        // Run analysis with all matching strategies
        const matchingFunctions = {
            matchByLabel,
            matchByPlaceholder,
            matchByFieldType,
            matchByInputType,
            matchByFormType,
            matchByName,
            matchById
        };

        const predictions = analyzeField(matchingItem, matchingFunctions);

        // Get top prediction
        const topPrediction = predictions[0];
        const existingAutocomplete = field.getAttribute('autocomplete');

        // Determine status
        const status = determineStatus(
            topPrediction,
            existingAutocomplete,
            config.confidenceThreshold
        );

        // Count statistics
        results.summary.analyzed++;
        if (topPrediction.confidenceScore >= config.confidenceThreshold) {
            results.summary.needsAutocomplete++;
        }
        if (existingAutocomplete && existingAutocomplete !== 'off') {
            results.summary.hasAutocomplete++;
        }
        if (existingAutocomplete === topPrediction.acValue) {
            results.summary.hasCorrectAutocomplete++;
        }
        if (status.level === 'violation') {
            results.summary.violations++;
        }
        if (status.level === 'warning') {
            results.summary.warnings++;
        }

        // Build field result
        const fieldResult = {
            // Element identification
            selector: getSelector(field),
            tagName: field.tagName.toLowerCase(),
            type: field.getAttribute('type'),
            id: field.id || null,
            name: field.name || null,

            // Context
            label: matchingItem.label,
            placeholder: matchingItem.placeholder,
            formId: formId,
            positionInForm: posInForm,
            positionInPage: posInFields,

            // Current autocomplete
            currentAutocomplete: existingAutocomplete,

            // Prediction
            predictedAutocomplete: topPrediction.acValue,
            confidence: topPrediction.confidenceScore,
            allPredictions: predictions.slice(0, 5).map(p => ({
                value: p.acValue,
                confidence: p.confidenceScore
            })),

            // Status
            status: status.status,
            level: status.level,
            message: status.message,

            // WCAG
            wcagCompliant: status.level !== 'violation'
        };

        results.fields.push(fieldResult);

        posInFields++;
    }

    return results;
}

/**
 * Determine the status of a field based on prediction and existing autocomplete
 */
function determineStatus(prediction, existingAutocomplete, threshold) {
    const predicted = prediction.acValue;
    const confidence = prediction.confidenceScore;

    // High confidence - autocomplete is recommended
    if (confidence >= threshold) {
        if (existingAutocomplete === predicted) {
            return {
                status: 'correct',
                level: 'pass',
                message: `Autocomplete attribute "${predicted}" is correct`
            };
        } else if (existingAutocomplete && existingAutocomplete !== 'off') {
            return {
                status: 'incorrect',
                level: 'violation',
                message: `Autocomplete should be "${predicted}" but is "${existingAutocomplete}"`
            };
        } else {
            return {
                status: 'missing',
                level: 'violation',
                message: `Missing autocomplete attribute, should be "${predicted}" (confidence: ${(confidence * 100).toFixed(0)}%)`
            };
        }
    }
    // Low confidence - autocomplete is optional
    else {
        if (existingAutocomplete && existingAutocomplete !== 'off') {
            return {
                status: 'present',
                level: 'warning',
                message: `Autocomplete "${existingAutocomplete}" present but confidence is low (${(confidence * 100).toFixed(0)}%)`
            };
        } else {
            return {
                status: 'not-applicable',
                level: 'pass',
                message: `Autocomplete not required (confidence: ${(confidence * 100).toFixed(0)}%)`
            };
        }
    }
}

/**
 * Generate a CSS selector for an element
 */
function getSelector(element) {
    if (element.id) {
        return `#${element.id}`;
    }
    if (element.name) {
        return `${element.tagName.toLowerCase()}[name="${element.name}"]`;
    }

    // Build selector from parent chain
    const path = [];
    let current = element;
    while (current && current.tagName) {
        let selector = current.tagName.toLowerCase();
        if (current.className && typeof current.className === 'string') {
            const classes = current.className.trim().split(/\s+/).filter(c => !c.includes('inspekt'));
            if (classes.length > 0) {
                selector += '.' + classes[0];
            }
        }
        path.unshift(selector);
        current = current.parentElement;
        if (path.length >= 3) break; // Limit depth
    }

    return path.join(' > ');
}

// Return the function for external use
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { checkAutocomplete };
} else {
    // Browser environment - return result directly
    checkAutocomplete;
}
