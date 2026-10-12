import json
import math
import re
import sys
import time

import httpx
from pydantic import ValidationError

from app.components.processing.notes import input_bound, request_body
from app.components.processing.schemas import LectureNote, Transcription
from app.libs.subprocesses import ResourceLimit, run_limited


class ProviderFailure(Exception):
    def __init__(self, code, *, retry_after=0, quota=False, permanent=False):
        self.code = code
        self.retry_after = retry_after
        self.quota = quota
        self.permanent = permanent
        super().__init__(code)


def reset_seconds(value):
    if not value or len(value) > 80:
        return 0
    try:
        if value.replace(".", "", 1).isdigit():
            seconds = float(value)
        else:
            parts = re.findall(r"(\d+(?:\.\d+)?)(ms|s|m|h)", value)
            if "".join(number + unit for number, unit in parts) != value:
                return 0
            seconds = sum(
                float(number) * {"ms": 0.001, "s": 1, "m": 60, "h": 3600}[unit]
                for number, unit in parts
            )
        return min(86400, max(0, math.ceil(seconds)))
    except (ValueError, OverflowError):
        return 0


def header_delay(headers):
    delays = [reset_seconds(headers.get("retry-after", ""))]
    for kind in ("tokens", "requests"):
        if headers.get(f"x-ratelimit-remaining-{kind}") == "0":
            delays.append(reset_seconds(headers.get(f"x-ratelimit-reset-{kind}", "")))
    return max(delays)


class GroqProvider:
    name = "groq"

    def __init__(self, api_key, transport=None):
        if not api_key:
            raise ValueError("Set GROQ_API_KEY privately before starting the worker")
        self.api_key = api_key
        self.transport = transport
        self.next_delay = 0

    def request(self, route, config, **arguments):
        if self.transport is not None:
            return self.request_inline(route, config, **arguments)
        payload = {"key": self.api_key, "route": route, "config": config.snapshot()}
        if "files" in arguments:
            payload["path"] = arguments["files"]["file"][1].name
            payload["data"] = arguments["data"]
        else:
            payload["json"] = arguments["json"]
        try:
            output = run_limited(
                [sys.executable, "-m", "app.components.processing.providers"],
                input=json.dumps(payload).encode(),
                timeout=config.provider_timeout,
                max_output=2 * 1024 * 1024 + 1024,
            )
            value = json.loads(output)
            if "error" in value:
                raise ProviderFailure(**value["error"])
            self.next_delay = value["delay"]
            return value["data"]
        except (OSError, ValueError, ResourceLimit) as error:
            raise ProviderFailure("provider_unavailable") from error

    def request_inline(self, route, config, **arguments):
        self.next_delay = 0
        deadline = time.monotonic() + config.provider_timeout
        try:
            with httpx.Client(
                transport=self.transport,
                timeout=httpx.Timeout(
                    min(45, config.provider_timeout), connect=10, write=30, pool=5
                ),
                follow_redirects=False,
                trust_env=False,
            ) as client:
                with client.stream(
                    "POST",
                    "https://api.groq.com/openai/v1/" + route,
                    headers={"Authorization": "Bearer " + self.api_key},
                    **arguments,
                ) as response:
                    wait = header_delay(response.headers)
                    if response.status_code == 429:
                        raise ProviderFailure(
                            "quota_wait", retry_after=max(60, wait or 3600), quota=True
                        )
                    if response.status_code in (401, 403):
                        raise ProviderFailure("provider_credentials", permanent=True)
                    if response.status_code >= 500:
                        raise ProviderFailure("provider_unavailable")
                    if response.status_code != 200:
                        raise ProviderFailure("provider_rejected", permanent=True)
                    content = bytearray()
                    for block in response.iter_bytes():
                        if (
                            time.monotonic() > deadline
                            or len(content) + len(block) > 2 * 1024 * 1024
                        ):
                            raise ProviderFailure("provider_response_limit")
                        content.extend(block)
                    self.next_delay = wait
                    return json.loads(content)
        except (httpx.HTTPError, ValueError, TypeError) as error:
            raise ProviderFailure("provider_unavailable") from error

    def transcribe(self, path, config):
        if path.stat().st_size > config.segment_bytes:
            raise ProviderFailure("audio_preparation", permanent=True)
        with path.open("rb") as source:
            result = self.request(
                "audio/transcriptions",
                config,
                files={"file": (path.name, source, "audio/flac")},
                data={
                    "model": "whisper-large-v3-turbo",
                    "response_format": "verbose_json",
                    "timestamp_granularities[]": "segment",
                    "temperature": "0",
                },
            )
        if not isinstance(result, dict):
            raise ProviderFailure("invalid_provider_output")
        language = {"english": "en", "korean": "ko"}.get(
            result.get("language"), result.get("language")
        )
        if language not in {"ko", "en"}:
            raise ProviderFailure("unsupported_language", permanent=True)
        try:
            return Transcription.model_validate(
                {
                    "text": result["text"],
                    "language": language,
                    "segments": [
                        {"start": float(s["start"]), "end": float(s["end"]), "text": s["text"]}
                        for s in result["segments"]
                    ],
                }
            ).model_dump()
        except (KeyError, TypeError, ValueError, ValidationError) as error:
            raise ProviderFailure("invalid_provider_output") from error

    def summarize(self, source, language, config):
        if input_bound(source, language, config) > config.input_tokens:
            raise ProviderFailure("summary_budget", permanent=True)
        result = self.request(
            "chat/completions", config, json=request_body(source, language, config)
        )
        try:
            choice = result["choices"][0]
            if choice["finish_reason"] != "stop":
                raise ValueError("Incomplete response")
            return LectureNote.model_validate_json(choice["message"]["content"]).model_dump()
        except (KeyError, IndexError, TypeError, ValueError, ValidationError) as error:
            raise ProviderFailure("invalid_provider_output") from error


