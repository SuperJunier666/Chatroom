import datetime
import sqlite3
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import socketio


app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")


sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')


socket_app = socketio.ASGIApp(sio)


templates = Jinja2Templates(directory="templates")


users = {}
private_chat_sessions = {}

def init_db():
    """初始化数据库和表结构"""
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

# -----------------
# 3. HTTP 路由 (FastAPI)
# -----------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """渲染主聊天页面并加载历史公共消息"""
    with sqlite3.connect('chat.db') as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT username, message, timestamp FROM messages ORDER BY timestamp ASC')
        messages = cursor.fetchall()
    # FastAPI 的模板渲染需要传递 request 对象
    return templates.TemplateResponse("index.html", {"request": request, "messages": messages})

# -----------------
# 4. Socket.IO 事件处理 (python-socketio)
# -----------------
# 注意：在 python-socketio 的异步模式下，
# SID (会话ID) 会作为第一个参数传递给事件处理函数，而不是通过 request 上下文获取。
# 所有 emit 操作都应使用 await sio.emit(...)

@sio.on('connect')
async def connect(sid, environ):
    """客户端连接事件"""
    print('Client connected:', sid)
    await sio.emit('my response', {'data': 'Connected'}, to=sid)

@sio.on('disconnect')
async def disconnect(sid):
    """客户端断开连接事件"""
    if sid in users:
        username = users[sid].get('username')
        
        # 清理用户的私聊会话状态
        if username and is_user_in_private_chat(username):
            other_username = private_chat_sessions.get(username)
            remove_private_chat_session(username)
            
            # 通知对方用户已断线
            if other_username:
                other_sid = get_sid_by_username(other_username)
                if other_sid:
                    await sio.emit('private_chat_ended_by_disconnect', {
                        'username': username,
                        'message': f'{username} 已断线，私聊会话结束'
                    }, to=other_sid)
        
        del users[sid]
        
        user_list = [user['username'] for user in users.values()]
        # 广播更新后的用户列表
        await sio.emit('user list', {'users': user_list})
    print('Client disconnected:', sid)

@sio.on('user joined')
async def handle_user_joined(sid, data):
    """用户加入聊天室事件"""
    username = data['username']
    if any(user.get('username') == username for user in users.values()):
        await sio.emit('username taken', {'username': username}, to=sid)
    else:
        users[sid] = {'username': username}
        await sio.emit('join successful', {'username': username}, to=sid)
        
        user_list = [user['username'] for user in users.values()]
        await sio.emit('user list', {'users': user_list})
        
        # 向其他用户广播新用户加入的消息
        # 在 python-socketio 中, include_self=False 等价于 skip_sid=sid
        await sio.emit('user joined', data, skip_sid=sid)

        # 检查并发送离线消息
        with sqlite3.connect('chat.db') as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT sender_username, message, timestamp FROM private_messages WHERE receiver_username = ? AND is_read = 0', (username,))
            unread_messages = cursor.fetchall()
            for msg in unread_messages:
                await sio.emit('missed_private_message', {
                    'sender_username': msg[0],
                    'message': msg[1],
                    'timestamp': msg[2]
                }, to=sid)
            # 标记为已读
            cursor.execute('UPDATE private_messages SET is_read = 1 WHERE receiver_username = ?', (username,))
            conn.commit()

@sio.on('chat message')
async def handle_message(sid, data):
    """处理公共聊天消息"""
    data['timestamp'] = datetime.datetime.now().strftime('%H:%M')
    with sqlite3.connect('chat.db') as conn:
        cursor = conn.cursor()
        cursor.execute('INSERT INTO messages (username, message, timestamp) VALUES (?, ?, ?)',
                       (data['username'], data['message'], data['timestamp']))
        conn.commit()
    await sio.emit('chat message', data)

# -----------------
# 5. 辅助函数
# -----------------
# 这些辅助函数基本保持不变，因为它们不直接与框架交互

def get_sid_by_username(username):
    for sid, user_data in users.items():
        if user_data.get('username') == username:
            return sid
    return None

def is_user_in_private_chat(username):
    return username in private_chat_sessions

def add_private_chat_session(user1, user2):
    private_chat_sessions[user1] = user2
    private_chat_sessions[user2] = user1

