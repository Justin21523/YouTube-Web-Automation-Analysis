/**
 * Utility Functions
 * Common helper functions used across the application
 */

/**
 * Format a number with thousand separators
 * @param {number} num - Number to format
 * @returns {string} Formatted number string
 */
export function formatNumber(num) {
    if (num === null || num === undefined) return '0';
    if (num >= 1000000) {
        return (num / 1000000).toFixed(1) + 'M';
    }
    if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'K';
    }
    return num.toLocaleString();
}

/**
 * Format duration in seconds to HH:MM:SS or MM:SS
 * @param {number} seconds - Duration in seconds
 * @returns {string} Formatted duration string
 */
export function formatDuration(seconds) {
    if (!seconds || seconds <= 0) return '0:00';

    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);

    if (hours > 0) {
        return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
}

/**
 * Format a date to relative time (e.g., "2 hours ago")
 * @param {string|Date} date - Date to format
 * @returns {string} Relative time string
 */
export function formatRelativeTime(date) {
    if (!date) return 'Unknown';

    const now = new Date();
    const then = new Date(date);
    const diffMs = now - then;
    const diffSecs = Math.floor(diffMs / 1000);
    const diffMins = Math.floor(diffSecs / 60);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);
    const diffWeeks = Math.floor(diffDays / 7);
    const diffMonths = Math.floor(diffDays / 30);
    const diffYears = Math.floor(diffDays / 365);

    if (diffSecs < 60) return 'Just now';
    if (diffMins < 60) return `${diffMins} minute${diffMins > 1 ? 's' : ''} ago`;
    if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
    if (diffDays < 7) return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
    if (diffWeeks < 4) return `${diffWeeks} week${diffWeeks > 1 ? 's' : ''} ago`;
    if (diffMonths < 12) return `${diffMonths} month${diffMonths > 1 ? 's' : ''} ago`;
    return `${diffYears} year${diffYears > 1 ? 's' : ''} ago`;
}

/**
 * Format a date to locale string
 * @param {string|Date} date - Date to format
 * @param {object} options - Intl.DateTimeFormat options
 * @returns {string} Formatted date string
 */
export function formatDate(date, options = {}) {
    if (!date) return 'Unknown';

    const defaultOptions = {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        ...options
    };

    return new Date(date).toLocaleDateString('zh-TW', defaultOptions);
}

/**
 * Extract YouTube video ID from URL or return as-is if already an ID
 * @param {string} input - YouTube URL or video ID
 * @returns {string|null} Video ID or null if invalid
 */
export function extractVideoId(input) {
    if (!input) return null;

    // Already a video ID (11 characters)
    if (/^[a-zA-Z0-9_-]{11}$/.test(input)) {
        return input;
    }

    // YouTube URL patterns
    const patterns = [
        /(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})/,
        /youtube\.com\/v\/([a-zA-Z0-9_-]{11})/,
        /youtube\.com\/shorts\/([a-zA-Z0-9_-]{11})/
    ];

    for (const pattern of patterns) {
        const match = input.match(pattern);
        if (match) return match[1];
    }

    return null;
}

/**
 * Get YouTube thumbnail URL
 * @param {string} videoId - YouTube video ID
 * @param {string} quality - Thumbnail quality (default, medium, high, maxres)
 * @returns {string} Thumbnail URL
 */
export function getYouTubeThumbnail(videoId, quality = 'high') {
    const qualities = {
        default: 'default',
        medium: 'mqdefault',
        high: 'hqdefault',
        maxres: 'maxresdefault'
    };
    return `https://img.youtube.com/vi/${videoId}/${qualities[quality] || 'hqdefault'}.jpg`;
}

/**
 * Debounce function execution
 * @param {Function} func - Function to debounce
 * @param {number} wait - Wait time in milliseconds
 * @returns {Function} Debounced function
 */
export function debounce(func, wait = 300) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * Throttle function execution
 * @param {Function} func - Function to throttle
 * @param {number} limit - Time limit in milliseconds
 * @returns {Function} Throttled function
 */
