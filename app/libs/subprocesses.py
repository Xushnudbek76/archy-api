import subprocess
import time


class ResourceLimit(Exception):
    pass


def run_limited(command, *, timeout, max_output, input=None, memory_bytes=768 * 1024 * 1024):
    deadline = time.monotonic() + timeout
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    payload = input
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ResourceLimit
            try:
                output, _ = process.communicate(input=payload, timeout=min(0.25, remaining))
                if process.returncode != 0 or len(output) > max_output:
                    raise ResourceLimit
                return output
            except subprocess.TimeoutExpired as error:
                payload = None
                if len(error.output or b"") > max_output:
                    raise ResourceLimit from None
                if process.poll() is None:
                    sample = subprocess.run(
                        ["ps", "-o", "rss=", "-p", str(process.pid)],
                        capture_output=True,
                        timeout=1,
                        text=True,
                    )
                    if sample.stdout.strip():
                        if int(sample.stdout.strip()) * 1024 > memory_bytes:
                            raise ResourceLimit from None
                    elif process.poll() is None:
                        raise ResourceLimit from None
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        raise ResourceLimit from error
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate()
