/**
 * Videos List Page
 * Video listing and management functionality
 */

import { api, videosAPI, tasksAPI } from '../core/api.js';
import { toast } from '../components/toast.js';
import {
    formatNumber,
    formatDuration,
    formatRelativeTime,
    getYouTubeThumbnail,
    extractVideoId,
    debounce
} from '../core/utils.js';

class VideosPage {
    constructor() {
        this.videos = [];
        this.currentPage = 1;
        this.pageSize = 20;
        this.totalCount = 0;
        this.viewMode = 'grid'; // 'grid' or 'list'
        this.filters = {
            search: '',
            sort: '-scraped_at'
        };

        this.init();
    }

    async init() {
        console.log('Initializing Videos Page...');

        this.bindEvents();
        await this.loadVideos();

        console.log('Videos Page initialized');
    }

    bindEvents() {
        // Search input with debounce
        const searchInput = document.getElementById('filter-search');
        if (searchInput) {
            searchInput.addEventListener('input', debounce((e) => {
                this.filters.search = e.target.value;
                this.currentPage = 1;
                this.loadVideos();
            }, 300));
        }

        // Sort select
        document.getElementById('filter-sort')?.addEventListener('change', (e) => {
            this.filters.sort = e.target.value;
            this.currentPage = 1;
            this.loadVideos();
        });

        // View toggles
        document.getElementById('view-grid')?.addEventListener('click', () => {
            this.setViewMode('grid');
        });

        document.getElementById('view-list')?.addEventListener('click', () => {
            this.setViewMode('list');
        });

        // Scrape modal
        document.getElementById('scrape-new')?.addEventListener('click', () => {
            this.openScrapeModal();
        });

        document.getElementById('empty-scrape')?.addEventListener('click', () => {
            this.openScrapeModal();
        });

        document.querySelectorAll('.close-modal').forEach(btn => {
            btn.addEventListener('click', () => this.closeScrapeModal());
        });

        document.getElementById('submit-scrape')?.addEventListener('click', () => {
            this.submitScrape();
        });

        // Comments checkbox toggle
        document.getElementById('fetch-comments')?.addEventListener('change', (e) => {
            const options = document.getElementById('comments-options');
            if (options) {
                options.classList.toggle('hidden', !e.target.checked);
            }
        });

        // Modal backdrop click
        document.getElementById('scrape-modal')?.addEventListener('click', (e) => {
            if (e.target.id === 'scrape-modal') {
                this.closeScrapeModal();
            }
        });

        // Pagination
        document.getElementById('page-prev')?.addEventListener('click', () => {
            if (this.currentPage > 1) {
                this.currentPage--;
                this.loadVideos();
            }
        });

        document.getElementById('page-next')?.addEventListener('click', () => {
            const totalPages = Math.ceil(this.totalCount / this.pageSize);
            if (this.currentPage < totalPages) {
                this.currentPage++;
                this.loadVideos();
            }
        });
    }

    async loadVideos() {
        const container = document.getElementById('videos-container');
        const emptyState = document.getElementById('empty-state');
        const pagination = document.getElementById('pagination');

        if (!container) return;

        // Show loading
        container.innerHTML = `
            <div class="col-span-full text-center py-12">
                <i data-lucide="loader" class="w-10 h-10 mx-auto text-blue-500 animate-spin"></i>
                <p class="mt-4 text-slate-400">Loading videos...</p>
            </div>
        `;

        try {
            const params = {
                skip: (this.currentPage - 1) * this.pageSize,
                limit: this.pageSize,
                sort: this.filters.sort
            };

            if (this.filters.search) {
                params.search = this.filters.search;
            }

            const data = await videosAPI.list(params);
            this.videos = data?.items || data || [];
            this.totalCount = data?.total || this.videos.length;

            if (this.videos.length === 0) {
                container.innerHTML = '';
                container.classList.add('hidden');
                emptyState?.classList.remove('hidden');
                pagination?.classList.add('hidden');
            } else {
                container.classList.remove('hidden');
                emptyState?.classList.add('hidden');
                this.renderVideos();
                this.updatePagination();
            }

            // Update count
            const countEl = document.getElementById('video-count');
            if (countEl) {
                countEl.textContent = `${this.totalCount} video${this.totalCount !== 1 ? 's' : ''}`;
            }

        } catch (error) {
            console.error('Failed to load videos:', error);

            // Check if it's a 404 (endpoint doesn't exist yet)
            if (error.status === 404) {
                container.innerHTML = `
                    <div class="col-span-full text-center py-12">
                        <i data-lucide="database" class="w-12 h-12 mx-auto text-slate-500 mb-4"></i>
                        <p class="text-slate-400">Videos API endpoint not available</p>
                        <p class="text-sm text-slate-500 mt-2">The backend may need a videos router</p>
                    </div>
                `;
            } else {
                container.innerHTML = `
                    <div class="col-span-full text-center py-12">
                        <i data-lucide="alert-circle" class="w-12 h-12 mx-auto text-red-500 mb-4"></i>
                        <p class="text-slate-400">Failed to load videos</p>
                        <p class="text-sm text-slate-500 mt-2">${error.message}</p>
                        <button onclick="videosPage.loadVideos()" class="btn btn-secondary mt-4">
                            Try Again
                        </button>
                    </div>
                `;
            }
        }

        // Reinitialize icons
        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    }