export function throttle(func, limit = 300) {
    let inThrottle;
    return function executedFunction(...args) {
        if (!inThrottle) {
            func(...args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

/**
 * Deep clone an object
 * @param {object} obj - Object to clone
 * @returns {object} Cloned object
 */
export function deepClone(obj) {
    return JSON.parse(JSON.stringify(obj));
}

/**
 * Generate a unique ID
 * @param {string} prefix - Optional prefix
 * @returns {string} Unique ID
 */
export function generateId(prefix = '') {
    const random = Math.random().toString(36).substring(2, 9);
    const timestamp = Date.now().toString(36);
    return prefix ? `${prefix}_${random}${timestamp}` : `${random}${timestamp}`;
}

/**
 * Truncate text to specified length
 * @param {string} text - Text to truncate
 * @param {number} length - Maximum length
 * @param {string} suffix - Suffix to add (default: '...')
 * @returns {string} Truncated text
 */
export function truncateText(text, length = 100, suffix = '...') {
    if (!text || text.length <= length) return text || '';
    return text.substring(0, length).trim() + suffix;
}

/**
 * Parse query string to object
 * @param {string} queryString - Query string (with or without leading ?)
 * @returns {object} Parsed query parameters
 */
export function parseQueryString(queryString) {
    const params = new URLSearchParams(queryString.replace(/^\?/, ''));
    const result = {};
    for (const [key, value] of params) {
        result[key] = value;
    }
    return result;
}

/**
 * Build query string from object
 * @param {object} params - Query parameters
 * @returns {string} Query string (without leading ?)
 */
export function buildQueryString(params) {
    const searchParams = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
        if (value !== null && value !== undefined && value !== '') {
            searchParams.append(key, value);
        }
    }
    return searchParams.toString();
}

/**
 * Escape HTML special characters
 * @param {string} text - Text to escape
 * @returns {string} Escaped text
 */
export function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Copy text to clipboard
 * @param {string} text - Text to copy
 * @returns {Promise<boolean>} Success status
 */
export async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        return true;
    } catch (err) {
        console.error('Failed to copy:', err);
        return false;
    }
}

/**
 * Get status color class based on status string
 * @param {string} status - Status string
 * @returns {string} Tailwind color class
 */
export function getStatusColor(status) {
    const colors = {
        pending: 'text-yellow-500',
        running: 'text-blue-500',
        processing: 'text-blue-500',
        completed: 'text-green-500',
        success: 'text-green-500',
        failed: 'text-red-500',
        error: 'text-red-500',
        cancelled: 'text-gray-500',
        healthy: 'text-green-500',
        degraded: 'text-yellow-500',
        unhealthy: 'text-red-500'
    };
    return colors[status?.toLowerCase()] || 'text-gray-500';
}

/**
 * Get status badge class based on status string
 * @param {string} status - Status string
 * @returns {string} Badge CSS class
 */
export function getStatusBadgeClass(status) {
    const classes = {
        pending: 'badge-warning',
        running: 'badge-info',
        processing: 'badge-info',
        completed: 'badge-success',
        success: 'badge-success',
        failed: 'badge-error',
        error: 'badge-error',
        cancelled: 'badge-secondary',
        healthy: 'badge-success',
        degraded: 'badge-warning',
        unhealthy: 'badge-error'
    };
    return classes[status?.toLowerCase()] || 'badge-secondary';
}

// Make functions available globally for non-module scripts
if (typeof window !== 'undefined') {
    window.utils = {
        formatNumber,
        formatDuration,
        formatRelativeTime,
        formatDate,
        extractVideoId,
        getYouTubeThumbnail,
        debounce,
        throttle,
        deepClone,
        generateId,
        truncateText,
        parseQueryString,
        buildQueryString,
        escapeHtml,
        copyToClipboard,
        getStatusColor,
        getStatusBadgeClass
    };
}
