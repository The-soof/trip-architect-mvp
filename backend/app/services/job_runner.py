from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from collections.abc import Callable
from typing import Any

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="trip-architect")


def submit_background_job(target: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    _executor.submit(target, *args, **kwargs)
