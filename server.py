#!/usr/bin/env python3
"""
PhoneMonitor — VPS сервер
Принимает MJPEG кадры с телефона, отдаёт браузеру.
Пробрасывает команды управления (тапы/свайпы) через WebSocket.

Установка:
    pip install flask flask-sock

Запуск:
    python server.py

Автозапуск через systemd (опционально):
    sudo nano /etc/systemd/system/phonemonitor.service
    ---
    [Unit]
    Description=PhoneMonitor
    After=network.target

    [Service]
    ExecStart=/usr/bin/python3 /root/phonemonitor/server.py
    Restart=always

    [Install]
    WantedBy=multi-user.target
    ---
    sudo systemctl enable --now phonemonitor
"""

import threading
import time
from flask import Flask, Response, send_file
from flask_sock import Sock
import json
import io

app = Flask(__name__)
sock = Sock(app)

# Последний кадр с телефона (bytes)
latest_frame: bytes | None = None
frame_lock   = threading.Lock()
frame_event  = threading.Event()

# WebSocket подключение телефона (ControlService)
phone_ws      = None
phone_lock    = threading.Lock()

# ── Телефон → сервер: загружает кадр ─────────────────────────────────────────

@app.route('/frame', methods=['POST'])
def receive_frame():
    from flask import request
    global latest_frame
    data = request.get_data()
    if data:
        with frame_lock:
            latest_frame = data
        frame_event.set()
        frame_event.clear()
    return '', 204

# ── Браузер → MJPEG стрим ─────────────────────────────────────────────────────

def mjpeg_generator():
    while True:
        # Ждём новый кадр максимум 2 секунды
        frame_event.wait(timeout=2.0)
        with frame_lock:
            frame = latest_frame
        if frame:
            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' +
                frame +
                b'\r\n'
            )
        else:
            time.sleep(0.05)

@app.route('/stream')
def stream():
    return Response(
        mjpeg_generator(),
        mimetype='multipart/x-mixed-replace; boundary=frame',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',   # nginx не буферизует
        }
    )

# ── WebSocket: браузер → команды → телефон ────────────────────────────────────

@sock.route('/ws/browser')
def ws_browser(ws):
    """Браузер шлёт сюда команды (тапы, свайпы, кнопки)."""
    try:
        while True:
            msg = ws.receive(timeout=30)
            if msg is None:
                break
            with phone_lock:
                p = phone_ws
            if p:
                try:
                    p.send(msg)
                except Exception:
                    pass
    except Exception:
        pass

@sock.route('/ws/commands')
def ws_phone(ws):
    """ControlService на телефоне подключается сюда."""
    global phone_ws
    with phone_lock:
        phone_ws = ws
    print("[+] Телефон (ControlService) подключён")
    try:
        while True:
            msg = ws.receive(timeout=60)
            if msg is None:
                break
    except Exception:
        pass
    finally:
        with phone_lock:
            phone_ws = None
        print("[-] Телефон отключился")

# ── Статус ────────────────────────────────────────────────────────────────────

@app.route('/status')
def status():
    return {
        'phone_control': phone_ws is not None,
        'streaming':     latest_frame is not None,
    }

# ── Главная страница ──────────────────────────────────────────────────────────

@app.route('/')
def index():
    with open('index.html', 'r', encoding='utf-8') as f:
        return f.read()

# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("=" * 45)
    print("  PhoneMonitor Server")
    print("  Открой: http://<VPS_IP>:8080")
    print("=" * 45)
    app.run(host='0.0.0.0', port=8080, threaded=True)
