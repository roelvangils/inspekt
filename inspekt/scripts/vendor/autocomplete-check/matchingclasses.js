/**
 * Autocomplete Check - Matching Classes
 * Converted from TypeScript source: https://github.com/PhilippRecke/Autocomplete-Check
 *
 * This file contains the 7 matching strategies for predicting autocomplete attributes:
 * 1. matchByLabel (weight: 5)
 * 2. matchByPlaceholder (weight: 4)
 * 3. matchByName (weight: 2)
 * 4. matchById (weight: 2)
 * 5. matchByFieldType (weight: 1)
 * 6. matchByInputType (weight: 1)
 * 7. matchByFormType (weight: 1)
 */

// Will be injected by the wrapper
let autocompleteDict = null;
let matchingClassesInfluence = null;
let getIdOfAcName = null;

function setDependencies(dict, influence, getIdFn) {
    autocompleteDict = dict;
    matchingClassesInfluence = influence;
    getIdOfAcName = getIdFn;
}

// Match by label text (highest weight: 5)
function matchByLabel(item) {
    let topResults = [];

    if (item.label === null) {
        return topResults;
    }

    topResults = topResults.concat(performMultiLanguageLabelMatch(item.label, true));

    return weighConfidences(topResults);
}

// Match by placeholder text (weight: 4)
function matchByPlaceholder(item) {
    let topResults = [];

    if (item.placeholder === null) {
        return topResults;
    }

    topResults = topResults.concat(performMultiLanguageLabelMatch(item.placeholder, false));

    return weighConfidences(topResults);
}

// Match by field type (input/textarea/select) (weight: 1)
function matchByFieldType(item) {
    const topResults = [];

    if (item.fieldType === null) {
        return topResults;
    }

    const possibleFieldTypes = autocompleteDict.byFieldType;

    if (Object.keys(possibleFieldTypes).includes(item.fieldType)) {

        for (const id of possibleFieldTypes[item.fieldType]) {

            let confidence = 0.75;

            if (possibleFieldTypes[item.fieldType].length < 30) {
                confidence = 1;
            }

            topResults.push({id: `${id}`, confidence: confidence, numOfLanguageMatches: 0});
        }
    }

    return weighConfidences(topResults);
}

// Match by input type attribute (weight: 1)
function matchByInputType(item) {
    const topResults = [];

    if (item.fieldType !== "input" || item.inputType === null) {
        return topResults;
    }

    const possibleInputTypes = autocompleteDict.byInputType;

    if (Object.keys(possibleInputTypes).includes(item.inputType)) {

        for (const id of possibleInputTypes[item.inputType]) {

            let confidence = 0.5;

            if (possibleInputTypes[item.inputType].length < 5) {
                confidence = 1;

            } else if (possibleInputTypes[item.inputType].length > 30) {
                confidence = 0.75;
            }

            topResults.push({id: `${id}`, confidence: confidence, numOfLanguageMatches: 0});
        }
    }

    return weighConfidences(topResults);
}

// Match by form type (login vs signup) - for password field disambiguation (weight: 1)
function matchByFormType(item) {
    const topResults = [];
    if (item.formId === undefined || item.formId === null) {
        return topResults;
    }
    if (item.formHeadings === null || item.formHeadings.length === 0) {
        return topResults;
    }

    const hits = {
        "login": {
            "full": 0,
            "partial": 0,
            "reverse-partial": 0,
            "none": 0
        },
        "signup": {
            "full": 0,
            "partial": 0,
            "reverse-partial": 0,
            "none": 0
        },
    };

    const foundLanguages = Object.keys(autocompleteDict).filter(key => key.startsWith("byFormType_"));

    for (const heading of item.formHeadings) {
        for (const language of foundLanguages) {
            const formTypes = autocompleteDict[language];
            for (const key of Object.keys(formTypes)) {
                const substringSearchResult = substringSearch(formTypes[key], heading);

                if (key === "login") {
                    hits.login[substringSearchResult] = hits.login[substringSearchResult] + 1;
                }

                if (key === "signup") {
                    hits.signup[substringSearchResult] = hits.signup[substringSearchResult] + 1;
                }
            }
        }
    }

    const loginScore = (hits.login.full * 2) + hits.login.partial;
    const signupScore = (hits.signup.full * 2) + hits.signup.partial;

    const newPasswordId = getIdOfAcName("new-password");
    const currentPasswordId = getIdOfAcName("current-password");

    if (loginScore < signupScore) {
        topResults.push({id: `${newPasswordId}`, confidence: 1, numOfLanguageMatches: 1});
        topResults.push({id: `${currentPasswordId}`, confidence: 0.5, numOfLanguageMatches: 1});
    } else {
        topResults.push({id: `${newPasswordId}`, confidence: 0.5, numOfLanguageMatches: 1});
        topResults.push({id: `${currentPasswordId}`, confidence: 1, numOfLanguageMatches: 1});
    }

    return weighConfidences(topResults);
}

