import subprocess
import sys


def test_worker_shutdown_cancellation_finishes(tmp_path):
    marker = tmp_path / "finished"
    code = """
import asyncio
import threading
from pathlib import Path
from app.libs.workers import run_worker

started = threading.Event()
release = threading.Event()

def persist():
    started.set()
    release.wait(2)
    Path(__import__('sys').argv[1]).write_text('finished')

async def main():
    asyncio.create_task(run_worker(persist))
    while not started.is_set():
        await asyncio.sleep(0.001)
    threading.Timer(0.1, release.set).start()

asyncio.run(main())
"""
    subprocess.run([sys.executable, "-c", code, str(marker)], check=True, timeout=3)
