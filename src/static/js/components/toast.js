/**
 * Toast Notification System
 * Provides non-blocking notifications to users
 */

class ToastManager {
    constructor(containerId = 'toast-container') {
        this.container = document.getElementById(containerId);
        if (!this.container) {
            this.container = document.createElement('div');
            this.container.id = containerId;
            this.container.className = 'fixed top-4 right-4 z-50 flex flex-col gap-2';
            document.body.appendChild(this.container);
        }
        this.toasts = [];
        this.defaultDuration = 4000;
    }

    /**
     * Show a toast notification
     * @param {string} message - Toast message
     * @param {string} type - Toast type (success, error, warning, info)
     * @param {object} options - Additional options
     * @returns {string} Toast ID
     */
    show(message, type = 'info', options = {}) {
        const id = `toast-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        const duration = options.duration ?? this.defaultDuration;

        const toast = document.createElement('div');
        toast.id = id;
        toast.className = `toast ${type} fade-in`;
        toast.innerHTML = this.getToastHTML(message, type, options);

        this.container.appendChild(toast);
        this.toasts.push(id);

        // Add close button functionality
        const closeBtn = toast.querySelector('.toast-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.dismiss(id));
        }

        // Auto dismiss
        if (duration > 0) {
            setTimeout(() => this.dismiss(id), duration);
        }

        return id;
    }

    /**
     * Get toast HTML content
     * @param {string} message - Toast message
     * @param {string} type - Toast type
     * @param {object} options - Options
     * @returns {string} HTML string
     */
    getToastHTML(message, type, options) {
        const icons = {
            success: '<svg class="w-5 h-5 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>',
            error: '<svg class="w-5 h-5 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>',
            warning: '<svg class="w-5 h-5 text-yellow-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>',
            info: '<svg class="w-5 h-5 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>'
        };

        const icon = icons[type] || icons.info;
        const title = options.title || '';

        return `
            <div class="flex items-start gap-3">
                <div class="flex-shrink-0 mt-0.5">
                    ${icon}
                </div>
                <div class="flex-1 min-w-0">
                    ${title ? `<p class="font-medium text-sm">${title}</p>` : ''}
                    <p class="text-sm text-slate-300">${message}</p>
                </div>
                <button class="toast-close flex-shrink-0 p-1 hover:bg-slate-700 rounded transition-colors">
                    <svg class="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                    </svg>
                </button>
            </div>
        `;
    }

    /**
     * Dismiss a toast
     * @param {string} id - Toast ID
     */
    dismiss(id) {
        const toast = document.getElementById(id);
        if (toast) {
            toast.style.animation = 'slideOut 0.3s ease forwards';
            setTimeout(() => {
                toast.remove();
                this.toasts = this.toasts.filter(t => t !== id);
            }, 300);
        }
    }

    /**
     * Dismiss all toasts
     */
    dismissAll() {
        this.toasts.forEach(id => this.dismiss(id));
    }

    // Convenience methods
    success(message, options = {}) {
        return this.show(message, 'success', options);
    }

    error(message, options = {}) {
        return this.show(message, 'error', { duration: 6000, ...options });
    }

    warning(message, options = {}) {
        return this.show(message, 'warning', options);
    }

    info(message, options = {}) {
        return this.show(message, 'info', options);
    }

    /**
     * Show a promise-based toast
     * Shows loading state, then success/error
     * @param {Promise} promise - Promise to track
     * @param {object} messages - Messages for each state
     * @returns {Promise} Original promise result
     */
    async promise(promise, messages = {}) {
        const {
            loading = 'Loading...',
            success = 'Success!',
            error = 'Something went wrong'
        } = messages;

        const id = this.show(loading, 'info', { duration: 0 });

        try {
            const result = await promise;
            this.dismiss(id);
            this.success(typeof success === 'function' ? success(result) : success);
            return result;
        } catch (err) {
            this.dismiss(id);
            this.error(typeof error === 'function' ? error(err) : error);
            throw err;
        }
    }
}

// Create singleton instance
const toast = new ToastManager();

// Export for ES modules
export { ToastManager, toast };

// Make available globally
if (typeof window !== 'undefined') {
    window.toast = toast;
    window.ToastManager = ToastManager;
}
