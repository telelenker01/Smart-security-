from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_socketio import SocketIO, emit
from flask_babel import Babel, gettext
import sqlite3
import threading
import time
import logging
from datetime import datetime
import json
import os

app = Flask(__name__)
app.secret_key = 'telelenker_smart_security_2024'
app.config['BABEL_DEFAULT_LOCALE'] = 'en'
app.config['BABEL_SUPPORTED_LOCALES'] = ['en', 'de', 'fr', 'tr', 'ar', 'ur']

socketio = SocketIO(app, cors_allowed_origins="*")
babel = Babel(app)

# Language selection
@babel.localeselector
def get_locale():
    return session.get('language', 'en')

# Company Information
COMPANY_INFO = {
    'name': 'Telelenker',
    'slogan': 'Smart Security System',
    'phone1': '+92 315 2820296',
    'phone2': '+92 316 2260608',
    'email': 'telelenker@gmail.com',
    'website': 'https://telelenker01.github.io/Portfolio-/'
}

# Database setup
def init_db():
    conn = sqlite3.connect('cameras.db')
    c = conn.cursor()
    
    # Cameras table
    c.execute('''CREATE TABLE IF NOT EXISTS cameras
                 (id INTEGER PRIMARY KEY, 
                  camera_number INTEGER UNIQUE,
                  camera_name TEXT,
                  location TEXT,
                  ip_address TEXT,
                  status TEXT DEFAULT 'offline',
                  last_seen TIMESTAMP,
                  password TEXT)''')
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY,
                  username TEXT UNIQUE,
                  password TEXT,
                  role TEXT DEFAULT 'user',
                  allowed_cameras TEXT)''')
    
    # Connection log
    c.execute('''CREATE TABLE IF NOT EXISTS connections
                 (id INTEGER PRIMARY KEY,
                  camera_number INTEGER,
                  connection_time TIMESTAMP,
                  disconnect_time TIMESTAMP)''')
    
    # Default admin user
    c.execute("INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, ?)",
              ('admin', 'admin123', 'admin'))
    
    # Default cameras data
    for i in range(1, 11):
        c.execute("INSERT OR IGNORE INTO cameras (camera_number, camera_name, location, password) VALUES (?, ?, ?, ?)",
                  (i, f'Camera {i}', f'Location {i}', f'cam{i}pass'))
    
    conn.commit()
    conn.close()

init_db()

# ESP32-CAM API endpoints
@app.route('/api/camera/register', methods=['POST'])
def camera_register():
    data = request.json
    camera_number = data.get('camera_number')
    ip_address = request.remote_addr
    camera_name = data.get('camera_name', f'Camera {camera_number}')
    
    conn = sqlite3.connect('cameras.db')
    c = conn.cursor()
    
    # Mark camera as online
    c.execute('''UPDATE cameras SET 
                 status=?, ip_address=?, last_seen=?
                 WHERE camera_number=?''',
              ('online', ip_address, datetime.now(), camera_number))
    
    # Connection log
    c.execute('''INSERT INTO connections (camera_number, connection_time)
                 VALUES (?, ?)''', (camera_number, datetime.now()))
    
    conn.commit()
    conn.close()
    
    # Send real-time notification
    socketio.emit('camera_online', {
        'camera_number': camera_number,
        'camera_name': camera_name,
        'ip_address': ip_address,
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    
    return jsonify({
        'status': 'success',
        'message': f'Camera {camera_number} registered successfully'
    })

@app.route('/api/camera/heartbeat', methods=['POST'])
def camera_heartbeat():
    data = request.json
    camera_number = data.get('camera_number')
    
    conn = sqlite3.connect('cameras.db')
    c = conn.cursor()
    c.execute('''UPDATE cameras SET last_seen=? WHERE camera_number=?''',
              (datetime.now(), camera_number))
    conn.commit()
    conn.close()
    
    return jsonify({'status': 'success'})

@app.route('/api/audio/send', methods=['POST'])
def send_audio():
    data = request.json
    camera_number = data.get('camera_number')
    audio_message = data.get('message', '')
    
    # Send audio message to camera (simulated)
    socketio.emit('audio_message', {
        'camera_number': camera_number,
        'message': audio_message,
        'timestamp': datetime.now().strftime("%H:%M:%S")
    })
    
    return jsonify({'status': 'success', 'message': 'Audio sent'})

# Language setting
@app.route('/set_language/<lang>')
def set_language(lang):
    if lang in app.config['BABEL_SUPPORTED_LOCALES']:
        session['language'] = lang
    return redirect(request.referrer or url_for('index'))

# Web interface
@app.route('/')
def index():
    return render_template('index.html', company=COMPANY_INFO)

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')
    login_type = request.form.get('login_type')
    
    conn = sqlite3.connect('cameras.db')
    c = conn.cursor()
    
    if login_type == 'single':
        c.execute('''SELECT * FROM cameras WHERE camera_number=? AND password=?''',
                  (username, password))
        camera = c.fetchone()
        
        if camera:
            session['camera_number'] = camera[1]
            session['camera_name'] = camera[2]
            session['login_type'] = 'single'
            return redirect(url_for('camera_view'))
        else:
            return render_template('index.html', company=COMPANY_INFO, error='Invalid camera number or password')
    
    else:
        c.execute('''SELECT * FROM users WHERE username=? AND password=? AND role='admin' ''',
                  (username, password))
        user = c.fetchone()
        
        if user:
            session['username'] = user[1]
            session['role'] = user[3]
            session['login_type'] = 'admin'
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('index.html', company=COMPANY_INFO, error='Invalid admin credentials')

@app.route('/camera')
def camera_view():
    if 'camera_number' not in session:
        return redirect(url_for('index'))
    
    camera_number = session['camera_number']
    
    conn = sqlite3.connect('cameras.db')
    c = conn.cursor()
    c.execute('''SELECT * FROM cameras WHERE camera_number=?''', (camera_number,))
    camera = c.fetchone()
    conn.close()
    
    return render_template('camera.html', camera=camera, company=COMPANY_INFO)

@app.route('/admin')
def admin_dashboard():
    if 'username' not in session or session.get('login_type') != 'admin':
        return redirect(url_for('index'))
    
    conn = sqlite3.connect('cameras.db')
    c = conn.cursor()
    c.execute('''SELECT * FROM cameras ORDER BY camera_number''')
    cameras = c.fetchall()
    conn.close()
    
    return render_template('admin.html', cameras=cameras, company=COMPANY_INFO)

@app.route('/api/cameras/status')
def cameras_status():
    conn = sqlite3.connect('cameras.db')
    c = conn.cursor()
    c.execute('''SELECT camera_number, camera_name, status, last_seen FROM cameras''')
    cameras = c.fetchall()
    conn.close()
    
    cameras_list = []
    for cam in cameras:
        cameras_list.append({
            'number': cam[0],
            'name': cam[1],
            'status': cam[2],
            'last_seen': cam[3]
        })
    
    return jsonify(cameras_list)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# WebSocket events
@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('audio_message')
def handle_audio_message(data):
    # Broadcast audio message to specific camera
    emit('audio_receive', data, room=data['camera_number'])

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)