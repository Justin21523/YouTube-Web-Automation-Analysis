/**
 * Video Detail Page
 * Individual video view functionality
 */

import { api, videosAPI, captionsAPI, tasksAPI } from '../core/api.js';
import { toast } from '../components/toast.js';
import {
    formatNumber,
    formatDuration,
    formatRelativeTime,
    formatDate,
    getYouTubeThumbnail
} from '../core/utils.js';

class VideoDetailPage {
    constructor() {
        this.videoId = window.VIDEO_ID;
        this.video = null;
        this.captions = null;
        this.comments = [];

        this.init();
    }

    async init() {
        if (!this.videoId) {
            this.showError('No video ID provided');
            return;
        }

        console.log('Loading video:', this.videoId);

        this.bindEvents();
        await this.loadVideo();
    }

    bindEvents() {
        // Tab navigation
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                this.switchTab(e.target.dataset.tab);
            });
        });

        // Action buttons
        document.getElementById('btn-refresh')?.addEventListener('click', () => {
            this.rescrapeVideo();
        });

        document.getElementById('btn-fetch-comments')?.addEventListener('click', () => {
            this.fetchComments();
        });

        document.getElementById('btn-fetch-captions')?.addEventListener('click', () => {
            this.fetchCaptions();
        });

        document.getElementById('btn-ask-ai')?.addEventListener('click', () => {
            this.askAI();
        });

        // Tab content buttons
        document.getElementById('load-comments')?.addEventListener('click', () => {
            this.loadComments();
        });

        document.getElementById('load-captions')?.addEventListener('click', () => {
            this.loadCaptions();
        });
    }

    async loadVideo() {
        try {
            const data = await videosAPI.get(this.videoId);
            this.video = data;
            this.renderVideo();
        } catch (error) {
            console.error('Failed to load video:', error);

            // If 404, try to show basic info from YouTube
            if (error.status === 404) {
                this.showBasicVideoInfo();
            } else {
                this.showError(error.message);
            }
        }
    }

    showBasicVideoInfo() {
        // Show basic info even if not in database
        document.getElementById('loading-state')?.classList.add('hidden');
        document.getElementById('video-content')?.classList.remove('hidden');

        const thumbnailUrl = getYouTubeThumbnail(this.videoId, 'maxres');

        document.getElementById('video-thumbnail').src = thumbnailUrl;
        document.getElementById('video-link').href = `https://www.youtube.com/watch?v=${this.videoId}`;
        document.getElementById('video-title').textContent = 'Video not in database';
        document.getElementById('video-description').textContent = 'This video has not been scraped yet. Click "Re-scrape Video" to fetch its data.';
        document.getElementById('meta-video-id').textContent = this.videoId;

        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    }

    renderVideo() {
        document.getElementById('loading-state')?.classList.add('hidden');
        document.getElementById('video-content')?.classList.remove('hidden');

        const v = this.video;

        // Thumbnail and link
        const thumbnailUrl = v.thumbnail_url || getYouTubeThumbnail(this.videoId, 'maxres');
        document.getElementById('video-thumbnail').src = thumbnailUrl;
        document.getElementById('video-link').href = `https://www.youtube.com/watch?v=${this.videoId}`;

        // Title and stats
        document.getElementById('video-title').textContent = v.title || 'Untitled';
        document.getElementById('video-views').textContent = formatNumber(v.view_count || 0);
        document.getElementById('video-likes').textContent = formatNumber(v.like_count || 0);
        document.getElementById('video-comments').textContent = formatNumber(v.comment_count || 0);
        document.getElementById('video-published').textContent = formatRelativeTime(v.published_at);

        // Channel info
        document.getElementById('channel-name').textContent = v.channel_title || v.channel_name || 'Unknown';
        document.getElementById('channel-subscribers').textContent =
            v.channel_subscriber_count ? `${formatNumber(v.channel_subscriber_count)} subscribers` : 'Subscribers unknown';

        // Metadata
        document.getElementById('meta-video-id').textContent = this.videoId;
        document.getElementById('meta-duration').textContent = formatDuration(v.duration_seconds || v.duration || 0);
        document.getElementById('meta-category').textContent = v.category || '--';
        document.getElementById('meta-scraped').textContent = formatRelativeTime(v.scraped_at || v.created_at);

        // Description
        document.getElementById('video-description').textContent = v.description || 'No description available';

        // Tags
        this.renderTags(v.tags || []);

        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    }

    renderTags(tags) {
        const container = document.getElementById('tags-list');
        if (!container) return;

        if (!tags || tags.length === 0) {
            container.innerHTML = '<span class="text-slate-400">No tags available</span>';
            return;
        }

        container.innerHTML = tags.map(tag => `
            <span class="px-3 py-1 bg-dark-tertiary rounded-full text-sm text-slate-300">
                ${tag}
            </span>
        `).join('');
    }

    showError(message) {
        document.getElementById('loading-state')?.classList.add('hidden');
        document.getElementById('error-state')?.classList.remove('hidden');
        document.getElementById('error-message').textContent = message;

        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    }

    switchTab(tabName) {
        // Update tab buttons
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tabName);
        });

        // Update tab content
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.add('hidden');
        });

        document.getElementById(`tab-${tabName}`)?.classList.remove('hidden');
    }

    async rescrapeVideo() {
        try {
            toast.info('Starting video scrape...');
            await tasksAPI.scrapeVideo(this.videoId, false, 0);
            toast.success('Scraping task started');
        } catch (error) {
            toast.error(`Failed to start scraping: ${error.message}`);
        }
    }

    async fetchComments() {
        try {
            toast.info('Fetching comments...');
            await tasksAPI.scrapeVideo(this.videoId, true, 500);
            toast.success('Comment fetch task started');
        } catch (error) {
            toast.error(`Failed to fetch comments: ${error.message}`);
        }
    }

    async fetchCaptions() {
        try {
            toast.info('Fetching captions...');
            await captionsAPI.fetch(this.videoId);
            toast.success('Caption fetch started');
        } catch (error) {
            toast.error(`Failed to fetch captions: ${error.message}`);
        }
    }

    async loadComments() {
        const container = document.getElementById('comments-list');
        if (!container) return;

        container.innerHTML = `
            <div class="text-center py-8">
                <i data-lucide="loader" class="w-8 h-8 mx-auto text-blue-500 animate-spin"></i>
                <p class="mt-2 text-slate-400">Loading comments...</p>
            </div>
        `;

        try {
            // This would need a comments endpoint
            const data = await api.get(`/videos/${this.videoId}/comments`);
            this.comments = data?.items || data || [];

            if (this.comments.length === 0) {
                container.innerHTML = `
                    <div class="text-center py-8 text-slate-400">
                        <i data-lucide="message-circle" class="w-8 h-8 mx-auto mb-2"></i>
                        <p>No comments found</p>
                        <button onclick="videoDetailPage.fetchComments()" class="btn btn-secondary mt-4">
                            Fetch Comments
                        </button>
                    </div>
                `;
            } else {
                container.innerHTML = this.comments.map(c => this.renderComment(c)).join('');
            }
        } catch (error) {
            console.error('Failed to load comments:', error);
            container.innerHTML = `
                <div class="text-center py-8 text-slate-400">
                    <i data-lucide="alert-circle" class="w-8 h-8 mx-auto mb-2"></i>
                    <p>Comments not available</p>
                    <button onclick="videoDetailPage.fetchComments()" class="btn btn-secondary mt-4">
                        Fetch Comments
                    </button>
                </div>
            `;
        }

        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    }

    renderComment(comment) {
        return `
            <div class="p-4 bg-dark-tertiary rounded-lg">
                <div class="flex items-start gap-3">
                    <div class="w-10 h-10 rounded-full bg-slate-700 flex items-center justify-center">
                        <i data-lucide="user" class="w-5 h-5 text-slate-400"></i>
                    </div>
                    <div class="flex-1">
                        <div class="flex items-center gap-2">
                            <span class="font-medium">${comment.author || 'Anonymous'}</span>
                            <span class="text-xs text-slate-400">${formatRelativeTime(comment.published_at)}</span>
                        </div>
                        <p class="mt-1 text-slate-300">${comment.text || comment.content || ''}</p>
                        <div class="flex items-center gap-4 mt-2 text-sm text-slate-400">
                            <span class="flex items-center gap-1">
                                <i data-lucide="thumbs-up" class="w-3 h-3"></i>
                                ${formatNumber(comment.like_count || 0)}
                            </span>
                            ${comment.reply_count ? `
                                <span class="flex items-center gap-1">
                                    <i data-lucide="message-circle" class="w-3 h-3"></i>
                                    ${comment.reply_count} replies
                                </span>
                            ` : ''}
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    async loadCaptions() {
        const container = document.getElementById('captions-content');
        if (!container) return;

        container.innerHTML = `
            <div class="text-center py-8">
                <i data-lucide="loader" class="w-8 h-8 mx-auto text-blue-500 animate-spin"></i>
                <p class="mt-2 text-slate-400">Loading captions...</p>
            </div>
        `;

        try {
            const data = await captionsAPI.getByVideo(this.videoId);
            this.captions = data?.captions || data || [];

            if (!this.captions || this.captions.length === 0) {
                container.innerHTML = `
                    <div class="text-center py-8 text-slate-400">
                        <i data-lucide="subtitles" class="w-8 h-8 mx-auto mb-2"></i>
                        <p>No captions available</p>
                        <button onclick="videoDetailPage.fetchCaptions()" class="btn btn-secondary mt-4">
                            Fetch Captions
                        </button>
                    </div>
                `;
            } else {
                this.renderCaptions();
            }
        } catch (error) {
            console.error('Failed to load captions:', error);
            container.innerHTML = `
                <div class="text-center py-8 text-slate-400">
                    <i data-lucide="alert-circle" class="w-8 h-8 mx-auto mb-2"></i>
                    <p>Captions not available</p>
                    <button onclick="videoDetailPage.fetchCaptions()" class="btn btn-secondary mt-4">
                        Fetch Captions
                    </button>
                </div>
            `;
        }

        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    }

    renderCaptions() {
        const container = document.getElementById('captions-content');
        if (!container || !this.captions) return;

        // Group by language if multiple
        const languages = [...new Set(this.captions.map(c => c.language || 'unknown'))];

        let html = '';

        if (languages.length > 1) {
            html += `
                <div class="mb-4">
                    <label class="text-sm text-slate-400">Language:</label>
                    <select id="caption-language" class="input ml-2" onchange="videoDetailPage.filterCaptions(this.value)">
                        ${languages.map(lang => `<option value="${lang}">${lang}</option>`).join('')}
                    </select>
                </div>
            `;
        }

        html += `<div id="caption-text" class="space-y-2 max-h-96 overflow-y-auto">`;

        this.captions.forEach(caption => {
            const startTime = formatDuration(caption.start || 0);
            html += `
                <div class="flex gap-3 p-2 hover:bg-dark-tertiary rounded transition-colors caption-item" data-language="${caption.language || 'unknown'}">
                    <span class="text-xs text-blue-500 font-mono w-16 flex-shrink-0">${startTime}</span>
                    <span class="text-sm">${caption.text || ''}</span>
                </div>
            `;
        });

        html += `</div>`;

        container.innerHTML = html;
    }

    filterCaptions(language) {
        document.querySelectorAll('.caption-item').forEach(item => {
            item.classList.toggle('hidden', item.dataset.language !== language);
        });
    }

    askAI() {
        // Navigate to chat with video context
        window.location.href = `/chat?video=${this.videoId}`;
    }
}

// Initialize page
const videoDetailPage = new VideoDetailPage();
window.videoDetailPage = videoDetailPage;

export { VideoDetailPage, videoDetailPage };
