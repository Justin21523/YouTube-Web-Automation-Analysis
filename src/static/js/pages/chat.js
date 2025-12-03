/**
 * Chat Page
 * AI Chat sessions list and new chat creation
 */

import { chatAPI, ragAPI, vqaAPI } from '../core/api.js';
import { toast } from '../components/toast.js';
import { formatRelativeTime, getYouTubeThumbnail } from '../core/utils.js';

class ChatPage {
    constructor() {
        this.currentMode = 'chat';
        this.sessions = [];
        this.currentSession = null;
        this.messages = [];
        this.videoContext = null;

        this.init();
    }

    async init() {
        console.log('Initializing Chat Page...');

        this.bindEvents();
        await this.loadSessions();
        this.checkURLParams();

        console.log('Chat Page initialized');
    }

    bindEvents() {
        // Mode tabs
        document.querySelectorAll('.chat-mode-tab').forEach(tab => {
            tab.addEventListener('click', (e) => {
                this.switchMode(e.target.closest('.chat-mode-tab').dataset.mode);
            });
        });

        // New session button
        document.getElementById('new-session')?.addEventListener('click', () => {
            this.openNewSessionModal();
        });

        // Modal
        document.querySelectorAll('.close-modal').forEach(btn => {
            btn.addEventListener('click', () => this.closeModal());
        });

        document.getElementById('new-session-modal')?.addEventListener('click', (e) => {
            if (e.target.id === 'new-session-modal') this.closeModal();
        });

        document.getElementById('create-session')?.addEventListener('click', () => {
            this.createSession();
        });

        // Chat form
        document.getElementById('chat-form')?.addEventListener('submit', (e) => {
            e.preventDefault();
            this.sendMessage();
        });

        // Auto-resize textarea
        const chatInput = document.getElementById('chat-input');
        if (chatInput) {
            chatInput.addEventListener('input', (e) => {
                this.autoResize(e.target);
                this.updateCharCount();
            });

            // Submit on Enter (but not Shift+Enter)
            chatInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendMessage();
                }
            });
        }

        // Quick prompts
        document.querySelectorAll('.quick-prompt').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const prompt = e.target.dataset.prompt;
                if (chatInput) {
                    chatInput.value = prompt;
                    this.autoResize(chatInput);
                    this.updateCharCount();
                    chatInput.focus();
                }
            });
        });

        // Clear chat
        document.getElementById('clear-chat')?.addEventListener('click', () => {
            this.clearChat();
        });

        // Remove context
        document.getElementById('remove-context')?.addEventListener('click', () => {
            this.removeVideoContext();
        });
    }

    switchMode(mode) {
        this.currentMode = mode;

        // Update tabs
        document.querySelectorAll('.chat-mode-tab').forEach(tab => {
            tab.classList.toggle('active', tab.dataset.mode === mode);
        });

        // Update description
        const descriptions = {
            chat: '<strong>General Chat:</strong> Have natural conversations with AI about any topic.',
            rag: '<strong>RAG Query:</strong> Search and retrieve information from your scraped video content and captions.',
            vqa: '<strong>Visual Q&A:</strong> Ask questions about video frames and visual content.'
        };

        const descEl = document.getElementById('mode-description');
        if (descEl) {
            descEl.innerHTML = `<p>${descriptions[mode]}</p>`;
        }
    }

    async loadSessions() {
        const container = document.getElementById('sessions-list');
        if (!container) return;

        try {
            // Try to get sessions - this may fail if user ID is not set
            const userId = this.getUserId();
            const data = await chatAPI.getUserSessions(userId);
            this.sessions = data?.sessions || data || [];

            if (this.sessions.length === 0) {
                container.innerHTML = `
                    <div class="text-center py-8 text-slate-400">
                        <i data-lucide="message-circle" class="w-8 h-8 mx-auto mb-2"></i>
                        <p class="text-sm">No recent sessions</p>
                    </div>
                `;
            } else {
                container.innerHTML = this.sessions.map(s => this.renderSessionItem(s)).join('');
            }

        } catch (error) {
            console.error('Failed to load sessions:', error);
            container.innerHTML = `
                <div class="text-center py-8 text-slate-400">
                    <i data-lucide="message-circle" class="w-8 h-8 mx-auto mb-2"></i>
                    <p class="text-sm">Start a new chat</p>
                </div>
            `;
        }

        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    }

    renderSessionItem(session) {
        const title = session.title || session.name || 'Chat Session';
        const lastMessage = session.last_message || 'No messages yet';

        return `
            <a href="/chat/${session.id}"
               class="block p-3 rounded-lg hover:bg-dark-tertiary transition-colors">
                <p class="font-medium truncate">${title}</p>
                <p class="text-xs text-slate-400 truncate mt-1">${lastMessage}</p>
                <p class="text-xs text-slate-500 mt-1">${formatRelativeTime(session.updated_at || session.created_at)}</p>
            </a>
        `;
    }

    getUserId() {
        // Try to get user ID from localStorage or generate one
        let userId = localStorage.getItem('chatUserId');
        if (!userId) {
            userId = 'user_' + Math.random().toString(36).substring(2, 11);
            localStorage.setItem('chatUserId', userId);
        }
        return userId;
    }

    checkURLParams() {
        const params = new URLSearchParams(window.location.search);
        const videoId = params.get('video');

        if (videoId) {
            this.setVideoContext(videoId);
        }
    }

    async setVideoContext(videoId) {
        this.videoContext = videoId;

        const contextEl = document.getElementById('video-context');
        if (!contextEl) return;

        contextEl.classList.remove('hidden');
        document.getElementById('context-thumbnail').src = getYouTubeThumbnail(videoId);
        document.getElementById('context-title').textContent = `Video: ${videoId}`;

        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    }

    removeVideoContext() {
        this.videoContext = null;
        document.getElementById('video-context')?.classList.add('hidden');

        // Update URL
        const url = new URL(window.location);
        url.searchParams.delete('video');
        window.history.replaceState({}, '', url);
    }

    openNewSessionModal() {
        document.getElementById('new-session-modal')?.classList.remove('hidden');

        // Pre-fill mode based on current tab
        const modeSelect = document.getElementById('new-session-mode');
        if (modeSelect) {
            modeSelect.value = this.currentMode;
        }

        // Pre-fill video if context exists
        if (this.videoContext) {
            const videoInput = document.getElementById('new-session-video');
            if (videoInput) {
                videoInput.value = this.videoContext;
            }
        }

        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    }

    closeModal() {
        document.getElementById('new-session-modal')?.classList.add('hidden');
    }

    async createSession() {
        const mode = document.getElementById('new-session-mode')?.value || 'chat';
        const name = document.getElementById('new-session-name')?.value?.trim() || null;
        const videoId = document.getElementById('new-session-video')?.value?.trim() || null;

        try {
            const data = {
                user_id: this.getUserId(),
                mode: mode,
                title: name,
                video_id: videoId
            };

            const session = await chatAPI.createSession(data);
            toast.success('Session created');
            this.closeModal();

            // Navigate to session
            window.location.href = `/chat/${session.id}`;

        } catch (error) {
            toast.error(`Failed to create session: ${error.message}`);
        }
    }

    autoResize(textarea) {
        textarea.style.height = 'auto';
        textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
    }

    updateCharCount() {
        const input = document.getElementById('chat-input');
        const counter = document.getElementById('char-count');
        if (input && counter) {
            counter.textContent = `${input.value.length}/4000`;
        }
    }

    async sendMessage() {
        const input = document.getElementById('chat-input');
        const content = input?.value?.trim();

        if (!content) return;

        // Add user message to UI
        this.addMessage('user', content);

        // Clear input
        input.value = '';
        this.autoResize(input);
        this.updateCharCount();

        // Show typing indicator
        this.showTyping(true);

        try {
            let response;

            // Send based on mode
            switch (this.currentMode) {
                case 'rag':
                    response = await ragAPI.generate(content, {
                        video_id: this.videoContext
                    });
                    break;

                case 'vqa':
                    // VQA needs a session
                    if (!this.currentSession) {
                        // Create a quick session
                        const session = await vqaAPI.createSession({
                            video_id: this.videoContext,
                            user_id: this.getUserId()
                        });
                        this.currentSession = session.id;
                    }
                    response = await vqaAPI.ask(this.currentSession, content);
                    break;

                default:
                    // General chat - send directly or via session
                    if (!this.currentSession) {
                        // Create session first
                        const session = await chatAPI.createSession({
                            user_id: this.getUserId(),
                            mode: 'chat'
                        });
                        this.currentSession = session.id;
                    }
                    response = await chatAPI.sendMessage(this.currentSession, content);
            }

            // Add AI response
            const aiMessage = response?.response || response?.answer ||
                              response?.content || response?.message ||
                              'No response received';
            this.addMessage('assistant', aiMessage);

        } catch (error) {
            console.error('Failed to send message:', error);
            this.addMessage('assistant', `Error: ${error.message}`, true);
        } finally {
            this.showTyping(false);
        }
    }

    addMessage(role, content, isError = false) {
        const container = document.getElementById('messages-container');
        if (!container) return;

        // Remove welcome message if present
        const welcome = container.querySelector('.text-center');
        if (welcome) welcome.remove();

        const messageEl = document.createElement('div');
        messageEl.className = `message ${role}`;

        // Process content (basic markdown)
        let processedContent = content;
        if (typeof marked !== 'undefined') {
            processedContent = marked.parse(content);
        }

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
        // Simple typing indicator in chat area
        const container = document.getElementById('messages-container');
        if (!container) return;

        const existingIndicator = container.querySelector('.typing-indicator');

        if (show && !existingIndicator) {
            const indicator = document.createElement('div');
            indicator.className = 'typing-indicator message assistant';
            indicator.innerHTML = `
                <div class="message-content">
                    <div class="flex items-center gap-2">
                        <div class="flex gap-1">
                            <span class="w-2 h-2 bg-slate-500 rounded-full animate-bounce"></span>
                            <span class="w-2 h-2 bg-slate-500 rounded-full animate-bounce" style="animation-delay: 0.1s"></span>
                            <span class="w-2 h-2 bg-slate-500 rounded-full animate-bounce" style="animation-delay: 0.2s"></span>
                        </div>
                    </div>
                </div>
            `;
            container.appendChild(indicator);
            container.scrollTop = container.scrollHeight;
        } else if (!show && existingIndicator) {
            existingIndicator.remove();
        }
    }

    clearChat() {
        const container = document.getElementById('messages-container');
        if (!container) return;

        container.innerHTML = `
            <div class="text-center py-12">
                <div class="w-20 h-20 mx-auto mb-4 rounded-full bg-blue-500/20 flex items-center justify-center">
                    <i data-lucide="bot" class="w-10 h-10 text-blue-500"></i>
                </div>
                <h3 class="text-lg font-semibold mb-2">Chat Cleared</h3>
                <p class="text-slate-400 text-sm">Start a new conversation</p>
            </div>
        `;

        this.messages = [];
        this.currentSession = null;

        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    }
}

// Initialize page
const chatPage = new ChatPage();
window.chatPage = chatPage;

export { ChatPage, chatPage };