class FixtureProvider:
    name = "fixture"
    next_delay = 0

    def transcribe(self, path, config):
        import av

        with av.open(str(path)) as media:
            duration = media.duration / av.time_base
        return {
            "text": "Synthetic fixture: a lecture explains functions and their inputs.",
            "language": "en",
            "segments": [
                {
                    "start": 0.0,
                    "end": float(duration),
                    "text": "Synthetic fixture: a lecture explains functions and their inputs.",
                }
            ],
        }

    def summarize(self, source, language, config):
        return {
            "overview": "Synthetic fixture notes about functions.",
            "key_concepts": ["Functions accept inputs."],
            "examples": [],
            "review_questions": ["What is a function input?"],
            "unclear_passages": [],
        }


def main():
    from pathlib import Path

    from app.components.processing.config import ProcessingSettings

    try:
        payload = json.loads(sys.stdin.buffer.read(2 * 1024 * 1024))
        config = ProcessingSettings(**payload["config"])
        provider = GroqProvider(payload["key"])
        route = payload["route"]
        if route == "audio/transcriptions":
            path = Path(payload["path"])
            if path.stat().st_size > config.segment_bytes:
                raise ProviderFailure("audio_preparation", permanent=True)
            with path.open("rb") as source:
                data = provider.request_inline(
                    route,
                    config,
                    data=payload["data"],
                    files={"file": (path.name, source, "audio/flac")},
                )
        elif route == "chat/completions":
            data = provider.request_inline(route, config, json=payload["json"])
        else:
            raise ProviderFailure("provider_rejected", permanent=True)
        print(json.dumps({"data": data, "delay": provider.next_delay}))
    except ProviderFailure as error:
        print(
            json.dumps(
                {
                    "error": {
                        "code": error.code,
                        "retry_after": error.retry_after,
                        "quota": error.quota,
                        "permanent": error.permanent,
                    }
                }
            )
        )
    except Exception:
        print(json.dumps({"error": {"code": "provider_unavailable"}}))


if __name__ == "__main__":
    main()