def remove_private_chat_session(username):
    if username in private_chat_sessions:
        other_user = private_chat_sessions.pop(username, None)
        if other_user and other_user in private_chat_sessions:
            private_chat_sessions.pop(other_user, None)


# -----------------
# 6. 私聊相关事件处理
# -----------------

@sio.on('private_chat_request')
async def handle_private_chat_request(sid, data):
    recipient_username = data['recipient_username']
    sender_username = users.get(sid, {}).get('username')
    if not sender_username:
        return
        
    if is_user_in_private_chat(sender_username):
        await sio.emit('private_chat_request_failed', {
            'error': 'you_are_busy', 'message': '您当前正在私聊中，无法发起新的私聊请求'
        }, to=sid)
        return
    
    if is_user_in_private_chat(recipient_username):
        await sio.emit('private_chat_request_failed', {
            'error': 'recipient_busy', 'message': f'{recipient_username} 正在和别人私聊，无法接受新的私聊请求'
        }, to=sid)
        return
    
    recipient_sid = get_sid_by_username(recipient_username)
    if recipient_sid:
        await sio.emit('private_chat_request', {'sender_username': sender_username}, to=recipient_sid)
    else:
        await sio.emit('private_chat_request_failed', {
            'error': 'user_offline', 'message': f'{recipient_username} 当前不在线'
        }, to=sid)

@sio.on('private_chat_accepted')
async def handle_private_chat_accepted(sid, data):
    sender_username = data['sender_username']
    recipient_username = users.get(sid, {}).get('username')
    if not recipient_username:
        return
        
    if is_user_in_private_chat(sender_username) or is_user_in_private_chat(recipient_username):
        await sio.emit('private_chat_accept_failed', {
            'error': 'session_conflict', 'message': '会话冲突，请稍后重试'
        }, to=sid)
        return
        
    sender_sid = get_sid_by_username(sender_username)
    if sender_sid:
        add_private_chat_session(sender_username, recipient_username)
        await sio.emit('private_chat_started', {'other_user': recipient_username}, to=sender_sid)
        await sio.emit('private_chat_started', {'other_user': sender_username}, to=sid)
    else:
        await sio.emit('private_chat_accept_failed', {
            'error': 'sender_offline', 'message': f'{sender_username} 已离线'
        }, to=sid)

@sio.on('private_chat_rejected')
async def handle_private_chat_rejected(sid, data):
    sender_username = data['sender_username']
    recipient_username = users.get(sid, {}).get('username')
    if not recipient_username:
        return
    sender_sid = get_sid_by_username(sender_username)
    if sender_sid:
        await sio.emit('private_chat_rejected', {'recipient_username': recipient_username}, to=sender_sid)

@sio.on('private_chat_ended')
async def handle_private_chat_ended(sid, data):
    username = users.get(sid, {}).get('username')
    if not username:
        return
    
    other_username = private_chat_sessions.get(username)
    if other_username:
        remove_private_chat_session(username)
        other_sid = get_sid_by_username(other_username)
        if other_sid:
            await sio.emit('private_chat_ended_by_other', {'username': username}, to=other_sid)
        await sio.emit('private_chat_ended_confirmed', {'other_user': other_username}, to=sid)


@sio.on('private_message')
async def handle_private_message(sid, data):
    sender_username = users.get(sid, {}).get('username')
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

        # 发送给接收者（如果在线）
        if recipient_sid:
            await sio.emit('private_message', {
                'sender_username': sender_username,
                'message': message,
                'timestamp': timestamp
            }, to=recipient_sid)

        # 回传给发送者，确认消息已发送
        await sio.emit('private_message_sent', {
            'recipient_username': recipient_username,
            'message': message,
            'timestamp': timestamp
        }, to=sid)

@sio.on('typing')
async def handle_typing(sid, data):
    await sio.emit('typing', data, skip_sid=sid)

@sio.on('stop typing')
async def handle_stop_typing(sid, data):
    await sio.emit('stop typing', data, skip_sid=sid)

# -----------------
# 7. 启动应用
# -----------------
# 将 Socket.IO 应用挂载到 FastAPI 应用的特定路径下
app.mount('/socket.io', socket_app)

if __name__ == '__main__':
    init_db()
    # 使用 uvicorn 运行 FastAPI 应用
    uvicorn.run("app_fastapi:app", host="0.0.0.0", port=5000, reload=True)