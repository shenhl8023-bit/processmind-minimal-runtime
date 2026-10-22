"""Small compatibility helpers shared by the Python 3.8 runtime."""

from __future__ import annotations

import asyncio
from functools import partial
from typing import Any, Callable, TypeVar


T = TypeVar("T")


def remove_suffix(value: str, suffix: str) -> str:
    """Return ``value`` without ``suffix`` when it is present."""

    if suffix and value.endswith(suffix):
        return value[: -len(suffix)]
    return value


async def run_in_thread(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run a blocking callable without relying on Python 3.9's ``to_thread``."""

    loop = asyncio.get_running_loop()
    call = partial(func, *args, **kwargs)
    return await loop.run_in_executor(None, call)
