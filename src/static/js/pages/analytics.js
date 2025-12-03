/**
 * Analytics Page
 * Data visualization and insights
 */

import { api, videosAPI } from '../core/api.js';
import { toast } from '../components/toast.js';
import { formatNumber, formatRelativeTime, getYouTubeThumbnail } from '../core/utils.js';

class AnalyticsPage {
    constructor() {
        this.timeRange = '30d';
        this.charts = {};

        this.init();
    }

    async init() {
        console.log('Initializing Analytics Page...');

        this.bindEvents();
        await this.loadAnalytics();

        console.log('Analytics Page initialized');
    }

    bindEvents() {
        // Time range selector
        document.getElementById('time-range')?.addEventListener('change', (e) => {
            this.timeRange = e.target.value;
            this.loadAnalytics();
        });

        // Refresh button
        document.getElementById('refresh-analytics')?.addEventListener('click', () => {
            this.loadAnalytics();
            toast.info('Refreshing analytics...');
        });

        // Export button
        document.getElementById('export-data')?.addEventListener('click', () => {
            this.exportData();
        });

        // Top videos sort
        document.getElementById('top-videos-sort')?.addEventListener('change', () => {
            this.loadTopVideos();
        });
    }

    async loadAnalytics() {
        await Promise.all([
            this.loadOverviewStats(),
            this.loadCharts(),
            this.loadTopVideos(),
            this.loadTopChannels(),
            this.loadRecentActivity()
        ]);
    }

    async loadOverviewStats() {
        try {
            // Try to get analytics overview
            const data = await api.get('/system/database');
            const stats = data?.statistics || {};

            // Update overview cards
            document.getElementById('total-views').textContent = formatNumber(stats.total_views || 0);
            document.getElementById('total-likes').textContent = formatNumber(stats.total_likes || 0);
            document.getElementById('total-comments-analyzed').textContent = formatNumber(stats.total_comments || 0);

            // Calculate engagement rate
            const totalViews = stats.total_views || 1;
            const totalLikes = stats.total_likes || 0;
            const engagementRate = ((totalLikes / totalViews) * 100).toFixed(2);
            document.getElementById('avg-engagement').textContent = `${engagementRate}%`;

        } catch (error) {
            console.error('Failed to load overview stats:', error);
        }
    }

    async loadCharts() {
        // Check if Chart.js is available
        if (typeof Chart === 'undefined') {
            console.warn('Chart.js not loaded');
            return;
        }

        // Initialize charts with placeholder data
        this.initScrapingChart();
        this.initDistributionChart();
        this.initViewsChart();
        this.initEngagementChart();
    }

    initScrapingChart() {
        const ctx = document.getElementById('scraping-chart')?.getContext('2d');
        if (!ctx) return;

        // Destroy existing chart
        if (this.charts.scraping) {
            this.charts.scraping.destroy();
        }

        // Generate sample data for last 7 days
        const labels = [];
        const data = [];
        for (let i = 6; i >= 0; i--) {
            const date = new Date();
            date.setDate(date.getDate() - i);
            labels.push(date.toLocaleDateString('en-US', { weekday: 'short' }));
            data.push(Math.floor(Math.random() * 50) + 10);
        }

        this.charts.scraping = new Chart(ctx, {
            type: 'line',
            data: {
                labels,
                datasets: [{
                    label: 'Videos Scraped',
                    data,
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: {
                            color: 'rgba(148, 163, 184, 0.1)'
                        }
                    },
                    x: {
                        grid: {
                            display: false
                        }
                    }
                }
            }
        });
    }

