/**
 * WebSocket Manager
 * Handles real-time communication with the backend
 */

class WebSocketManager {
    constructor(options = {}) {
        this.baseUrl = options.baseUrl || this.getWebSocketUrl();
        this.reconnectInterval = options.reconnectInterval || 3000;
        this.maxReconnectAttempts = options.maxReconnectAttempts || 10;
        this.pingInterval = options.pingInterval || 30000;

        this.socket = null;
        this.clientId = null;
        this.reconnectAttempts = 0;
        this.isConnected = false;
        this.isConnecting = false;
        this.shouldReconnect = true;

        // Event handlers
        this.eventHandlers = new Map();

        // Ping timer
        this.pingTimer = null;

        // Message queue for offline messages
        this.messageQueue = [];

        // Subscribed channels
        this.subscriptions = new Set();
    }

    /**
     * Get WebSocket URL based on current location
     */
    getWebSocketUrl() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        return `${protocol}//${window.location.host}`;
    }

    /**
     * Connect to WebSocket server
     * @param {string} endpoint - WebSocket endpoint (e.g., '/ws' or '/ws/tasks')
     * @returns {Promise<void>}
     */
    connect(endpoint = '/ws') {
        return new Promise((resolve, reject) => {
            if (this.isConnected) {
                resolve();
                return;
            }

            if (this.isConnecting) {
                // Wait for existing connection attempt
                const checkInterval = setInterval(() => {
                    if (this.isConnected) {
                        clearInterval(checkInterval);
                        resolve();
                    }
                }, 100);
                return;
            }

            this.isConnecting = true;
            this.shouldReconnect = true;

            // Generate client ID
            this.clientId = this.clientId || `client_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

            const url = `${this.baseUrl}${endpoint}?client_id=${this.clientId}`;
            console.log('Connecting to WebSocket:', url);

            try {
                this.socket = new WebSocket(url);

                this.socket.onopen = () => {
                    console.log('WebSocket connected');
                    this.isConnected = true;
                    this.isConnecting = false;
                    this.reconnectAttempts = 0;

                    // Start ping timer
                    this.startPingTimer();

                    // Send queued messages
                    this.flushMessageQueue();

                    // Resubscribe to channels
                    this.resubscribe();

                    // Trigger connect event
                    this.emit('connect', { clientId: this.clientId });

                    resolve();
                };

                this.socket.onmessage = (event) => {
                    this.handleMessage(event);
                };

                this.socket.onclose = (event) => {
                    console.log('WebSocket closed:', event.code, event.reason);
                    this.isConnected = false;
                    this.isConnecting = false;
                    this.stopPingTimer();

                    this.emit('disconnect', { code: event.code, reason: event.reason });

                    // Attempt reconnection
                    if (this.shouldReconnect) {
                        this.scheduleReconnect(endpoint);
                    }
                };

                this.socket.onerror = (error) => {
                    console.error('WebSocket error:', error);
                    this.isConnecting = false;
                    this.emit('error', error);

                    if (!this.isConnected) {
                        reject(error);
                    }
                };

            } catch (error) {
                this.isConnecting = false;
                reject(error);
            }
        });
    }

    /**
     * Disconnect from WebSocket server
     */
    disconnect() {
        this.shouldReconnect = false;
        this.stopPingTimer();

        if (this.socket) {
            this.socket.close(1000, 'Client disconnect');
            this.socket = null;
        }

        this.isConnected = false;
        this.isConnecting = false;
    }

    /**
     * Schedule reconnection attempt
     */
    scheduleReconnect(endpoint) {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('Max reconnection attempts reached');
            this.emit('reconnect_failed');
            return;
        }

        this.reconnectAttempts++;
        const delay = this.reconnectInterval * Math.min(this.reconnectAttempts, 5);

        console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);

        setTimeout(() => {
            if (this.shouldReconnect && !this.isConnected) {
                this.connect(endpoint).catch(err => {
                    console.error('Reconnection failed:', err);
                });
            }
        }, delay);
    }

    /**
     * Handle incoming WebSocket message
     */
    handleMessage(event) {
        try {
            const message = JSON.parse(event.data);
            const type = message.type;

            // Handle system messages
            if (type === 'connected') {
                this.clientId = message.client_id;
            } else if (type === 'pong') {
                // Pong received, connection is alive
                return;
            }

            // Emit message event
            this.emit('message', message);

            // Emit specific event type
            if (type) {
                this.emit(type, message);
            }

        } catch (error) {
            console.error('Error parsing WebSocket message:', error);
        }
    }

    /**
     * Send a message to the server
     * @param {string} type - Message type
     * @param {object} data - Message data
     * @param {string} channel - Optional channel
     */
    send(type, data = {}, channel = null) {
        const message = {
            type,
            data,
            channel,
            timestamp: new Date().toISOString(),
        };

        if (this.isConnected && this.socket) {
            this.socket.send(JSON.stringify(message));
        } else {
            // Queue message for later
            this.messageQueue.push(message);
        }
    }

    /**
     * Send raw JSON message
     */
    sendRaw(message) {
        if (this.isConnected && this.socket) {
            this.socket.send(JSON.stringify(message));
        } else {
            this.messageQueue.push(message);
        }
    }

    /**
     * Flush message queue
     */
    flushMessageQueue() {
        while (this.messageQueue.length > 0 && this.isConnected) {
            const message = this.messageQueue.shift();
            this.socket.send(JSON.stringify(message));
        }
    }

    /**
     * Subscribe to a channel
     * @param {string} channel - Channel name
     */
    subscribe(channel) {
        this.subscriptions.add(channel);

        if (this.isConnected) {
            this.send('subscribe', {}, channel);
        }
    }

    /**
     * Unsubscribe from a channel
     * @param {string} channel - Channel name
     */
    unsubscribe(channel) {
        this.subscriptions.delete(channel);

        if (this.isConnected) {
            this.send('unsubscribe', {}, channel);
        }
    }

    /**
     * Resubscribe to all channels after reconnect
     */
    resubscribe() {
        for (const channel of this.subscriptions) {
            this.send('subscribe', {}, channel);
        }
    }

    /**
     * Start ping timer to keep connection alive
     */
    startPingTimer() {
        this.stopPingTimer();
        this.pingTimer = setInterval(() => {
            if (this.isConnected) {
                this.send('ping');
            }
        }, this.pingInterval);
    }

    /**
     * Stop ping timer
     */
    stopPingTimer() {
        if (this.pingTimer) {
            clearInterval(this.pingTimer);
            this.pingTimer = null;
        }
    }

    /**
     * Register an event handler
     * @param {string} event - Event name
     * @param {Function} handler - Event handler
     */
    on(event, handler) {
        if (!this.eventHandlers.has(event)) {
            this.eventHandlers.set(event, new Set());
        }
        this.eventHandlers.get(event).add(handler);

        // Return unsubscribe function
        return () => {
            this.off(event, handler);
        };
    }

    /**
     * Remove an event handler
     * @param {string} event - Event name
     * @param {Function} handler - Event handler
     */
    off(event, handler) {
        const handlers = this.eventHandlers.get(event);
        if (handlers) {
            handlers.delete(handler);
        }
    }

    /**
     * Emit an event to all registered handlers
     * @param {string} event - Event name
     * @param {*} data - Event data
     */
    emit(event, data) {
        const handlers = this.eventHandlers.get(event);
        if (handlers) {
            handlers.forEach(handler => {
                try {
                    handler(data);
                } catch (error) {
                    console.error(`Error in event handler for '${event}':`, error);
                }
            });
        }
    }

    /**
     * Get connection status
     */
    getStatus() {
        return {
            connected: this.isConnected,
            connecting: this.isConnecting,
            clientId: this.clientId,
            subscriptions: Array.from(this.subscriptions),
            queuedMessages: this.messageQueue.length,
        };
    }
}


/**
 * Task-specific WebSocket connection
 */
class TaskWebSocket extends WebSocketManager {
    constructor() {
        super();
        this.taskHandlers = new Map();
    }

    /**
     * Connect to tasks WebSocket endpoint
     */
    async connectTasks() {
        await this.connect('/ws/tasks');

        // Set up task event handlers
        this.on('task_update', (msg) => this.handleTaskUpdate(msg));
        this.on('task_started', (msg) => this.handleTaskStarted(msg));
        this.on('task_completed', (msg) => this.handleTaskCompleted(msg));
        this.on('task_failed', (msg) => this.handleTaskFailed(msg));
    }

    handleTaskUpdate(message) {
        this.emit('tasks:update', message.data);
    }

    handleTaskStarted(message) {
        this.emit('tasks:started', message.data);
        if (window.toast) {
            window.toast.info(`Task started: ${message.data?.name || 'Unknown'}`);
        }
    }

    handleTaskCompleted(message) {
        this.emit('tasks:completed', message.data);
        if (window.toast) {
            window.toast.success(`Task completed: ${message.data?.name || 'Unknown'}`);
        }
    }

    handleTaskFailed(message) {
        this.emit('tasks:failed', message.data);
        if (window.toast) {
            window.toast.error(`Task failed: ${message.data?.name || 'Unknown'}`);
        }
    }

    /**
     * Request a task status refresh
     */
    refreshTasks() {
        this.send('refresh');
    }

    /**
     * Subscribe to a specific task's updates
     */
    subscribeToTask(taskId) {
        this.send('subscribe_task', { task_id: taskId });
    }
}


// Create singleton instances
const wsManager = new WebSocketManager();
const taskWS = new TaskWebSocket();

// Export
export { WebSocketManager, TaskWebSocket, wsManager, taskWS };

// Make available globally
if (typeof window !== 'undefined') {
    window.wsManager = wsManager;
    window.taskWS = taskWS;
    window.WebSocketManager = WebSocketManager;
    window.TaskWebSocket = TaskWebSocket;
}
