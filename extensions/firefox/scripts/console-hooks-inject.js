/**
 * Console Hooks - MAIN World Script (Firefox)
 *
 * This script runs in the page's MAIN world and intercepts all console methods.
 * It's loaded as an external script to bypass CSP restrictions on inline scripts.
 */

(function() {
    'use strict';

    // Don't re-inject if already hooked
    if (window.__INSPEKT_CONSOLE_HOOKED__) return;
    window.__INSPEKT_CONSOLE_HOOKED__ = true;

    const buffer = [];
    const MAX_MESSAGES = 1000;
    const timers = {};  // Track console.time() timers
    const counters = {}; // Track console.count() counters

    // Helper to format arguments, handling %c CSS styling
    function formatArgs(args) {
        if (args.length === 0) return '';
        const first = args[0];
        if (typeof first === 'string' && first.includes('%c')) {
            const cssCount = (first.match(/%c/g) || []).length;
            let message = first.replace(/%c/g, '');
            const remaining = args.slice(1 + cssCount);
            if (remaining.length > 0) {
                message += ' ' + remaining.map(stringify).join(' ');
            }
            return message.trim();
        }
        return args.map(stringify).join(' ');
    }

    // Sensitive data patterns to redact from console output
    // This helps prevent accidental exposure of credentials, tokens, and API keys
    const SENSITIVE_PATTERNS = [
        // Passwords in various formats
        { regex: /(password|passwd|pwd)\s*[=:]\s*['"][^'"]+['"]/gi,
          replacement: '$1=***REDACTED***' },
        { regex: /(password|passwd|pwd)\s*[=:]\s*[^\s,;'"}\]]+/gi,
          replacement: '$1=***REDACTED***' },
        // API keys and secrets
        { regex: /(api[_-]?key|secret[_-]?key|api[_-]?secret)\s*[=:]\s*['"][^'"]+['"]/gi,
          replacement: '$1=***REDACTED***' },
        { regex: /(api[_-]?key|secret[_-]?key|api[_-]?secret)\s*[=:]\s*[^\s,;'"}\]]+/gi,
          replacement: '$1=***REDACTED***' },
        // Bearer tokens
        { regex: /Bearer\s+[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]*/gi,
          replacement: 'Bearer ***REDACTED***' },
        { regex: /Bearer\s+[A-Za-z0-9\-_=]{20,}/gi,
          replacement: 'Bearer ***REDACTED***' },
        // JWT tokens (eyJ... format)
        { regex: /eyJ[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]*/g,
          replacement: '***JWT_REDACTED***' },
        // AWS keys
        { regex: /AKIA[0-9A-Z]{16}/g,
          replacement: '***AWS_KEY_REDACTED***' },
        // Generic tokens and secrets in JSON
        { regex: /"(token|access_token|refresh_token|auth_token|secret)"\s*:\s*"[^"]+"/gi,
          replacement: '"$1":"***REDACTED***"' },
        // Authorization headers
        { regex: /(Authorization|X-Api-Key|X-Auth-Token)\s*[=:]\s*['"][^'"]+['"]/gi,
          replacement: '$1=***REDACTED***' }
    ];

    // Filter sensitive data from console messages
    function filterSensitive(message) {
        if (typeof message !== 'string') return message;
        let filtered = message;
        for (const pattern of SENSITIVE_PATTERNS) {
            filtered = filtered.replace(pattern.regex, pattern.replacement);
        }
        return filtered;
    }

    // Helper to stringify values
    function stringify(a) {
        // Handle special values that JSON.stringify mangles
        if (a === undefined) return 'undefined';
        if (a === null) return 'null';
        if (typeof a === 'number') {
            if (Number.isNaN(a)) return 'NaN';
            if (!Number.isFinite(a)) return a > 0 ? 'Infinity' : '-Infinity';
        }
        if (typeof a === 'symbol') return a.toString();
        if (typeof a === 'function') return `[Function: ${a.name || 'anonymous'}]`;
        if (typeof a === 'string') return a;
        try {
            return JSON.stringify(a);
        } catch {
            return String(a);
        }
    }

    // Helper to add to buffer
    function addToBuffer(level, message) {
        const trimmed = message.trim();
        // Filter sensitive data before storing
        const filtered = filterSensitive(trimmed === '' ? '(empty)' : trimmed);
        buffer.push({
            level,
            timestamp: new Date().toISOString(),
            message: filtered
        });
        if (buffer.length > MAX_MESSAGES) buffer.shift();
    }

    // Hook basic logging methods: log, error, warn, info, debug
    ['log', 'error', 'warn', 'info', 'debug'].forEach(level => {
        const original = console[level];
        console[level] = function(...args) {
            addToBuffer(level, formatArgs(args));
            return original.apply(console, args);
        };
    });

    // Hook console.table()
    const originalTable = console.table;
    console.table = function(data, columns) {
        let message;
        try {
            // Store as JSON for CLI to render nicely
            message = '[table:json]' + JSON.stringify({data, columns: columns || null});
        } catch (e) {
            message = '[table] ' + String(data);
        }
        addToBuffer('log', message);
        return originalTable.apply(console, arguments);
    };

    // Hook console.dir()
    const originalDir = console.dir;
    console.dir = function(obj, options) {
        let message = '[dir] ';
        try {
            message += JSON.stringify(obj, null, 2);
        } catch {
            message += String(obj);
        }
        addToBuffer('log', message);
        return originalDir.apply(console, arguments);
    };

    // Hook console.count()
    const originalCount = console.count;
    console.count = function(label = 'default') {
        counters[label] = (counters[label] || 0) + 1;
        addToBuffer('log', `${label}: ${counters[label]}`);
        return originalCount.apply(console, arguments);
    };

    // Hook console.countReset()
    const originalCountReset = console.countReset;
    console.countReset = function(label = 'default') {
        counters[label] = 0;
        addToBuffer('log', `${label}: 0`);
        return originalCountReset.apply(console, arguments);
    };

    // Hook console.time()
    const originalTime = console.time;
    console.time = function(label = 'default') {
        timers[label] = performance.now();
        return originalTime.apply(console, arguments);
    };

    // Hook console.timeLog()
    const originalTimeLog = console.timeLog;
    console.timeLog = function(label = 'default', ...args) {
        if (timers[label] !== undefined) {
            const elapsed = performance.now() - timers[label];
            const extra = args.length > 0 ? ' ' + formatArgs(args) : '';
            addToBuffer('log', `${label}: ${elapsed.toFixed(3)}ms${extra}`);
        }
        return originalTimeLog.apply(console, arguments);
    };

    // Hook console.timeEnd()
    const originalTimeEnd = console.timeEnd;
    console.timeEnd = function(label = 'default') {
        if (timers[label] !== undefined) {
            const elapsed = performance.now() - timers[label];
            addToBuffer('log', `${label}: ${elapsed.toFixed(3)}ms`);
            delete timers[label];
        }
        return originalTimeEnd.apply(console, arguments);
    };

    // Hook console.assert()
    const originalAssert = console.assert;
    console.assert = function(condition, ...args) {
        if (!condition) {
            const message = args.length > 0 ? formatArgs(args) : '(no message)';
            addToBuffer('error', '[assert] ' + message);
        }
        return originalAssert.apply(console, arguments);
    };

    // Hook console.trace()
    const originalTrace = console.trace;
    console.trace = function(...args) {
        const label = args.length > 0 ? formatArgs(args) : 'console.trace';
        // Get stack trace
        const stack = new Error().stack || '';
        const lines = stack.split('\n').slice(2).join('\n'); // Skip Error and this function
        addToBuffer('log', `[trace] ${label}\n${lines}`);
        return originalTrace.apply(console, arguments);
    };

    // Hook console.group() and console.groupCollapsed()
    const originalGroup = console.group;
    console.group = function(...args) {
        const label = args.length > 0 ? formatArgs(args) : 'console.group';
        addToBuffer('log', `[group] ${label}`);
        return originalGroup.apply(console, arguments);
    };

    const originalGroupCollapsed = console.groupCollapsed;
    console.groupCollapsed = function(...args) {
        const label = args.length > 0 ? formatArgs(args) : 'console.group';
        addToBuffer('log', `[group] ${label}`);
        return originalGroupCollapsed.apply(console, arguments);
    };

    // console.groupEnd() - no need to log, just call original

    // Hook console.clear() - log that it was called
    const originalClear = console.clear;
    console.clear = function() {
        addToBuffer('log', '[clear] Console was cleared');
        return originalClear.apply(console, arguments);
    };

    // Store buffer reference for retrieval
    window.__INSPEKT_CONSOLE_LOGS__ = buffer;
})();
