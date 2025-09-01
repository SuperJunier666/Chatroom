from flask import Flask, render_template, request, session
from flask_socketio import SocketIO, emit
import datetime
import sqlite3

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins='*')
users = {}
# 私聊会话状态表：记录当前正在进行的私聊会话
# 格式：{username: other_username} 表示username正在和other_username私聊
private_chat_sessions = {}

def init_db():
    with sqlite3.connect('chat.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS private_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_username TEXT NOT NULL,
                receiver_username TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                is_read INTEGER DEFAULT 0
            )
        ''')
        conn.commit()

@app.route('/')
def index():
    with sqlite3.connect('chat.db') as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT username, message, timestamp FROM messages ORDER BY timestamp ASC')
        messages = cursor.fetchall()
    return render_template('index.html', messages=messages)

@socketio.on('connect')
def test_connect():
    emit('my response', {'data': 'Connected'})

@socketio.on('disconnect')
def test_disconnect():
    if request.sid in users:
        username = users[request.sid].get('username')
        
        # 清理用户的私聊会话状态
        if username and is_user_in_private_chat(username):
            other_username = private_chat_sessions.get(username)
            remove_private_chat_session(username)
            
            # 通知对方用户已断线
            if other_username:
                other_sid = get_sid_by_username(other_username)
                if other_sid:
                    emit('private_chat_ended_by_disconnect', {
                        'username': username,
                        'message': f'{username} 已断线，私聊会话结束'
                    }, to=other_sid)
        
        del users[request.sid]
    
    user_list = [user['username'] for user in users.values()]
    emit('user list', {'users': user_list}, broadcast=True)
    print('Client disconnected')

@socketio.on('user joined')
def handle_user_joined(data):
    username = data['username']
    if any(user.get('username') == username for user in users.values()):
        emit('username taken', {'username': username})
    else:
        users[request.sid] = {'username': username}
        emit('join successful', {'username': username})
        user_list = [user['username'] for user in users.values()]
        emit('user list', {'users': user_list}, broadcast=True)
        emit('user joined', data, broadcast=True, include_self=False)

        with sqlite3.connect('chat.db') as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT sender_username, message, timestamp FROM private_messages WHERE receiver_username = ? AND is_read = 0', (username,))
            unread_messages = cursor.fetchall()
            for msg in unread_messages:
                emit('missed_private_message', {
                    'sender_username': msg[0],
                    'message': msg[1],
                    'timestamp': msg[2]
                })

            cursor.execute('UPDATE private_messages SET is_read = 1 WHERE receiver_username = ?', (username,))
            conn.commit()

@socketio.on('chat message')
def handle_message(data):
    data['timestamp'] = datetime.datetime.now().strftime('%H:%M')
    with sqlite3.connect('chat.db') as conn:
        cursor = conn.cursor()
        cursor.execute('INSERT INTO messages (username, message, timestamp) VALUES (?, ?, ?)',
                       (data['username'], data['message'], data['timestamp']))
        conn.commit()
    emit('chat message', data, broadcast=True)

def get_sid_by_username(username):
    for sid, user_data in users.items():
        if user_data.get('username') == username:
            return sid
    return None

def is_user_in_private_chat(username):
    """检查用户是否正在私聊中"""
    return username in private_chat_sessions

def add_private_chat_session(user1, user2):
    """添加私聊会话记录"""
    private_chat_sessions[user1] = user2
    private_chat_sessions[user2] = user1

def remove_private_chat_session(username):
    """移除用户的私聊会话记录"""
    if username in private_chat_sessions:
        other_user = private_chat_sessions[username]
        del private_chat_sessions[username]
        if other_user in private_chat_sessions:
            del private_chat_sessions[other_user]

@socketio.on('private_chat_request')
def handle_private_chat_request(data):
    recipient_username = data['recipient_username']
    sender_username = users.get(request.sid, {}).get('username')
    if not sender_username:
        return 
    
    # 检查发送者是否已经在私聊中
    if is_user_in_private_chat(sender_username):
        emit('private_chat_request_failed', {
            'error': 'you_are_busy',
            'message': '您当前正在私聊中，无法发起新的私聊请求'
        })
        return
    
    # 检查接收者是否已经在私聊中
    if is_user_in_private_chat(recipient_username):
        emit('private_chat_request_failed', {
            'error': 'recipient_busy',
            'message': f'{recipient_username} 正在和别人私聊，无法接受新的私聊请求'
        })
        return
    
    recipient_sid = get_sid_by_username(recipient_username)
    if recipient_sid:
        emit('private_chat_request', {'sender_username': sender_username}, to=recipient_sid)
    else:
        emit('private_chat_request_failed', {
            'error': 'user_offline',
            'message': f'{recipient_username} 当前不在线'
        })

@socketio.on('private_chat_accepted')
def handle_private_chat_accepted(data):
    sender_username = data['sender_username']
    recipient_username = users.get(request.sid, {}).get('username')
    if not recipient_username:
        return
    
    # 再次检查双方是否都空闲（防止并发请求导致的问题）
    if is_user_in_private_chat(sender_username) or is_user_in_private_chat(recipient_username):
        emit('private_chat_accept_failed', {
            'error': 'session_conflict',
            'message': '会话冲突，请稍后重试'
        })
        return
    
    sender_sid = get_sid_by_username(sender_username)
    if sender_sid:
        # 将双方加入私聊会话状态表
        add_private_chat_session(sender_username, recipient_username)
        
        emit('private_chat_started', {'other_user': recipient_username}, to=sender_sid)
        emit('private_chat_started', {'other_user': sender_username}, to=request.sid)
    else:
        emit('private_chat_accept_failed', {
            'error': 'sender_offline',
            'message': f'{sender_username} 已离线'
        })

@socketio.on('private_chat_rejected')
def handle_private_chat_rejected(data):
    sender_username = data['sender_username']
    recipient_username = users.get(request.sid, {}).get('username')
    if not recipient_username:
        return
    sender_sid = get_sid_by_username(sender_username)
    if sender_sid:
        emit('private_chat_rejected', {'recipient_username': recipient_username}, to=sender_sid)

@socketio.on('private_chat_ended')
def handle_private_chat_ended(data):
    """处理私聊结束事件"""
    username = users.get(request.sid, {}).get('username')
    if not username:
        return
    
    # 获取对方用户名
    other_username = private_chat_sessions.get(username)
    if other_username:
        # 清理会话状态
        remove_private_chat_session(username)
        
        # 通知对方会话已结束
        other_sid = get_sid_by_username(other_username)
        if other_sid:
            emit('private_chat_ended_by_other', {'username': username}, to=other_sid)
        
        # 确认给发起者
        emit('private_chat_ended_confirmed', {'other_user': other_username})

@socketio.on('private_message')
def handle_private_message(data):
    sender_username = users.get(request.sid, {}).get('username')
    recipient_username = data['receiver_username']
    message = data['message']
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if sender_username and recipient_username and message:
        recipient_sid = get_sid_by_username(recipient_username)

        with sqlite3.connect('chat.db') as conn:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO private_messages (sender_username, receiver_username, message, timestamp) VALUES (?, ?, ?, ?)',
                (sender_username, recipient_username, message, timestamp)
            )
            conn.commit()

        if recipient_sid:
            emit('private_message', {
                'sender_username': sender_username,
                'message': message,
                'timestamp': timestamp
            }, room=recipient_sid)

        emit('private_message_sent', {
            'recipient_username': recipient_username,
            'message': message,
            'timestamp': timestamp
        }, room=request.sid)

@socketio.on('typing')
def handle_typing(data):
    emit('typing', data, broadcast=True, include_self=False)

@socketio.on('stop typing')
def handle_stop_typing(data):
    emit('stop typing', data, broadcast=True, include_self=False)

if __name__ == '__main__':
    init_db()
    socketio.run(app)