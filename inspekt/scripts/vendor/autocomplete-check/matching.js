/**
 * Autocomplete Check - Main Matching Logic
 * Converted from TypeScript source: https://github.com/PhilippRecke/Autocomplete-Check
 *
 * This file orchestrates the autocomplete prediction algorithm by:
 * 1. Running all 7 matching strategies
 * 2. Aggregating results with weighted averaging
 * 3. Applying length penalties
 * 4. Returning sorted confidence scores for all autocomplete values
 */

// Note: autocompleteDict is declared in matchingclasses.js
// Will be loaded and injected by wrapper
let classesInfluence = null;

/**
 * Generate matching item from a form field element
 * @param {HTMLInputElement|HTMLTextAreaElement|HTMLSelectElement} input
 * @param {Document} document
 * @param {number} posInFields
 * @param {number} posInForm
 * @param {string} formId
 * @returns {Object} matchingItem
 */
function generateMatchingItem(input, document, posInFields, posInForm, formId) {

    const labelList = [...document.getElementsByTagName('label')]
        .filter(label => label.htmlFor == input.id);

    const selectCollection = input instanceof HTMLSelectElement ? input.options : null;
    let selectList = null;
    const selectListValues = [];
    if (selectCollection !== null) {
        for (const item of selectCollection) {
            selectListValues.push(item.value);
        }
        selectList = selectListValues;
    }

    const itemResult = {
        id: input.id || null,

        formId: formId ? formId : null,
        positionInForm: posInForm,
        formHeadings: getHeadingsOfForm(document, formId),
        positionInFields: posInFields,
        label: labelList[0]?.textContent?.trim() ?? null,
        name: input.name || null,
        value: input.value || null,
        checked: input instanceof HTMLInputElement ? input.checked : null,
        selectValues: selectList,
        ariaLabel: input.getAttribute("aria-label"),
        ariaDisabled: input.ariaDisabled || null,
        ariaHidden: input.getAttribute("aria-hidden") || null,
        inputType: input.type || null,
        fieldType: input.tagName.toLowerCase(),
        isInTable: isElementInsideTableCell(input),
        autocomplete: input.getAttribute("autocomplete"),
        correctAutocomplete: null,

        placeholder: input.getAttribute("placeholder"),
        maxLength: input.getAttribute("maxLength") === null ? null : Number(input.getAttribute("maxLength")),
        disabled: input.getAttribute("disabled") || null,
        required: input.required,
        pattern: input.getAttribute("pattern")
    };

    return itemResult;
}

/**
 * Main analysis function - runs all matching strategies and returns sorted predictions
 * @param {Object} data - matchingItem object
 * @param {Object} matchingFunctions - Object containing all matching functions
 * @returns {Array} Sorted array of autocomplete predictions with confidence scores
 */
function analyzeField(data, matchingFunctions) {

    const testResults = generateEmptyTestResults();

    const logTestResults = false;

    logTestResults && console.log(`Individual TestResults for item: ${data.name}`);
    logTestResults && console.log(data);

    // Run all 7 matching strategies
    const labelResults = matchingFunctions.matchByLabel(data);
    logTestResults && console.log(`byLabel: ${data.label}`);
    logTestResults && console.log(labelResults);
    updateTestResults(testResults, labelResults, classesInfluence.matchBy.Label, classesInfluence.testType.Label);

    const placeholderResults = matchingFunctions.matchByPlaceholder(data);
    logTestResults && console.log(`byPlaceholder: ${data.placeholder}`);
    logTestResults && console.log(placeholderResults);
    updateTestResults(testResults, placeholderResults, classesInfluence.matchBy.Placeholder, classesInfluence.testType.Placeholder);

    const fieldTypeResults = matchingFunctions.matchByFieldType(data);
    logTestResults && console.log(`byFieldType: ${data.fieldType}`);
    logTestResults && console.log(fieldTypeResults);
    updateTestResults(testResults, fieldTypeResults, classesInfluence.matchBy.FieldType, classesInfluence.testType.FieldType);

    const inputTypeResults = matchingFunctions.matchByInputType(data);
    logTestResults && console.log(`byInputType: ${data.inputType}`);
    logTestResults && console.log(inputTypeResults);
    updateTestResults(testResults, inputTypeResults, classesInfluence.matchBy.InputType, classesInfluence.testType.InputType);

    const formTypeResults = matchingFunctions.matchByFormType(data);
    logTestResults && console.log(`byFormType: ${data.formId}`);
    logTestResults && console.log(formTypeResults);
    updateTestResults(testResults, formTypeResults, classesInfluence.matchBy.FormType, classesInfluence.testType.FormType);

    const inputNameResults = matchingFunctions.matchByName(data);
    logTestResults && console.log(`byName: ${data.name}`);
    logTestResults && console.log(inputNameResults);
    updateTestResults(testResults, inputNameResults, classesInfluence.matchBy.Name, classesInfluence.testType.Name);

    const inputIdResults = matchingFunctions.matchById(data);
    logTestResults && console.log(`byId: ${data.id}`);
    logTestResults && console.log(inputIdResults);
    updateTestResults(testResults, inputIdResults, classesInfluence.matchBy.Id, classesInfluence.testType.Id);

    logTestResults && console.log("--------collected test results unweighted:");
    logTestResults && console.log(testResults);

    const matchingTableResult = weighTestResults(testResults);

    logTestResults && console.log(matchingTableResult);

    const sortedMatchingResults = matchingTableResult.sort((a, b) => b.confidenceScore - a.confidenceScore);

    return sortedMatchingResults;
}

