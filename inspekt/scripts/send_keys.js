// Send keys to the active element in the browser.
//
// Three modes driven by `delayMs`:
//   -1   human-like (rhythm, pauses, typos — see humanDelay/applyTypo)
//    0   paste-speed (1ms/char)
//   >0   fixed delay per char
//
// Human mode is driven by one `skill` parameter in [0..1] (see `P` profile).
// Tunable tables (digraphs, trigrams, commonSwap, keyPos, adjacent, mirror)
// are grouped at the top under TABLES so tuning lives in one place.
(function(text, delayMs, clearFirst, typoRate, skill) {
    var activeEl = document.activeElement;
    if (!activeEl) return Promise.resolve({ error: 'No active element found' });

    var isInput = activeEl.tagName === 'INPUT' ||
                  activeEl.tagName === 'TEXTAREA' ||
                  activeEl.isContentEditable;
    if (!isInput) {
        return Promise.resolve({
            error: 'Active element is not an input field',
            activeElement: activeEl.tagName,
            hint: 'Click on an input field first'
        });
    }

    // Inputs like email/number/date throw on selectionStart access.
    var NO_SELECTION_TYPES = ['email','number','date','datetime-local','month','time','week','color'];
    var canUseSelection = activeEl.tagName !== 'INPUT' ||
        NO_SELECTION_TYPES.indexOf((activeEl.type || 'text').toLowerCase()) === -1;

    if (clearFirst) {
        if (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA') {
            activeEl.value = '';
            if (canUseSelection) { activeEl.selectionStart = 0; activeEl.selectionEnd = 0; }
        } else if (activeEl.isContentEditable) {
            activeEl.textContent = '';
        }
    }

    var isHumanMode = delayMs === -1;

    // =============================================================
    // TABLES — lookups only. Grouped at top so tuning happens here.
    // =============================================================
    var TABLES = {
        // Common English+Dutch digraphs typed faster as motor units.
        digraph: {
            'th':0.62,'he':0.68,'in':0.70,'er':0.65,'an':0.70,'re':0.68,'on':0.72,
            'en':0.70,'nd':0.73,'ed':0.70,'es':0.70,'ou':0.73,'ti':0.72,'te':0.68,
            'is':0.72,'at':0.73,'al':0.73,'ar':0.74,'st':0.70,'to':0.76,'nt':0.72,
            'ng':0.78,'se':0.72,'ha':0.74,'as':0.75,'io':0.80,'le':0.72,'ve':0.72,
            'co':0.78,'me':0.74,'de':0.75,'hi':0.76,'ri':0.75,'ro':0.76,'ic':0.78,
            'ne':0.73,'ea':0.80,'ra':0.76,'ce':0.75,'li':0.74,'ch':0.73,'be':0.78,
            'ec':0.80,'ma':0.78,'si':0.76,'om':0.80,'ur':0.77,'ca':0.78,'el':0.74,
            'ta':0.76,'la':0.75,'ns':0.74,'di':0.77,'fo':0.80,'ho':0.78,'pe':0.76,
            'pr':0.82,'no':0.77,'ct':0.78,'us':0.77,'ac':0.78,'ot':0.78,'il':0.75,
            'tr':0.80,'ly':0.76,'nc':0.78,'et':0.75,'ut':0.78,'so':0.78,'rs':0.76,
            'un':0.77,'lo':0.76,'wa':0.78,'ge':0.77,'ie':0.78,'wh':0.75,
            // Dutch
            'ij':0.62,'oe':0.70,'ui':0.73,'eu':0.73,'ei':0.70,'au':0.76,
            'nk':0.76,'dt':0.78,'gt':0.80,'kt':0.78,'pt':0.80,
            // Same-finger reaches that are SLOWER
            'ce':1.10,'nu':1.12,'my':1.15,'ym':1.18,'br':1.08,'rb':1.10,
            'vt':1.15,'tv':1.18,'bg':1.12,'gb':1.15,'hn':1.10,'nh':1.08,
            'ju':1.10,'uj':1.12,'ki':1.08,'ik':1.10,'lo':1.08,'ol':1.06
        },
        // Famously-typo'd transposition pairs. If the upcoming digraph matches,
        // a typo here is very likely a swap (e.g. "the" → "teh").
        commonSwap: {
            'th':1,'he':1,'er':1,'re':1,'io':1,'on':1,'ie':1,'ei':1,'hi':1,'ou':1,
            'in':1,'ni':1,'se':1,'es':1,'at':1,'ha':1,'an':1,'na':1
        },
        // Most-common English trigrams typed as single motor chunks.
        // Applied multiplicatively to the delay at the FIRST char of the match.
        trigram: {
            'the':0.55,'ing':0.55,'and':0.58,'ion':0.60,'tio':0.60,'ent':0.60,
            'ati':0.62,'for':0.60,'her':0.62,'ter':0.62,'hat':0.62,'tha':0.62,
            'ere':0.62,'ate':0.63,'his':0.63,'con':0.63,'res':0.64,'ver':0.64,
            'all':0.62,'ons':0.65,'nce':0.65,'men':0.65,'ith':0.64,'ted':0.65,
            'ers':0.64,'pro':0.66,'thi':0.62,'wit':0.66,'are':0.65,'ess':0.66,
            'not':0.65,'ive':0.65,'was':0.66,'ect':0.66,'rea':0.66,'com':0.66,
            'eve':0.66,'per':0.66,'int':0.66,'est':0.65,'sta':0.66,'cti':0.66,
            'ica':0.68,'ist':0.66,'ear':0.68,'ain':0.66,'one':0.65,'our':0.66,
            'iti':0.68,'rat':0.68,
            // Dutch
            'een':0.60,'het':0.58,'van':0.60,'dat':0.62,'met':0.62
        },
        // QWERTY position (hand, finger, row). Space is both hands.
        // finger: 0=pinky … 3=index; 4=thumb. row: 1=top, 2=home (fastest), 3=bottom.
        keyPos: {
            'q':{h:'L',f:0,r:1},'a':{h:'L',f:0,r:2},'z':{h:'L',f:0,r:3},
            'w':{h:'L',f:1,r:1},'s':{h:'L',f:1,r:2},'x':{h:'L',f:1,r:3},
            'e':{h:'L',f:2,r:1},'d':{h:'L',f:2,r:2},'c':{h:'L',f:2,r:3},
            'r':{h:'L',f:3,r:1},'f':{h:'L',f:3,r:2},'v':{h:'L',f:3,r:3},
            't':{h:'L',f:3,r:1},'g':{h:'L',f:3,r:2},'b':{h:'L',f:3,r:3},
            'y':{h:'R',f:3,r:1},'h':{h:'R',f:3,r:2},'n':{h:'R',f:3,r:3},
            'u':{h:'R',f:3,r:1},'j':{h:'R',f:3,r:2},'m':{h:'R',f:3,r:3},
            'i':{h:'R',f:2,r:1},'k':{h:'R',f:2,r:2},',':{h:'R',f:2,r:3},
            'o':{h:'R',f:1,r:1},'l':{h:'R',f:1,r:2},'.':{h:'R',f:1,r:3},
            'p':{h:'R',f:0,r:1},';':{h:'R',f:0,r:2},'/':{h:'R',f:0,r:3},
            ' ':{h:'B',f:4,r:4}
        },
        // (home-row is r=2 — used directly in handPosDelay for a small speed bonus)
        // Adjacent keys used for "adjacent-key" typos.
        adjacent: {
            '1':'2q','2':'13w','3':'24e','4':'35r','5':'46t','6':'57y',
            '7':'68u','8':'79i','9':'80o','0':'9-p',
            'q':'12wa','w':'q3es','e':'w4rd','r':'e5tf','t':'r6yg','y':'t7uh',
            'u':'y8ij','i':'u9ok','o':'i0pl','p':'o-',
            'a':'qwsz','s':'awedxz','d':'serfcx','f':'drtgvc','g':'ftyhbv',
            'h':'gyujnb','j':'huikmn','k':'jiol,m','l':'kop;',
            'z':'asx','x':'zsdc','c':'xdfv','v':'cfgb','b':'vghn','n':'bhjm','m':'njk,'
        },
        // Mirror keys (same finger, opposite hand) for wrong-hand typos.
        mirror: {
            'q':'p','w':'o','e':'i','r':'u','t':'y',
            'a':';','s':'l','d':'k','f':'j','g':'h',
            'z':'/','x':'.','c':',','v':'m','b':'n',
            'p':'q','o':'w','i':'e','u':'r','y':'t',
            ';':'a','l':'s','k':'d','j':'f','h':'g',
            '/':'z','.':'x',',':'c','m':'v','n':'b'
        }
    };

    // =============================================================
    // PROFILE — every tunable derived from one `skill` param [0..1].
    // skill=0 → slow/error-prone beginner; skill=1 → fast/accurate expert.
    // =============================================================
    if (typeof skill !== 'number' || isNaN(skill)) skill = 0.7;
    skill = Math.max(0, Math.min(1, skill));
    var P = {
        baseMedian: 170 - 80 * skill,       // 170ms → 90ms
        sigma:      0.45 - 0.15 * skill,    // 0.45 → 0.30
        typoRate:   typoRate,               // user-controlled
        fatigueSlope: 0.20 - 0.12 * skill,  // more fatigue at low skill
        arAlpha:    0.65,                   // tempo streakiness (0=i.i.d, 1=frozen)
        minDelay:   38,
        maxDelay:   350                     // applies to non-punctuation
    };
    var prevLogDelay = null;                // AR(1) state for autocorrelated tempo

    // =============================================================
    // STAT HELPERS
    // =============================================================
    function gaussian(mean, stdDev) {
        var u1 = Math.random() || 0.0001;
        var z = Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * Math.random());
        return mean + z * stdDev;
    }
    function logNormal(median, sigma) {
        var r = Math.exp(Math.log(median) + gaussian(0, sigma));
        return Math.max(35, Math.min(r, median * 4));
    }
    function sleep(ms) { return new Promise(function(r) { setTimeout(r, ms); }); }
    function rand(min, max) { return min + Math.random() * (max - min); }

    // =============================================================
    // TIMING COMPONENTS
    // =============================================================
    function digraphMult(prev, curr) {
        if (!prev) return 1.0;
        // Same-letter doubles (ee, oo, tt, …) are a bounce of one finger — uniformly quick.
        if (prev.toLowerCase() === curr.toLowerCase()) return 0.72;
        return TABLES.digraph[(prev + curr).toLowerCase()] || 1.0;
    }
    // Trigram chunking: if the next 3 chars form a common motor unit (e.g. "the", "ing"),
    // speed up the entry keystroke — that's when motor planning fires.
    function trigramMult(pos) {
        if (pos + 3 > text.length) return 1.0;
        var tri = text.substr(pos, 3).toLowerCase();
        return TABLES.trigram[tri] || 1.0;
    }
    function handPosDelay(prev, curr) {
        var a = prev && TABLES.keyPos[prev.toLowerCase()];
        var b = TABLES.keyPos[curr.toLowerCase()];
        if (!a || !b) return 0;
        var d = 0;
        if (a.h !== b.h && a.h !== 'B' && b.h !== 'B') d -= rand(8, 20);      // alternating hands faster
        else if (a.h === b.h && a.f === b.f && prev !== curr) d += rand(20, 55); // same finger slower
        else if (a.h === b.h && Math.abs(a.f - b.f) === 1) d += rand(5, 15);   // adjacent finger slightly slower
        if (a.r === 2 && b.r === 2) d -= rand(5, 10);                          // both home-row: extra speed
        return d;
    }
    function shiftDelay(prev, curr) {
        var prevUp = prev && /[A-Z]/.test(prev);
        var currUp = /[A-Z]/.test(curr);
        if (currUp && !prevUp) return rand(25, 70);
        if (!currUp && prevUp) return rand(10, 30);
        return 0;
    }
    function fatigueMult(pos, total) {
        if (total < 40) return 1.0;
        var progress = pos / total;
        if (progress < 0.25) return 1.0;
        var noise = (Math.random() - 0.5) * 0.04;
        return 1.0 + (progress - 0.25) * P.fatigueSlope + noise;
    }

    // Burst typing: humans type 3–7 chars then micro-pause.
    var burst = { inBurst: 0, len: 4 + Math.floor(Math.random() * 4) };
    function burstPause(ch) {
        burst.inBurst++;
        if (burst.inBurst >= burst.len) {
            burst.inBurst = 0;
            burst.len = 3 + Math.floor(Math.random() * 5);
            return logNormal(60, 0.5);
        }
        if (ch === ' ' && Math.random() < 0.35) {
            burst.inBurst = 0;
            burst.len = 3 + Math.floor(Math.random() * 5);
            return logNormal(40, 0.4);
        }
        return 0;
    }

    // Word-onset planning: humans pause BEFORE starting a word while the motor
    // program loads. Longer/harder words → longer pause.
    function wordOnsetPause(prevChar, pos) {
        if (pos > 0 && prevChar !== ' ' && prevChar !== null) return 0;
        if (pos === 0) return 0;  // first keystroke handled by caller's initial delay
        // Length of the word we're about to type.
        var end = text.indexOf(' ', pos);
        var wordLen = (end === -1 ? text.length : end) - pos;
        if (wordLen < 2) return 0;
        // 35% chance of planning pause, magnitude scales with word length.
        if (Math.random() > 0.35) return 0;
        return logNormal(70 + wordLen * 14, 0.45);
    }

    function humanDelay(prevChar, ch, pos, total) {
        var d = logNormal(P.baseMedian, P.sigma);
        d *= digraphMult(prevChar, ch);
        d *= trigramMult(pos);
        d += handPosDelay(prevChar, ch);
        d += shiftDelay(prevChar, ch);
        d *= fatigueMult(pos, total);
        d += burstPause(ch);
        d += wordOnsetPause(prevChar, pos);

        if ('.!?'.indexOf(ch) !== -1) d += logNormal(220, 0.5);
        else if (ch === ',') d += logNormal(65, 0.4);
        else if (ch === ':' || ch === ';') d += logNormal(80, 0.45);
        if (ch === ' ' && Math.random() < 0.10) d += logNormal(120, 0.5);

        if ('0123456789'.indexOf(ch) !== -1) d *= 1.20;
        else if ('!@#$%^&*()_+={}[]|\\:;"\'<>?,./`~'.indexOf(ch) !== -1) d *= 1.30;
        if (total >= 80 && pos > 40 && Math.random() < 0.015) d += logNormal(500, 0.6);

        // AR(1) in log-space: "rhythm memory" — fast/slow runs streak as real humans do.
        // Applied after all additive effects so the whole delay stream is autocorrelated.
        d = Math.max(20, d);
        var logD = Math.log(d);
        if (prevLogDelay !== null) logD = P.arAlpha * prevLogDelay + (1 - P.arAlpha) * logD;
        prevLogDelay = logD;
        d = Math.exp(logD);

        d = Math.max(d, P.minDelay);
        if ('.!?,;:'.indexOf(ch) === -1) d = Math.min(d, P.maxDelay);
        return Math.round(d);
    }

    // =============================================================
    // TYPO MODEL
    // =============================================================
    function adjacentKey(ch) {
        var adj = TABLES.adjacent[ch];
        return adj ? adj[Math.floor(Math.random() * adj.length)] : ch;
    }
    function mirrorKey(ch) {
        var lo = ch.toLowerCase();
        var m = TABLES.mirror[lo];
        if (!m) return ch;
        return ch === ch.toUpperCase() ? m.toUpperCase() : m;
    }
    // Returns a typo plan: the `wrong` string is committed instead of `intended`.
    // Both strings describe a span of the source text (intended.length source chars).
    function planTypo(ch, nextCh) {
        // If the digraph is a famously-swapped pair, strongly favor transposition.
        if (nextCh && /[a-zA-Z]/.test(nextCh) &&
            TABLES.commonSwap[(ch + nextCh).toLowerCase()] &&
            Math.random() < 0.70) {
            return { wrong: nextCh + ch, intended: ch + nextCh };
        }
        var r = Math.random();
        if (r < 0.52) return { wrong: adjacentKey(ch), intended: ch };              // adjacent key
        if (r < 0.72 && nextCh && /[a-zA-Z]/.test(nextCh))
                      return { wrong: nextCh + ch, intended: ch + nextCh };         // transposition
        if (r < 0.84) return { wrong: ch + ch, intended: ch };                      // double-hit
        if (r < 0.92) {
            var m = mirrorKey(ch);
            if (m !== ch) return { wrong: m, intended: ch };                        // wrong-hand
        }
        if (r < 0.96 && /[a-zA-Z]/.test(ch)) {
            var flipped = ch === ch.toLowerCase() ? ch.toUpperCase() : ch.toLowerCase();
            if (flipped !== ch) return { wrong: flipped, intended: ch };             // capitalization slip
        }
        return { wrong: ch + adjacentKey(ch), intended: ch };                        // insertion
    }

    // =============================================================
    // KEY DISPATCH
    // =============================================================
    function keyEvent(type, ch) {
        var code = ch.charCodeAt(0);
        return new KeyboardEvent(type, {
            key: ch, code: 'Key' + ch.toUpperCase(),
            charCode: code, keyCode: code, which: code,
            bubbles: true, cancelable: true
        });
    }
    function insertChar(ch) {
        activeEl.dispatchEvent(keyEvent('keydown', ch));
        activeEl.dispatchEvent(keyEvent('keypress', ch));
        if (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA') {
            if (canUseSelection) {
                var s = activeEl.selectionStart, e = activeEl.selectionEnd, v = activeEl.value;
                activeEl.value = v.substring(0, s) + ch + v.substring(e);
                activeEl.selectionStart = activeEl.selectionEnd = s + 1;
            } else {
                activeEl.value += ch;
            }
        } else if (activeEl.isContentEditable) {
            var sel = window.getSelection();
            var range = sel.getRangeAt(0);
            range.deleteContents();
            range.insertNode(document.createTextNode(ch));
            range.collapse(false);
        }
        activeEl.dispatchEvent(new InputEvent('input', {
            data: ch, inputType: 'insertText', bubbles: true, cancelable: true
        }));
        activeEl.dispatchEvent(keyEvent('keyup', ch));
    }
    function pressBackspace() {
        var init = { key: 'Backspace', code: 'Backspace', keyCode: 8, which: 8, bubbles: true, cancelable: true };
        activeEl.dispatchEvent(new KeyboardEvent('keydown', init));
        if (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA') {
            if (canUseSelection) {
                var s = activeEl.selectionStart, e = activeEl.selectionEnd, v = activeEl.value;
                if (s === e && s > 0) {
                    activeEl.value = v.substring(0, s - 1) + v.substring(e);
                    activeEl.selectionStart = activeEl.selectionEnd = s - 1;
                } else if (s !== e) {
                    activeEl.value = v.substring(0, s) + v.substring(e);
                    activeEl.selectionStart = activeEl.selectionEnd = s;
                }
            } else if (activeEl.value.length > 0) {
                activeEl.value = activeEl.value.substring(0, activeEl.value.length - 1);
            }
        } else if (activeEl.isContentEditable) {
            var sel = window.getSelection();
            if (sel.rangeCount > 0) {
                var r = sel.getRangeAt(0);
                if (r.collapsed && r.startOffset > 0) {
                    r.setStart(r.startContainer, r.startOffset - 1);
                    r.deleteContents();
                } else if (!r.collapsed) {
                    r.deleteContents();
                }
            }
        }
        activeEl.dispatchEvent(new InputEvent('input', { inputType: 'deleteContentBackward', bubbles: true, cancelable: true }));
        activeEl.dispatchEvent(new KeyboardEvent('keyup', init));
    }

    // =============================================================
    // TYPING LOOP (async)
    // =============================================================
    // Commit a typo, then optionally type a few more correct chars before realizing
    // the mistake — a big "tell" humans give and bots usually miss.
    // Returns how many source-text chars were consumed (handled by this call).
    async function applyTypo(typo, pos) {
        var prev = pos > 0 ? text[pos - 1] : null;

        // 1. Type the wrong chars at normal rhythm.
        for (var k = 0; k < typo.wrong.length; k++) {
            if (k > 0) await sleep(humanDelay(prev, typo.wrong[k], pos + k, text.length));
            insertChar(typo.wrong[k]);
            prev = typo.wrong[k];
        }

        // 2. Coast past the error typing correct chars (0–4, geometric-ish).
        var lookahead = 0;
        while (lookahead < 4 && Math.random() < 0.55) lookahead++;
        var cursor = pos + typo.intended.length;
        var trail = '';
        while (lookahead > 0 && cursor < text.length) {
            var tc = text[cursor];
            if (tc === ' ' || '.!?,;:'.indexOf(tc) !== -1) break;   // realize at word/phrase break
            await sleep(humanDelay(prev, tc, cursor, text.length));
            insertChar(tc);
            trail += tc;
            prev = tc;
            cursor++;
            lookahead--;
        }

        // 3. Notice and erase the whole wrong run.
        await sleep(rand(180, 420));
        var erase = typo.wrong.length + trail.length;
        for (var b = 0; b < erase; b++) {
            pressBackspace();
            await sleep(rand(45, 85));
        }

        // 4. Retype the intended span plus whatever correct chars we'd coasted into.
        var retype = typo.intended + trail;
        await sleep(rand(60, 130));
        prev = pos > 0 ? text[pos - 1] : null;
        for (var j = 0; j < retype.length; j++) {
            if (j > 0) await sleep(humanDelay(prev, retype[j], pos + j, text.length));
            insertChar(retype[j]);
            prev = retype[j];
        }
        return retype.length;
    }

    async function run() {
        var prev = null;
        for (var i = 0; i < text.length; ) {
            var ch = text[i];
            var nextCh = i < text.length - 1 ? text[i + 1] : null;

            if (isHumanMode && Math.random() < P.typoRate && TABLES.adjacent[ch]) {
                var typo = planTypo(ch, nextCh);
                var consumed = await applyTypo(typo, i);
                prev = text[i + consumed - 1];
                i += consumed;
            } else {
                insertChar(ch);
                prev = ch;
                i++;
            }

            if (i < text.length) {
                var d;
                if (isHumanMode) d = humanDelay(prev, text[i], i, text.length);
                else d = Math.max(delayMs, 1);
                await sleep(d);
            }
        }

        var mode, message;
        if (isHumanMode) { mode = 'human'; message = 'Typed ' + text.length + ' character(s) (human-like): "' + text + '"'; }
        else if (delayMs === 0) { mode = 'pasted'; message = 'Pasted ' + text.length + ' character(s): "' + text + '"'; }
        else { mode = 'typed'; message = 'Typed ' + text.length + ' character(s): "' + text + '"'; }

        return { ok: true, message: message, element: activeEl.tagName, length: text.length, mode: mode };
    }

    return run();
})(TEXT_PLACEHOLDER, DELAY_PLACEHOLDER, CLEAR_PLACEHOLDER, TYPO_RATE_PLACEHOLDER, SKILL_PLACEHOLDER)
