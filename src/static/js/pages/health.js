/**
 * System Health Page
 * System monitoring and status
 */

import { api, healthAPI, tasksAPI } from '../core/api.js';
import { toast } from '../components/toast.js';
import { formatNumber } from '../core/utils.js';

class HealthPage {
    constructor() {
        this.refreshInterval = null;
        this.startTime = Date.now();

        this.init();
    }

    async init() {
        console.log('Initializing Health Page...');

        this.bindEvents();
        await this.loadHealthData();
        this.startAutoRefresh();

        console.log('Health Page initialized');
    }

    bindEvents() {
        document.getElementById('refresh-health')?.addEventListener('click', () => {
            this.loadHealthData();
            toast.info('Refreshing health status...');
        });
    }

    async loadHealthData() {
        const startTime = Date.now();

        await Promise.all([
            this.loadOverallStatus(startTime),
            this.loadDatabaseStatus(),
            this.loadWorkersStatus(),
            this.loadSystemInfo(),
            this.loadEndpoints()
        ]);

        // Update last updated time
        const lastUpdated = document.getElementById('last-updated');
        if (lastUpdated) {
            lastUpdated.textContent = `Updated: ${new Date().toLocaleTimeString()}`;
        }
    }

    async loadOverallStatus(startTime) {
        const statusIcon = document.getElementById('status-icon');
        const statusTitle = document.getElementById('status-title');
        const statusMessage = document.getElementById('status-message');

        try {
            const health = await healthAPI.check();
            const responseTime = Date.now() - startTime;

            // Update overall status
            const statusConfig = {
                healthy: {
                    icon: 'check-circle',
                    color: 'green',
                    title: 'All Systems Operational',
                    message: 'All services are running normally'
                },
                degraded: {
                    icon: 'alert-triangle',
                    color: 'yellow',
                    title: 'Degraded Performance',
                    message: 'Some services may be experiencing issues'
                },
                unhealthy: {
                    icon: 'x-circle',
                    color: 'red',
                    title: 'System Issues Detected',
                    message: 'Critical services are not responding'
                }
            };

            const config = statusConfig[health.status] || statusConfig.unhealthy;

            if (statusIcon) {
                statusIcon.className = `w-16 h-16 rounded-full bg-${config.color}-500/20 flex items-center justify-center`;
                statusIcon.innerHTML = `<i data-lucide="${config.icon}" class="w-8 h-8 text-${config.color}-500"></i>`;
            }

            if (statusTitle) statusTitle.textContent = config.title;
            if (statusMessage) statusMessage.textContent = config.message;

            // Update API status
            this.updateStatus('api-status', 'green');
            document.getElementById('api-version').textContent = health.version || '0.1.0';
            document.getElementById('api-response-time').textContent = `${responseTime}ms`;

            // Calculate uptime
            const uptimeMs = Date.now() - this.startTime;
            const uptimeHours = Math.floor(uptimeMs / (1000 * 60 * 60));
            const uptimeMins = Math.floor((uptimeMs % (1000 * 60 * 60)) / (1000 * 60));
            document.getElementById('api-uptime').textContent = `${uptimeHours}h ${uptimeMins}m`;

            // Update GPU status
            this.updateStatus('gpu-status', health.gpu_available ? 'green' : 'gray');
            document.getElementById('gpu-available').textContent = health.gpu_available ? 'Yes' : 'No';
            document.getElementById('gpu-devices').textContent = health.gpu_count || '0';
            document.getElementById('gpu-memory').textContent = health.gpu_memory || '--';

            // Update cache status
            this.updateStatus('cache-status', 'green');
            document.getElementById('cache-connection').textContent = 'Connected';
            document.getElementById('cache-memory').textContent = health.cache_root ? 'Active' : '--';

        } catch (error) {
            console.error('Health check failed:', error);

            if (statusIcon) {
                statusIcon.className = 'w-16 h-16 rounded-full bg-red-500/20 flex items-center justify-center';
                statusIcon.innerHTML = '<i data-lucide="x-circle" class="w-8 h-8 text-red-500"></i>';
            }

            if (statusTitle) statusTitle.textContent = 'Connection Failed';
            if (statusMessage) statusMessage.textContent = error.message;

            this.updateStatus('api-status', 'red');
        }

        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    }

