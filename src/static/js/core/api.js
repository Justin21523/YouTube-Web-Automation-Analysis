/**
 * API Client
 * Centralized HTTP client for API communication
 */

/**
 * Custom API Error class
 */
class APIError extends Error {
    constructor(message, status, data = null) {
        super(message);
        this.name = 'APIError';
        this.status = status;
        this.data = data;
    }
}

/**
 * API Client class
 * Provides methods for making HTTP requests to the backend
 */
class APIClient {
    constructor(baseURL = '/api/v1') {
        this.baseURL = baseURL;
        this.defaultHeaders = {
            'Content-Type': 'application/json',
        };
    }

    /**
     * Make an HTTP request
     * @param {string} endpoint - API endpoint
     * @param {object} options - Fetch options
     * @returns {Promise<any>} Response data
     */
    async request(endpoint, options = {}) {
        const url = `${this.baseURL}${endpoint}`;
        const config = {
            headers: { ...this.defaultHeaders, ...options.headers },
            ...options,
        };

        try {
            const response = await fetch(url, config);

            // Handle empty responses
            const contentType = response.headers.get('content-type');
            let data = null;

            if (contentType && contentType.includes('application/json')) {
                data = await response.json();
            } else if (response.status !== 204) {
                data = await response.text();
            }

            if (!response.ok) {
                const errorMessage = data?.detail || data?.error || data?.message || 'Request failed';
                throw new APIError(errorMessage, response.status, data);
            }

            return data;
        } catch (error) {
            if (error instanceof APIError) {
                throw error;
            }
            throw new APIError(
                error.message || 'Network error',
                0,
                { original: error.message }
            );
        }
    }

    /**
     * GET request
     * @param {string} endpoint - API endpoint
     * @param {object} params - Query parameters
     * @returns {Promise<any>} Response data
     */
    async get(endpoint, params = {}) {
        const queryString = new URLSearchParams(
            Object.entries(params).filter(([_, v]) => v !== null && v !== undefined && v !== '')
        ).toString();
        const url = queryString ? `${endpoint}?${queryString}` : endpoint;
        return this.request(url, { method: 'GET' });
    }

    /**
     * POST request
     * @param {string} endpoint - API endpoint
     * @param {object} data - Request body
     * @returns {Promise<any>} Response data
     */
    async post(endpoint, data = {}) {
        return this.request(endpoint, {
            method: 'POST',
            body: JSON.stringify(data),
        });
    }

    /**
     * PUT request
     * @param {string} endpoint - API endpoint
     * @param {object} data - Request body
     * @returns {Promise<any>} Response data
     */
    async put(endpoint, data = {}) {
        return this.request(endpoint, {
            method: 'PUT',
            body: JSON.stringify(data),
        });
    }

    /**
     * PATCH request
     * @param {string} endpoint - API endpoint
     * @param {object} data - Request body
     * @returns {Promise<any>} Response data
     */
    async patch(endpoint, data = {}) {
        return this.request(endpoint, {
            method: 'PATCH',
            body: JSON.stringify(data),
        });
    }

    /**
     * DELETE request
     * @param {string} endpoint - API endpoint
     * @returns {Promise<any>} Response data
     */
    async delete(endpoint) {
        return this.request(endpoint, { method: 'DELETE' });
    }
}

// Create API instance
const api = new APIClient();

// ============================================================================
// API Modules - Organized by feature
// ============================================================================

/**
 * Tasks API
 */
const tasksAPI = {
    /**
     * Get all active tasks
     */
    getActive: () => api.get('/tasks/active/list'),

    /**
     * Get failed tasks
     * @param {number} limit - Max results
     */
    getFailed: (limit = 50) => api.get('/tasks/failed/list', { limit }),

    /**
     * Get task status
     * @param {string} taskId - Task ID
     */
    getStatus: (taskId) => api.get(`/tasks/${taskId}/status`),

    /**
     * Get task statistics
     */
    getStatistics: () => api.get('/tasks/statistics'),

    /**
     * Get worker status
     */
    getWorkerStatus: () => api.get('/tasks/workers/status'),

    /**
     * Scrape a single video
     * @param {string} videoId - YouTube video ID
     * @param {boolean} fetchComments - Whether to fetch comments
     * @param {number} maxComments - Max comments to fetch
     */
    scrapeVideo: (videoId, fetchComments = false, maxComments = 500) =>
        api.post('/tasks/scrape/video', { video_id: videoId, fetch_comments: fetchComments, max_comments: maxComments }),

    /**
     * Scrape multiple videos
     * @param {string[]} videoIds - Array of video IDs
     */
    scrapeVideos: (videoIds) =>
        api.post('/tasks/scrape/videos/batch', { video_ids: videoIds }),

    /**
     * Search and scrape videos
     * @param {string} query - Search query
     * @param {number} maxResults - Max results
     */
    searchAndScrape: (query, maxResults = 20) =>
        api.post('/tasks/scrape/search', { query, max_results: maxResults }),

    /**
     * Scrape channel
     * @param {string} channelId - Channel ID
     * @param {number} maxVideos - Max videos to fetch
     */
    scrapeChannel: (channelId, maxVideos = 50) =>
        api.post('/tasks/scrape/channel', { channel_id: channelId, max_videos: maxVideos }),

    /**
     * Cancel a task
     * @param {string} taskId - Task ID
     */
    cancel: (taskId) => api.delete(`/tasks/${taskId}`),

    /**
     * Retry a failed task
     * @param {string} taskId - Task ID
     */
    retry: (taskId) => api.post(`/tasks/${taskId}/retry`),
};

