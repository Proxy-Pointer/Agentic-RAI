"""
Trace Collector — real-time observability via SSE-compatible async queue.
All pipeline steps emit structured trace events to a global event stream.
The frontend maintains a persistent SSE connection to /api/stream.
"""
import asyncio
import time
from typing import Optional


class TraceCollector:
    def __init__(self):
        # Global subscriber queue — one per SSE client connection
        self._subscribers: list[asyncio.Queue] = []
        self._request_starts: dict[str, float] = {}

    def start_request(self, request_id: str):
        self._request_starts[request_id] = time.perf_counter()

    def _elapsed_ms(self, request_id: str) -> int:
        start = self._request_starts.get(request_id, time.perf_counter())
        return int((time.perf_counter() - start) * 1000)

    async def emit(
        self,
        request_id: str,
        agent: str,
        event: str,
        detail: str,
        status: str = "ok",   # ok | blocked | warn | hitl | done
    ):
        payload = {
            "type": "trace",
            "request_id": request_id,
            "t_ms": self._elapsed_ms(request_id),
            "agent": agent,
            "event": event,
            "detail": detail,
            "status": status,
        }
        dead = []
        for q in self._subscribers:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self._subscribers.remove(q)

    async def emit_response(self, request_id: str, response: dict):
        payload = {"type": "response", "request_id": request_id, **response}
        for q in self._subscribers:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    def subscribe(self) -> asyncio.Queue:
        """Create and register a new subscriber queue. Returns the queue."""
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self._subscribers:
            self._subscribers.remove(q)

    def cleanup_request(self, request_id: str):
        self._request_starts.pop(request_id, None)


# Module-level singleton
tracer = TraceCollector()
