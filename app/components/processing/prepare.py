import hashlib
import json
import resource
import sys
from pathlib import Path

import av

from app.libs.subprocesses import ResourceLimit, run_limited

RATE = 16000
MAX_PCM_BYTES = 48 * 1024 * 1024


class PreparationError(Exception):
    pass


def encode_segment(raw, target, start, samples):
    with raw.open("rb") as source, av.open(str(target), "w", format="flac") as output:
        source.seek(start * 2)
        stream = output.add_stream("flac", rate=RATE)
        stream.layout = "mono"
        done = 0
        while done < samples:
            count = min(4096, samples - done)
            frame = av.AudioFrame(format="s16", layout="mono", samples=count)
            frame.sample_rate = RATE
            frame.pts = done
            frame.planes[0].update(source.read(count * 2))
            for packet in stream.encode(frame):
                output.mux(packet)
            done += count
        for packet in stream.encode(None):
            output.mux(packet)


def prepare_file(source, directory, config):
    raw = directory / "decoded.pcm"
    count = 0
    with av.open(str(source)) as container, raw.open("wb") as pcm:
        stream = next((s for s in container.streams if s.type == "audio"), None)
        if stream is None:
            raise PreparationError
        resampler = av.AudioResampler(format="s16", layout="mono", rate=RATE)

        def write(frames):
            nonlocal count
            for frame in frames:
                count += frame.samples
                if count * 2 > MAX_PCM_BYTES:
                    raise PreparationError
                pcm.write(bytes(frame.planes[0])[: frame.samples * 2])

        for frame in container.decode(stream):
            write(resampler.resample(frame))
        write(resampler.resample(None))
    if count <= 0:
        raise PreparationError
    manifest = []

    def split(start, samples):
        target = directory / f"{start}-{samples}.flac"
        encode_segment(raw, target, start, samples)
        if target.stat().st_size > config.segment_bytes:
            target.unlink()
            if samples < 2:
                raise PreparationError
            half = samples // 2
            split(start, half)
            split(start + half, samples - half)
        else:
            target.chmod(0o600)
            manifest.append(
                {
                    "startSample": start,
                    "samples": samples,
                    "file": target.name,
                    "bytes": target.stat().st_size,
                    "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                }
            )

    width = config.segment_seconds * RATE
    for start in range(0, count, width):
        split(start, min(width, count - start))
    raw.unlink()
    return {"version": 1, "sampleRate": RATE, "totalSamples": count, "segments": manifest}


def prepare_audio(source, directory, config):
    try:
        output = run_limited(
            [
                sys.executable,
                "-m",
                "app.components.processing.prepare",
                str(source),
                str(directory),
                str(config.segment_seconds),
                str(config.segment_bytes),
                str(config.prepare_cpu_seconds),
            ],
            timeout=config.prepare_timeout,
            max_output=131072,
        )
        return json.loads(output)
    except (OSError, ValueError, ResourceLimit) as error:
        raise PreparationError from error


def main():
    from app.components.processing.config import ProcessingSettings

    config = ProcessingSettings(
        segment_seconds=int(sys.argv[3]),
        segment_bytes=int(sys.argv[4]),
        prepare_cpu_seconds=int(sys.argv[5]),
    )
    resource.setrlimit(
        resource.RLIMIT_CPU, (config.prepare_cpu_seconds, config.prepare_cpu_seconds)
    )
    if sys.platform != "darwin":
        resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024))
    av.logging.set_level(av.logging.PANIC)
    try:
        print(json.dumps(prepare_file(Path(sys.argv[1]), Path(sys.argv[2]), config)))
        return 0
    except Exception:
        return 1


if __name__ == "__main__":
    sys.exit(main())
