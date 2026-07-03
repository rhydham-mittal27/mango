"""mango/tasks.py

Fire-and-forget background work with its own DB session — the pattern a
request handler uses to kick off something that shouldn't block the
response (send an email, trigger a scoring job, ...) without borrowing
the request's own session (which closes when the response is sent, long
before a background task finishes). Hand-rolled versions of this
routinely get two things wrong: they forget to open a fresh session, and
they let the task's exception vanish silently since `asyncio.create_task`
swallows it unless something is watching.

Classes: none.

Functions (2):
    - run_in_background: schedules a plain coroutine as a background
      task, logging (not swallowing) any exception it raises.
    - Database.spawn (see mango/db.py): the usual entry point — opens a
      fresh session for the task and commits/rolls back around it, on
      top of `run_in_background`.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

logger = logging.getLogger("mango.tasks")  # logger for background-task exceptions that would otherwise vanish silently

_background_tasks: set[asyncio.Task] = set()  # keeps a strong reference so tasks aren't GC'd mid-flight


def run_in_background(coro: Coroutine[Any, Any, Any], *, name: str | None = None) -> asyncio.Task:
    """Schedule `coro` as a fire-and-forget background task.

    Keeps a strong reference to the task (asyncio only holds a weak one,
    so an unreferenced task can be garbage-collected before it finishes —
    a well-known footgun) and logs any exception the task raises instead
    of letting it disappear, which is what `asyncio.create_task` alone
    does if nothing ever awaits or reads the task's result.
    """
    task = asyncio.create_task(coro, name=name)  # the scheduled task
    _background_tasks.add(task)  # hold a strong reference until the task finishes

    def _on_done(finished: asyncio.Task) -> None:
        """Log the task's exception (if any) and stop tracking it."""
        _background_tasks.discard(finished)
        if finished.cancelled():
            return
        exc = finished.exception()  # the task's exception, or None if it completed cleanly
        if exc is not None:
            logger.error("background task %r failed", finished.get_name(), exc_info=exc)

    task.add_done_callback(_on_done)
    return task
