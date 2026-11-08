"""Single-source sync must not widen catalog writes to other providers."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from sqlalchemy import select

from app.models.catalog import NumbersCatalogNormalized
from app.models.enums import InventoryKind
from app.modules.catalog.apply_mask_types import apply_mask_types
from app.modules.catalog.geographic_from_regions import (
    _GEO_UPDATE_SQL,
    geographic_update_sql,
)
from app.modules.sync_engine.persist import apply_rtu_connected_flags
from app.modules.sync_engine.unified import (
    _committed_kinds,
    _scope_filter,
    normalize_sync_provider,
)
from app.providers.errors import ProviderError
from app.providers.finenumbers.enrich import catalog_scope_clauses


def test_unknown_provider_is_rejected():
    try:
        normalize_sync_provider("didww")
        assert False, "expected unknown provider"
    except ProviderError as exc:
        assert exc.code == "SYNC_UNKNOWN_PROVIDER"
    assert normalize_sync_provider(None) is None
    assert normalize_sync_provider("  MCN ") == "mcn"


def test_committed_kinds_follow_cutover_flags_only():
    assert _committed_kinds({}) == set()
    assert _committed_kinds({"_free_cutover_committed": True}) == {"free"}
    assert _committed_kinds(
        {"_free_cutover_committed": True, "_purchased_cutover_committed": True}
    ) == {"free", "purchased"}


def test_skip_scope_does_not_open_catalog_writes():
    assert _scope_filter(None) is None
    assert _scope_filter("skip") is None
    provider_id = uuid.uuid4()
    scoped = _scope_filter((provider_id, {"free"}))
    assert scoped is not None
    assert scoped[0] == provider_id
    assert scoped[1] == (InventoryKind.free,)


def test_geographic_sql_is_unchanged_without_a_source_filter():
    sql, params = geographic_update_sql()
    assert sql == _GEO_UPDATE_SQL
    assert params == {}


def test_geographic_sql_limits_one_source():
    provider_id = uuid.uuid4()
    sql, params = geographic_update_sql(
        provider_id=provider_id,
        inventory_kinds=(InventoryKind.free,),
    )
    assert "n.provider_id = :provider_id" in sql
    assert "n.inventory_kind::text IN :inventory_kinds" in sql
    assert params["provider_id"] == provider_id
    assert params["inventory_kinds"] == ["free"]


def test_enrich_scope_clauses_are_empty_for_a_full_sync():
    assert catalog_scope_clauses() == []
    provider_id = uuid.uuid4()
    clauses = catalog_scope_clauses(
        provider_id=provider_id,
        inventory_kinds=(InventoryKind.purchased,),
    )
    stmt = select(NumbersCatalogNormalized.id).where(*clauses)
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": False}))
    assert "provider_id" in compiled
    assert "inventory_kind" in compiled


def test_rtu_filter_adds_provider_predicate():
    db = MagicMock()
    result = MagicMock()
    result.all.return_value = []
    db.execute.return_value = result
    provider_id = uuid.uuid4()
    apply_rtu_connected_flags(db, reg_keys=set(), provider_id=provider_id)
    stmt = db.execute.call_args.args[0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": False}))
    assert compiled.count("provider_id") >= 2


def test_rtu_without_provider_does_not_add_a_second_provider_predicate():
    db = MagicMock()
    result = MagicMock()
    result.all.return_value = []
    db.execute.return_value = result
    apply_rtu_connected_flags(db, reg_keys=set())
    wide = str(db.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": False}))
    db.execute.reset_mock()
    apply_rtu_connected_flags(db, reg_keys=set(), provider_id=uuid.uuid4())
    narrow = str(db.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": False}))
    assert len(narrow) > len(wide)


def test_mask_types_query_limits_one_source():
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    db.scalars.return_value.__iter__ = lambda self: iter(())
    provider_id = uuid.uuid4()
    apply_mask_types(
        db,
        provider_id=provider_id,
        inventory_kinds=(InventoryKind.free,),
    )
    number_stmt = db.scalars.call_args_list[-1].args[0]
    compiled = str(number_stmt.compile(compile_kwargs={"literal_binds": False}))
    assert "provider_id" in compiled
    assert "inventory_kind" in compiled