// Match by name attribute (weight: 2)
function matchByName(item) {
    let topResults = [];

    if (item.name === null) {
        return topResults;
    }

    topResults = topResults.concat(performMultiLanguageLabelMatch(item.name, true));

    return weighConfidences(topResults);
}

// Match by id attribute (weight: 2)
function matchById(item) {
    let topResults = [];

    if (item.id === null) {
        return topResults;
    }

    topResults = topResults.concat(performMultiLanguageLabelMatch(item.id, true));

    return weighConfidences(topResults);
}

// Weigh confidences based on length and average (currently returns data as-is)
function weighConfidences(data) {
    const totalConfidence = data.reduce((sum, item) => sum + item.confidence, 0);
    const averageWeight = totalConfidence / data.length;

    // Note: Original implementation returns data as-is, not recalculated weights
    return data;
}

// Core substring search algorithm
// Returns: "full" (100%), "partial" (80%), "reverse-partial" (55%), or "none" (0%)
function substringSearch(labelExamples, labelText) {
    // Search for full occurrences
    if (labelExamples.map(label => sanitizeKeyword(label)).includes(sanitizeKeyword(labelText))) {
        return "full";
    }

    // Split by whitespace, filter out empty strings
    const labelWords = labelText.split(/\s+/).filter(Boolean);

    let partialHit = false;
    let reversePartialHit = false;

    // Search for partial occurrences (substrings in both label and examples)
    for (const word of labelWords) {

        // Do not search for empty strings
        const sanitizedWord = sanitizeKeyword(word);
        if (sanitizedWord === "") {
            continue;
        }

        // Only perform partial searches on words that are at least 3 characters long
        if (sanitizedWord.length < 3) {
            continue;
        }

        // If any word is a substring in any label array, return partial
        // Example: dict="telephone", word="phone"
        if (labelExamples.some(label => sanitizeKeyword(label).indexOf(sanitizedWord) !== -1)) {
            partialHit = true;
        }

        // If any dict entry is substring of label word, return reverse-partial
        // Example: dict="phone", word="telephone"
        if (labelExamples.some(label => sanitizedWord.indexOf(sanitizeKeyword(label)) !== -1)) {
            reversePartialHit = true;
        }
    }

    // Partial is higher valued than reverse hit
    if (partialHit) {
        return "partial";
    }

    if (reversePartialHit) {
        return "reverse-partial";
    }

    return "none";
}

// Sanitize keyword for matching
function sanitizeKeyword(keyword) {
    // Remove whitespace and keep only alphanumeric chars, set to lowercase
    return keyword.replace(/ /g, "").replace(/\W/g, '').toLowerCase();
}

// Perform multi-language label matching
function performMultiLanguageLabelMatch(searchString, overrideFullMatches) {

    const topResults = [];

    const foundLanguages = Object.keys(autocompleteDict).filter(key => key.startsWith("byLabel_"));

    // Always perform English search first
    const labelExamplesEN = autocompleteDict.byLabel_EN;
    for (const id of Object.keys(labelExamplesEN)) {
        const substringSearchResult = substringSearch(labelExamplesEN[id], searchString);

        if (["full", "partial", "reverse-partial"].includes(substringSearchResult)) {
            topResults.push({
                id: id,
                confidence: 1 * matchingClassesInfluence.labelSubstringSearch[substringSearchResult],
                numOfLanguageMatches: 1
            });
        }
    }

    // Search other languages
    for (const language of foundLanguages) {
        if (language === "byLabel_EN") {continue;}

        const labelExamples = autocompleteDict[language];
        for (const id of Object.keys(labelExamples)) {
            const substringSearchResult = substringSearch(labelExamples[id], searchString);

            if (["full", "partial", "reverse-partial"].includes(substringSearchResult)) {

                const foundIndex = topResults.findIndex(i => i.id == id);
                // Check if entry already exists in results. If so update only confidence score

                if (foundIndex === -1) {
                    topResults.push({
                        id: id,
                        confidence: 1 * matchingClassesInfluence.labelSubstringSearch[substringSearchResult],
                        numOfLanguageMatches: 1
                    });

                // If EN is a direct hit, don't override
                } else if (overrideFullMatches && topResults[foundIndex].confidence === matchingClassesInfluence.labelSubstringSearch["full"]) {
                    // Do nothing
                // If there is a direct hit, override EN search result
                } else if (overrideFullMatches && substringSearchResult === "full") {
                    topResults[foundIndex].confidence = matchingClassesInfluence.labelSubstringSearch[substringSearchResult];
                } else {
                    topResults[foundIndex].confidence = (topResults[foundIndex].confidence + 1 * matchingClassesInfluence.labelSubstringSearch[substringSearchResult]) / (topResults[foundIndex].numOfLanguageMatches + 1);
                    topResults[foundIndex].numOfLanguageMatches = topResults[foundIndex].numOfLanguageMatches + 1;
                }
            }
        }
    }

    return topResults;
}
