import asyncio
import json

import httpx

from app.components.processing.providers import header_delay
from app.libs.errors import ApiError


def invalid():
    return ApiError(
        502, "invalid_provider_output", "The tutor provider returned incomplete content."
    )


class EventParser:
    def __init__(self):
        self.buffer = bytearray()
        self.total = 0
        self.stopped = False
        self.done = False

    def feed(self, block):
        self.total += len(block)
        if self.total > 262144:
            raise invalid()
        self.buffer.extend(block)
        result = []
        while b"\n\n" in self.buffer or b"\r\n\r\n" in self.buffer:
            marker = b"\r\n\r\n" if b"\r\n\r\n" in self.buffer else b"\n\n"
            frame, _, remaining = self.buffer.partition(marker)
            self.buffer = bytearray(remaining)
            if len(frame) > 32768:
                raise invalid()
            lines = [
                line[5:].lstrip()
                for line in frame.decode("utf-8").splitlines()
                if line.startswith("data:")
            ]
            if not lines:
                continue
            data = "\n".join(lines)
            if self.done:
                raise invalid()
            if data == "[DONE]":
                if not self.stopped:
                    raise invalid()
                self.done = True
                continue
            value = json.loads(data)
            choices = value["choices"]
            if not choices:
                continue
            if self.stopped or len(choices) != 1:
                raise invalid()
            choice = choices[0]
            delta = choice["delta"]
            if delta.get("tool_calls"):
                raise invalid()
            text = delta.get("content")
            if text is not None:
                if not isinstance(text, str):
                    raise invalid()
                if text:
                    result.append(text)
            finish = choice.get("finish_reason")
            if finish is not None:
                if finish != "stop":
                    raise invalid()
                self.stopped = True
        if len(self.buffer) > 32768:
            raise invalid()
        return result

    def complete(self):
        if not self.done or self.buffer.strip():
            raise invalid()


async def stream_answer(body, config, *, transport=None):
    if config.backend == "fixture":
        sources = json.loads(body["messages"][1]["content"].split("\n", 1)[1])
        text = "Synthetic fixture tutor: " + sources[0]["text"][:300]
        for start in range(0, len(text), 40):
            await asyncio.sleep(0)
            yield text[start : start + 40]
        return
    if config.backend != "groq" or not config.api_key:
        raise ApiError(503, "tutor_unavailable", "Configure the tutor AI provider.")
    parser = EventParser()
    try:
        async with (
            asyncio.timeout(30),
            httpx.AsyncClient(
                transport=transport,
                timeout=httpx.Timeout(10, connect=5, pool=5),
                trust_env=False,
                follow_redirects=False,
            ) as client,
        ):
            async with client.stream(
                "POST",
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": "Bearer " + config.api_key},
                json=body,
            ) as response:
                if response.status_code == 429:
                    raise ApiError(
                        429,
                        "quota_wait",
                        "Tutor provider quota exhausted. Try later.",
                        retry_after=max(60, header_delay(response.headers) or 3600),
                    )
                if response.status_code != 200:
                    raise ApiError(
                        503, "tutor_provider_unavailable", "The tutor provider is unavailable."
                    )
                async for block in response.aiter_bytes():
                    for text in parser.feed(block):
                        yield text
                parser.complete()
    except (TimeoutError, httpx.TimeoutException):
        raise ApiError(504, "tutor_timeout", "The tutor timed out. Try again.") from None
    except httpx.HTTPError:
        raise ApiError(
            503, "tutor_provider_unavailable", "The tutor provider is unavailable."
        ) from None
    except (ValueError, KeyError, IndexError, TypeError):
        raise invalid() from None
