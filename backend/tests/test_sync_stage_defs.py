from app.modules.sync_engine.progress import (
    _PHASE_STAGE,
    STAGE_DEFS,
    build_initial_progress,
)

_PROVIDERS = (
    "sipout",
    "runexis",
    "uis",
    "novofon",
    "aurora",
    "exolve",
    "voximplant",
    "mcn",
    "finenumbers",
)

_TAIL = (
    "finalize",
    "operator_enrichment",
    "rtu_flags",
    "geographic_from_regions",
    "mask_types",
    "catalog_snapshot",
)


def test_stage_defs_full_provider_matrix():
    ids = [s["id"] for s in STAGE_DEFS]
    assert ids[0] == "prepare"
    assert STAGE_DEFS[0]["group"] == "Подготовка"
    assert ids[-6:] == list(_TAIL)
    assert all(s["group"] == "Завершение" for s in STAGE_DEFS[-6:])
    assert "Общее" not in {s["group"] for s in STAGE_DEFS}
    for provider in _PROVIDERS:
        assert f"{provider}_dictionaries" in ids
        assert f"{provider}_free" in ids
        assert f"{provider}_purchased" in ids
        assert _PHASE_STAGE[(provider, "dictionaries")] == f"{provider}_dictionaries"
        assert _PHASE_STAGE[(provider, "free")] == f"{provider}_free"
        assert _PHASE_STAGE[(provider, "purchased")] == f"{provider}_purchased"
    progress = build_initial_progress()
    assert [s["id"] for s in progress["stages"]] == ids
    assert progress["stages"][1]["id"] == "sipout_dictionaries"
    assert progress["scope"] == {"provider": None}

    one = build_initial_progress(provider="mcn")
    one_ids = [s["id"] for s in one["stages"]]
    assert one_ids[0] == "prepare"
    assert "mcn_dictionaries" in one_ids
    assert "mcn_free" in one_ids
    assert "mcn_purchased" in one_ids
    assert "sipout_free" not in one_ids
    assert "runexis_free" not in one_ids
    assert one_ids[-6:] == list(_TAIL)
    assert one["scope"] == {"provider": "mcn"}
