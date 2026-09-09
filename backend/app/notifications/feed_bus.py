"""In-process broadcast for notification feed updates.

Listeners register an asyncio.Event; `notify()` sets all of them so
waiting SSE connections wake up and poll the DB for new rows.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager

_listeners: set[asyncio.Event] = set()


def notify() -> None:
    for evt in _listeners:
        evt.set()


@contextmanager
def listen():
    evt = asyncio.Event()
    _listeners.add(evt)
    try:
        yield evt
    finally:
        _listeners.discard(evt)
