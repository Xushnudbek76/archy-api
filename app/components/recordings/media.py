import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


class InvalidAudio(Exception):
    code = "invalid_audio"


class DurationError(InvalidAudio):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class AudioInfo:
    content_type: str
    duration_seconds: float | None


def inspect_audio(path: Path, max_duration_seconds: int | None = None) -> AudioInfo:
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).with_name("probe.py")),
                str(path),
                str(max_duration_seconds or 0),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=30,
        )
        data = json.loads(result.stdout)
        if data.get("error_code") in {"audio_too_long", "duration_unavailable"}:
            raise DurationError(data["error_code"])
        return AudioInfo(**data)
    except subprocess.TimeoutExpired:
        if max_duration_seconds is not None:
            raise DurationError("duration_unavailable") from None
        raise InvalidAudio from None
    except subprocess.CalledProcessError as error:
        if max_duration_seconds is not None and error.returncode < 0:
            raise DurationError("duration_unavailable") from None
        raise InvalidAudio from None
    except (ValueError, TypeError, OSError):
        raise InvalidAudio from None
