/**
 * Video Search Page
 * YouTube search and batch scraping functionality
 */

import { api, tasksAPI } from '../core/api.js';
import { toast } from '../components/toast.js';
import {
    formatNumber,
    formatDuration,
    getYouTubeThumbnail,
    extractVideoId,
    debounce
} from '../core/utils.js';

class SearchPage {
    constructor() {
        this.results = [];
        this.selectedVideos = new Set();
        this.searchHistory = this.loadSearchHistory();

        this.init();
    }

    async init() {
        console.log('Initializing Search Page...');

        this.bindEvents();
        this.renderSearchHistory();

        // Check for initial query
        if (window.INITIAL_QUERY) {
            document.getElementById('search-query').value = window.INITIAL_QUERY;
            this.performSearch();
        }

        console.log('Search Page initialized');
    }

    bindEvents() {
        // Search form
        document.getElementById('search-form')?.addEventListener('submit', (e) => {
            e.preventDefault();
            this.performSearch();
        });

        // Clear history
        document.getElementById('clear-history')?.addEventListener('click', () => {
            this.clearSearchHistory();
        });

        // Scrape selected
        document.getElementById('scrape-selected')?.addEventListener('click', () => {
            this.scrapeSelected();
        });
    }

    loadSearchHistory() {
        try {
            return JSON.parse(localStorage.getItem('searchHistory') || '[]');
        } catch {
            return [];
        }
    }

    saveSearchHistory() {
        localStorage.setItem('searchHistory', JSON.stringify(this.searchHistory.slice(0, 10)));
    }

    renderSearchHistory() {
        const container = document.getElementById('search-history');
        if (!container) return;

        if (this.searchHistory.length === 0) {
            container.innerHTML = '<span class="text-slate-400 text-sm">No recent searches</span>';
            return;
        }

        container.innerHTML = this.searchHistory.map(query => `
            <button class="px-3 py-1.5 bg-dark-tertiary hover:bg-slate-700 rounded-full text-sm transition-colors"
                onclick="searchPage.searchFromHistory('${query.replace(/'/g, "\\'")}')">
                ${query}
            </button>
        `).join('');
    }

    searchFromHistory(query) {
        document.getElementById('search-query').value = query;
        this.performSearch();
    }

    clearSearchHistory() {
        this.searchHistory = [];
        this.saveSearchHistory();
        this.renderSearchHistory();
        toast.info('Search history cleared');
    }

    async performSearch() {
        const query = document.getElementById('search-query')?.value?.trim();

        if (!query) {
            toast.warning('Please enter a search query');
            return;
        }

        // Check if it's a video URL/ID
        const videoId = extractVideoId(query);
        if (videoId) {
            // Direct scrape
            await this.scrapeDirectVideo(videoId);
            return;
        }

        // Add to history
        if (!this.searchHistory.includes(query)) {
            this.searchHistory.unshift(query);
            this.saveSearchHistory();
            this.renderSearchHistory();
        }

        // Show UI
        document.getElementById('results-section')?.classList.remove('hidden');
        document.getElementById('tips-section')?.classList.add('hidden');

        // Show loading
        document.getElementById('results-loading')?.classList.remove('hidden');
        document.getElementById('results-container')?.classList.add('hidden');
        document.getElementById('no-results')?.classList.add('hidden');

        const maxResults = parseInt(document.getElementById('max-results')?.value) || 20;
        const autoScrape = document.getElementById('auto-scrape')?.checked || false;

        try {
            // Use the search and scrape endpoint
            if (autoScrape) {
                const result = await tasksAPI.searchAndScrape(query, maxResults);
                toast.success(`Search task started for "${query}"`);

                // Show placeholder results
                this.showSearchInProgress(query, maxResults);
            } else {
                // Just search (would need a search-only endpoint)
                // For now, we'll use the scrape endpoint and show results
                const result = await tasksAPI.searchAndScrape(query, maxResults);
                toast.success(`Searching and scraping "${query}"...`);
                this.showSearchInProgress(query, maxResults);
            }

        } catch (error) {
            console.error('Search failed:', error);
            toast.error(`Search failed: ${error.message}`);

            document.getElementById('results-loading')?.classList.add('hidden');
            document.getElementById('no-results')?.classList.remove('hidden');
        }
    }

    showSearchInProgress(query, maxResults) {
        document.getElementById('results-loading')?.classList.add('hidden');

        const container = document.getElementById('results-container');
        if (!container) return;

        container.classList.remove('hidden');
        container.innerHTML = `
            <div class="col-span-full bg-dark-secondary rounded-xl p-8 text-center border border-slate-700">
                <div class="w-16 h-16 mx-auto mb-4 rounded-full bg-blue-500/20 flex items-center justify-center">
                    <i data-lucide="loader" class="w-8 h-8 text-blue-500 animate-spin"></i>
                </div>
                <h3 class="text-lg font-semibold mb-2">Search Task Started</h3>
                <p class="text-slate-400 mb-4">
                    Searching YouTube for "${query}" and scraping up to ${maxResults} videos...
                </p>
                <p class="text-sm text-slate-500">
                    Check the <a href="/tasks" class="text-blue-500 hover:underline">Tasks page</a> for progress
                </p>
            </div>
        `;

        document.getElementById('results-count').textContent = 'Task started';

        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    }

