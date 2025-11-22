/**
 * Connection Manager Module
 * Monitors WebSocket connection status and updates UI
 */

import { evalInPage } from '../utils/devtools.js';

export class ConnectionManager {
    constructor() {
        this.statusIndicator = document.getElementById('statusIndicator');
        this.statusText = document.getElementById('statusText');
        this.serverCallout = document.getElementById('serverCallout');
        this.btnCopyServerCommand = document.getElementById('copyServerCommand');

        this.checkInterval = null;
    }

    /**
     * Initialize connection manager and start monitoring
     */
    init() {
        this.setupEventListeners();
        this.start();
    }

    /**
     * Setup event listeners
     */
    setupEventListeners() {
        // Server callout copy button
        this.btnCopyServerCommand.addEventListener('click', () => {
            navigator.clipboard.writeText('inspekt server start').then(() => {
                console.log('[Inspekt Panel] Server start command copied to clipboard');
                this.btnCopyServerCommand.innerHTML = '<span class="material-icons md-18">check</span>';
                setTimeout(() => {
                    this.btnCopyServerCommand.innerHTML = '<span class="material-icons md-18">content_copy</span>';
                }, 2000);
            }).catch(err => {
                console.error('[Inspekt Panel] Failed to copy:', err);
            });
        });
    }

    /**
     * Start checking connection status
     */
    start() {
        this.checkStatus();
    }

    /**
     * Check connection status once
     */
    checkStatus() {
        try {
            evalInPage('window.__INSPEKT_WS_CONNECTED__', (result, error) => {
                console.log('[Connection Manager] Status check - Result:', result, 'Error:', error);

                if (error) {
                    console.error('[Connection Manager] Error checking connection:', error);
                    this.updateStatus('disconnected');
                } else {
                    // result can be: 'connecting', true (connected), or false (disconnected)
                    if (result === true) {
                        console.log('[Connection Manager] WebSocket is connected');
                        this.updateStatus('connected');
                    } else if (result === 'connecting') {
                        console.log('[Connection Manager] WebSocket is connecting');
                        this.updateStatus('connecting');
                    } else {
                        console.log('[Connection Manager] WebSocket is disconnected, result:', result);
                        this.updateStatus('disconnected');
                    }
                }
            });
        } catch (err) {
            console.error('[Connection Manager] Exception in checkStatus:', err);
            this.updateStatus('disconnected');
        }

        // Recheck every 2 seconds for faster updates
        this.checkInterval = setTimeout(() => this.checkStatus(), 2000);
    }

    /**
     * Update connection status UI
     * @param {string} status - 'connected', 'connecting', or 'disconnected'
     */
    updateStatus(status) {
        console.log('[Connection Manager] Updating UI status to:', status);

        if (status === 'connected') {
            this.statusIndicator.className = 'status-indicator connected';
            this.statusText.textContent = 'Connected';
            this.serverCallout.style.display = 'none';
        } else if (status === 'connecting') {
            this.statusIndicator.className = 'status-indicator connecting';
            this.statusText.textContent = 'Connecting…';
            this.serverCallout.style.display = 'none';
        } else {
            this.statusIndicator.className = 'status-indicator disconnected';
            this.statusText.textContent = 'Disconnected';
            this.serverCallout.style.display = 'flex';
        }
    }

    /**
     * Stop checking connection status
     */
    stop() {
        if (this.checkInterval) {
            clearTimeout(this.checkInterval);
            this.checkInterval = null;
        }
    }
}