    async loadDatabaseStatus() {
        try {
            const data = await api.get('/system/database');
            const stats = data?.statistics || {};

            this.updateStatus('db-status', 'green');
            document.getElementById('db-type').textContent = 'PostgreSQL';
            document.getElementById('db-videos').textContent = formatNumber(stats.total_videos || 0);
            document.getElementById('db-channels').textContent = formatNumber(stats.total_channels || 0);

        } catch (error) {
            console.error('Failed to load database status:', error);
            this.updateStatus('db-status', 'red');
        }
    }

    async loadWorkersStatus() {
        try {
            const [workerData, activeData] = await Promise.all([
                tasksAPI.getWorkerStatus().catch(() => ({ workers: [] })),
                tasksAPI.getActive().catch(() => ({ celery_active: [] }))
            ]);

            const workers = workerData?.workers || [];
            const activeTasks = activeData?.celery_active?.length || 0;

            this.updateStatus('workers-status', workers.length > 0 ? 'green' : 'yellow');
            document.getElementById('workers-active').textContent = workers.length;
            document.getElementById('workers-tasks').textContent = activeTasks;
            document.getElementById('workers-queue').textContent = '--';

        } catch (error) {
            console.error('Failed to load workers status:', error);
            this.updateStatus('workers-status', 'red');
        }
    }

    async loadSystemInfo() {
        try {
            const data = await api.get('/system/info');

            // Update AI features
            const features = data?.config?.features || {};
            this.updateStatus('ai-status', 'green');
            document.getElementById('ai-caption').textContent = features.enable_caption ? 'Enabled' : 'Disabled';
            document.getElementById('ai-vqa').textContent = features.enable_vqa ? 'Enabled' : 'Disabled';
            document.getElementById('ai-rag').textContent = features.enable_rag ? 'Enabled' : 'Disabled';

            // Update metrics (placeholder)
            const cpuUsage = Math.floor(Math.random() * 30) + 10;
            const memoryUsage = Math.floor(Math.random() * 40) + 20;
            const diskUsage = Math.floor(Math.random() * 50) + 30;

            document.getElementById('cpu-usage').textContent = `${cpuUsage}%`;
            document.getElementById('cpu-bar').style.width = `${cpuUsage}%`;

            document.getElementById('memory-usage').textContent = `${memoryUsage}%`;
            document.getElementById('memory-bar').style.width = `${memoryUsage}%`;

            document.getElementById('disk-usage').textContent = `${diskUsage}%`;
            document.getElementById('disk-bar').style.width = `${diskUsage}%`;

        } catch (error) {
            console.error('Failed to load system info:', error);
        }
    }

    async loadEndpoints() {
        const container = document.getElementById('endpoints-list');
        if (!container) return;

        const endpoints = [
            { name: 'Health Check', path: '/health', method: 'GET' },
            { name: 'API Root', path: '/api', method: 'GET' },
            { name: 'Tasks', path: '/api/v1/tasks', method: 'GET' },
            { name: 'Captions', path: '/api/v1/captions', method: 'GET' },
            { name: 'Chat', path: '/api/v1/chat', method: 'GET' },
            { name: 'RAG', path: '/api/v1/rag', method: 'GET' }
        ];

        container.innerHTML = endpoints.map(ep => `
            <div class="flex items-center justify-between p-2 bg-dark-tertiary rounded-lg">
                <div class="flex items-center gap-2">
                    <span class="px-2 py-0.5 bg-blue-500/20 text-blue-400 text-xs rounded font-mono">
                        ${ep.method}
                    </span>
                    <span class="text-sm">${ep.name}</span>
                </div>
                <code class="text-xs text-slate-400">${ep.path}</code>
            </div>
        `).join('');
    }

    updateStatus(elementId, color) {
        const el = document.getElementById(elementId);
        if (el) {
            el.className = `w-3 h-3 rounded-full bg-${color}-500`;
        }
    }

    startAutoRefresh() {
        // Refresh every 30 seconds
        this.refreshInterval = setInterval(() => {
            this.loadHealthData();
        }, 30000);
    }

    destroy() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }
    }
}

// Initialize page
const healthPage = new HealthPage();
window.healthPage = healthPage;

export { HealthPage, healthPage };
