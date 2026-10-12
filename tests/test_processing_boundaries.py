import json
import wave
from dataclasses import replace
from random import Random

import av
import httpx
import pytest

from app.components.processing.config import ProcessingSettings
from app.components.processing.notes import input_bound, split_content
from app.components.processing.prepare import prepare_audio
from app.components.processing.providers import GroqProvider, ProviderFailure, reset_seconds


@pytest.mark.parametrize(
    "source,language",
    [
        ("한글 강의에서 함수와 입력을 설명합니다.\n" * 400, "ko"),
        ("A lecture explains function inputs and outputs.\n" * 600, "en"),
    ],
)
def test_summary_splitting_keeps_every_character_and_bounds_each_request(source, language):
    config = ProcessingSettings()
    parts = split_content(source, language, config)
    assert len(parts) > 1
    assert "".join(parts) == source
    assert all(input_bound(p, language, config) <= 4000 for p in parts)


def test_byte_checked_flac_segments_have_no_missing_samples(tmp_path):
    from array import array

    source = tmp_path / "noise.wav"
    noise = array("h", [Random(i).randint(-32768, 32767) for i in range(32000)])
    with wave.open(str(source), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(noise.tobytes())
    target = tmp_path / "prepared"
    target.mkdir()
    manifest = prepare_audio(source, target, replace(ProcessingSettings(), segment_bytes=65536))
    assert manifest["totalSamples"] == 32000
    assert len(manifest["segments"]) > 1
    offset = 0
    decoded = array("h")
    for part in manifest["segments"]:
        assert part["startSample"] == offset
        assert part["bytes"] <= 65536
        with av.open(str(target / part["file"])) as audio:
            for frame in audio.decode(audio.streams.audio[0]):
                decoded.frombytes(bytes(frame.planes[0])[: frame.samples * 2])
        offset += part["samples"]
    assert decoded == noise


@pytest.mark.parametrize(
    "value,expected",
    [("2m59.5s", 180), ("300ms", 1), ("12", 12), ("not a duration", 0), ("9e100", 0)],
)
def test_retry_duration_parsing_is_bounded(value, expected):
    assert reset_seconds(value) == expected


def test_quota_response_uses_metadata_and_unknown_quota_waits_conservatively():
    for headers, expected in [({"retry-after": "120"}, 120), ({}, 3600)]:
        provider = GroqProvider(
            "synthetic",
            httpx.MockTransport(lambda r, headers=headers: httpx.Response(429, headers=headers)),
        )
        with pytest.raises(ProviderFailure) as failure:
            provider.summarize("A lecture about functions.", "en", ProcessingSettings())
        assert failure.value.quota and failure.value.retry_after == expected


def test_groq_summary_requests_strict_schema_and_rejects_incomplete_output():
    def server(request):
        body = json.loads(request.content)
        assert body["response_format"]["json_schema"]["strict"] is True
        assert body["max_completion_tokens"] == 1500
        assert body["reasoning_effort"] == "low"
        assert body["messages"][1]["content"].startswith("<lecture_content>")
        return httpx.Response(
            200, json={"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]}
        )

    with pytest.raises(ProviderFailure) as failure:
        GroqProvider("synthetic", httpx.MockTransport(server)).summarize(
            "Lecture.", "ko", ProcessingSettings()
        )
    assert failure.value.code == "invalid_provider_output"


def test_transcription_rejects_wrong_shape_without_exposing_content(tmp_path):
    source = tmp_path / "segment.flac"
    source.write_bytes(b"synthetic")
    provider = GroqProvider(
        "synthetic-secret",
        httpx.MockTransport(lambda r: httpx.Response(200, json=["private transcript"])),
    )
    with pytest.raises(ProviderFailure) as failure:
        provider.transcribe(source, ProcessingSettings())
    assert failure.value.code == "invalid_provider_output"
    assert "private transcript" not in str(failure.value)
