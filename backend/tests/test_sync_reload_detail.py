from app.modules.sync_engine.service import _number_reload_detail, _number_reload_stats


def test_number_reload_detail_shows_drop_breakdown():
    detail = _number_reload_detail(fetched=26915, parsed=26915, upserted=24541)
    assert "fetched=26915" in detail
    assert "parsed=26915" in detail
    assert "upserted=24541" in detail
    assert "unmapped_dropped=0" in detail
    assert "duplicates_dropped=2374" in detail


def test_number_reload_detail_unmapped():
    detail = _number_reload_detail(fetched=100, parsed=90, upserted=90)
    assert "unmapped_dropped=10" in detail
    assert "duplicates_dropped=0" in detail


def test_number_reload_stats_uses_deduped_input():
    stats = _number_reload_stats(
        fetched=100,
        parsed=95,
        persist_stats={"upserted": 80, "deduped_input": 80},
        previous=10,
    )
    assert stats["unmapped_dropped"] == 5
    assert stats["duplicates_dropped"] == 15
    assert stats["fetched"] == 100
    assert stats["parsed"] == 95
    assert stats["previous"] == 10
