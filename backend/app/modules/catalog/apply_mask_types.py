"""Fill catalog type_label/premium from mask_types after geographic rewrite."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Text, bindparam, select, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Session, load_only

from app.models.catalog import NumbersCatalogNormalized
from app.models.mask_types import MaskType
from app.modules.catalog.beauty_mask import beauty_mask, digits_only

_BATCH = 8_000


def normalize_key_part(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return str(value).replace("\xa0", " ").strip()
    text_value = str(value).replace("\xa0", " ").strip()
    if text_value.endswith(".0") and text_value[:-2].lstrip("-").isdigit():
        text_value = text_value[:-2]
    return text_value


def lookup_type_premium(
    index: dict[tuple[str, str, str, str], tuple[str | None, str | None]],
    *,
    digit_capacity: str,
    category: str,
    abc: str,
    mask: str,
) -> tuple[str | None, str | None] | None:
    exact = index.get((digit_capacity, category, abc, mask))
    if exact is not None:
        return exact
    if abc:
        return index.get((digit_capacity, category, "", mask))
    return None


def build_mask_type_index(
    rows: list[MaskType],
) -> dict[tuple[str, str, str, str], tuple[str | None, str | None]]:
    return {
        (
            row.digit_capacity or "",
            row.category or "",
            row.abc or "",
            row.mask,
        ): (row.type_label, row.premium)
        for row in rows
    }


def resolve_catalog_type_premium(
    index: dict[tuple[str, str, str, str], tuple[str | None, str | None]],
    *,
    number_local: str | None,
    number_category: str | None,
    abc_code: str | None,
) -> tuple[str | None, str | None]:
    mask = beauty_mask(number_local)
    if mask is None:
        return None, None
    cap = str(len(digits_only(number_local)))
    cat = (number_category or "").strip()
    abc = (abc_code or "").strip()
    found = lookup_type_premium(
        index,
        digit_capacity=cap,
        category=cat,
        abc=abc,
        mask=mask,
    )
    if found is None:
        return None, None
    return found


def _norm_blank(value: str | None) -> str | None:
    return None if value in (None, "") else value


def _values_distinct(current: str | None, new: str | None) -> bool:
    return _norm_blank(current) != _norm_blank(new)


def apply_mask_types(db: Session) -> dict[str, int]:
    rows = db.scalars(select(MaskType)).all()
    index = build_mask_type_index(list(rows))
    stmt = (
        select(NumbersCatalogNormalized)
        .options(
            load_only(
                NumbersCatalogNormalized.id,
                NumbersCatalogNormalized.number_local,
                NumbersCatalogNormalized.number_category,
                NumbersCatalogNormalized.abc_code,
                NumbersCatalogNormalized.type_label,
                NumbersCatalogNormalized.premium,
            )
        )
        .where(NumbersCatalogNormalized.is_currently_present.is_(True))
        .execution_options(yield_per=_BATCH, stream_results=True)
    )

    pending: list[tuple[UUID, str | None, str | None]] = []
    scanned = 0
    matched = 0
    updated = 0
    cleared = 0

    def flush() -> None:
        nonlocal updated
        if not pending:
            return
        updated += _bulk_update(db, pending)
        pending.clear()

    for row in db.scalars(stmt).yield_per(_BATCH):
        scanned += 1
        new_type, new_prem = resolve_catalog_type_premium(
            index,
            number_local=row.number_local,
            number_category=row.number_category,
            abc_code=row.abc_code,
        )
        if new_type is not None or new_prem is not None:
            matched += 1
        type_changed = _values_distinct(row.type_label, new_type)
        prem_changed = _values_distinct(row.premium, new_prem)
        if not type_changed and not prem_changed:
            continue
        if new_type is None and new_prem is None and (
            row.type_label is not None or row.premium is not None
        ):
            cleared += 1
        pending.append((row.id, new_type, new_prem))
        if len(pending) >= _BATCH:
            flush()
    flush()
    return {
        "directory": len(index),
        "scanned": scanned,
        "matched": matched,
        "updated": updated,
        "cleared": cleared,
    }


def _bulk_update(
    db: Session,
    pairs: list[tuple[UUID, str | None, str | None]],
) -> int:
    if not pairs:
        return 0
    bind = db.get_bind()
    ids = [p[0] for p in pairs]
    types = [p[1] for p in pairs]
    prems = [p[2] for p in pairs]
    if bind.dialect.name == "postgresql":
        stmt = text(
            """
            UPDATE numbers_catalog_normalized AS c
            SET type_label = v.type_label,
                premium = v.premium,
                updated_at = now()
            FROM unnest(:ids, :types, :prems)
                AS v(id, type_label, premium)
            WHERE c.id = v.id
            """
        ).bindparams(
            bindparam("ids", type_=ARRAY(PGUUID(as_uuid=True))),
            bindparam("types", type_=ARRAY(Text())),
            bindparam("prems", type_=ARRAY(Text())),
        )
        db.execute(stmt, {"ids": ids, "types": types, "prems": prems})
        return len(pairs)
    for catalog_id, type_label, premium in pairs:
        db.execute(
            text(
                """
                UPDATE numbers_catalog_normalized
                SET type_label = :type_label,
                    premium = :premium,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """
            ),
            {"id": catalog_id, "type_label": type_label, "premium": premium},
        )
    return len(pairs)
