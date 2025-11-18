/**
 * Inspekt - Domain Permission Manager (Shared)
 *
 * Handles opt-in permission system for domains
 * Cross-browser compatible (works with chrome and browser APIs)
 */

const InspektPermissions = {
    STORAGE_KEY: 'inspekt_allowed_domains',

    /**
     * Get the domain from a URL
     */
    getDomain(url) {
        try {
            const urlObj = new URL(url || window.location.href);
            return urlObj.hostname;
        } catch (e) {
            return null;
        }
    },

    /**
     * Check if a domain is allowed
     */
    async isAllowed(domain) {
        domain = domain || this.getDomain();
        if (!domain) return false;

        const storage = typeof chrome !== 'undefined' ? chrome.storage : browser.storage;
        const result = await storage.sync.get(this.STORAGE_KEY);
        const allowedDomains = result[this.STORAGE_KEY] || [];

        return allowedDomains.includes(domain);
    },

    /**
     * Add a domain to the allowed list
     */
    async allowDomain(domain) {
        domain = domain || this.getDomain();
        if (!domain) return false;

        const storage = typeof chrome !== 'undefined' ? chrome.storage : browser.storage;
        const result = await storage.sync.get(this.STORAGE_KEY);
        const allowedDomains = result[this.STORAGE_KEY] || [];

        if (!allowedDomains.includes(domain)) {
            allowedDomains.push(domain);
            await storage.sync.set({ [this.STORAGE_KEY]: allowedDomains });
        }

        return true;
    },

    /**
     * Remove a domain from the allowed list
     */
    async removeDomain(domain) {
        const storage = typeof chrome !== 'undefined' ? chrome.storage : browser.storage;
        const result = await storage.sync.get(this.STORAGE_KEY);
        const allowedDomains = result[this.STORAGE_KEY] || [];

        const filtered = allowedDomains.filter(d => d !== domain);
        await storage.sync.set({ [this.STORAGE_KEY]: filtered });

        return true;
    },

    /**
     * Get all allowed domains
     */
    async getAllowedDomains() {
        const storage = typeof chrome !== 'undefined' ? chrome.storage : browser.storage;
        const result = await storage.sync.get(this.STORAGE_KEY);
        return result[this.STORAGE_KEY] || [];
    },

    /**
     * Show opt-in modal for the current domain
     */
    async showOptInModal() {
        const domain = this.getDomain();
        if (!domain) return false;

        return new Promise((resolve) => {
            // Create modal overlay
            const overlay = document.createElement('div');
            overlay.id = 'inspekt-permission-modal';
            overlay.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.7);
                z-index: 2147483647;
                display: flex;
                align-items: center;
                justify-content: center;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            `;

            // Create modal content
            const modal = document.createElement('div');
            modal.style.cssText = `
                background: white;
                border-radius: 12px;
                padding: 32px;
                max-width: 500px;
                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
                animation: inspekt-modal-appear 0.3s ease-out;
            `;

            // Add animation keyframes
            const style = document.createElement('style');
            style.textContent = `
                @keyframes inspekt-modal-appear {
                    from {
                        opacity: 0;
                        transform: translateY(-20px) scale(0.95);
                    }
                    to {
                        opacity: 1;
                        transform: translateY(0) scale(1);
                    }
                }
            `;
            document.head.appendChild(style);

            modal.innerHTML = `
                <div style="text-align: center; margin-bottom: 24px;">
                    <div style="font-size: 48px; margin-bottom: 16px;">⚡</div>
                    <h2 style="margin: 0 0 12px 0; color: #333; font-size: 24px; font-weight: 600;">
                        Inspekt
                    </h2>
                    <p style="margin: 0; color: #666; font-size: 14px;">
                        Allow CLI control of this website?
                    </p>
                </div>

                <div style="background: #f5f5f5; padding: 16px; border-radius: 8px; margin-bottom: 24px;">
                    <div style="display: flex; align-items: center; margin-bottom: 12px;">
                        <div style="font-size: 24px; margin-right: 12px;">🌐</div>
                        <div>
                            <div style="font-weight: 600; color: #333; font-size: 16px;">${domain}</div>
                            <div style="color: #666; font-size: 13px;">This domain</div>
                        </div>
                    </div>

                    <div style="font-size: 13px; color: #666; line-height: 1.5;">
                        Inspekt will be able to:
                        <ul style="margin: 8px 0 0 0; padding-left: 20px;">
                            <li>Execute commands from your CLI</li>
                            <li>Read and modify page content</li>
                            <li>Interact with page elements</li>
                        </ul>
                    </div>
                </div>

                <div style="background: #fff3cd; border: 1px solid #ffc107; padding: 12px; border-radius: 6px; margin-bottom: 24px;">
                    <div style="display: flex; align-items: start;">
                        <div style="margin-right: 8px; font-size: 16px;">⚠️</div>
                        <div style="font-size: 13px; color: #856404; line-height: 1.5;">
                            <strong>Important:</strong> Only allow Inspekt on websites you trust.
                            This grants your local CLI full control over this domain.
                        </div>
                    </div>
                </div>

                <div style="display: flex; gap: 12px;">
                    <button id="inspekt-deny-btn" style="
                        flex: 1;
                        padding: 12px 24px;
                        border: 2px solid #e0e0e0;
                        background: white;
                        color: #666;
                        border-radius: 8px;
                        font-size: 14px;
                        font-weight: 600;
                        cursor: pointer;
                        transition: all 0.2s;
                    ">
                        Deny
                    </button>
                    <button id="inspekt-allow-btn" style="
                        flex: 1;
                        padding: 12px 24px;
                        border: none;
                        background: linear-gradient(135deg, #0066ff 0%, #004db3 100%);
                        color: white;
                        border-radius: 8px;
                        font-size: 14px;
                        font-weight: 600;
                        cursor: pointer;
                        transition: all 0.2s;
                    ">
                        Allow ${domain}
                    </button>
                </div>

                <div style="margin-top: 16px; text-align: center;">
                    <a href="https://github.com/roelvangils/inspekt" target="_blank" style="
                        color: #0066ff;
                        text-decoration: none;
                        font-size: 12px;
                    ">Learn more about Inspekt</a>
                </div>
            `;

            overlay.appendChild(modal);
            document.body.appendChild(overlay);

            // Add hover effects
            const allowBtn = modal.querySelector('#inspekt-allow-btn');
            const denyBtn = modal.querySelector('#inspekt-deny-btn');

            allowBtn.addEventListener('mouseenter', () => {
                allowBtn.style.transform = 'translateY(-2px)';
                allowBtn.style.boxShadow = '0 4px 12px rgba(0, 102, 255, 0.3)';
            });
            allowBtn.addEventListener('mouseleave', () => {
                allowBtn.style.transform = 'translateY(0)';
                allowBtn.style.boxShadow = 'none';
            });

            denyBtn.addEventListener('mouseenter', () => {
                denyBtn.style.background = '#f5f5f5';
                denyBtn.style.borderColor = '#ccc';
            });
            denyBtn.addEventListener('mouseleave', () => {
                denyBtn.style.background = 'white';
                denyBtn.style.borderColor = '#e0e0e0';
            });

            // Handle button clicks
            allowBtn.addEventListener('click', async () => {
                await this.allowDomain(domain);
                document.body.removeChild(overlay);
                resolve(true);
            });

            denyBtn.addEventListener('click', () => {
                document.body.removeChild(overlay);
                resolve(false);
            });

            // Close on overlay click
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) {
                    document.body.removeChild(overlay);
                    resolve(false);
                }
            });
        });
    },

    /**
     * Check permission and show modal if needed
     */
    async checkAndRequest() {
        const domain = this.getDomain();
        if (!domain) return false;

        const allowed = await this.isAllowed(domain);
        if (allowed) {
            return true;
        }

        // Show opt-in modal
        const result = await this.showOptInModal();
        return result;
    }
};

// Support legacy ZenPermissions name for backward compatibility
const ZenPermissions = InspektPermissions;

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = InspektPermissions;
}
