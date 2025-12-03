/**
 * Tasks Page
 * Task management and monitoring functionality
 */

import { tasksAPI } from '../core/api.js';
import { toast } from '../components/toast.js';
import { formatRelativeTime, formatDuration, extractVideoId } from '../core/utils.js';

class TasksPage {
    constructor() {
        this.activeTasks = [];
        this.failedTasks = [];
        this.workers = [];
        this.refreshInterval = null;
        this.modalType = null;

        this.init();
    }

    async init() {
        console.log('Initializing Tasks Page...');

        this.bindEvents();
        await this.loadAllData();
        this.startAutoRefresh();

        console.log('Tasks Page initialized');
    }

    bindEvents() {
        // Refresh button
        document.getElementById('refresh-tasks')?.addEventListener('click', () => {
            this.loadAllData();
            toast.info('Refreshing tasks...');
        });

        // Quick actions
        document.getElementById('quick-scrape')?.addEventListener('click', () => {
            this.openModal('scrape');
        });

        document.getElementById('quick-search')?.addEventListener('click', () => {
            this.openModal('search');
        });

        document.getElementById('quick-channel')?.addEventListener('click', () => {
            this.openModal('channel');
        });

        // Clear failed
        document.getElementById('clear-failed')?.addEventListener('click', () => {
            this.clearFailedTasks();
        });

        // Modal
        document.querySelectorAll('.close-modal').forEach(btn => {
            btn.addEventListener('click', () => this.closeModal());
        });

        document.getElementById('task-modal')?.addEventListener('click', (e) => {
            if (e.target.id === 'task-modal') this.closeModal();
        });

        document.getElementById('modal-submit')?.addEventListener('click', () => {
            this.submitModal();
        });
    }

    async loadAllData() {
        await Promise.all([
            this.loadActiveTasks(),
            this.loadFailedTasks(),
            this.loadWorkers(),
            this.loadStatistics()
        ]);
    }

    async loadActiveTasks() {
        const container = document.getElementById('active-tasks');
        if (!container) return;

        try {
            const data = await tasksAPI.getActive();
            this.activeTasks = data?.celery_active || [];
            const reserved = data?.celery_reserved || [];

            // Update stats
            document.getElementById('stat-active').textContent = this.activeTasks.length;
            document.getElementById('stat-reserved').textContent = reserved.length;
            document.getElementById('active-count').textContent =
                `${this.activeTasks.length} active, ${reserved.length} reserved`;

            if (this.activeTasks.length === 0 && reserved.length === 0) {
                container.innerHTML = `
                    <div class="text-center py-8 text-slate-400">
                        <i data-lucide="check-circle" class="w-8 h-8 mx-auto mb-2"></i>
                        <p>No active tasks</p>
                    </div>
                `;
            } else {
                container.innerHTML = [
                    ...this.activeTasks.map(t => this.renderActiveTask(t, 'running')),
                    ...reserved.map(t => this.renderActiveTask(t, 'reserved'))
                ].join('');
            }

        } catch (error) {
            console.error('Failed to load active tasks:', error);
            container.innerHTML = `
                <div class="text-center py-8 text-slate-400">
                    <i data-lucide="alert-circle" class="w-8 h-8 mx-auto mb-2"></i>
                    <p>Failed to load tasks</p>
                </div>
            `;
        }

        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    }

    renderActiveTask(task, status) {
        const statusColors = {
            running: 'bg-blue-500',
            reserved: 'bg-yellow-500',
            pending: 'bg-gray-500'
        };

        const statusIcons = {
            running: 'loader',
            reserved: 'clock',
            pending: 'circle'
        };

        const taskName = task.name?.split('.').pop() || 'Unknown';

        return `
            <div class="flex items-center gap-3 p-3 bg-dark-tertiary rounded-lg">
                <div class="w-10 h-10 rounded-lg ${statusColors[status]}/20 flex items-center justify-center">
                    <i data-lucide="${statusIcons[status]}"
                       class="w-5 h-5 ${statusColors[status].replace('bg-', 'text-')} ${status === 'running' ? 'animate-spin' : ''}"></i>
                </div>
                <div class="flex-1 min-w-0">
                    <p class="font-medium truncate">${taskName}</p>
                    <p class="text-xs text-slate-400 truncate">
                        ID: ${task.id?.substring(0, 12) || '--'}...
                    </p>
                </div>
                <div class="flex items-center gap-2">
                    <span class="px-2 py-1 rounded-full text-xs ${statusColors[status]}/20 ${statusColors[status].replace('bg-', 'text-')}">
                        ${status}
                    </span>
                    <button class="p-1 hover:bg-slate-700 rounded transition-colors"
                        onclick="tasksPage.cancelTask('${task.id}')" title="Cancel task">
                        <i data-lucide="x" class="w-4 h-4 text-slate-400 hover:text-red-400"></i>
                    </button>
                </div>
            </div>
        `;
    }

