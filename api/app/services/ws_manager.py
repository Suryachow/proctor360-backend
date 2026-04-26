from collections import defaultdict
from fastapi import WebSocket


class WSManager:
    def __init__(self):
        self.connections: dict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, channel: str, websocket: WebSocket):
        await websocket.accept()
        self.connections[channel].append(websocket)

    def disconnect(self, channel: str, websocket: WebSocket):
        if websocket in self.connections[channel]:
            self.connections[channel].remove(websocket)

    async def broadcast(self, channel: str, payload: dict):
        targets = list(self.connections[channel])
        if channel == "admin_violations":
            # Compatibility fan-out: admin dashboards may subscribe on either channel.
            targets.extend(self.connections["admin"])

        # De-duplicate sockets while preserving order.
        deduped = []
        seen = set()
        for conn in targets:
            key = id(conn)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(conn)

        stale = []
        for conn in deduped:
            try:
                await conn.send_json(payload)
            except Exception:
                stale.append(conn)
        for conn in stale:
            self.disconnect(channel, conn)
            if channel == "admin_violations":
                self.disconnect("admin", conn)


ws_manager = WSManager()
