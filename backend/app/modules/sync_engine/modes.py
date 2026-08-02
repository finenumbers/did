import enum


class SyncMode(str, enum.Enum):
    full = "full"
    free_only = "free_only"
    purchased_only = "purchased_only"
    dictionaries_only = "dictionaries_only"
