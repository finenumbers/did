from decimal import Decimal

from app.modules.catalog.apply_mask_types import (
    build_mask_type_index,
    lookup_type_premium,
    resolve_catalog_type_premium,
)
from app.modules.catalog.beauty_mask import (
    all_beauty_masks,
    beauty_mask,
    canonical_beauty_masks,
    enumerate_beauty_masks,
)


def test_beauty_mask_examples():
    assert beauty_mask("1102003") == "XX0Y00Z"
    assert beauty_mask("1200034") == "XY000ZA"
    assert beauty_mask("1213340") == "XYXZZA0"
    assert beauty_mask("1111111") == "XXXXXXX"
    assert beauty_mask("00000") == "00000"


def test_beauty_mask_lengths_and_junk():
    assert beauty_mask("12345") == "XYZAB"
    assert beauty_mask("123456") == "XYZABC"
    assert beauty_mask("1234") is None
    assert beauty_mask("12345678") is None
    assert beauty_mask("12ab345") == "XYZAB"
    assert beauty_mask(None) is None


def test_enumerate_counts():
    assert len(enumerate_beauty_masks(5)) == 203
    assert len(enumerate_beauty_masks(6)) == 877
    assert len(enumerate_beauty_masks(7)) == 4140
    assert len(all_beauty_masks()) == 5220
    assert len(canonical_beauty_masks()) == 5220


def test_enumerate_contains_examples():
    assert "XX0Y00Z" in enumerate_beauty_masks(7)
    assert "00000" in enumerate_beauty_masks(5)
    assert "XXXXXXX" in canonical_beauty_masks()


def test_mask_digit_capacity_is_mask_length():
    from app.modules.catalog.beauty_mask import mask_digit_capacity

    assert mask_digit_capacity("XXXXXXX") == "7"
    assert mask_digit_capacity("00000") == "5"
    assert mask_digit_capacity(enumerate_beauty_masks(6)[0]) == "6"


def test_beauty_mask_round_trip_enumerated():
    for mask in enumerate_beauty_masks(5):
        letter_to_digit: dict[str, str] = {}
        next_d = 1
        built: list[str] = []
        for ch in mask:
            if ch == "0":
                built.append("0")
                continue
            if ch not in letter_to_digit:
                letter_to_digit[ch] = str(next_d)
                next_d += 1
            built.append(letter_to_digit[ch])
        assert beauty_mask("".join(built)) == mask


def test_lookup_prefers_exact_abc_then_empty():
    class Row:
        def __init__(self, cap, cat, abc, mask, type_label, premium, purchase):
            self.digit_capacity = cap
            self.category = cat
            self.abc = abc
            self.mask = mask
            self.type_label = type_label
            self.premium = premium
            self.purchase = purchase

    index = build_mask_type_index(
        [
            Row(
                "7",
                "Городской",
                "",
                "XXXXXXX",
                "обычный",
                Decimal("1"),
                Decimal("3"),
            ),
            Row(
                "7",
                "Городской",
                "495",
                "XXXXXXX",
                "москва",
                Decimal("2"),
                Decimal("10"),
            ),
        ]
    )
    assert lookup_type_premium(
        index, digit_capacity="7", category="Городской", abc="495", mask="XXXXXXX"
    ) == ("москва", Decimal("2"), Decimal("10"))
    assert lookup_type_premium(
        index, digit_capacity="7", category="Городской", abc="499", mask="XXXXXXX"
    ) == ("обычный", Decimal("1"), Decimal("3"))
    assert (
        lookup_type_premium(
            index, digit_capacity="7", category="Мобильный", abc="495", mask="XXXXXXX"
        )
        is None
    )


def test_resolve_uses_local_length_and_falls_back():
    class Row:
        def __init__(self, cap, cat, abc, mask, type_label, premium, purchase):
            self.digit_capacity = cap
            self.category = cat
            self.abc = abc
            self.mask = mask
            self.type_label = type_label
            self.premium = premium
            self.purchase = purchase

    index = build_mask_type_index(
        [
            Row(
                "7",
                "Городской",
                "",
                "XXXXXXX",
                "тип",
                Decimal("5"),
                Decimal("6"),
            )
        ]
    )
    assert resolve_catalog_type_premium(
        index,
        number_local="1111111",
        number_category="Городской",
        abc_code="495",
    ) == ("тип", Decimal("5"), Decimal("6"))
    assert resolve_catalog_type_premium(
        index,
        number_local="1111",
        number_category="Городской",
        abc_code="495",
    ) == (None, None, None)
