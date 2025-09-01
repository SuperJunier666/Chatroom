document.addEventListener('DOMContentLoaded', () => {
    const socket = io();
    let username = '';

    const state = {
        messages: [],
        users: [],
        typingUsers: new Set(),
    };

    const ui = {
        sidebar: document.getElementById('sidebar'),
        chatArea: document.getElementById('chat-area'),
        messages: document.getElementById('messages'),
        userList: document.getElementById('user-list'),
        typingIndicator: document.getElementById('typing-indicator'),
        form: document.querySelector('form'),
        input: document.getElementById('m'),
        sidebarToggle: document.getElementById('sidebar-toggle'),
        usernameModal: document.getElementById('username-modal'),
        usernameInput: document.getElementById('username-input'),
        usernameSubmit: document.getElementById('username-submit'),
        usernameError: document.getElementById('username-error'),
        customConfirmModal: document.getElementById('custom-confirm-modal'),
        customConfirmText: document.getElementById('custom-confirm-text'),
        confirmYes: document.getElementById('confirm-yes'),
        confirmNo: document.getElementById('confirm-no'),
        privateChatRequestModal: document.getElementById('private-chat-request-modal'),
        privateChatRequestText: document.getElementById('private-chat-request-text'),
        acceptPrivateChat: document.getElementById('accept-private-chat'),
        rejectPrivateChat: document.getElementById('reject-private-chat'),
        privateChatWindow: document.getElementById('private-chat-window'),
        privateChatWith: document.getElementById('private-chat-with'),
        closePrivateChat: document.getElementById('close-private-chat'),
        privateMessages: document.getElementById('private-messages'),
        privateChatForm: document.getElementById('private-chat-form'),
        privateMessageInput: document.getElementById('private-m'),
    };

    function createPrivateMessageElement(data) {
        const liWrapper = document.createElement('li');
        liWrapper.classList.add('private-message-wrapper');

        const messageBubble = document.createElement('div');
        messageBubble.classList.add('private-message');

        if (data.sender_username === username) {
            liWrapper.classList.add('sent');
            messageBubble.classList.add('sent');
        } else {
            liWrapper.classList.add('received');
            messageBubble.classList.add('received');
        }

        messageBubble.textContent = data.message;

        const timestampSpan = document.createElement('span');
        timestampSpan.className = 'timestamp';
        timestampSpan.textContent = data.timestamp;

        liWrapper.append(messageBubble, timestampSpan);
        return liWrapper;
    }

    function showNotification(message) {
        const notification = document.createElement('div');
        notification.className = 'notification';
        notification.textContent = message;
        document.body.appendChild(notification);
        setTimeout(() => {
            notification.remove();
        }, 3000);
    }

    const renderer = {
        renderMessages() {
            ui.messages.innerHTML = '';
            state.messages.forEach(msg => {
                const item = this.createMessageElement(msg);
                ui.messages.appendChild(item);
            });
            ui.messages.scrollTop = ui.messages.scrollHeight;
        },

        createMessageElement(data) {
            const item = document.createElement('li');
            if (data.username === username) item.classList.add('self');
            if (data.type === 'user-joined') {
                item.classList.add('user-joined');
                item.textContent = data.message;
                return item;
            }

            const usernameSpan = document.createElement('span');
            usernameSpan.className = 'username';
            usernameSpan.textContent = data.username;

            const messageBody = document.createElement('div');
            messageBody.className = 'message-body';
            messageBody.textContent = data.message;

            const timestampSpan = document.createElement('span');
            timestampSpan.className = 'timestamp';
            timestampSpan.textContent = data.timestamp;

            item.append(usernameSpan, messageBody, timestampSpan);
            return item;
        },

        renderUserList() {
            ui.userList.innerHTML = '';
            state.users.forEach(user => {
                if (user === username) return; // Don't show self in user list for private chat
                const item = document.createElement('li');
                const statusIndicator = document.createElement('span');
                statusIndicator.className = 'online-indicator';
                item.append(statusIndicator, user);
                item.addEventListener('click', () => {
                    ui.customConfirmText.textContent = `Do you want to start a private chat with ${user}?`;
                    ui.customConfirmModal.style.display = 'flex'; // FIX: Use flex to center

                    const yesHandler = () => {
                        socket.emit('private_chat_request', { recipient_username: user });
                        const unreadBadge = item.querySelector('.unread-badge');
                        if (unreadBadge) {
                            unreadBadge.remove();
                        }
                        cleanup();
                    };

                    const noHandler = () => {
                        cleanup();
                    };

                    const cleanup = () => {
                        ui.customConfirmModal.style.display = 'none';
                        ui.confirmYes.removeEventListener('click', yesHandler);
                        ui.confirmNo.removeEventListener('click', noHandler);
                    };

                    ui.confirmYes.addEventListener('click', yesHandler);
                    ui.confirmNo.addEventListener('click', noHandler);
                });
                ui.userList.appendChild(item);
            });
        },

        renderTypingIndicator() {
            const typingList = Array.from(state.typingUsers).filter(u => u !== username);
            ui.typingIndicator.textContent = typingList.length > 0 ? `${typingList.join(', ')} is typing...` : '';
        },
    };

    const sidebarController = {
        isOpen: localStorage.getItem('sidebarOpen') !== 'false',

        init() {
            this.update();
            ui.sidebarToggle.addEventListener('click', () => this.toggle());
            ui.sidebarToggle.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    this.toggle();
                }
            });

            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape' && this.isOpen) {
                    this.toggle();
                }
            });
        },

        toggle() {
            this.isOpen = !this.isOpen;
            localStorage.setItem('sidebarOpen', this.isOpen);
            this.update();
        },

        update() {
            ui.sidebar.classList.toggle('collapsed', !this.isOpen);
            ui.sidebarToggle.setAttribute('aria-expanded', this.isOpen);
            if (this.isOpen) {
                const firstFocusable = ui.sidebar.querySelector('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
                if (firstFocusable) firstFocusable.focus();
            } else {
                ui.input.focus();
            }
        },
    };

    const handleUserLogin = () => {
        const enteredUsername = ui.usernameInput.value.trim();
        if (enteredUsername) {
            socket.emit('user joined', { username: enteredUsername });
        }
    };

    ui.usernameSubmit.addEventListener('click', handleUserLogin);
    ui.usernameInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') handleUserLogin();
    });

    ui.usernameInput.addEventListener('input', () => {
        ui.usernameError.textContent = '';
    });

    ui.form.addEventListener('submit', (e) => {
        e.preventDefault();
        if (ui.input.value) {
            socket.emit('chat message', { username, message: ui.input.value });
            socket.emit('stop typing', { username });
            ui.input.value = '';
        }
    });

    let typingTimeout;
    ui.input.addEventListener('input', () => {
        clearTimeout(typingTimeout);
        if (ui.input.value) {
            socket.emit('typing', { username });
            typingTimeout = setTimeout(() => {
                socket.emit('stop typing', { username });
            }, 3000);
        } else {
            socket.emit('stop typing', { username });
        }
    });

    // --- Socket.IO Event Listeners ---
    socket.on('connect', () => console.log('Connected to server'));
    socket.on('connect_error', (err) => console.error('Connection error:', err));

    socket.on('join successful', (data) => {
        username = data.username;
        ui.usernameModal.style.display = 'none';
        ui.input.focus();
    });

    socket.on('user joined', (data) => {
        state.messages.push({ type: 'user-joined', message: `${data.username} has joined.` });
        renderer.renderMessages();
    });

    socket.on('chat message', (data) => {
        state.messages.push({ type: 'chat', ...data });
        state.typingUsers.delete(data.username);
        renderer.renderMessages();
        renderer.renderTypingIndicator();
    });

    socket.on('user list', (data) => {
        state.users = data.users;
        renderer.renderUserList();
    });

    socket.on('typing', (data) => {
        state.typingUsers.add(data.username);
        renderer.renderTypingIndicator();
    });

    socket.on('stop typing', (data) => {
        state.typingUsers.delete(data.username);
        renderer.renderTypingIndicator();
    });

    socket.on('username taken', (data) => {
        ui.usernameError.textContent = `Username "${data.username}" is already taken. Please choose another one.`;
        ui.usernameInput.value = '';
        ui.usernameInput.focus();
    });

    // --- Private Chat Logic ---
    socket.on('private_chat_request', (data) => {
        ui.privateChatRequestText.textContent = `${data.sender_username} wants to chat with you.`;
        ui.privateChatRequestModal.style.display = 'flex'; // FIX: Use flex to center

        const acceptHandler = () => {
            socket.emit('private_chat_accepted', { sender_username: data.sender_username, receiver_username: username });
            cleanup();
        };

        const rejectHandler = () => {
            socket.emit('private_chat_rejected', { sender_username: data.sender_username, receiver_username: username });
            cleanup();
        };

        const cleanup = () => {
            ui.privateChatRequestModal.style.display = 'none';
            ui.acceptPrivateChat.removeEventListener('click', acceptHandler);
            ui.rejectPrivateChat.removeEventListener('click', rejectHandler);
        };

        ui.acceptPrivateChat.addEventListener('click', acceptHandler);
        ui.rejectPrivateChat.addEventListener('click', rejectHandler);
    });

    socket.on('private_chat_started', (data) => {
        ui.privateChatWith.textContent = data.other_user;
        ui.privateChatWindow.style.display = 'flex';
        ui.privateMessages.innerHTML = ''; // Clear previous messages
    });

    socket.on('private_chat_rejected', (data) => {
        showNotification(`${data.receiver_username} rejected your chat request.`);
    });

    // 处理私聊请求失败的情况
    socket.on('private_chat_request_failed', (data) => {
        showNotification(data.message);
    });

    // 处理私聊接受失败的情况
    socket.on('private_chat_accept_failed', (data) => {
        showNotification(data.message);
    });

    // 处理对方主动结束私聊
    socket.on('private_chat_ended_by_other', (data) => {
        showNotification(`${data.username} 结束了私聊`);
        ui.privateChatWindow.style.display = 'none';
    });

    // 处理对方断线导致私聊结束
    socket.on('private_chat_ended_by_disconnect', (data) => {
        showNotification(data.message);
        ui.privateChatWindow.style.display = 'none';
    });

    // 处理私聊结束确认
    socket.on('private_chat_ended_confirmed', (data) => {
        showNotification(`已结束与 ${data.other_user} 的私聊`);
    });

    socket.on('private_message_sent', (data) => {
        const item = createPrivateMessageElement({
            sender_username: username, 
            message: data.message,
            timestamp: data.timestamp
        });
        ui.privateMessages.appendChild(item);
        ui.privateMessages.scrollTop = ui.privateMessages.scrollHeight;
    });
    
    socket.on('private_message', (data) => {
        const item = createPrivateMessageElement(data);
        ui.privateMessages.appendChild(item);
        ui.privateMessages.scrollTop = ui.privateMessages.scrollHeight;
    });

    ui.closePrivateChat.addEventListener('click', () => {
        // 发送私聊结束事件到服务器
        socket.emit('private_chat_ended', {});
        ui.privateChatWindow.style.display = 'none';
    });

    ui.privateChatForm.addEventListener('submit', (e) => {
        e.preventDefault();
        if (ui.privateMessageInput.value) {
            const message = ui.privateMessageInput.value;
            const recipient = ui.privateChatWith.textContent;
            socket.emit('private_message', {
                sender_username: username,
                receiver_username: recipient,
                message: message
            });
            ui.privateMessageInput.value = '';
        }
    });


    // --- Initialization ---
    sidebarController.init();
    renderer.renderMessages();
    renderer.renderUserList();
});