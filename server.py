#!/usr/bin/env python3
import threading
import time
import os
from flask import Flask, Response, request
from flask_sock import Sock

app = Flask(__name__)
sock = Sock(app)

latest_frame = None
frame_lock   = threading.Lock()
frame_event  = threading.Event()

phone_ws   = None
phone_lock = threading.Lock()

@app.route('/frame', methods=['POST'])
def receive_frame():
    global latest_frame
    data = request.get_data()
    if data:
        with frame_lock:
            latest_frame = data
        frame_event.set()
        frame_event.clear()
    return '', 204

def mjpeg_generator():
    while True:
        frame_event.wait(timeout=2.0)
        with frame_lock:
            frame = latest_frame
        if frame:
            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' +
                frame + b'\r\n'
            )
        else:
            time.sleep(0.05)

@app.route('/stream')
def stream():
    return Response(
        mjpeg_generator(),
        mimetype='multipart/x-mixed-replace; boundary=frame',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )

@sock.route('/ws/browser')
def ws_browser(ws):
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
    global phone_ws
    with phone_lock:
        phone_ws = ws
    print("[+] Телефон подключён")
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

@app.route('/status')
def status():
    return {
        'phone_control': phone_ws is not None,
        'streaming':     latest_frame is not None,
    }

@app.route('/')
def index():
    with open('index.html', 'r', encoding='utf-8') as f:
        return f.read()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    print(f"  PhoneMonitor запущен на порту {port}")
    app.run(host='0.0.0.0', port=port, threaded=True)
