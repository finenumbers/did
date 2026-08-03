import enum


class ProviderCode(str, enum.Enum):
    runexis = "runexis"
    sipout = "sipout"
    finenumbers = "finenumbers"
    uis = "uis"


class InventoryKind(str, enum.Enum):
    free = "free"
    purchased = "purchased"


class SyncJobType(str, enum.Enum):
    """DB/Alembic enum. Active sync modes: full, free_only. Other values are historical."""

    free_numbers = "free_numbers"
    purchased_numbers = "purchased_numbers"
    regions = "regions"
    cities = "cities"
    connection_test = "connection_test"
    full = "full"
    free_only = "free_only"
    purchased_only = "purchased_only"  # legacy DB value; unused by engine
    dictionaries_only = "dictionaries_only"  # legacy DB value; unused by engine


class SyncJobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"
    partial = "partial"


class SyncLogLevel(str, enum.Enum):
    debug = "debug"
    info = "info"
    warning = "warning"
    error = "error"


class ConnectionTestStatus(str, enum.Enum):
    never_tested = "never_tested"
    ok = "ok"
    failed = "failed"


class MappingConfidence(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class HistoryChangeSource(str, enum.Enum):
    sync = "sync"
    manual = "manual"
    system = "system"
