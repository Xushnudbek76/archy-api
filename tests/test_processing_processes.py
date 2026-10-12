import sys
import time

import pytest


def test_bounded_process_timeout_kills_and_reaps_the_child():
    from app.libs.subprocesses import ResourceLimit, run_limited

    started = time.monotonic()
    with pytest.raises(ResourceLimit):
        run_limited(
            [sys.executable, "-c", "import time;time.sleep(20)"], timeout=0.2, max_output=1024
        )
    assert time.monotonic() - started < 3


def test_bounded_process_rejects_excessive_output_and_memory():
    from app.libs.subprocesses import ResourceLimit, run_limited

    with pytest.raises(ResourceLimit):
        run_limited([sys.executable, "-c", 'print("x"*10000)'], timeout=2, max_output=1024)
    with pytest.raises(ResourceLimit):
        run_limited(
            [sys.executable, "-c", "import time;data=bytearray(50*1024*1024);time.sleep(5)"],
            timeout=2,
            max_output=1024,
            memory_bytes=20 * 1024 * 1024,
        )
