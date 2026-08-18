"""Fill catalog type/premium/prices from mask_types after geographic rewrite."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import Numeric, Text, bindparam, select, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Session, load_only

from app.models.catalog import NumbersCatalogNormalized
from app.models.mask_types import MaskType
from app.modules.catalog.beauty_mask import beauty_mask, digits_only

_BATCH = 8_000

MaskTypeValues = tuple[str | None, Decimal | None, Decimal | None, Decimal | None]


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
    index: dict[tuple[str, str, str, str], MaskTypeValues],
    *,
    digit_capacity: str,
    category: str,
    abc: str,
    mask: str,
) -> MaskTypeValues | None:
    exact = index.get((digit_capacity, category, abc, mask))
    if exact is not None:
        return exact
    if abc:
        return index.get((digit_capacity, category, "", mask))
    return None


def build_mask_type_index(
    rows: list[MaskType],
) -> dict[tuple[str, str, str, str], MaskTypeValues]:
    return {
        (
            row.digit_capacity or "",
            row.category or "",
            row.abc or "",
            row.mask,
        ): (row.type_label, row.premium, row.purchase, row.period)
        for row in rows
    }


def resolve_catalog_type_premium(
    index: dict[tuple[str, str, str, str], MaskTypeValues],
    *,
    number_local: str | None,
    number_category: str | None,
    abc_code: str | None,
) -> MaskTypeValues:
    mask = beauty_mask(number_local)
    if mask is None:
        return None, None, None, None
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
        return None, None, None, None
    return found


def _norm_label(value: str | None) -> str | None:
    return None if value in (None, "") else value


def _norm_money(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(value)


def _values_changed(current: MaskTypeValues, new: MaskTypeValues) -> bool:
    return (
        _norm_label(current[0]) != _norm_label(new[0])
        or _norm_money(current[1]) != _norm_money(new[1])
        or _norm_money(current[2]) != _norm_money(new[2])
        or _norm_money(current[3]) != _norm_money(new[3])
    )


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
                NumbersCatalogNormalized.mask_purchase,
                NumbersCatalogNormalized.mask_period,
            )
        )
        .where(NumbersCatalogNormalized.is_currently_present.is_(True))
        .execution_options(yield_per=_BATCH, stream_results=True)
    )

    pending: list[tuple[UUID, str | None, Decimal | None, Decimal | None, Decimal | None]] = []
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
        new_vals = resolve_catalog_type_premium(
            index,
            number_local=row.number_local,
            number_category=row.number_category,
            abc_code=row.abc_code,
        )
        if any(v is not None for v in new_vals):
            matched += 1
        current = (row.type_label, row.premium, row.mask_purchase, row.mask_period)
        if not _values_changed(current, new_vals):
            continue
        if all(v is None for v in new_vals) and any(v is not None for v in current):
            cleared += 1
        pending.append((row.id, *new_vals))
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
    pairs: list[tuple[UUID, str | None, Decimal | None, Decimal | None, Decimal | None]],
) -> int:
    if not pairs:
        return 0
    bind = db.get_bind()
    ids = [p[0] for p in pairs]
    types = [p[1] for p in pairs]
    prems = [p[2] for p in pairs]
    buys = [p[3] for p in pairs]
    periods = [p[4] for p in pairs]
    money = Numeric(18, 4)
    if bind.dialect.name == "postgresql":
        stmt = text(
            """
            UPDATE numbers_catalog_normalized AS c
            SET type_label = v.type_label,
                premium = v.premium,
                mask_purchase = v.mask_purchase,
                mask_period = v.mask_period,
                updated_at = now()
            FROM unnest(:ids, :types, :prems, :buys, :periods)
                AS v(id, type_label, premium, mask_purchase, mask_period)
            WHERE c.id = v.id
            """
        ).bindparams(
            bindparam("ids", type_=ARRAY(PGUUID(as_uuid=True))),
            bindparam("types", type_=ARRAY(Text())),
            bindparam("prems", type_=ARRAY(money)),
            bindparam("buys", type_=ARRAY(money)),
            bindparam("periods", type_=ARRAY(money)),
        )
        db.execute(
            stmt,
            {
                "ids": ids,
                "types": types,
                "prems": prems,
                "buys": buys,
                "periods": periods,
            },
        )
        return len(pairs)
    for catalog_id, type_label, premium, mask_purchase, mask_period in pairs:
        db.execute(
            text(
                """
                UPDATE numbers_catalog_normalized
                SET type_label = :type_label,
                    premium = :premium,
                    mask_purchase = :mask_purchase,
                    mask_period = :mask_period,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """
            ),
            {
                "id": catalog_id,
                "type_label": type_label,
                "premium": premium,
                "mask_purchase": mask_purchase,
                "mask_period": mask_period,
            },
        )
    return len(pairs)
