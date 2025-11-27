# server.py
import asyncio
from typing import List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(title="WebSocket microservice")

# Si tu veux autoriser le navigateur à se connecter depuis d'autres origines,
# décommente / adapte les origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # -> restreindre en production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}


class ConnectionManager:
    def __init__(self):
        self.active: List[WebSocket] = []
        self.lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self.lock:
            self.active.append(websocket)

    async def disconnect(self, websocket: WebSocket):
        async with self.lock:
            if websocket in self.active:
                self.active.remove(websocket)

    async def broadcast(self, message: str, sender: WebSocket | None = None):
        async with self.lock:
            to_remove = []
            for connection in list(self.active):
                if connection is sender:
                    continue
                try:
                    await connection.send_text(message)
                except Exception:
                    # marque pour suppression si connexion morte
                    to_remove.append(connection)
            for r in to_remove:
                if r in self.active:
                    self.active.remove(r)


manager = ConnectionManager()


@app.websocket("/ws/hello")
async def websocket_hello(websocket: WebSocket):
    """
    Simple echo-style websocket: envoie "Hello" puis renvoie ce que l'utilisateur envoie.
    """
    await websocket.accept()
    try:
        await websocket.send_text("Hello")
        while True:
            # receive_text can raise WebSocketDisconnect
            message = await websocket.receive_text()
            await websocket.send_text("vous avez dit: " + message)
    except WebSocketDisconnect:
        # closed by client
        await websocket.close()
    except Exception:
        # catch-all pour éviter que l'endpoint plante
        try:
            await websocket.close()
        except Exception:
            pass


@app.websocket("/ws/broadcast/{name}")
async def websocket_broadcast(websocket: WebSocket, name: str):
    """
    Broadcast endpoint: chaque message reçu est renvoyé à tous les autres clients.
    Envoie un message de bienvenue avec le nombre de connexions.
    """
    await manager.connect(websocket)
    try:
        # bienvenue
        await websocket.send_text(f"Bienvenue {name}, il y a {len(manager.active)} connecte(s).")
        # boucle principale
        while True:
            message = await websocket.receive_text()
            text = f"{name}: {message}"
            await manager.broadcast(text, sender=websocket)
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception:
        # sécurité: déconnecte proprement si erreur inattendue
        await manager.disconnect(websocket)
        try:
            await websocket.close()
        except Exception:
            pass


# Optionnel: endpoint pour voir nombre de connexions depuis HTTP
@app.get("/metrics")
async def metrics():
    return {"active_connections": len(manager.active)}


if __name__ == "__main__":
    # Développement : lance avec uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
