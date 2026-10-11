import json
import math
import sys

import av


def probe(path):
    with (
        open(path, "rb") as source,
        av.open(
            source,
            options={
                "format_whitelist": "wav,mp3,mov,flac,ogg,matroska,webm",
                "enable_drefs": "0",
                "probesize": str(4 * 1024 * 1024),
                "analyzeduration": "5000000",
            },
        ) as container,
    ):
        formats = set(container.format.name.split(","))
        kinds = {
            "wav": "audio/wav",
            "mp3": "audio/mpeg",
            "mov": "audio/mp4",
            "flac": "audio/flac",
            "ogg": "audio/ogg",
            "webm": "audio/webm",
            "matroska": "audio/webm",
        }
        content_type = next((value for kind, value in kinds.items() if kind in formats), None)
        if not content_type or not container.streams.audio:
            raise ValueError
        for stream in container.streams.video:
            if not stream.disposition & av.stream.Disposition.attached_pic:
                raise ValueError
        stream = container.streams.audio[0]
        stream.codec_context.thread_count = 1
        frame = next(container.decode(stream), None)
        if frame is None or frame.samples < 1:
            raise ValueError
        duration = container.duration / av.time_base if container.duration is not None else None
        if duration is not None and (not math.isfinite(duration) or duration <= 0):
            duration = None
        return {"content_type": content_type, "duration_seconds": duration}


if __name__ == "__main__":
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
        if sys.platform == "linux":
            resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
        print(json.dumps(probe(sys.argv[1])))
    except Exception:
        sys.exit(1)
