// Send keys to the active element in the browser
// Enhanced human-like typing simulation for bot detection evasion
(function(text, delayMs, clearFirst, typoRate) {
    return new Promise(function(resolve) {
        var activeEl = document.activeElement;

        if (!activeEl) {
            resolve({ error: 'No active element found' });
            return;
        }

        // Check if element can receive text input
        var isInput = activeEl.tagName === 'INPUT' ||
                      activeEl.tagName === 'TEXTAREA' ||
                      activeEl.isContentEditable;

        if (!isInput) {
            resolve({
                error: 'Active element is not an input field',
                activeElement: activeEl.tagName,
                hint: 'Click on an input field first'
            });
            return;
        }

        // Clear existing content if requested
        if (clearFirst) {
            if (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA') {
                activeEl.value = '';
                activeEl.selectionStart = 0;
                activeEl.selectionEnd = 0;
            } else if (activeEl.isContentEditable) {
                activeEl.textContent = '';
            }
        }

        var i = 0;
        var prevChar = null;
        var isHumanMode = delayMs === -1;  // -1 signals human-like typing

        // ============================================================
        // STATISTICAL DISTRIBUTION FUNCTIONS
        // Human typing follows log-normal distribution, not uniform
        // ============================================================

        // Box-Muller transform for Gaussian random numbers
        function gaussianRandom(mean, stdDev) {
            var u1 = Math.random();
            var u2 = Math.random();
            // Avoid log(0) which gives -Infinity
            if (u1 === 0) u1 = 0.0001;
            var z = Math.sqrt(-2.0 * Math.log(u1)) * Math.cos(2.0 * Math.PI * u2);
            return mean + z * stdDev;
        }

        // Log-normal distribution - matches real human reaction time data
        // Research shows human IKI (inter-keystroke intervals) follow log-normal
        function logNormalDelay(median, sigma) {
            var mu = Math.log(median);
            var gaussian = gaussianRandom(0, sigma);
            var result = Math.exp(mu + gaussian);
            // Clamp to reasonable range (prevent extreme outliers)
            return Math.max(35, Math.min(result, median * 4));
        }

        // ============================================================
        // DIGRAPH TIMING - Common letter pairs typed faster
        // Based on motor learning and finger movement patterns
        // ============================================================

        var digraphSpeed = {
            // English digraphs - very common, typed as units
            'th': 0.62, 'he': 0.68, 'in': 0.70, 'er': 0.65, 'an': 0.70,
            're': 0.68, 'on': 0.72, 'en': 0.70, 'nd': 0.73, 'ed': 0.70,
            'es': 0.70, 'ou': 0.73, 'ti': 0.72, 'te': 0.68, 'is': 0.72,
            'at': 0.73, 'al': 0.73, 'ar': 0.74, 'st': 0.70, 'to': 0.76,
            'nt': 0.72, 'ng': 0.78, 'se': 0.72, 'ha': 0.74, 'as': 0.75,
            'io': 0.80, 'le': 0.72, 've': 0.72, 'co': 0.78, 'me': 0.74,
            'de': 0.75, 'hi': 0.76, 'ri': 0.75, 'ro': 0.76, 'ic': 0.78,
            'ne': 0.73, 'ea': 0.80, 'ra': 0.76, 'ce': 0.75, 'li': 0.74,
            'ch': 0.73, 'be': 0.78, 'll': 0.68, 'ec': 0.80, 'ma': 0.78,
            'si': 0.76, 'om': 0.80, 'ur': 0.77, 'ca': 0.78, 'el': 0.74,
            'ta': 0.76, 'la': 0.75, 'ns': 0.74, 'di': 0.77, 'fo': 0.80,
            'ho': 0.78, 'pe': 0.76, 'ec': 0.80, 'pr': 0.82, 'no': 0.77,
            'ct': 0.78, 'us': 0.77, 'ac': 0.78, 'ot': 0.78, 'il': 0.75,
            'tr': 0.80, 'ly': 0.76, 'nc': 0.78, 'et': 0.75, 'ut': 0.78,
            'ss': 0.70, 'so': 0.78, 'rs': 0.76, 'un': 0.77, 'lo': 0.76,
            'wa': 0.78, 'ge': 0.77, 'ie': 0.78, 'wh': 0.75, 'ee': 0.72,
            'oo': 0.73, 'tt': 0.72, 'ff': 0.74, 'pp': 0.75, 'rr': 0.75,
            'mm': 0.76, 'nn': 0.74,

            // Dutch digraphs - common in Dutch text
            'ij': 0.62, 'aa': 0.68, 'oe': 0.70, 'ui': 0.73, 'eu': 0.73,
            'ei': 0.70, 'au': 0.76, 'ou': 0.73, 'uu': 0.75, 'sch': 0.70,
            'nk': 0.76, 'dt': 0.78, 'gt': 0.80, 'kt': 0.78, 'pt': 0.80,
            'cht': 0.75, 'ng': 0.78,
            // Common Dutch words/combos typed as chunks
            'van': 0.70, 'een': 0.68, 'het': 0.65, 'dat': 0.70, 'met': 0.72,
            'niet': 0.68, 'voor': 0.70, 'zijn': 0.72, 'naar': 0.73,

            // Same-finger sequences are SLOWER (requires sequential finger movement)
            'ed': 0.70, 'de': 0.75, // d and e - same finger on QWERTY
            'ce': 1.10, 'ec': 1.12, // c and e - reaching
            'nu': 1.12, 'un': 1.10, // same finger sequences
            'my': 1.15, 'ym': 1.18,
            'br': 1.08, 'rb': 1.10, // reaching across
            'vt': 1.15, 'tv': 1.18,
            'bg': 1.12, 'gb': 1.15,
            'hn': 1.10, 'nh': 1.08,
            'ju': 1.10, 'uj': 1.12,
            'ki': 1.08, 'ik': 1.10,
            'lo': 1.08, 'ol': 1.06
        };

        function getDigraphMultiplier(prev, curr) {
            if (!prev) return 1.0;
            var digraph = (prev + curr).toLowerCase();
            return digraphSpeed[digraph] || 1.0;
        }

        // ============================================================
        // HAND POSITION MODELING
        // Keys on same hand/finger are slower, alternating hands faster
        // ============================================================

        var keyPositions = {
            // Left hand keys
            'q': {hand: 'L', finger: 0, row: 1}, 'a': {hand: 'L', finger: 0, row: 2}, 'z': {hand: 'L', finger: 0, row: 3},
            'w': {hand: 'L', finger: 1, row: 1}, 's': {hand: 'L', finger: 1, row: 2}, 'x': {hand: 'L', finger: 1, row: 3},
            'e': {hand: 'L', finger: 2, row: 1}, 'd': {hand: 'L', finger: 2, row: 2}, 'c': {hand: 'L', finger: 2, row: 3},
            'r': {hand: 'L', finger: 3, row: 1}, 'f': {hand: 'L', finger: 3, row: 2}, 'v': {hand: 'L', finger: 3, row: 3},
            't': {hand: 'L', finger: 3, row: 1}, 'g': {hand: 'L', finger: 3, row: 2}, 'b': {hand: 'L', finger: 3, row: 3},
            // Right hand keys
            'y': {hand: 'R', finger: 3, row: 1}, 'h': {hand: 'R', finger: 3, row: 2}, 'n': {hand: 'R', finger: 3, row: 3},
            'u': {hand: 'R', finger: 3, row: 1}, 'j': {hand: 'R', finger: 3, row: 2}, 'm': {hand: 'R', finger: 3, row: 3},
            'i': {hand: 'R', finger: 2, row: 1}, 'k': {hand: 'R', finger: 2, row: 2}, ',': {hand: 'R', finger: 2, row: 3},
            'o': {hand: 'R', finger: 1, row: 1}, 'l': {hand: 'R', finger: 1, row: 2}, '.': {hand: 'R', finger: 1, row: 3},
            'p': {hand: 'R', finger: 0, row: 1}, ';': {hand: 'R', finger: 0, row: 2}, '/': {hand: 'R', finger: 0, row: 3},
            // Space - both thumbs
            ' ': {hand: 'B', finger: 4, row: 4}
        };

        function getHandPositionDelay(prev, curr) {
            var prevPos = keyPositions[prev?.toLowerCase()];
            var currPos = keyPositions[curr.toLowerCase()];

            if (!prevPos || !currPos) return 0;

            // Alternating hands = faster (parallel movement preparation)
            if (prevPos.hand !== currPos.hand && prevPos.hand !== 'B' && currPos.hand !== 'B') {
                return -8 - Math.random() * 12; // 8-20ms FASTER
            }

            // Same hand, same finger (not same key) = much slower
            if (prevPos.hand === currPos.hand && prevPos.finger === currPos.finger && prev !== curr) {
                return 20 + Math.random() * 35; // 20-55ms slower
            }

            // Same hand, adjacent fingers = slightly slower
            if (prevPos.hand === currPos.hand && Math.abs(prevPos.finger - currPos.finger) === 1) {
                return 5 + Math.random() * 10; // 5-15ms slower
            }

            return 0;
        }

        // ============================================================
        // BURST TYPING - Humans type in bursts, not steady streams
        // ============================================================

        var burstState = {
            charsInBurst: 0,
            burstLength: 4 + Math.floor(Math.random() * 4), // 4-7 chars per burst
            totalChars: 0
        };

        function resetBurst() {
            burstState.charsInBurst = 0;
            burstState.burstLength = 3 + Math.floor(Math.random() * 5); // 3-7 chars
        }

        function updateBurstAndGetPause(char, position) {
            burstState.charsInBurst++;
            burstState.totalChars++;

            // End of burst - add micro-pause
            if (burstState.charsInBurst >= burstState.burstLength) {
                resetBurst();
                return logNormalDelay(60, 0.5); // 40-120ms micro-pause
            }

            // Word boundaries often trigger burst reset
            if (char === ' ' && Math.random() < 0.35) {
                resetBurst();
                return logNormalDelay(40, 0.4);
            }

            return 0;
        }

        // ============================================================
        // FATIGUE SIMULATION - Gradual slowdown on longer texts
        // ============================================================

        function getFatigueMultiplier(position, totalLength) {
            // No fatigue for short texts
            if (totalLength < 40) return 1.0;

            var progress = position / totalLength;

            // Fatigue starts after 25% of text
            if (progress < 0.25) return 1.0;

            // Linear increase up to 12% slower by end
            var fatigueBase = 1.0 + (progress - 0.25) * 0.16;

            // Add some noise
            var noise = (Math.random() - 0.5) * 0.04;

            return fatigueBase + noise;
        }

        // Occasional micro-breaks during long typing sessions
        function shouldTakeMicroBreak(position, totalLength) {
            if (totalLength < 80) return false;
            // 1.5% chance after position 40
            return position > 40 && Math.random() < 0.015;
        }

        function getMicroBreakDuration() {
            return logNormalDelay(500, 0.6); // 300-1000ms
        }

        // ============================================================
        // SHIFT KEY TIMING - Capitals require pressing shift
        // ============================================================

        function getShiftKeyDelay(prev, curr) {
            var prevIsUpper = prev && /[A-Z]/.test(prev);
            var currIsUpper = /[A-Z]/.test(curr);

            // Starting to type uppercase - pressing shift
            if (currIsUpper && !prevIsUpper) {
                return 25 + Math.random() * 45; // 25-70ms to press shift
            }

            // Releasing shift after uppercase
            if (!currIsUpper && prevIsUpper) {
                return 10 + Math.random() * 20; // 10-30ms to release shift
            }

            return 0;
        }

        // ============================================================
        // KEYBOARD LAYOUT for typos
        // ============================================================

        var keyboardLayout = {
            // Number row
            '1': '2q', '2': '13w', '3': '24e', '4': '35r', '5': '46t', '6': '57y', '7': '68u', '8': '79i', '9': '80o', '0': '9-p',
            // Top letter row (qwerty)
            'q': '12wa', 'w': 'q3es', 'e': 'w4rd', 'r': 'e5tf', 't': 'r6yg', 'y': 't7uh', 'u': 'y8ij', 'i': 'u9ok', 'o': 'i0pl', 'p': 'o-',
            // Middle letter row (asdfgh)
            'a': 'qwsz', 's': 'awedxz', 'd': 'serfcx', 'f': 'drtgvc', 'g': 'ftyhbv', 'h': 'gyujnb', 'j': 'huikmn', 'k': 'jiol,m', 'l': 'kop;',
            // Bottom letter row (zxcvbn)
            'z': 'asx', 'x': 'zsdc', 'c': 'xdfv', 'v': 'cfgb', 'b': 'vghn', 'n': 'bhjm', 'm': 'njk,',
            // Uppercase versions
            'Q': '12WA', 'W': 'Q3ES', 'E': 'W4RD', 'R': 'E5TF', 'T': 'R6YG', 'Y': 'T7UH', 'U': 'Y8IJ', 'I': 'U9OK', 'O': 'I0PL', 'P': 'O-',
            'A': 'QWSZ', 'S': 'AWEDXZ', 'D': 'SERFCX', 'F': 'DRTGVC', 'G': 'FTYHBV', 'H': 'GYUJNB', 'J': 'HUIKMN', 'K': 'JIOL,M', 'L': 'KOP;',
            'Z': 'ASX', 'X': 'ZSDC', 'C': 'XDFV', 'V': 'CFGB', 'B': 'VGHN', 'N': 'BHJM', 'M': 'NJK,'
        };

        // Mirror keys (same position, opposite hand) for wrong-hand typos
        var mirrorKeys = {
            'q': 'p', 'w': 'o', 'e': 'i', 'r': 'u', 't': 'y',
            'a': ';', 's': 'l', 'd': 'k', 'f': 'j', 'g': 'h',
            'z': '/', 'x': '.', 'c': ',', 'v': 'm', 'b': 'n',
            'p': 'q', 'o': 'w', 'i': 'e', 'u': 'r', 'y': 't',
            ';': 'a', 'l': 's', 'k': 'd', 'j': 'f', 'h': 'g',
            '/': 'z', '.': 'x', ',': 'c', 'm': 'v', 'n': 'b'
        };

        function getAdjacentKey(char) {
            var adjacent = keyboardLayout[char];
            if (adjacent && adjacent.length > 0) {
                return adjacent[Math.floor(Math.random() * adjacent.length)];
            }
            return char;
        }

        function getMirrorKey(char) {
            var lower = char.toLowerCase();
            var mirror = mirrorKeys[lower];
            if (mirror) {
                // Preserve case
                return char === char.toUpperCase() ? mirror.toUpperCase() : mirror;
            }
            return char;
        }

        // ============================================================
        // ENHANCED TYPO MODEL - Multiple error types
        // ============================================================

        // Typo type probabilities
        var typoTypes = {
            adjacent: 0.55,      // Adjacent key
            transposition: 0.20, // Swap two characters
            doubleHit: 0.12,     // Same key twice
            wrongHand: 0.08,     // Mirror key on opposite hand
            insertion: 0.05      // Extra random char inserted
        };

        function generateTypo(char, nextChar) {
            var rand = Math.random();
            var cumulative = 0;

            // Adjacent key (most common)
            cumulative += typoTypes.adjacent;
            if (rand < cumulative) {
                return { type: 'adjacent', wrongChar: getAdjacentKey(char), backspaces: 1 };
            }

            // Transposition (swap with next char)
            cumulative += typoTypes.transposition;
            if (rand < cumulative && nextChar && /[a-zA-Z]/.test(nextChar)) {
                return { type: 'transposition', wrongChar: nextChar, nextWrong: char, backspaces: 2 };
            }

            // Double-hit (same key twice)
            cumulative += typoTypes.doubleHit;
            if (rand < cumulative) {
                return { type: 'doubleHit', wrongChar: char, extraChar: char, backspaces: 1 };
            }

            // Wrong hand (mirror key)
            cumulative += typoTypes.wrongHand;
            if (rand < cumulative) {
                var mirror = getMirrorKey(char);
                if (mirror !== char) {
                    return { type: 'wrongHand', wrongChar: mirror, backspaces: 1 };
                }
            }

            // Insertion (extra char)
            var extraChar = getAdjacentKey(char);
            return { type: 'insertion', wrongChar: char, extraChar: extraChar, backspaces: 1 };
        }

        // ============================================================
        // MAIN HUMAN DELAY FUNCTION - Combines all factors
        // ============================================================

        function getHumanDelay(char, nextChar, position) {
            // Base speed: ~100 WPM median with log-normal distribution
            // Log-normal sigma of 0.35 gives realistic variance
            var baseMedian = 115;
            var sigma = 0.35;

            // Start with log-normal base delay
            var delay = logNormalDelay(baseMedian, sigma);

            // Apply digraph speed adjustment
            delay *= getDigraphMultiplier(prevChar, char);

            // Apply hand position delay
            delay += getHandPositionDelay(prevChar, char);

            // Apply shift key timing
            delay += getShiftKeyDelay(prevChar, char);

            // Apply fatigue multiplier
            delay *= getFatigueMultiplier(position, text.length);

            // Apply burst typing pause
            delay += updateBurstAndGetPause(char, position);

            // Punctuation pauses (using log-normal for natural variation)
            if ('.!?'.indexOf(char) !== -1) {
                delay += logNormalDelay(220, 0.5); // Sentence end pause
            } else if (char === ',') {
                delay += logNormalDelay(65, 0.4); // Comma pause
            } else if (char === ':' || char === ';') {
                delay += logNormalDelay(80, 0.45);
            }

            // Thinking pauses after spaces (10% chance)
            if (char === ' ' && Math.random() < 0.10) {
                delay += logNormalDelay(120, 0.5);
            }

            // Numbers and special characters - slower (reaching)
            if ('0123456789'.indexOf(char) !== -1) {
                delay *= 1.20;
            } else if ('!@#$%^&*()_+={}[]|\\:;"\'<>?,./`~'.indexOf(char) !== -1) {
                delay *= 1.30;
            }

            // Check for micro-break
            if (shouldTakeMicroBreak(position, text.length)) {
                delay += getMicroBreakDuration();
            }

            // Ensure minimum delay (bot detection flags <35ms as suspicious)
            delay = Math.max(delay, 38);

            // Cap maximum for normal chars (punctuation can exceed)
            if ('.!?,;:'.indexOf(char) === -1) {
                delay = Math.min(delay, 350);
            }

            return Math.round(delay);
        }

        // ============================================================
        // KEY EVENT HELPERS
        // ============================================================

        function createKeyEvent(type, char) {
            var charCode = char.charCodeAt(0);
            return new KeyboardEvent(type, {
                key: char,
                code: 'Key' + char.toUpperCase(),
                charCode: charCode,
                keyCode: charCode,
                which: charCode,
                bubbles: true,
                cancelable: true
            });
        }

        function insertChar(char) {
            activeEl.dispatchEvent(createKeyEvent('keydown', char));
            activeEl.dispatchEvent(createKeyEvent('keypress', char));

            if (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA') {
                var start = activeEl.selectionStart;
                var end = activeEl.selectionEnd;
                var value = activeEl.value;
                activeEl.value = value.substring(0, start) + char + value.substring(end);
                activeEl.selectionStart = activeEl.selectionEnd = start + 1;
            } else if (activeEl.isContentEditable) {
                var selection = window.getSelection();
                var range = selection.getRangeAt(0);
                range.deleteContents();
                range.insertNode(document.createTextNode(char));
                range.collapse(false);
            }

            activeEl.dispatchEvent(new InputEvent('input', {
                data: char,
                inputType: 'insertText',
                bubbles: true,
                cancelable: true
            }));
            activeEl.dispatchEvent(createKeyEvent('keyup', char));
        }

        function pressBackspace() {
            var backspaceEvent = new KeyboardEvent('keydown', {
                key: 'Backspace',
                code: 'Backspace',
                keyCode: 8,
                which: 8,
                bubbles: true,
                cancelable: true
            });
            activeEl.dispatchEvent(backspaceEvent);

            if (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA') {
                var start = activeEl.selectionStart;
                var end = activeEl.selectionEnd;
                var value = activeEl.value;
                if (start === end && start > 0) {
                    activeEl.value = value.substring(0, start - 1) + value.substring(end);
                    activeEl.selectionStart = activeEl.selectionEnd = start - 1;
                } else if (start !== end) {
                    activeEl.value = value.substring(0, start) + value.substring(end);
                    activeEl.selectionStart = activeEl.selectionEnd = start;
                }
            } else if (activeEl.isContentEditable) {
                var selection = window.getSelection();
                if (selection.rangeCount > 0) {
                    var range = selection.getRangeAt(0);
                    if (range.collapsed && range.startOffset > 0) {
                        range.setStart(range.startContainer, range.startOffset - 1);
                        range.deleteContents();
                    } else if (!range.collapsed) {
                        range.deleteContents();
                    }
                }
            }

            activeEl.dispatchEvent(new InputEvent('input', {
                inputType: 'deleteContentBackward',
                bubbles: true,
                cancelable: true
            }));
            activeEl.dispatchEvent(new KeyboardEvent('keyup', {
                key: 'Backspace',
                code: 'Backspace',
                keyCode: 8,
                which: 8,
                bubbles: true,
                cancelable: true
            }));
        }

        // ============================================================
        // MAIN TYPING LOOP
        // ============================================================

        function typeNextChar() {
            if (i >= text.length) {
                var mode;
                var message;
                if (isHumanMode) {
                    mode = 'human';
                    message = 'Typed ' + text.length + ' character(s) (human-like): "' + text + '"';
                } else if (delayMs === 0) {
                    mode = 'pasted';
                    message = 'Pasted ' + text.length + ' character(s): "' + text + '"';
                } else {
                    mode = 'typed';
                    message = 'Typed ' + text.length + ' character(s): "' + text + '"';
                }
                resolve({
                    ok: true,
                    message: message,
                    element: activeEl.tagName,
                    length: text.length,
                    mode: mode
                });
                return;
            }

            var char = text[i];
            var nextChar = i < text.length - 1 ? text[i + 1] : null;

            // In human mode, occasionally make typos (then correct them)
            if (isHumanMode && Math.random() < typoRate && keyboardLayout[char]) {
                var typo = generateTypo(char, nextChar);

                if (typo.type === 'transposition' && nextChar) {
                    // Transposition: type next char first, then current char, then fix
                    insertChar(typo.wrongChar);  // nextChar typed first
                    setTimeout(function() {
                        insertChar(typo.nextWrong);  // current char typed second
                        // Realize mistake
                        setTimeout(function() {
                            pressBackspace();
                            setTimeout(function() {
                                pressBackspace();
                                // Now type correctly
                                setTimeout(function() {
                                    insertChar(char);
                                    setTimeout(function() {
                                        insertChar(nextChar);
                                        prevChar = nextChar;
                                        i += 2; // Skip both chars since we typed them
                                        continueTyping();
                                    }, 40 + Math.random() * 30);
                                }, 40 + Math.random() * 30);
                            }, 50 + Math.random() * 40);
                        }, 80 + Math.random() * 80);
                    }, 50 + Math.random() * 40);
                    return;
                } else if (typo.type === 'doubleHit') {
                    // Double hit: type char twice, then backspace once
                    insertChar(typo.wrongChar);
                    setTimeout(function() {
                        insertChar(typo.extraChar);
                        setTimeout(function() {
                            pressBackspace();
                            prevChar = char;
                            i++;
                            continueTyping();
                        }, 70 + Math.random() * 60);
                    }, 30 + Math.random() * 30);
                    return;
                } else if (typo.type === 'insertion') {
                    // Insertion: type extra char, then correct char, then backspace the extra
                    insertChar(typo.extraChar);
                    setTimeout(function() {
                        insertChar(char);
                        setTimeout(function() {
                            // Realize there's an extra char before
                            pressBackspace();
                            pressBackspace();
                            setTimeout(function() {
                                insertChar(char);
                                prevChar = char;
                                i++;
                                continueTyping();
                            }, 40 + Math.random() * 30);
                        }, 90 + Math.random() * 80);
                    }, 50 + Math.random() * 40);
                    return;
                } else {
                    // Adjacent or wrong-hand: simple wrong char, backspace, correct
                    insertChar(typo.wrongChar);
                    setTimeout(function() {
                        pressBackspace();
                        setTimeout(function() {
                            insertChar(char);
                            prevChar = char;
                            i++;
                            continueTyping();
                        }, 40 + Math.random() * 40);
                    }, 80 + Math.random() * 100);
                    return;
                }
            }

            // Normal typing (no typo)
            insertChar(char);
            prevChar = char;
            i++;
            continueTyping();
        }

        function continueTyping() {
            if (i < text.length) {
                var actualDelay;
                if (isHumanMode) {
                    var nextChar = i < text.length - 1 ? text[i] : null;
                    actualDelay = getHumanDelay(text[i], nextChar, i);
                } else {
                    // Non-human mode: use specified delay or minimum 1ms
                    actualDelay = Math.max(delayMs, 1);
                }
                setTimeout(typeNextChar, actualDelay);
            } else {
                // All done - small delay to ensure last char processed
                setTimeout(typeNextChar, 1);
            }
        }

        typeNextChar();
    });
})(TEXT_PLACEHOLDER, DELAY_PLACEHOLDER, CLEAR_PLACEHOLDER, TYPO_RATE_PLACEHOLDER)
