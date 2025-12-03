/**
 * Chat Session Page
 * Individual chat session functionality
 */

import { chatAPI, ragAPI, vqaAPI } from '../core/api.js';
import { toast } from '../components/toast.js';
import { formatRelativeTime } from '../core/utils.js';

class ChatSessionPage {
    constructor() {
        this.sessionId = window.SESSION_ID;
        this.session = null;
        this.messages = [];
        this.isLoading = false;

        this.init();
    }

    async init() {
        if (!this.sessionId) {
            toast.error('No session ID provided');
            return;
        }

        console.log('Initializing Chat Session:', this.sessionId);

        this.bindEvents();
        await this.loadSession();

        console.log('Chat Session initialized');
    }

    bindEvents() {
        // Message form
        document.getElementById('message-form')?.addEventListener('submit', (e) => {
            e.preventDefault();
            this.sendMessage();
        });

        // Auto-resize textarea
        const input = document.getElementById('message-input');
        if (input) {
            input.addEventListener('input', (e) => this.autoResize(e.target));

            // Submit on Enter
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendMessage();
                }
            });
        }

        // End session
        document.getElementById('end-session')?.addEventListener('click', () => {
            this.endSession();
        });

        // Settings
        document.getElementById('session-settings')?.addEventListener('click', () => {
            toast.info('Settings coming soon');
        });
    }

    async loadSession() {
        try {
            const data = await chatAPI.getSession(this.sessionId);
            this.session = data;

            // Update UI
            document.getElementById('session-title').textContent =
                data.title || data.name || 'Chat Session';
            document.getElementById('session-mode').textContent =
                (data.mode || 'chat').toUpperCase();

            // Show context panel for RAG/VQA
            if (data.mode === 'rag' || data.mode === 'vqa') {
                document.getElementById('context-panel')?.classList.remove('hidden');

                if (data.mode === 'rag') {
                    document.getElementById('sources-section')?.classList.remove('hidden');
                } else if (data.mode === 'vqa') {
                    document.getElementById('frames-section')?.classList.remove('hidden');
                }
            }

            // Load messages
            await this.loadMessages();

        } catch (error) {
            console.error('Failed to load session:', error);
            toast.error('Failed to load session');
        }
    }

    async loadMessages() {
        const container = document.getElementById('messages');
        if (!container) return;

        try {
            const data = await chatAPI.getMessages(this.sessionId);
            this.messages = data?.messages || data || [];

            if (this.messages.length === 0) {
                container.innerHTML = `
                    <div class="text-center py-12 text-slate-400">
                        <i data-lucide="message-circle" class="w-12 h-12 mx-auto mb-4"></i>
                        <p>No messages yet. Start the conversation!</p>
                    </div>
                `;
            } else {
                container.innerHTML = this.messages.map(m => this.renderMessage(m)).join('');
                container.scrollTop = container.scrollHeight;
            }

        } catch (error) {
            console.error('Failed to load messages:', error);
            container.innerHTML = `
                <div class="text-center py-12 text-slate-400">
                    <p>Start a conversation</p>
                </div>
            `;
        }

        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    }

    renderMessage(message) {
        const role = message.role || (message.is_user ? 'user' : 'assistant');
        const content = message.content || message.text || '';
        const time = message.created_at || message.timestamp;

        // Process markdown
        let processedContent = content;
        if (typeof marked !== 'undefined') {
            processedContent = marked.parse(content);
        }

        return `
            <div class="message ${role}">
                <div class="message-content">
                    ${processedContent}
                </div>
                <p class="text-xs text-slate-500 mt-1 ${role === 'user' ? 'text-right' : ''}">
                    ${role === 'user' ? 'You' : 'AI'} · ${formatRelativeTime(time)}
                </p>
            </div>
        `;
    }

    autoResize(textarea) {
        textarea.style.height = 'auto';
        textarea.style.height = Math.min(textarea.scrollHeight, 150) + 'px';
    }

    async sendMessage() {
        if (this.isLoading) return;

        const input = document.getElementById('message-input');
        const content = input?.value?.trim();

        if (!content) return;

        this.isLoading = true;

        // Add user message to UI
        this.addMessageToUI('user', content);

        // Clear input
        input.value = '';
        this.autoResize(input);

        // Show typing indicator
        this.showTyping(true);

        try {
            let response;
            const mode = this.session?.mode || 'chat';

            switch (mode) {
                case 'rag':
                    response = await ragAPI.generate(content, {
                        session_id: this.sessionId
                    });

                    // Show sources if available
                    if (response.sources) {
                        this.renderSources(response.sources);
                    }
                    break;

                case 'vqa':
                    response = await vqaAPI.ask(this.sessionId, content);

                    // Show relevant frames if available
                    if (response.frames) {
                        this.renderFrames(response.frames);
                    }
                    break;

                default:
                    response = await chatAPI.sendMessage(this.sessionId, content);
            }

            // Extract response content
            const aiMessage = response?.response || response?.answer ||
                              response?.content || response?.message ||
                              'No response received';

            this.addMessageToUI('assistant', aiMessage);

        } catch (error) {
            console.error('Failed to send message:', error);
            this.addMessageToUI('assistant', `Error: ${error.message}`, true);
        } finally {
            this.showTyping(false);
            this.isLoading = false;
        }
    }

    addMessageToUI(role, content, isError = false) {
        const container = document.getElementById('messages');
        if (!container) return;

        // Remove empty state
        const emptyState = container.querySelector('.text-center');
        if (emptyState) emptyState.remove();

        // Process markdown
        let processedContent = content;
        if (typeof marked !== 'undefined') {
            processedContent = marked.parse(content);
        }

        const messageEl = document.createElement('div');
        messageEl.className = `message ${role}`;
        messageEl.innerHTML = `
            <div class="message-content ${isError ? 'border border-red-500/50' : ''}">
                ${processedContent}
            </div>
            <p class="text-xs text-slate-500 mt-1 ${role === 'user' ? 'text-right' : ''}">
                ${role === 'user' ? 'You' : 'AI'} · just now
            </p>
        `;

        container.appendChild(messageEl);
        container.scrollTop = container.scrollHeight;

        this.messages.push({ role, content });
    }

    showTyping(show) {
        const indicator = document.getElementById('typing-indicator');
        if (indicator) {
            indicator.classList.toggle('hidden', !show);
        }

        // Also scroll to bottom
        const container = document.getElementById('messages');
        if (container && show) {
            container.scrollTop = container.scrollHeight;
        }
    }

    renderSources(sources) {
        const container = document.getElementById('sources-list');
        if (!container || !sources || sources.length === 0) return;

        container.innerHTML = sources.map((source, i) => `
            <div class="p-2 bg-dark-tertiary rounded-lg text-sm">
                <p class="font-medium truncate">${source.title || `Source ${i + 1}`}</p>
                <p class="text-xs text-slate-400 mt-1 line-clamp-2">${source.snippet || source.text || ''}</p>
                ${source.video_id ? `
                    <a href="/videos/${source.video_id}" class="text-xs text-blue-400 hover:underline mt-1 block">
                        View video
                    </a>
                ` : ''}
            </div>
        `).join('');
    }

    renderFrames(frames) {
        const container = document.getElementById('frames-grid');
        if (!container || !frames || frames.length === 0) return;

        container.innerHTML = frames.map(frame => `
            <div class="relative aspect-video rounded overflow-hidden">
                <img src="${frame.url || frame.path}"
                     class="w-full h-full object-cover"
                     alt="Frame at ${frame.timestamp || ''}">
                ${frame.timestamp ? `
                    <span class="absolute bottom-1 right-1 px-1 py-0.5 bg-black/70 text-white text-xs rounded">
                        ${frame.timestamp}
                    </span>
                ` : ''}
            </div>
        `).join('');
    }

    async endSession() {
        if (!confirm('End this session?')) return;

        try {
            await chatAPI.endSession(this.sessionId);
            toast.success('Session ended');
            window.location.href = '/chat';
        } catch (error) {
            toast.error(`Failed to end session: ${error.message}`);
        }
    }
}

// Initialize page
const chatSessionPage = new ChatSessionPage();
window.chatSessionPage = chatSessionPage;

export { ChatSessionPage, chatSessionPage };
