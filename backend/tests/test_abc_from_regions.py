from uuid import uuid4

from app.modules.catalog.abc_from_regions import abc_local_updates, capacity_lookup
from app.providers.finenumbers.contract import OPERATOR_NOT_IN_REGISTRY


def test_capacity_lookup_skips_sentinel_and_invalid():
    samara = type("R", (), {"city_name": "Самара", "region_name": "Самарская область", "digit_capacity": 6})()
    bad = type("R", (), {"city_name": OPERATOR_NOT_IN_REGISTRY, "region_name": OPERATOR_NOT_IN_REGISTRY, "digit_capacity": 6})()
    invalid = type("R", (), {"city_name": "Пермь", "region_name": None, "digit_capacity": 9})()
    lookup = capacity_lookup([samara, bad, invalid])
    assert lookup == {("Самара", "Самарская область"): 6}


def test_abc_local_updates_only_matching_geo_and_changed_split():
    samara_id = uuid4()
    moscow_id = uuid4()
    missing_id = uuid4()
    same_id = uuid4()
    lookup = {("Самара", "Самарская область"): 6, ("Москва", "Москва"): 7}
    rows = [
        (samara_id, "73842399999", "Самара", "Самарская область", "384", "2399999"),
        (moscow_id, "74951234567", "Москва", "Москва", "495", "1234567"),
        (missing_id, "78121234567", "Питер", "ЛО", "812", "1234567"),
        (same_id, "73833999999", "Самара", "Самарская область", "3842", "399999"),
    ]
    # last row: capacity 6 of 73833999999 is 3833+999999, not 3842+399999
    updates = abc_local_updates(lookup, rows)
    by_id = {row_id: (abc, local) for row_id, abc, local in updates}
    assert by_id[samara_id] == ("3842", "399999")
    assert moscow_id not in by_id
    assert missing_id not in by_id
    assert by_id[same_id] == ("3833", "999999")


def test_abc_local_updates_does_not_touch_category_fields():
    catalog_id = uuid4()
    lookup = {("Кемерово", "Кемеровская область"): 6}
    updates = abc_local_updates(
        lookup,
        [(catalog_id, "73842123456", "Кемерово", "Кемеровская область", "384", "2123456")],
    )
    assert updates == [(catalog_id, "3842", "123456")]