    async loadFailedTasks() {
        const container = document.getElementById('failed-tasks');
        if (!container) return;

        try {
            const data = await tasksAPI.getFailed(20);
            this.failedTasks = data?.failed_tasks || [];

            document.getElementById('stat-failed').textContent = this.failedTasks.length;

            if (this.failedTasks.length === 0) {
                container.innerHTML = `
                    <div class="text-center py-8 text-slate-400">
                        <i data-lucide="check-circle" class="w-8 h-8 mx-auto mb-2"></i>
                        <p>No failed tasks</p>
                    </div>
                `;
            } else {
                container.innerHTML = this.failedTasks.map(t => this.renderFailedTask(t)).join('');
            }

        } catch (error) {
            console.error('Failed to load failed tasks:', error);
        }

        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    }

    renderFailedTask(task) {
        const taskName = task.name?.split('.').pop() || 'Unknown';
        const errorMsg = task.exception?.substring(0, 100) || 'Unknown error';

        return `
            <div class="p-3 bg-dark-tertiary rounded-lg border-l-4 border-red-500">
                <div class="flex items-start justify-between">
                    <div class="flex-1 min-w-0">
                        <p class="font-medium truncate">${taskName}</p>
                        <p class="text-xs text-red-400 mt-1 truncate">${errorMsg}</p>
                        <p class="text-xs text-slate-500 mt-1">
                            ${formatRelativeTime(task.timestamp)}
                        </p>
                    </div>
                    <div class="flex items-center gap-2">
                        <button class="p-1 hover:bg-slate-700 rounded transition-colors"
                            onclick="tasksPage.retryTask('${task.id}')" title="Retry">
                            <i data-lucide="refresh-cw" class="w-4 h-4 text-slate-400 hover:text-blue-400"></i>
                        </button>
                    </div>
                </div>
            </div>
        `;
    }

    async loadWorkers() {
        const container = document.getElementById('workers-list');
        if (!container) return;

        try {
            const data = await tasksAPI.getWorkerStatus();
            this.workers = data?.workers || [];

            document.getElementById('stat-workers').textContent = this.workers.length;

            if (this.workers.length === 0) {
                container.innerHTML = `
                    <div class="text-center py-4 text-slate-400">
                        <i data-lucide="alert-circle" class="w-6 h-6 mx-auto mb-2"></i>
                        <p class="text-sm">No workers online</p>
                    </div>
                `;
            } else {
                container.innerHTML = this.workers.map(w => this.renderWorker(w)).join('');
            }

        } catch (error) {
            console.error('Failed to load workers:', error);
            container.innerHTML = `
                <div class="text-center py-4 text-slate-400">
                    <p class="text-sm">Failed to load workers</p>
                </div>
            `;
        }

        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    }

    renderWorker(worker) {
        const name = worker.name || worker.hostname || 'Unknown';
        const active = worker.active || 0;

        return `
            <div class="flex items-center justify-between p-2 bg-dark-tertiary rounded-lg">
                <div class="flex items-center gap-2">
                    <span class="w-2 h-2 rounded-full bg-green-500"></span>
                    <span class="text-sm truncate">${name}</span>
                </div>
                <span class="text-xs text-slate-400">${active} active</span>
            </div>
        `;
    }

    async loadStatistics() {
        try {
            const data = await tasksAPI.getStatistics();

            document.getElementById('stat-total-processed').textContent =
                data?.total_processed || '0';
            document.getElementById('stat-success-rate').textContent =
                data?.success_rate ? `${(data.success_rate * 100).toFixed(1)}%` : '--';
            document.getElementById('stat-avg-duration').textContent =
                data?.avg_duration ? `${data.avg_duration.toFixed(1)}s` : '--';

        } catch (error) {
            console.error('Failed to load statistics:', error);
        }
    }

    async cancelTask(taskId) {
        if (!taskId) return;

        try {
            await tasksAPI.cancel(taskId);
            toast.success('Task cancelled');
            await this.loadActiveTasks();
        } catch (error) {
            toast.error(`Failed to cancel task: ${error.message}`);
        }
    }

    async retryTask(taskId) {
        if (!taskId) return;

        try {
            await tasksAPI.retry(taskId);
            toast.success('Task retried');
            await this.loadAllData();
        } catch (error) {
            toast.error(`Failed to retry task: ${error.message}`);
        }
    }

    async clearFailedTasks() {
        toast.info('Clearing failed tasks...');
        // This would need a backend endpoint
        this.failedTasks = [];
        await this.loadFailedTasks();
    }

