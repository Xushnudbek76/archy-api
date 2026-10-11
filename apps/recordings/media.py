import json
import subprocess
import sys
from pathlib import Path


class InvalidAudio(Exception):
    pass


def inspect_audio(path):
    try:
        result = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("probe.py")), str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=30,
        )
        return json.loads(result.stdout)
    except (subprocess.SubprocessError, ValueError, OSError):
        raise InvalidAudio from None