    renderVideos() {
        const container = document.getElementById('videos-container');
        if (!container) return;

        if (this.viewMode === 'grid') {
            container.className = 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4';
            container.innerHTML = this.videos.map(v => this.renderVideoCard(v)).join('');
        } else {
            container.className = 'space-y-3';
            container.innerHTML = this.videos.map(v => this.renderVideoRow(v)).join('');
        }

        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    }

    renderVideoCard(video) {
        const thumbnailUrl = video.thumbnail_url || getYouTubeThumbnail(video.video_id || video.id);
        const duration = formatDuration(video.duration_seconds || video.duration || 0);
        const views = formatNumber(video.view_count || video.views || 0);
        const videoId = video.video_id || video.id;

        return `
            <a href="/videos/${videoId}" class="video-card group bg-dark-secondary rounded-xl overflow-hidden border border-slate-700 hover:border-blue-500/50 transition-all">
                <div class="relative aspect-video">
                    <img src="${thumbnailUrl}" alt="${video.title || 'Video'}"
                        class="w-full h-full object-cover"
                        onerror="this.src='https://via.placeholder.com/320x180?text=No+Thumbnail'">
                    <span class="absolute bottom-2 right-2 px-1.5 py-0.5 bg-black/80 text-white text-xs rounded">
                        ${duration}
                    </span>
                </div>
                <div class="p-3">
                    <h3 class="font-medium text-sm line-clamp-2 group-hover:text-blue-400 transition-colors">
                        ${video.title || 'Untitled'}
                    </h3>
                    <p class="text-xs text-slate-400 mt-1 truncate">
                        ${video.channel_title || video.channel_name || 'Unknown Channel'}
                    </p>
                    <div class="flex items-center gap-2 mt-2 text-xs text-slate-500">
                        <span>${views} views</span>
                        <span>•</span>
                        <span>${formatRelativeTime(video.published_at || video.scraped_at)}</span>
                    </div>
                </div>
            </a>
        `;
    }

    renderVideoRow(video) {
        const thumbnailUrl = video.thumbnail_url || getYouTubeThumbnail(video.video_id || video.id);
        const duration = formatDuration(video.duration_seconds || video.duration || 0);
        const views = formatNumber(video.view_count || video.views || 0);
        const videoId = video.video_id || video.id;

        return `
            <a href="/videos/${videoId}" class="flex gap-4 p-3 bg-dark-secondary rounded-xl border border-slate-700 hover:border-blue-500/50 transition-all group">
                <div class="relative w-48 flex-shrink-0">
                    <img src="${thumbnailUrl}" alt="${video.title || 'Video'}"
                        class="w-full aspect-video object-cover rounded-lg"
                        onerror="this.src='https://via.placeholder.com/192x108?text=No+Thumbnail'">
                    <span class="absolute bottom-1 right-1 px-1.5 py-0.5 bg-black/80 text-white text-xs rounded">
                        ${duration}
                    </span>
                </div>
                <div class="flex-1 min-w-0 py-1">
                    <h3 class="font-medium line-clamp-2 group-hover:text-blue-400 transition-colors">
                        ${video.title || 'Untitled'}
                    </h3>
                    <p class="text-sm text-slate-400 mt-1">
                        ${video.channel_title || video.channel_name || 'Unknown Channel'}
                    </p>
                    <div class="flex items-center gap-3 mt-2 text-sm text-slate-500">
                        <span class="flex items-center gap-1">
                            <i data-lucide="eye" class="w-3 h-3"></i>
                            ${views}
                        </span>
                        <span class="flex items-center gap-1">
                            <i data-lucide="thumbs-up" class="w-3 h-3"></i>
                            ${formatNumber(video.like_count || 0)}
                        </span>
                        <span>${formatRelativeTime(video.published_at || video.scraped_at)}</span>
                    </div>
                </div>
            </a>
        `;
    }

