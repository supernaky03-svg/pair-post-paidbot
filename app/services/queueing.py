
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict

from ..core.logging import logger


JobFactory = Callable[[], Awaitable[object]]


@dataclass(slots=True)
class QueueJob:
    factory: JobFactory
    future: asyncio.Future
    description: str = ""


class SourceQueueManager:
    def __init__(self) -> None:
        self.queues: Dict[str, asyncio.Queue[QueueJob]] = {}
        self.tasks: Dict[str, asyncio.Task] = {}

    async def submit(self, source_key: str, factory: JobFactory, description: str = ""):
        queue = self.queues.setdefault(source_key, asyncio.Queue())
        if source_key not in self.tasks or self.tasks[source_key].done():
            self.tasks[source_key] = asyncio.create_task(self._worker(source_key))
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        await queue.put(QueueJob(factory=factory, future=future, description=description))
        return await future

    async def _worker(self, source_key: str) -> None:
        queue = self.queues[source_key]
        while True:
            job = await queue.get()
            try:
                result = await job.factory()
                if not job.future.done():
                    job.future.set_result(result)
            except Exception as exc:
                logger.exception("Source queue job failed for %s | %s", source_key, job.description)
                if not job.future.done():
                    job.future.set_exception(exc)
            finally:
                queue.task_done()
            if queue.empty():
                await asyncio.sleep(0)
                if queue.empty():
                    break
        self.tasks.pop(source_key, None)

    def pending_count(self, source_key: str) -> int:
        queue = self.queues.get(source_key)
        return queue.qsize() if queue else 0

    def total_pending(self) -> int:
        return sum(queue.qsize() for queue in self.queues.values())
