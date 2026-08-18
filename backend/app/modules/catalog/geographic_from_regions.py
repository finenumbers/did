"""Final-stage geographic ABC split + city/region from regions_directory."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.regions_directory import RegionsDirectory
from app.providers.msisdn_split import (
    DIGIT_CAPACITY_DEFAULT,
    split_msisdn,
    split_msisdn_by_capacity,
)


@dataclass(frozen=True)
class RegionAbcRow:
    abc: str
    digit_capacity: int
    city_name: str
    region_name: str | None


def is_geographic_msisdn(msisdn: str | None) -> bool:
    """True for 7XXXXXXXXXX that is not mobile (9*) and not 800."""
    digits = "".join(ch for ch in str(msisdn or "") if ch.isdigit())
    if len(digits) != 11 or not digits.startswith("7"):
        return False
    national = digits[1:]
    return not national.startswith("9") and not national.startswith("800")


def match_geographic_abc(
    msisdn: str | None,
    directory: Mapping[str, RegionAbcRow],
) -> tuple[str, str, str | None, str | None] | None:
    """Longest ABC prefix (5, then 4, then 3) against the directory.

    Geographic MSISDN with no directory hit falls back to 3+7 and empty geo.
    Non-geographic / invalid MSISDN → None (caller must not rewrite the row).
    """
    if not is_geographic_msisdn(msisdn):
        return None
    digits = "".join(ch for ch in str(msisdn) if ch.isdigit())
    national = digits[1:]
    for abc_len in (5, 4, 3):
        prefix = national[:abc_len]
        row = directory.get(prefix)
        if row is None:
            continue
        if len(row.abc) + int(row.digit_capacity) != 10:
            continue
        if len(row.abc) != abc_len:
            continue
        parts = split_msisdn_by_capacity(digits, row.digit_capacity)
        if parts is None:
            continue
        abc, local = parts
        if abc != row.abc:
            continue
        return abc, local, row.city_name, row.region_name
    default = split_msisdn(digits)
    if default is None:
        abc = national[: 10 - DIGIT_CAPACITY_DEFAULT]
        local = national[10 - DIGIT_CAPACITY_DEFAULT :]
        return abc, local, None, None
    abc, local = default
    return abc, local, None, None


_GEO_UPDATE_SQL = """
WITH src AS (
  SELECT
    n.id,
    COALESCE(d5.abc, d4.abc, d3.abc, substring(n.msisdn FROM 2 FOR 3)) AS abc_code,
    CASE
      WHEN d5.abc IS NOT NULL THEN substring(n.msisdn FROM 7 FOR 5)
      WHEN d4.abc IS NOT NULL THEN substring(n.msisdn FROM 6 FOR 6)
      WHEN d3.abc IS NOT NULL THEN substring(n.msisdn FROM 5 FOR 7)
      ELSE substring(n.msisdn FROM 5 FOR 7)
    END AS number_local,
    CASE
      WHEN d5.abc IS NOT NULL THEN d5.city_name
      WHEN d4.abc IS NOT NULL THEN d4.city_name
      WHEN d3.abc IS NOT NULL THEN d3.city_name
      ELSE NULL
    END AS city_name,
    CASE
      WHEN d5.abc IS NOT NULL THEN d5.region_name
      WHEN d4.abc IS NOT NULL THEN d4.region_name
      WHEN d3.abc IS NOT NULL THEN d3.region_name
      ELSE NULL
    END AS region_name,
    (d5.abc IS NOT NULL OR d4.abc IS NOT NULL OR d3.abc IS NOT NULL) AS matched
  FROM numbers_catalog_normalized n
  LEFT JOIN regions_directory d5
    ON d5.abc = substring(n.msisdn FROM 2 FOR 5)
   AND char_length(d5.abc) + d5.digit_capacity = 10
  LEFT JOIN regions_directory d4
    ON d4.abc = substring(n.msisdn FROM 2 FOR 4)
   AND char_length(d4.abc) + d4.digit_capacity = 10
  LEFT JOIN regions_directory d3
    ON d3.abc = substring(n.msisdn FROM 2 FOR 3)
   AND char_length(d3.abc) + d3.digit_capacity = 10
  WHERE n.is_currently_present
    AND n.msisdn ~ '^7[0-9]{10}$'
    AND substring(n.msisdn FROM 2 FOR 1) <> '9'
    AND substring(n.msisdn FROM 2 FOR 3) <> '800'
),
upd AS (
  UPDATE numbers_catalog_normalized AS n
  SET
    abc_code = src.abc_code,
    number_local = src.number_local,
    city_name = src.city_name,
    region_name = src.region_name,
    updated_at = now()
  FROM src
  WHERE n.id = src.id
  RETURNING src.matched
)
SELECT
  count(*) FILTER (WHERE matched) AS matched,
  count(*) FILTER (WHERE NOT matched) AS reset
FROM upd
"""


def apply_geographic_from_regions(db: Session) -> dict[str, int]:
    """Rewrite present geographic catalog rows from regions_directory. One SQL pass."""
    directory_n = int(db.scalar(select(func.count()).select_from(RegionsDirectory)) or 0)
    row = db.execute(text(_GEO_UPDATE_SQL)).one()
    matched = int(row.matched or 0)
    reset = int(row.reset or 0)
    return {
        "directory": directory_n,
        "matched": matched,
        "reset": reset,
        "scanned": matched + reset,
    }
