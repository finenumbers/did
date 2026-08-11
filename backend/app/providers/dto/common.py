from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ConnectionConfig:
    base_url: str | None
    auth_settings: dict[str, Any]
    extra_settings: dict[str, Any] = field(default_factory=dict)


@dataclass
class RawHttpResult:
    status_code: int
    body_text: str
    body_json: Any | None
    headers: dict[str, str]
    elapsed_ms: float
    request_url: str


@dataclass
class DiagnosticsResult:
    ok: bool
    message: str
    checked_at: datetime
    details: dict[str, Any] = field(default_factory=dict)
    raw: RawHttpResult | None = None


@dataclass
class SyncLimitation:
    provider: str
    capability: str
    message: str
    doc_refs: list[str] = field(default_factory=list)


@dataclass
class SyncResult:
    fetched: int = 0
    parsed: int = 0
    upserted: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    limitations: list[SyncLimitation] = field(default_factory=list)
    items: list[Any] = field(default_factory=list)
    # Raw API items that failed to produce provider_number_key / NormalizedNumber
    unmapped_raw: list[dict[str, Any]] = field(default_factory=list)
    raw_envelopes: list[RawHttpResult] = field(default_factory=list)
    diagnostics: DiagnosticsResult | None = None
    # Provider-specific stats merged into job category block (e.g. Runexis integrity).
    extra_stats: dict[str, Any] = field(default_factory=dict)
