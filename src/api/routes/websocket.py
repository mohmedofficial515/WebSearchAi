"""WebSocket stream — replays event history then live-pushes new events.

Each task gets its own channel `/ws/{task_id}`. The frontend opens one
WS per active task; backends fan events out via `utils.event_bus.bus`.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ...utils.event_bus import bus


router = APIRouter(tags=["websocket"])


@router.websocket("/ws/{task_id}")
async def ws_stream(ws: WebSocket, task_id: str) -> None:
    await ws.accept()
    q = bus.subscribe(task_id)
    try:
        for ev in bus.history(task_id):
            await ws.send_text(json.dumps(ev.to_dict(), ensure_ascii=False, default=str))
        while True:
            ev = await q.get()
            await ws.send_text(json.dumps(ev.to_dict(), ensure_ascii=False, default=str))
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(task_id, q)
