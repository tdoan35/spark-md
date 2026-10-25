import asyncio
from collections import deque
import json
from threading import RLock


class Events:
    def __init__(self):
        self.lock = RLock()
        self.sequence = 0
        self.history = deque(maxlen=2000)
        self.clients = set()

    def emit(self, event, payload):
        with self.lock:
            self.sequence += 1
            frame = f'id: {self.sequence}\nevent: {event}\ndata: {json.dumps(payload)}\n\n'
            self.history.append((self.sequence, frame))
            for loop, queue in tuple(self.clients):
                def deliver(q=queue, message=frame):
                    if q.full():
                        q.get_nowait()
                    q.put_nowait(message)
                if not loop.is_closed():
                    loop.call_soon_threadsafe(deliver)

    async def stream(self, last_id=None):
        queue = asyncio.Queue(maxsize=2000)
        client = (asyncio.get_running_loop(), queue)
        with self.lock:
            replay = [frame for seq, frame in self.history if last_id is not None and seq > last_id]
            self.clients.add(client)
        try:
            yield ': connected\nretry: 3000\n\n'
            for frame in replay:
                yield frame
            while True:
                try:
                    yield await asyncio.wait_for(queue.get(), 15)
                except asyncio.TimeoutError:
                    yield ': ping\n\n'
        finally:
            with self.lock:
                self.clients.discard(client)
