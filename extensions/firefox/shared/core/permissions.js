/**
 * Inspekt - Domain Permission Manager (Shared)
 *
 * Handles user-initiated permission system for domains
 * Cross-browser compatible (works with chrome and browser APIs)
 *
 * New Features:
 * - Parent domain grants subdomain access
 * - Temporary "bypass all domains" mode
 * - Timestamp tracking for domain additions
 * - No intrusive modals - permission granted via popup button only
 */

const InspektPermissions = {
    STORAGE_KEY: 'inspekt_allowed_domains',
    TEMP_BYPASS_KEY: 'inspekt_temp_bypass',
    PERMANENT_BYPASS_KEY: 'inspekt_permanent_bypass',  // For isolated/VM environments

    /**
     * Get the domain from a URL
     * For file:// URLs, returns 'local-file' as a special domain
     */
    getDomain(url) {
        try {
            const urlObj = new URL(url || window.location.href);

            // Handle file:// URLs - hostname is empty for these
            if (urlObj.protocol === 'file:') {
                return 'local-file';
            }

            return urlObj.hostname;
        } catch (e) {
            return null;
        }
    },

    /**
     * Check if a requested domain matches an allowed domain
     * Supports parent domain → subdomain matching
     *
     * Examples:
     *  - matchesDomain('github.com', 'github.com') → true
     *  - matchesDomain('www.github.com', 'github.com') → true (subdomain)
     *  - matchesDomain('api.github.com', 'github.com') → true (subdomain)
     *  - matchesDomain('github.com', 'www.github.com') → false (parent doesn't match child)
     *  - matchesDomain('example.com', 'github.com') → false (different domains)
     */
    matchesDomain(requestedDomain, allowedDomain) {
        // Exact match
        if (requestedDomain === allowedDomain) {
            return true;
        }

        // Check if requestedDomain is a subdomain of allowedDomain
        // e.g., 'www.github.com' should match 'github.com'
        if (requestedDomain.endsWith('.' + allowedDomain)) {
            return true;
        }

        // Special case for localhost with port
        // 'localhost:3000' should match 'localhost'
        if (allowedDomain === 'localhost' && requestedDomain.startsWith('localhost:')) {
            return true;
        }

        // Also check if allowed domain has port but requested doesn't
        // 'localhost' should match 'localhost:8080' if 'localhost:8080' is allowed
        const requestedParts = requestedDomain.split(':');
        const allowedParts = allowedDomain.split(':');
        if (requestedParts[0] === allowedParts[0]) {
            // Same base domain, different or missing ports
            return true;
        }

        return false;
    },

    /**
     * Check if permanent bypass is enabled (for isolated/VM environments)
     * This is set by the bridge server when running in isolated mode
     */
    async isPermanentBypassActive() {
        try {
            const storage = typeof chrome !== 'undefined' ? chrome.storage : browser.storage;
            const result = await storage.sync.get(this.PERMANENT_BYPASS_KEY);
            const bypass = result[this.PERMANENT_BYPASS_KEY];
            return bypass && bypass.enabled === true;
        } catch (e) {
            return false;
        }
    },

    /**
     * Enable or disable permanent bypass (for isolated/VM environments)
     * @param {boolean} enabled - Whether to enable permanent bypass
     */
    async setPermanentBypass(enabled) {
        const storage = typeof chrome !== 'undefined' ? chrome.storage : browser.storage;

        if (enabled) {
            await storage.sync.set({
                [this.PERMANENT_BYPASS_KEY]: {
                    enabled: true,
                    enabledAt: new Date().toISOString(),
                    reason: 'isolated_mode'
                }
            });
            console.log('[Inspekt] Permanent bypass ENABLED (isolated mode)');
        } else {
            await storage.sync.remove(this.PERMANENT_BYPASS_KEY);
            console.log('[Inspekt] Permanent bypass DISABLED');
        }

        return { ok: true, enabled: enabled };
    },

    /**
     * Check if temporary bypass is active
     * Returns true if bypass enabled and not expired
     */
    async isTempBypassActive() {
        const storage = typeof chrome !== 'undefined' ? chrome.storage : browser.storage;
        const result = await storage.sync.get(this.TEMP_BYPASS_KEY);
        const bypass = result[this.TEMP_BYPASS_KEY];

        if (!bypass || !bypass.enabled) {
            return false;
        }

        // Check if expired
        if (bypass.expiresAt) {
            const now = new Date().getTime();
            const expiresAt = new Date(bypass.expiresAt).getTime();

            if (now >= expiresAt) {
                // Expired - clear it
                await this.clearTempBypass();
                return false;
            }
        }

        return true;
    },

    /**
     * Set temporary bypass for all domains
     * @param {number} durationMinutes - Duration in minutes (0 to disable)
     */
    async setTempBypass(durationMinutes) {
        const storage = typeof chrome !== 'undefined' ? chrome.storage : browser.storage;

        if (durationMinutes === 0) {
            // Disable bypass
            await this.clearTempBypass();
            return { ok: true, enabled: false };
        }

        const now = new Date();
        const expiresAt = new Date(now.getTime() + durationMinutes * 60 * 1000);

        const bypass = {
            enabled: true,
            expiresAt: expiresAt.toISOString(),
            durationMinutes: durationMinutes
        };

        await storage.sync.set({ [this.TEMP_BYPASS_KEY]: bypass });

        return {
            ok: true,
            enabled: true,
            expiresAt: bypass.expiresAt,
            durationMinutes: durationMinutes
        };
    },

    /**
     * Clear temporary bypass
     */
    async clearTempBypass() {
        const storage = typeof chrome !== 'undefined' ? chrome.storage : browser.storage;
        await storage.sync.remove(this.TEMP_BYPASS_KEY);
    },

    /**
     * Get temporary bypass status
     */
    async getTempBypassStatus() {
        const storage = typeof chrome !== 'undefined' ? chrome.storage : browser.storage;
        const result = await storage.sync.get(this.TEMP_BYPASS_KEY);
        const bypass = result[this.TEMP_BYPASS_KEY];

        if (!bypass || !bypass.enabled) {
            return { enabled: false };
        }

        // Check if expired
        const now = new Date().getTime();
        const expiresAt = new Date(bypass.expiresAt).getTime();

        if (now >= expiresAt) {
            await this.clearTempBypass();
            return { enabled: false };
        }

        const remainingMs = expiresAt - now;
        const remainingMinutes = Math.ceil(remainingMs / (60 * 1000));

        return {
            enabled: true,
            expiresAt: bypass.expiresAt,
            durationMinutes: bypass.durationMinutes,
            remainingMinutes: remainingMinutes
        };
    },

    /**
     * Migrate legacy storage format (array) to new format (object with metadata)
     * This runs automatically on first access
     */
    async migrateLegacyStorage() {
        const storage = typeof chrome !== 'undefined' ? chrome.storage : browser.storage;
        const result = await storage.sync.get(this.STORAGE_KEY);
        const data = result[this.STORAGE_KEY];

        // If no data or already migrated (is object), skip
        if (!data || typeof data === 'object' && !Array.isArray(data)) {
            return;
        }

        // If data is array (legacy format), migrate it
        if (Array.isArray(data)) {
            const migrated = {};
            const now = new Date().toISOString();

            data.forEach(domain => {
                migrated[domain] = {
                    addedAt: now,
                    permanent: true
                };
            });

            await storage.sync.set({ [this.STORAGE_KEY]: migrated });
            console.log('[Inspekt] Migrated', data.length, 'domains to new format');
        }
    },

    /**
     * Check if a domain is allowed
     * Supports subdomain matching, temp bypass, and permanent bypass (isolated mode)
     * Local files (file://) are allowed by default
     */
    async isAllowed(domain) {
        domain = domain || this.getDomain();
        if (!domain) return false;

        // Local files are always allowed by default
        // (user already opted in by enabling "Allow access to file URLs" in browser)
        if (domain === 'local-file') {
            return true;
        }

        // Check permanent bypass first (for isolated/VM environments)
        const permanentBypassActive = await this.isPermanentBypassActive();
        if (permanentBypassActive) {
            return true;
        }

        // Check temp bypass (bypasses all domain checks)
        const bypassActive = await this.isTempBypassActive();
        if (bypassActive) {
            return true;
        }

        // Ensure migration has run
        await this.migrateLegacyStorage();

        const storage = typeof chrome !== 'undefined' ? chrome.storage : browser.storage;
        const result = await storage.sync.get(this.STORAGE_KEY);
        const allowedDomains = result[this.STORAGE_KEY] || {};

        // Check each allowed domain for match (including subdomains)
        for (const allowedDomain of Object.keys(allowedDomains)) {
            if (this.matchesDomain(domain, allowedDomain)) {
                return true;
            }
        }

        return false;
    },

    /**
     * Add a domain to the allowed list with timestamp
     */
    async allowDomain(domain) {
        domain = domain || this.getDomain();
        if (!domain) return false;

        // Ensure migration has run
        await this.migrateLegacyStorage();

        const storage = typeof chrome !== 'undefined' ? chrome.storage : browser.storage;
        const result = await storage.sync.get(this.STORAGE_KEY);
        const allowedDomains = result[this.STORAGE_KEY] || {};

        // Check if already exists
        if (!allowedDomains[domain]) {
            allowedDomains[domain] = {
                addedAt: new Date().toISOString(),
                permanent: true
            };
            await storage.sync.set({ [this.STORAGE_KEY]: allowedDomains });
        }

        return true;
    },

    /**
     * Remove a domain from the allowed list
     */
    async removeDomain(domain) {
        // Ensure migration has run
        await this.migrateLegacyStorage();

        const storage = typeof chrome !== 'undefined' ? chrome.storage : browser.storage;
        const result = await storage.sync.get(this.STORAGE_KEY);
        const allowedDomains = result[this.STORAGE_KEY] || {};

        if (allowedDomains[domain]) {
            delete allowedDomains[domain];
            await storage.sync.set({ [this.STORAGE_KEY]: allowedDomains });
        }

        return true;
    },

    /**
     * Get all allowed domains with metadata
     * Returns object: { "github.com": { addedAt: "…", permanent: true }, ... }
     */
    async getAllowedDomains() {
        // Ensure migration has run
        await this.migrateLegacyStorage();

        const storage = typeof chrome !== 'undefined' ? chrome.storage : browser.storage;
        const result = await storage.sync.get(this.STORAGE_KEY);
        return result[this.STORAGE_KEY] || {};
    },

    /**
     * Get all allowed domains as simple array (for backwards compatibility)
     */
    async getAllowedDomainsArray() {
        const domains = await this.getAllowedDomains();
        return Object.keys(domains);
    },

    /**
     * Check domain permission WITHOUT showing modal
     * Returns true if:
     * - Temp bypass is active, OR
     * - Domain is explicitly allowed (including subdomain matching)
     *
     * Returns false otherwise (user must allow via popup button)
     */
    async checkAndRequest() {
        const domain = this.getDomain();
        if (!domain) return false;

        const allowed = await this.isAllowed(domain);
        return allowed;
    }
};

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = InspektPermissions;
}
