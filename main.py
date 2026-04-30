import asyncio
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
import uvicorn

app = FastAPI()

# Все подключённые WebSocket клиенты (телефоны)
connected_phones: list[WebSocket] = []

# Последний кадр с телефона
last_frame: bytes = b""


@app.post("/frame")
async def receive_frame(request: Request):
    global last_frame
    last_frame = await request.body()
    return Response(status_code=200)


@app.get("/latest.jpg")
async def get_frame():
    if not last_frame:
        return Response(status_code=204)
    return Response(content=last_frame, media_type="image/jpeg")


@app.websocket("/ws/commands")
async def ws_commands(websocket: WebSocket):
    await websocket.accept()
    connected_phones.append(websocket)
    try:
        while True:
            # Держим соединение живым, читаем пинги
            await websocket.receive_text()
    except WebSocketDisconnect:
        connected_phones.remove(websocket)


@app.post("/start")
async def start_capture():
    """Кнопка на сайте → отправляем команду на все подключённые телефоны"""
    if not connected_phones:
        return {"ok": False, "error": "Телефон не подключён"}
    
    dead = []
    for phone in connected_phones:
        try:
            await phone.send_text('{"type":"start_capture"}')
        except Exception:
            dead.append(phone)
    
    for d in dead:
        connected_phones.remove(d)
    
    return {"ok": True, "sent_to": len(connected_phones)}


@app.post("/cmd")
async def send_command(request: Request):
    """Тап/свайп/назад/домой с сайта → на телефон"""
    body = await request.json()
    dead = []
    for phone in connected_phones:
        try:
            import json
            await phone.send_text(json.dumps(body))
        except Exception:
            dead.append(phone)
    for d in dead:
        connected_phones.remove(d)
    return {"ok": True}


@app.get("/status")
async def status():
    return {"online": len(connected_phones) > 0, "phones": len(connected_phones)}


@app.get("/")
async def index():
    with open("index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
