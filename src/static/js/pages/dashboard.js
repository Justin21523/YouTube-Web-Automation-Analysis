/**
 * Dashboard Page
 * Main dashboard functionality
 */

import { api, healthAPI, tasksAPI } from '../core/api.js';
import { toast } from '../components/toast.js';
import { formatNumber, formatRelativeTime, extractVideoId } from '../core/utils.js';

class DashboardPage {
    constructor() {
        this.refreshInterval = null;
        this.init();
    }

    async init() {
        console.log('Initializing Dashboard...');

        // Bind event listeners
        this.bindEvents();

        // Load initial data
        await this.loadAllData();

        // Start periodic refresh
        this.startAutoRefresh();

        console.log('Dashboard initialized');
    }

    bindEvents() {
        // Refresh button
        document.getElementById('refresh-stats')?.addEventListener('click', () => {
            this.loadAllData();
            toast.info('Refreshing dashboard...');
        });

        // Quick actions
        document.getElementById('quick-scrape-video')?.addEventListener('click', () => {
            this.openScrapeModal();
        });

        document.getElementById('quick-search')?.addEventListener('click', () => {
            window.location.href = '/videos/search';
        });

        document.getElementById('quick-chat')?.addEventListener('click', () => {
            window.location.href = '/chat';
        });

        document.getElementById('quick-analytics')?.addEventListener('click', () => {
            window.location.href = '/analytics';
        });

        // Scrape modal
        document.getElementById('close-scrape-modal')?.addEventListener('click', () => {
            this.closeScrapeModal();
        });

        document.getElementById('cancel-scrape')?.addEventListener('click', () => {
            this.closeScrapeModal();
        });

        document.getElementById('submit-scrape')?.addEventListener('click', () => {
            this.submitScrape();
        });

        // Toggle comments options
        document.getElementById('scrape-comments')?.addEventListener('change', (e) => {
            const optionsDiv = document.getElementById('scrape-comments-options');
            if (optionsDiv) {
                optionsDiv.classList.toggle('hidden', !e.target.checked);
            }
        });

        // Close modal on backdrop click
        document.getElementById('scrape-modal')?.addEventListener('click', (e) => {
            if (e.target.id === 'scrape-modal') {
                this.closeScrapeModal();
            }
        });
    }

    async loadAllData() {
        await Promise.all([
            this.loadSystemStatus(),
            this.loadDatabaseStats(),
            this.loadTaskStats(),
            this.loadRecentActivity(),
            this.loadRunningTasks()
        ]);
    }

    async loadSystemStatus() {
        try {
            const health = await healthAPI.check();

            // Update status indicator
            const indicator = document.getElementById('status-indicator');
            const statusText = document.getElementById('status-text');
            const statusDetail = document.getElementById('status-detail');

            const statusColors = {
                healthy: 'bg-green-500',
                degraded: 'bg-yellow-500',
                unhealthy: 'bg-red-500'
            };

            if (indicator) {
                indicator.className = `w-3 h-3 rounded-full ${statusColors[health.status] || 'bg-gray-500'}`;
                indicator.classList.remove('animate-pulse');
            }

            if (statusText) {
                statusText.textContent = health.status === 'healthy'
                    ? 'All systems operational'
                    : `System status: ${health.status}`;
            }

            if (statusDetail) {
                statusDetail.textContent = `Database: ${health.database || 'connected'} | GPU: ${health.gpu_available ? 'Available' : 'Not available'}`;
            }

            // Update version
            const versionDisplay = document.getElementById('version-display');
            if (versionDisplay) {
                versionDisplay.textContent = `v${health.version || '0.1.0'}`;
            }

            // Update GPU info
            this.updateElement('gpu-info', health.gpu_available ? 'Available' : 'Not available');
            this.updateStatusDot('gpu-status', health.gpu_available ? 'green' : 'gray');

            // Update DB status
            this.updateStatusDot('db-status', 'green');
            this.updateElement('db-name', health.database || 'PostgreSQL');

            // Update cache status
            this.updateStatusDot('cache-status', 'green');
            this.updateElement('cache-size', health.cache_root ? 'Active' : '--');

        } catch (error) {
            console.error('Failed to load system status:', error);
            this.updateElement('status-text', 'Unable to connect');
            this.updateElement('status-detail', error.message);
            document.getElementById('status-indicator')?.classList.add('bg-red-500');
        }
    }

