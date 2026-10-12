from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProcessingSettings:
    backend: str = "disabled"
    api_key: str = field(default="", repr=False)
    workers: int = 0
    segment_seconds: int = 300
    segment_bytes: int = 8 * 1024 * 1024
    input_tokens: int = 4000
    output_tokens: int = 1500
    summary_interval: int = 60
    provider_timeout: int = 180
    prepare_timeout: int = 180
    prepare_cpu_seconds: int = 120
    lease_seconds: int = 600
    heartbeat_seconds: int = 30
    max_attempts: int = 3
    max_deferrals: int = 24

    def snapshot(self):
        return {
            name: getattr(self, name)
            for name in (
                "segment_seconds",
                "segment_bytes",
                "input_tokens",
                "output_tokens",
                "summary_interval",
                "provider_timeout",
                "prepare_timeout",
                "prepare_cpu_seconds",
                "lease_seconds",
                "heartbeat_seconds",
                "max_attempts",
                "max_deferrals",
            )
        }


def load_processing(values, mode):
    data = ProcessingSettings(
        backend=values.get("AI_BACKEND", "fixture" if mode == "test" else "disabled"),
        api_key=values.get("GROQ_API_KEY", ""),
        workers=int(values.get("PROCESSING_WORKERS", "0")),
        **{
            name: int(values.get("PROCESSING_" + name.upper(), default))
            for name, default in ProcessingSettings().snapshot().items()
        },
    )
    if (
        data.backend not in {"disabled", "groq", "fixture"}
        or data.workers not in {0, 1}
        or (mode == "test" and data.backend == "groq")
        or (mode == "production" and data.backend == "fixture")
        or not 1 <= data.segment_seconds <= 300
        or not 65536 <= data.segment_bytes <= 8 * 1024 * 1024
        or not 3000 <= data.input_tokens <= 6000
        or not 512 <= data.output_tokens <= 1500
        or not 60 <= data.summary_interval <= 86400
        or not 10 <= data.provider_timeout <= 300
        or not 30 <= data.prepare_timeout <= 600
        or not 20 <= data.prepare_cpu_seconds <= 300
        or data.lease_seconds < max(data.provider_timeout, data.prepare_timeout) + 120
        or not 5 <= data.heartbeat_seconds <= data.lease_seconds // 4
        or not 1 <= data.max_attempts <= 5
        or not 1 <= data.max_deferrals <= 48
    ):
        raise ValueError("Invalid processing configuration")
    return data