    async scrapeDirectVideo(videoId) {
        toast.info(`Scraping video: ${videoId}`);

        try {
            await tasksAPI.scrapeVideo(videoId, false, 0);
            toast.success('Scraping task started');

            // Show result
            document.getElementById('results-section')?.classList.remove('hidden');
            document.getElementById('tips-section')?.classList.add('hidden');
            document.getElementById('results-loading')?.classList.add('hidden');

            const container = document.getElementById('results-container');
            if (container) {
                container.classList.remove('hidden');
                container.innerHTML = `
                    <div class="col-span-full bg-dark-secondary rounded-xl overflow-hidden border border-slate-700">
                        <div class="flex gap-4 p-4">
                            <img src="${getYouTubeThumbnail(videoId)}"
                                class="w-48 aspect-video object-cover rounded-lg"
                                alt="Video thumbnail">
                            <div class="flex-1">
                                <h3 class="font-semibold mb-2">Video ID: ${videoId}</h3>
                                <p class="text-slate-400 text-sm mb-4">
                                    Scraping task has been started. Check the Tasks page for progress.
                                </p>
                                <div class="flex gap-2">
                                    <a href="/videos/${videoId}" class="btn btn-primary btn-sm">
                                        View Details
                                    </a>
                                    <a href="/tasks" class="btn btn-secondary btn-sm">
                                        View Tasks
                                    </a>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
            }

            document.getElementById('results-count').textContent = '1 video';

        } catch (error) {
            toast.error(`Failed to scrape: ${error.message}`);
        }
    }

    renderResults() {
        const container = document.getElementById('results-container');
        if (!container) return;

        document.getElementById('results-loading')?.classList.add('hidden');

        if (this.results.length === 0) {
            container.classList.add('hidden');
            document.getElementById('no-results')?.classList.remove('hidden');
            return;
        }

        container.classList.remove('hidden');
        document.getElementById('no-results')?.classList.add('hidden');

        container.innerHTML = this.results.map(video => this.renderResultCard(video)).join('');

        // Update count
        document.getElementById('results-count').textContent = `${this.results.length} results`;

        // Update selection
        this.updateSelectionUI();

        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    }

    renderResultCard(video) {
        const videoId = video.video_id || video.id;
        const isSelected = this.selectedVideos.has(videoId);

        return `
            <div class="video-result bg-dark-secondary rounded-xl overflow-hidden border ${isSelected ? 'border-blue-500' : 'border-slate-700'} transition-all cursor-pointer"
                onclick="searchPage.toggleSelection('${videoId}')"
                data-video-id="${videoId}">
                <div class="relative aspect-video">
                    <img src="${video.thumbnail_url || getYouTubeThumbnail(videoId)}"
                        class="w-full h-full object-cover"
                        onerror="this.src='https://via.placeholder.com/320x180?text=No+Thumbnail'">
                    <span class="absolute bottom-2 right-2 px-1.5 py-0.5 bg-black/80 text-white text-xs rounded">
                        ${formatDuration(video.duration || 0)}
                    </span>
                    ${isSelected ? `
                        <div class="absolute top-2 right-2 w-6 h-6 bg-blue-500 rounded-full flex items-center justify-center">
                            <i data-lucide="check" class="w-4 h-4 text-white"></i>
                        </div>
                    ` : ''}
                </div>
                <div class="p-3">
                    <h3 class="font-medium text-sm line-clamp-2">${video.title || 'Untitled'}</h3>
                    <p class="text-xs text-slate-400 mt-1 truncate">${video.channel_title || 'Unknown Channel'}</p>
                    <div class="flex items-center gap-2 mt-2 text-xs text-slate-500">
                        <span>${formatNumber(video.view_count || 0)} views</span>
                    </div>
                </div>
            </div>
        `;
    }

    toggleSelection(videoId) {
        if (this.selectedVideos.has(videoId)) {
            this.selectedVideos.delete(videoId);
        } else {
            this.selectedVideos.add(videoId);
        }

        this.updateSelectionUI();

        // Update card visual
        const card = document.querySelector(`[data-video-id="${videoId}"]`);
        if (card) {
            const isSelected = this.selectedVideos.has(videoId);
            card.classList.toggle('border-blue-500', isSelected);
            card.classList.toggle('border-slate-700', !isSelected);
        }
    }

    updateSelectionUI() {
        const count = this.selectedVideos.size;
        const scrapeBtn = document.getElementById('scrape-selected');
        const countSpan = document.getElementById('selected-count');

        if (scrapeBtn) {
            scrapeBtn.classList.toggle('hidden', count === 0);
        }

        if (countSpan) {
            countSpan.textContent = count;
        }
    }

    async scrapeSelected() {
        const videoIds = Array.from(this.selectedVideos);

        if (videoIds.length === 0) {
            toast.warning('No videos selected');
            return;
        }

        try {
            await tasksAPI.scrapeVideos(videoIds);
            toast.success(`Started scraping ${videoIds.length} videos`);

            // Clear selection
            this.selectedVideos.clear();
            this.updateSelectionUI();

        } catch (error) {
            toast.error(`Failed to start batch scrape: ${error.message}`);
        }
    }
}

// Initialize page
const searchPage = new SearchPage();
window.searchPage = searchPage;

export { SearchPage, searchPage };