    async loadDatabaseStats() {
        try {
            const response = await api.get('/system/database');
            const stats = response.statistics || {};

            this.updateElement('stat-videos', formatNumber(stats.total_videos || 0));
            this.updateElement('stat-channels', formatNumber(stats.total_channels || 0));
            this.updateElement('stat-comments', formatNumber(stats.total_comments || 0));
            this.updateElement('db-name', response.database_url || 'PostgreSQL');

        } catch (error) {
            console.error('Failed to load database stats:', error);
        }
    }

    async loadTaskStats() {
        try {
            const [activeData, workerData] = await Promise.all([
                tasksAPI.getActive().catch(() => ({ celery_active: [] })),
                tasksAPI.getWorkerStatus().catch(() => ({ workers: [] }))
            ]);

            const activeTasks = activeData?.celery_active?.length || 0;
            this.updateElement('stat-tasks', activeTasks);

            // Update worker info
            const workers = workerData?.workers || [];
            const workerCount = workers.length;
            this.updateElement('worker-count', workerCount > 0 ? `${workerCount} active` : 'No workers');
            this.updateStatusDot('worker-status', workerCount > 0 ? 'green' : 'yellow');

        } catch (error) {
            console.error('Failed to load task stats:', error);
        }
    }

    async loadRecentActivity() {
        const container = document.getElementById('activity-list');
        if (!container) return;

        try {
            // Try to get recent tasks or activity
            const [activeData, failedData] = await Promise.all([
                tasksAPI.getActive().catch(() => ({ celery_active: [] })),
                tasksAPI.getFailed(5).catch(() => ({ failed_tasks: [] }))
            ]);

            const activities = [];

            // Add active tasks
            (activeData?.celery_active || []).forEach(task => {
                activities.push({
                    type: 'running',
                    name: task.name || 'Task',
                    time: task.time_start || new Date().toISOString(),
                    id: task.id
                });
            });

            // Add failed tasks
            (failedData?.failed_tasks || []).slice(0, 3).forEach(task => {
                activities.push({
                    type: 'failed',
                    name: task.name || 'Task',
                    time: task.time || new Date().toISOString(),
                    id: task.id
                });
            });

            if (activities.length === 0) {
                container.innerHTML = `
                    <div class="text-center py-8 text-slate-400">
                        <i data-lucide="inbox" class="w-8 h-8 mx-auto mb-2"></i>
                        <p>No recent activity</p>
                    </div>
                `;
            } else {
                container.innerHTML = activities.map(activity => this.renderActivityItem(activity)).join('');
            }

            // Re-initialize icons
            if (typeof lucide !== 'undefined') {
                lucide.createIcons();
            }

        } catch (error) {
            console.error('Failed to load activity:', error);
            container.innerHTML = `
                <div class="text-center py-8 text-slate-400">
                    <i data-lucide="alert-circle" class="w-8 h-8 mx-auto mb-2"></i>
                    <p>Failed to load activity</p>
                </div>
            `;
        }
    }

    renderActivityItem(activity) {
        const icons = {
            running: 'loader',
            completed: 'check-circle',
            failed: 'x-circle',
            pending: 'clock'
        };

        const colors = {
            running: 'text-blue-500',
            completed: 'text-green-500',
            failed: 'text-red-500',
            pending: 'text-yellow-500'
        };

        return `
            <div class="flex items-center gap-3 p-3 rounded-lg hover:bg-dark-tertiary transition-colors">
                <i data-lucide="${icons[activity.type] || 'activity'}"
                   class="w-5 h-5 ${colors[activity.type] || 'text-slate-400'} ${activity.type === 'running' ? 'animate-spin' : ''}"></i>
                <div class="flex-1 min-w-0">
                    <p class="text-sm font-medium truncate">${activity.name}</p>
                    <p class="text-xs text-slate-400">${formatRelativeTime(activity.time)}</p>
                </div>
                <span class="text-xs px-2 py-1 rounded-full bg-dark-tertiary text-slate-400">${activity.type}</span>
            </div>
        `;
    }

