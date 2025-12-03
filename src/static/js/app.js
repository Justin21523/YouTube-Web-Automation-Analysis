/**
 * Main Application Entry Point
 * Initializes global functionality and utilities
 */

// Import core modules
import { api, healthAPI } from './core/api.js';
import { toast } from './components/toast.js';
import * as utils from './core/utils.js';

/**
 * Application State
 */
const AppState = {
    theme: localStorage.getItem('theme') || 'dark',
    sidebarOpen: true,
    activeTasks: 0,
    systemHealth: 'unknown'
};

/**
 * Initialize the application
 */
async function initApp() {
    console.log('🚀 Initializing YouTube Automation Analysis...');

    // Initialize theme
    initTheme();

    // Initialize health check
    await checkSystemHealth();

    // Initialize active tasks badge
    await updateActiveTasksBadge();

    // Start periodic updates
    startPeriodicUpdates();

    // Initialize global event listeners
    initGlobalEventListeners();

    console.log('✅ Application initialized');
}

/**
 * Initialize theme
 */
function initTheme() {
    const theme = AppState.theme;
    document.documentElement.setAttribute('data-theme', theme);

    if (theme === 'dark') {
        document.documentElement.classList.add('dark');
    } else {
        document.documentElement.classList.remove('dark');
    }

    // Theme toggle button
    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', toggleTheme);
    }
}

/**
 * Toggle theme between light and dark
 */
function toggleTheme() {
    const newTheme = AppState.theme === 'dark' ? 'light' : 'dark';
    AppState.theme = newTheme;
    localStorage.setItem('theme', newTheme);

    document.documentElement.setAttribute('data-theme', newTheme);
    if (newTheme === 'dark') {
        document.documentElement.classList.add('dark');
    } else {
        document.documentElement.classList.remove('dark');
    }

    // Update icon
    const icon = document.querySelector('#theme-toggle i');
    if (icon) {
        icon.setAttribute('data-lucide', newTheme === 'dark' ? 'moon' : 'sun');
        lucide.createIcons();
    }
}

/**
 * Check system health
 */
async function checkSystemHealth() {
    try {
        const health = await healthAPI.check();
        AppState.systemHealth = health.status;

        // Update health indicator
        const indicator = document.getElementById('health-indicator');
        if (indicator) {
            const colors = {
                healthy: 'bg-green-500',
                degraded: 'bg-yellow-500',
                unhealthy: 'bg-red-500'
            };
            indicator.className = `ml-auto w-2 h-2 rounded-full ${colors[health.status] || 'bg-gray-500'}`;
        }
    } catch (error) {
        console.error('Health check failed:', error);
        AppState.systemHealth = 'unknown';
    }
}

/**
 * Update active tasks badge
 */
async function updateActiveTasksBadge() {
    try {
        const data = await api.get('/tasks/active/list');
        const activeTasks = data?.celery_active?.length || 0;
        AppState.activeTasks = activeTasks;

        const badge = document.getElementById('active-tasks-badge');
        if (badge) {
            if (activeTasks > 0) {
                badge.textContent = activeTasks;
                badge.classList.remove('hidden');
            } else {
                badge.classList.add('hidden');
            }
        }
    } catch (error) {
        console.error('Failed to fetch active tasks:', error);
    }
}

/**
 * Start periodic updates
 */
function startPeriodicUpdates() {
    // Update active tasks every 10 seconds
    setInterval(updateActiveTasksBadge, 10000);

    // Update health every 30 seconds
    setInterval(checkSystemHealth, 30000);
}

/**
 * Initialize global event listeners
 */
function initGlobalEventListeners() {
    // Global keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        // Ctrl/Cmd + K for search
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            const searchInput = document.getElementById('global-search');
            if (searchInput) {
                searchInput.focus();
            }
        }

        // Escape to close modals
        if (e.key === 'Escape') {
            closeAllModals();
        }
    });

    // Global click handler for closing dropdowns
    document.addEventListener('click', (e) => {
        const dropdowns = document.querySelectorAll('.dropdown-menu.show');
        dropdowns.forEach(dropdown => {
            if (!dropdown.contains(e.target)) {
                dropdown.classList.remove('show');
            }
        });
    });

    // Handle global search
    const globalSearch = document.getElementById('global-search');
    if (globalSearch) {
        globalSearch.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                const query = e.target.value.trim();
                if (query) {
                    window.location.href = `/videos/search?q=${encodeURIComponent(query)}`;
                }
            }
        });
    }
}

/**
 * Close all open modals
 */
function closeAllModals() {
    const modals = document.querySelectorAll('[id$="-modal"]:not(.hidden)');
    modals.forEach(modal => {
        modal.classList.add('hidden');
    });
}

/**
 * Show loading overlay
 * @param {string} message - Loading message
 */
function showLoading(message = 'Loading...') {
    const overlay = document.getElementById('loading-overlay');
    const messageEl = document.getElementById('loading-message');

    if (overlay) {
        overlay.classList.remove('hidden');
    }
    if (messageEl) {
        messageEl.textContent = message;
    }
}

/**
 * Hide loading overlay
 */
function hideLoading() {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) {
        overlay.classList.add('hidden');
    }
}

/**
 * Format bytes to human readable size
 * @param {number} bytes - Bytes
 * @returns {string} Formatted size
 */
function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

/**
 * Confirm action with modal
 * @param {string} message - Confirmation message
 * @param {object} options - Options
 * @returns {Promise<boolean>} User's choice
 */
function confirm(message, options = {}) {
    return new Promise((resolve) => {
        const {
            title = 'Confirm',
            confirmText = 'Confirm',
            cancelText = 'Cancel',
            type = 'warning'
        } = options;

        const modal = document.createElement('div');
        modal.className = 'fixed inset-0 bg-black/50 flex items-center justify-center z-50';
        modal.innerHTML = `
            <div class="bg-dark-secondary rounded-xl shadow-2xl w-full max-w-md mx-4 overflow-hidden">
                <div class="p-6">
                    <h3 class="text-lg font-semibold mb-2">${title}</h3>
                    <p class="text-slate-300">${message}</p>
                </div>
                <div class="flex justify-end gap-3 p-4 border-t border-slate-700">
                    <button class="cancel-btn px-4 py-2 text-sm font-medium text-slate-300 hover:text-white transition-colors">
                        ${cancelText}
                    </button>
                    <button class="confirm-btn px-4 py-2 bg-${type === 'danger' ? 'red' : 'blue'}-600 hover:bg-${type === 'danger' ? 'red' : 'blue'}-700 text-white rounded-lg text-sm font-medium transition-colors">
                        ${confirmText}
                    </button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        const confirmBtn = modal.querySelector('.confirm-btn');
        const cancelBtn = modal.querySelector('.cancel-btn');

        confirmBtn.addEventListener('click', () => {
            modal.remove();
            resolve(true);
        });

        cancelBtn.addEventListener('click', () => {
            modal.remove();
            resolve(false);
        });

        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.remove();
                resolve(false);
            }
        });
    });
}

// Export global utilities
export {
    AppState,
    initApp,
    toggleTheme,
    checkSystemHealth,
    updateActiveTasksBadge,
    showLoading,
    hideLoading,
    formatBytes,
    confirm,
    closeAllModals
};

// Make utilities available globally
if (typeof window !== 'undefined') {
    window.AppState = AppState;
    window.showLoading = showLoading;
    window.hideLoading = hideLoading;
    window.formatBytes = formatBytes;
    window.confirmAction = confirm;

    // Initialize app when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initApp);
    } else {
        initApp();
    }
}
