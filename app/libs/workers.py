import asyncio
from functools import partial

import anyio


async def run_worker(function, *args, **kwargs):
    task = asyncio.create_task(anyio.to_thread.run_sync(partial(function, *args, **kwargs)))
    cancelled = False
    while True:
        try:
            result = await asyncio.shield(task)
            break
        except asyncio.CancelledError:
            if task.cancelled():
                raise
            cancelled = True
        except Exception:
            if cancelled:
                raise asyncio.CancelledError from None
            raise
    if cancelled:
        raise asyncio.CancelledError
    return result