    setViewMode(mode) {
        this.viewMode = mode;

        // Update toggle buttons
        document.querySelectorAll('.view-toggle').forEach(btn => {
            btn.classList.toggle('active', btn.id === `view-${mode}`);
        });

        this.renderVideos();
    }

    updatePagination() {
        const pagination = document.getElementById('pagination');
        const pageNumbers = document.getElementById('page-numbers');
        const prevBtn = document.getElementById('page-prev');
        const nextBtn = document.getElementById('page-next');
        const pageInfo = document.getElementById('page-info');

        const totalPages = Math.ceil(this.totalCount / this.pageSize);

        if (totalPages <= 1) {
            pagination?.classList.add('hidden');
            return;
        }

        pagination?.classList.remove('hidden');

        // Update buttons
        if (prevBtn) prevBtn.disabled = this.currentPage === 1;
        if (nextBtn) nextBtn.disabled = this.currentPage === totalPages;

        // Update page info
        if (pageInfo) {
            pageInfo.textContent = `Page ${this.currentPage} of ${totalPages}`;
        }

        // Update page numbers
        if (pageNumbers) {
            let html = '';
            const maxVisible = 5;
            let start = Math.max(1, this.currentPage - Math.floor(maxVisible / 2));
            let end = Math.min(totalPages, start + maxVisible - 1);

            if (end - start < maxVisible - 1) {
                start = Math.max(1, end - maxVisible + 1);
            }

            for (let i = start; i <= end; i++) {
                html += `
                    <button class="px-3 py-1 rounded ${i === this.currentPage ? 'bg-blue-600 text-white' : 'hover:bg-dark-tertiary'}"
                        onclick="videosPage.goToPage(${i})">
                        ${i}
                    </button>
                `;
            }

            pageNumbers.innerHTML = html;
        }
    }

    goToPage(page) {
        this.currentPage = page;
        this.loadVideos();
    }

    openScrapeModal() {
        document.getElementById('scrape-modal')?.classList.remove('hidden');
        document.getElementById('scrape-input')?.focus();
        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    }

    closeScrapeModal() {
        document.getElementById('scrape-modal')?.classList.add('hidden');
        document.getElementById('scrape-input').value = '';
        document.getElementById('fetch-comments').checked = false;
        document.getElementById('comments-options')?.classList.add('hidden');
    }

    async submitScrape() {
        const input = document.getElementById('scrape-input');
        const value = input?.value?.trim();

        if (!value) {
            toast.warning('Please enter a video URL or ID');
            return;
        }

        const videoId = extractVideoId(value);
        if (!videoId) {
            toast.error('Invalid YouTube URL or video ID');
            return;
        }

        const fetchComments = document.getElementById('fetch-comments')?.checked || false;
        const maxComments = parseInt(document.getElementById('max-comments')?.value) || 500;

        try {
            await tasksAPI.scrapeVideo(videoId, fetchComments, maxComments);
            toast.success(`Scraping started for video: ${videoId}`);
            this.closeScrapeModal();
        } catch (error) {
            toast.error(`Failed to start scraping: ${error.message}`);
        }
    }
}

// Initialize page
const videosPage = new VideosPage();
window.videosPage = videosPage;

export { VideosPage, videosPage };
