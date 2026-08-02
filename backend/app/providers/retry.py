"""System-level timeout/retry — OPERATIONAL, not derived from provider docs."""

from dataclasses import dataclass, field


@dataclass
class TimeoutConfig:
    connect_timeout: float = 10.0
    read_timeout: float = 60.0
    total_timeout: float = 90.0


@dataclass
class RetryPolicy:
    max_attempts: int = 3
    backoff_seconds: float = 1.0
    retry_on_status: list[int] = field(default_factory=lambda: [502, 503, 504])