/**
 * Videos API (if exists)
 */
const videosAPI = {
    /**
     * Get video list
     * @param {object} params - Query parameters
     */
    list: (params = {}) => api.get('/videos', params),

    /**
     * Get video by ID
     * @param {string} videoId - Video ID
     */
    get: (videoId) => api.get(`/videos/${videoId}`),

    /**
     * Search videos
     * @param {string} query - Search query
     * @param {object} params - Additional parameters
     */
    search: (query, params = {}) => api.get('/videos/search', { query, ...params }),
};

/**
 * Captions API
 */
const captionsAPI = {
    /**
     * Get captions for a video
     * @param {string} videoId - Video ID
     */
    getByVideo: (videoId) => api.get(`/captions/video/${videoId}`),

    /**
     * Get available languages
     * @param {string} videoId - Video ID
     */
    getLanguages: (videoId) => api.get(`/captions/video/${videoId}/languages`),

    /**
     * Fetch captions
     * @param {string} videoId - Video ID
     * @param {object} options - Options
     */
    fetch: (videoId, options = {}) =>
        api.post('/captions/fetch', { video_id: videoId, ...options }),

    /**
     * Search captions
     * @param {string} query - Search query
     * @param {object} params - Additional parameters
     */
    search: (query, params = {}) =>
        api.post('/captions/search', { query, ...params }),
};

/**
 * Chat API
 */
const chatAPI = {
    /**
     * Create a new session
     * @param {object} data - Session data
     */
    createSession: (data) => api.post('/chat/sessions', data),

    /**
     * Get session details
     * @param {string} sessionId - Session ID
     */
    getSession: (sessionId) => api.get(`/chat/sessions/${sessionId}`),

    /**
     * Get user sessions
     * @param {string} userId - User ID
     */
    getUserSessions: (userId) => api.get(`/chat/users/${userId}/sessions`),

    /**
     * Send a message
     * @param {string} sessionId - Session ID
     * @param {string} content - Message content
     */
    sendMessage: (sessionId, content) =>
        api.post(`/chat/sessions/${sessionId}/messages`, { content }),

    /**
     * Get session messages
     * @param {string} sessionId - Session ID
     */
    getMessages: (sessionId) => api.get(`/chat/sessions/${sessionId}/messages`),

    /**
     * End a session
     * @param {string} sessionId - Session ID
     */
    endSession: (sessionId) => api.post(`/chat/sessions/${sessionId}/end`),

    /**
     * Get templates
     */
    getTemplates: () => api.get('/chat/templates'),
};

/**
 * RAG API
 */
const ragAPI = {
    /**
     * Generate response
     * @param {string} query - Query string
     * @param {object} options - Options
     */
    generate: (query, options = {}) =>
        api.post('/rag/generate', { query, ...options }),

    /**
     * Search documents
     * @param {string} query - Search query
     * @param {object} params - Parameters
     */
    search: (query, params = {}) =>
        api.post('/rag/search', { query, ...params }),

    /**
     * Get indexes
     */
    getIndexes: () => api.get('/rag/indexes'),
};

/**
 * VQA API
 */
const vqaAPI = {
    /**
     * Create VQA session
     * @param {object} data - Session data
     */
    createSession: (data) => api.post('/vqa/sessions', data),

    /**
     * Ask question
     * @param {string} sessionId - Session ID
     * @param {string} question - Question
     * @param {object} options - Options
     */
    ask: (sessionId, question, options = {}) =>
        api.post(`/vqa/sessions/${sessionId}/ask`, { question, ...options }),

    /**
     * Extract frames
     * @param {string} videoId - Video ID
     * @param {object} options - Options
     */
    extractFrames: (videoId, options = {}) =>
        api.post('/vqa/frames/extract', { video_id: videoId, ...options }),

    /**
     * Get frames for video
     * @param {string} videoId - Video ID
     */
    getFrames: (videoId) => api.get(`/vqa/frames/video/${videoId}`),

    /**
     * Get available models
     */
    getModels: () => api.get('/vqa/models'),
};

/**
 * Health API
 */
const healthAPI = {
    /**
     * Full health check
     */
    check: () => fetch('/health').then(r => r.json()),

    /**
     * Liveness probe
     */
    live: () => fetch('/health/live').then(r => r.json()),

    /**
     * Readiness probe
     */
    ready: () => fetch('/health/ready').then(r => r.json()),

    /**
     * Get metrics
     */
    metrics: () => fetch('/health/metrics').then(r => r.json()),

    /**
     * Get version
     */
    version: () => fetch('/health/version').then(r => r.json()),
};

// Export everything
export {
    APIClient,
    APIError,
    api,
    tasksAPI,
    videosAPI,
    captionsAPI,
    chatAPI,
    ragAPI,
    vqaAPI,
    healthAPI
};

// Make available globally
if (typeof window !== 'undefined') {
    window.api = api;
    window.APIError = APIError;
    window.tasksAPI = tasksAPI;
    window.videosAPI = videosAPI;
    window.captionsAPI = captionsAPI;
    window.chatAPI = chatAPI;
    window.ragAPI = ragAPI;
    window.vqaAPI = vqaAPI;
    window.healthAPI = healthAPI;
}