    initDistributionChart() {
        const ctx = document.getElementById('distribution-chart')?.getContext('2d');
        if (!ctx) return;

        if (this.charts.distribution) {
            this.charts.distribution.destroy();
        }

        this.charts.distribution = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['Music', 'Gaming', 'Education', 'Entertainment', 'Tech', 'Other'],
                datasets: [{
                    data: [30, 25, 15, 15, 10, 5],
                    backgroundColor: [
                        '#ef4444',
                        '#3b82f6',
                        '#22c55e',
                        '#eab308',
                        '#8b5cf6',
                        '#64748b'
                    ]
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'right',
                        labels: {
                            color: '#94a3b8'
                        }
                    }
                }
            }
        });
    }

    initViewsChart() {
        const ctx = document.getElementById('views-chart')?.getContext('2d');
        if (!ctx) return;

        if (this.charts.views) {
            this.charts.views.destroy();
        }

        const labels = ['0-1K', '1K-10K', '10K-100K', '100K-1M', '1M+'];
        const data = [45, 30, 15, 7, 3];

        this.charts.views = new Chart(ctx, {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    label: 'Videos',
                    data,
                    backgroundColor: '#3b82f6'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: {
                            color: 'rgba(148, 163, 184, 0.1)'
                        }
                    },
                    x: {
                        grid: {
                            display: false
                        }
                    }
                }
            }
        });
    }

    initEngagementChart() {
        const ctx = document.getElementById('engagement-chart')?.getContext('2d');
        if (!ctx) return;

        if (this.charts.engagement) {
            this.charts.engagement.destroy();
        }

        const labels = [];
        const likesData = [];
        const commentsData = [];

        for (let i = 6; i >= 0; i--) {
            const date = new Date();
            date.setDate(date.getDate() - i);
            labels.push(date.toLocaleDateString('en-US', { weekday: 'short' }));
            likesData.push(Math.floor(Math.random() * 1000) + 200);
            commentsData.push(Math.floor(Math.random() * 200) + 50);
        }

        this.charts.engagement = new Chart(ctx, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    {
                        label: 'Likes',
                        data: likesData,
                        borderColor: '#22c55e',
                        tension: 0.4
                    },
                    {
                        label: 'Comments',
                        data: commentsData,
                        borderColor: '#eab308',
                        tension: 0.4
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        labels: {
                            color: '#94a3b8'
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: {
                            color: 'rgba(148, 163, 184, 0.1)'
                        }
                    },
                    x: {
                        grid: {
                            display: false
                        }
                    }
                }
            }
        });
    }

    async loadTopVideos() {
        const container = document.getElementById('top-videos');
        if (!container) return;

        try {
            const sortBy = document.getElementById('top-videos-sort')?.value || 'views';
            const data = await videosAPI.list({ limit: 5, sort: `-${sortBy === 'views' ? 'view_count' : sortBy === 'likes' ? 'like_count' : 'comment_count'}` });
            const videos = data?.items || data || [];

            if (videos.length === 0) {
                container.innerHTML = `
                    <div class="text-center py-8 text-slate-400">
                        <i data-lucide="video-off" class="w-8 h-8 mx-auto mb-2"></i>
                        <p class="text-sm">No videos found</p>
                    </div>
                `;
            } else {
                container.innerHTML = videos.map((v, i) => `
                    <a href="/videos/${v.video_id || v.id}" class="flex items-center gap-3 p-2 rounded-lg hover:bg-dark-tertiary transition-colors">
                        <span class="text-lg font-bold text-slate-500 w-6">${i + 1}</span>
                        <img src="${v.thumbnail_url || getYouTubeThumbnail(v.video_id || v.id)}"
                             class="w-16 h-9 rounded object-cover"
                             onerror="this.src='https://via.placeholder.com/64x36'">
                        <div class="flex-1 min-w-0">
                            <p class="text-sm font-medium truncate">${v.title || 'Untitled'}</p>
                            <p class="text-xs text-slate-400">${formatNumber(v.view_count || 0)} views</p>
                        </div>
                    </a>
                `).join('');
            }

        } catch (error) {
            console.error('Failed to load top videos:', error);
            container.innerHTML = `
                <div class="text-center py-8 text-slate-400">
                    <p class="text-sm">Failed to load videos</p>
                </div>
            `;
        }

        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    }

    async loadTopChannels() {
        const container = document.getElementById('top-channels');
        if (!container) return;

        // Placeholder - would need a channels API endpoint
        container.innerHTML = `
            <div class="text-center py-8 text-slate-400">
                <i data-lucide="users" class="w-8 h-8 mx-auto mb-2"></i>
                <p class="text-sm">Channel data coming soon</p>
            </div>
        `;

        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    }

    async loadRecentActivity() {
        const tbody = document.getElementById('recent-activity');
        if (!tbody) return;

        try {
            const data = await videosAPI.list({ limit: 10, sort: '-scraped_at' });
            const videos = data?.items || data || [];

            if (videos.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="5" class="p-8 text-center text-slate-400">
                            No recent activity
                        </td>
                    </tr>
                `;
            } else {
                tbody.innerHTML = videos.map(v => `
                    <tr class="border-b border-slate-700 hover:bg-dark-tertiary transition-colors">
                        <td class="p-4">
                            <a href="/videos/${v.video_id || v.id}" class="flex items-center gap-3">
                                <img src="${v.thumbnail_url || getYouTubeThumbnail(v.video_id || v.id)}"
                                     class="w-12 h-7 rounded object-cover"
                                     onerror="this.src='https://via.placeholder.com/48x27'">
                                <span class="truncate max-w-xs">${v.title || 'Untitled'}</span>
                            </a>
                        </td>
                        <td class="p-4 text-slate-400">${v.channel_title || '--'}</td>
                        <td class="p-4">${formatNumber(v.view_count || 0)}</td>
                        <td class="p-4 text-slate-400">${formatRelativeTime(v.scraped_at)}</td>
                        <td class="p-4">
                            <span class="px-2 py-1 rounded-full text-xs bg-green-500/20 text-green-400">
                                Complete
                            </span>
                        </td>
                    </tr>
                `).join('');
            }

        } catch (error) {
            console.error('Failed to load recent activity:', error);
            tbody.innerHTML = `
                <tr>
                    <td colspan="5" class="p-8 text-center text-slate-400">
                        Failed to load activity
                    </td>
                </tr>
            `;
        }
    }

    exportData() {
        toast.info('Export feature coming soon');
    }
}

// Initialize page
const analyticsPage = new AnalyticsPage();
window.analyticsPage = analyticsPage;

export { AnalyticsPage, analyticsPage };
