import enum


class SyncMode(str, enum.Enum):
    """Modes used by unified sync. purchased/dictionaries-only removed (Wave 2)."""

    full = "full"
    free_only = "free_only"
