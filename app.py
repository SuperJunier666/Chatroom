from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import datetime
import sqlite3

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins='*')
users = {}

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
        del users[request.sid]
    emit('user list', {'users': list(users.values())}, broadcast=True)
    print('Client disconnected')

@socketio.on('user joined')
def handle_user_joined(data):
    username = data['username']
    if username in users.values():
        emit('username taken', {'username': username})
    else:
        users[request.sid] = username
        emit('join successful', {'username': username})
        emit('user list', {'users': list(users.values())}, broadcast=True)
        emit('user joined', data, broadcast=True, include_self=False)

@socketio.on('chat message')
def handle_message(data):
    data['timestamp'] = datetime.datetime.now().strftime('%H:%M')
    with sqlite3.connect('chat.db') as conn:
        cursor = conn.cursor()
        cursor.execute('INSERT INTO messages (username, message, timestamp) VALUES (?, ?, ?)',
                       (data['username'], data['message'], data['timestamp']))
        conn.commit()
    emit('chat message', data, broadcast=True)

@socketio.on('typing')
def handle_typing(data):
    emit('typing', data, broadcast=True, include_self=False)

@socketio.on('stop typing')
def handle_stop_typing(data):
    emit('stop typing', data, broadcast=True, include_self=False)

if __name__ == '__main__':
    init_db()
    socketio.run(app)