/**
 * Get autocomplete name from ID
 * @param {string} id
 * @returns {string} Autocomplete value name
 */
function getNameOfAcId(id) {
    const foundIndex = Object.keys(autocompleteDict.byId).indexOf(id);
    if (foundIndex === -1) {
        return "!ERROR!";
    } else {
        return autocompleteDict.byId[id];
    }
}

/**
 * Get autocomplete ID from name
 * @param {string} name
 * @returns {string} Autocomplete ID
 */
function getIdOfAcName(name) {
    const foundIndex = Object.entries(autocompleteDict.byId).map(([key, value]) => value).indexOf(name);
    if (foundIndex === -1) {
        return "!ERROR!";
    } else {
        return Object.keys(autocompleteDict.byId)[foundIndex];
    }
}

/**
 * Generate empty test results table
 * @returns {Array} Empty test results for all autocomplete classes
 */
function generateEmptyTestResults() {
    const testResults = [];
    for (const key of Object.keys(autocompleteDict.byId)) {
        testResults.push({
            classId: key,
            resultsAndWeights: []
        });
    }
    return testResults;
}

/**
 * Update test results with new matching results
 * @param {Array} testResults - Accumulated test results
 * @param {Array} newResults - New results from a matching strategy
 * @param {number} testInfluence - Weight of this test
 * @param {string} testType - "inclusive" or "exclusive"
 */
function updateTestResults(testResults, newResults, testInfluence, testType) {

    // Empty list, to be populated with negative test results (0 confidence score)
    const tmpResults = [...newResults];

    if (testType === "inclusive") {
        // For inclusive tests, add 0-confidence entries for classes not found
        for (const key of Object.keys(autocompleteDict.byId)) {
            if (!newResults.find(r => r.id === key)) {
                tmpResults.push({
                    id: key,
                    confidence: 0,
                    numOfLanguageMatches: 0
                });
            }
        }
    }

    for (const newResult of tmpResults) {
        const foundIndex = testResults.findIndex(i => i.classId == newResult.id);
        const newResultsAndWeightsItem = {result: newResult.confidence, weight: testInfluence};

        if (foundIndex === -1) {
            testResults.push({
                classId: newResult.id,
                resultsAndWeights: [newResultsAndWeightsItem]
            });
        } else {
            testResults[foundIndex].resultsAndWeights.push(newResultsAndWeightsItem);
        }
    }
}

/**
 * Calculate weighted average with length penalty
 * @param {Array} testResults - Test results from all strategies
 * @returns {Array} Matching table with confidence scores
 */
function weighTestResults(testResults) {

    const table = [];

    // Calculate highest length of all results
    const maxLength = testResults.reduce((maxn, item) => Math.max(maxn, item.resultsAndWeights.length), 0);

    // Average of classes, but weigh individual test based on influence
    for (const classResult of testResults) {

        // Calculate scaleFactor of individual classResult length
        const scaleFactor = classResult.resultsAndWeights.length / maxLength;

        const weightedSum = classResult.resultsAndWeights.reduce((sum, item) => sum + (item.result * item.weight), 0);
        const summedInfluences = classResult.resultsAndWeights.reduce((sum, item) => sum + item.weight, 0);
        const weightedResult = weightedSum / summedInfluences;

        // Penalize fewer results
        const lengthPenalty = (1 - weightedResult) * ((1 - scaleFactor) / maxLength) * classesInfluence.lengthPenaltyMultiplier;

        const penalizedResult = weightedResult - lengthPenalty;

        table.push({
            acValue: getNameOfAcId(classResult.classId),
            acId: classResult.classId,
            confidenceScore: penalizedResult
        });
    }

    return table;
}

/**
 * Get headings within a form
 * @param {Document} doc
 * @param {string} formId
 * @returns {Array} Array of heading texts
 */
function getHeadingsOfForm(doc, formId) {
    const headings = [];

    if (formId === undefined || formId === null) {
        return headings;
    }

    const form = doc.getElementById(formId);

    if (form === null) {
        return headings;
    }

    const headingTags = ["h1", "h2", "h3", "h4", "h5", "h6"];

    for (const hx of headingTags) {
        const hs = form.getElementsByTagName(hx);
        for (const h of hs) {
            if (h.innerHTML === "") {
                continue;
            }
            headings.push(h.innerHTML);
        }
    }

    return headings;
}

/**
 * Check if element is inside a table cell
 * @param {HTMLElement} element
 * @returns {boolean}
 */
function isElementInsideTableCell(element) {
    let tmpElement = element;
    while (tmpElement && tmpElement.tagName !== 'HTML') {
        if (tmpElement.tagName === 'TD') {
            return true;
        }
        tmpElement = tmpElement.parentNode;
    }
    return false;
}