    async loadRunningTasks() {
        const container = document.getElementById('running-tasks');
        if (!container) return;

        try {
            const data = await tasksAPI.getActive();
            const tasks = data?.celery_active || [];

            if (tasks.length === 0) {
                container.innerHTML = `
                    <div class="text-center py-8 text-slate-400">
                        <i data-lucide="check-circle" class="w-8 h-8 mx-auto mb-2"></i>
                        <p>No tasks currently running</p>
                    </div>
                `;
            } else {
                container.innerHTML = tasks.map(task => this.renderTaskItem(task)).join('');
            }

            // Re-initialize icons
            if (typeof lucide !== 'undefined') {
                lucide.createIcons();
            }

        } catch (error) {
            console.error('Failed to load running tasks:', error);
        }
    }

    renderTaskItem(task) {
        return `
            <div class="flex items-center gap-3 p-3 rounded-lg bg-dark-tertiary">
                <div class="w-8 h-8 rounded-lg bg-blue-500/20 flex items-center justify-center">
                    <i data-lucide="loader" class="w-4 h-4 text-blue-500 animate-spin"></i>
                </div>
                <div class="flex-1 min-w-0">
                    <p class="text-sm font-medium truncate">${task.name || 'Unknown task'}</p>
                    <p class="text-xs text-slate-400 truncate">ID: ${task.id?.substring(0, 8) || '--'}...</p>
                </div>
                <button class="btn btn-sm btn-secondary" onclick="dashboardPage.cancelTask('${task.id}')">
                    Cancel
                </button>
            </div>
        `;
    }

    async cancelTask(taskId) {
        if (!taskId) return;

        try {
            await tasksAPI.cancel(taskId);
            toast.success('Task cancelled');
            await this.loadRunningTasks();
        } catch (error) {
            toast.error(`Failed to cancel task: ${error.message}`);
        }
    }

    openScrapeModal() {
        const modal = document.getElementById('scrape-modal');
        if (modal) {
            modal.classList.remove('hidden');
            document.getElementById('scrape-video-input')?.focus();
        }
        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    }

    closeScrapeModal() {
        const modal = document.getElementById('scrape-modal');
        if (modal) {
            modal.classList.add('hidden');
        }
        // Reset form
        const input = document.getElementById('scrape-video-input');
        if (input) input.value = '';
        const checkbox = document.getElementById('scrape-comments');
        if (checkbox) checkbox.checked = false;
        document.getElementById('scrape-comments-options')?.classList.add('hidden');
    }

    async submitScrape() {
        const input = document.getElementById('scrape-video-input');
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

        const fetchComments = document.getElementById('scrape-comments')?.checked || false;
        const maxComments = parseInt(document.getElementById('scrape-max-comments')?.value) || 500;

        try {
            const result = await tasksAPI.scrapeVideo(videoId, fetchComments, maxComments);
            toast.success(`Scraping started for video: ${videoId}`);
            this.closeScrapeModal();

            // Refresh running tasks
            await this.loadRunningTasks();

        } catch (error) {
            toast.error(`Failed to start scraping: ${error.message}`);
        }
    }

    updateElement(id, value) {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    }

    updateStatusDot(id, color) {
        const el = document.getElementById(id);
        if (el) {
            el.className = `w-2 h-2 rounded-full bg-${color}-500`;
        }
    }

    startAutoRefresh() {
        // Refresh every 30 seconds
        this.refreshInterval = setInterval(() => {
            this.loadTaskStats();
            this.loadRunningTasks();
        }, 30000);
    }

    destroy() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }
    }
}

// Initialize dashboard
const dashboardPage = new DashboardPage();

// Make available globally for inline event handlers
window.dashboardPage = dashboardPage;

export { DashboardPage, dashboardPage };
