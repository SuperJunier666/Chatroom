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
    };

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
                const item = document.createElement('li');
                const statusIndicator = document.createElement('span');
                statusIndicator.className = 'online-indicator';
                item.append(statusIndicator, user);
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
                // Focus first interactive element in sidebar
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

    sidebarController.init();
    renderer.renderMessages();
    renderer.renderUserList();
});