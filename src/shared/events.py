"""Events module."""
import asyncio
from typing import Callable, Any

_listeners: dict[str, list[Callable]] = {}

def on(event: str, callback: Callable):
    _listeners.setdefault(event, []).append(callback)

def emit(event: str, *args, **kwargs):
    for callback in _listeners.get(event, []):
        try:
            if asyncio.iscoroutinefunction(callback):
                asyncio.create_task(callback(*args, **kwargs))
            else:
                callback(*args, **kwargs)
        except Exception:
            pass