    openModal(type) {
        this.modalType = type;
        const modal = document.getElementById('task-modal');
        const title = document.getElementById('modal-title');
        const content = document.getElementById('modal-content');

        if (!modal || !content) return;

        const configs = {
            scrape: {
                title: 'Scrape Video',
                content: `
                    <div>
                        <label class="block text-sm font-medium text-slate-300 mb-2">Video URL or ID</label>
                        <input type="text" id="input-video"
                            class="input w-full"
                            placeholder="Enter YouTube URL or video ID">
                    </div>
                    <div class="flex items-center gap-2">
                        <input type="checkbox" id="input-comments" class="form-checkbox">
                        <label for="input-comments" class="text-sm text-slate-300">Fetch comments</label>
                    </div>
                    <div id="comments-options" class="hidden">
                        <label class="block text-sm font-medium text-slate-300 mb-2">Max Comments</label>
                        <input type="number" id="input-max-comments" class="input w-full" value="500">
                    </div>
                `
            },
            search: {
                title: 'Search & Scrape',
                content: `
                    <div>
                        <label class="block text-sm font-medium text-slate-300 mb-2">Search Query</label>
                        <input type="text" id="input-query"
                            class="input w-full"
                            placeholder="Enter search keywords">
                    </div>
                    <div>
                        <label class="block text-sm font-medium text-slate-300 mb-2">Max Results</label>
                        <input type="number" id="input-max-results" class="input w-full" value="20" min="1" max="50">
                    </div>
                `
            },
            channel: {
                title: 'Scrape Channel',
                content: `
                    <div>
                        <label class="block text-sm font-medium text-slate-300 mb-2">Channel ID or URL</label>
                        <input type="text" id="input-channel"
                            class="input w-full"
                            placeholder="Enter channel ID or URL">
                    </div>
                    <div>
                        <label class="block text-sm font-medium text-slate-300 mb-2">Max Videos</label>
                        <input type="number" id="input-max-videos" class="input w-full" value="50" min="1" max="500">
                    </div>
                `
            }
        };

        const config = configs[type];
        if (!config) return;

        title.textContent = config.title;
        content.innerHTML = config.content;

        // Bind comment toggle
        if (type === 'scrape') {
            document.getElementById('input-comments')?.addEventListener('change', (e) => {
                document.getElementById('comments-options')?.classList.toggle('hidden', !e.target.checked);
            });
        }

        modal.classList.remove('hidden');

        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }

        // Focus first input
        content.querySelector('input')?.focus();
    }

    closeModal() {
        document.getElementById('task-modal')?.classList.add('hidden');
        this.modalType = null;
    }

    async submitModal() {
        switch (this.modalType) {
            case 'scrape':
                await this.submitScrape();
                break;
            case 'search':
                await this.submitSearch();
                break;
            case 'channel':
                await this.submitChannel();
                break;
        }
    }

    async submitScrape() {
        const input = document.getElementById('input-video');
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

        const fetchComments = document.getElementById('input-comments')?.checked || false;
        const maxComments = parseInt(document.getElementById('input-max-comments')?.value) || 500;

        try {
            await tasksAPI.scrapeVideo(videoId, fetchComments, maxComments);
            toast.success(`Scraping started: ${videoId}`);
            this.closeModal();
            await this.loadActiveTasks();
        } catch (error) {
            toast.error(`Failed: ${error.message}`);
        }
    }

    async submitSearch() {
        const query = document.getElementById('input-query')?.value?.trim();
        const maxResults = parseInt(document.getElementById('input-max-results')?.value) || 20;

        if (!query) {
            toast.warning('Please enter a search query');
            return;
        }

        try {
            await tasksAPI.searchAndScrape(query, maxResults);
            toast.success(`Search task started: "${query}"`);
            this.closeModal();
            await this.loadActiveTasks();
        } catch (error) {
            toast.error(`Failed: ${error.message}`);
        }
    }

    async submitChannel() {
        const channelId = document.getElementById('input-channel')?.value?.trim();
        const maxVideos = parseInt(document.getElementById('input-max-videos')?.value) || 50;

        if (!channelId) {
            toast.warning('Please enter a channel ID');
            return;
        }

        try {
            await tasksAPI.scrapeChannel(channelId, maxVideos);
            toast.success(`Channel scrape started: ${channelId}`);
            this.closeModal();
            await this.loadActiveTasks();
        } catch (error) {
            toast.error(`Failed: ${error.message}`);
        }
    }

    startAutoRefresh() {
        // Refresh every 5 seconds
        this.refreshInterval = setInterval(() => {
            this.loadActiveTasks();
        }, 5000);
    }

    destroy() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }
    }
}

// Initialize page
const tasksPage = new TasksPage();
window.tasksPage = tasksPage;

export { TasksPage, tasksPage };
