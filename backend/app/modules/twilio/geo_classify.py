"""Split Twilio region/locality into UI columns. Never invent names."""

from __future__ import annotations

from app.providers.twilio import contract

KEEP_COUNTRIES = frozenset({"US", "CA", "GB", "DE", "FR"})

US_STATE_NAMES: dict[str, str] = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
    "DC": "District of Columbia",
}

CA_PROVINCE_NAMES: dict[str, str] = {
    "AB": "Alberta",
    "BC": "British Columbia",
    "MB": "Manitoba",
    "NB": "New Brunswick",
    "NL": "Newfoundland and Labrador",
    "NS": "Nova Scotia",
    "NT": "Northwest Territories",
    "NU": "Nunavut",
    "ON": "Ontario",
    "PE": "Prince Edward Island",
    "QC": "Quebec",
    "SK": "Saskatchewan",
    "YT": "Yukon",
}

_GB_REGIONS = ("England", "Scotland", "Wales", "Northern Ireland")
_DE_REGIONS = (
    "Baden-Württemberg",
    "Bavaria",
    "Bayern",
    "Berlin",
    "Brandenburg",
    "Bremen",
    "Hamburg",
    "Hesse",
    "Hessen",
    "Lower Saxony",
    "Niedersachsen",
    "Mecklenburg-Vorpommern",
    "North Rhine-Westphalia",
    "Nordrhein-Westfalen",
    "Rhineland-Palatinate",
    "Rheinland-Pfalz",
    "Saarland",
    "Saxony",
    "Sachsen",
    "Saxony-Anhalt",
    "Sachsen-Anhalt",
    "Schleswig-Holstein",
    "Thuringia",
    "Thüringen",
)
_FR_REGIONS = (
    "Auvergne-Rhône-Alpes",
    "Auvergne-Rhone-Alpes",
    "Bourgogne-Franche-Comté",
    "Bourgogne-Franche-Comte",
    "Brittany",
    "Bretagne",
    "Centre-Val de Loire",
    "Corsica",
    "Corse",
    "Grand Est",
    "Hauts-de-France",
    "Île-de-France",
    "Ile-de-France",
    "Ile de France",
    "Normandy",
    "Normandie",
    "Nouvelle-Aquitaine",
    "Occitanie",
    "Occitania",
    "Pays de la Loire",
    "Provence-Alpes-Côte d'Azur",
    "Provence-Alpes-Cote d'Azur",
    "Provence-Alpes-Côte d’Azur",
    "Guadeloupe",
    "Martinique",
    "Guyane",
    "French Guiana",
    "La Réunion",
    "La Reunion",
    "Réunion",
    "Reunion",
    "Mayotte",
)

_DENY_EXTRA: dict[str, tuple[str, ...]] = {
    "GB": (
        "united kingdom",
        "great britain",
        "uk",
        "gb",
        "united kingdom proper",
    ),
    "DE": (
        "germany",
        "deutschland",
        "de",
        "federal republic of germany",
        "bundesrepublik deutschland",
    ),
    "FR": (
        "france",
        "fr",
        "french republic",
        "republique francaise",
        "république française",
    ),
    "US": ("united states", "usa", "us", "united states of america"),
    "CA": ("canada", "ca"),
}


def _norm(value: str | None) -> str:
    return " ".join((value or "").split()).casefold()


def _clean(value: str | None) -> str | None:
    text = " ".join((value or "").split())
    return text or None


def _keep_map(country_iso: str) -> dict[str, str]:
    iso = (country_iso or "").strip().upper()
    mapping: dict[str, str] = {}
    if iso == "US":
        for code, name in US_STATE_NAMES.items():
            mapping[_norm(code)] = name
            mapping[_norm(name)] = name
        for code in contract.US_STATE_CODES:
            mapping.setdefault(_norm(code), US_STATE_NAMES.get(code, code))
    elif iso == "CA":
        for code, name in CA_PROVINCE_NAMES.items():
            mapping[_norm(code)] = name
            mapping[_norm(name)] = name
        for code in contract.CA_PROVINCE_CODES:
            mapping.setdefault(_norm(code), CA_PROVINCE_NAMES.get(code, code))
    elif iso == "GB":
        for name in _GB_REGIONS:
            mapping[_norm(name)] = name
    elif iso == "DE":
        for name in _DE_REGIONS:
            mapping[_norm(name)] = name
    elif iso == "FR":
        for name in _FR_REGIONS:
            mapping[_norm(name)] = name
    return mapping


def keep_region_displays(country_iso: str) -> set[str]:
    return set(_keep_map(country_iso).values())


def _is_deny(country_iso: str, country_name: str | None, value: str | None) -> bool:
    key = _norm(value)
    if not key:
        return False
    iso = (country_iso or "").strip().upper()
    if key == _norm(iso):
        return True
    if key == _norm(country_name):
        return True
    return key in {_norm(item) for item in _DENY_EXTRA.get(iso, ())}


def classify_token(
    country_iso: str,
    country_name: str | None,
    value: str | None,
) -> tuple[str, str | None]:
    cleaned = _clean(value)
    if cleaned is None:
        return "empty", None
    if _is_deny(country_iso, country_name, cleaned):
        return "deny", None
    keep = _keep_map(country_iso)
    display = keep.get(_norm(cleaned))
    if display:
        return "keep", display
    return "unknown", cleaned


def classify_geo(
    *,
    country_iso: str,
    country_name: str | None,
    region_raw: str | None,
    locality_raw: str | None,
) -> tuple[str | None, str | None]:
    iso = (country_iso or "").strip().upper()
    r_kind, r_value = classify_token(iso, country_name, region_raw)
    l_kind, l_value = classify_token(iso, country_name, locality_raw)
    has_keep = iso in KEEP_COUNTRIES

    region: str | None = None
    city: str | None = None
    if r_kind == "keep":
        region = r_value
    elif l_kind == "keep":
        region = l_value
    if l_kind == "unknown":
        city = l_value
    if r_kind == "unknown":
        if has_keep:
            if l_kind != "unknown":
                city = r_value
        elif l_kind == "unknown":
            if _norm(region_raw) == _norm(locality_raw):
                region = None
                city = l_value
            else:
                region = r_value
                city = l_value
        else:
            city = r_value
    if r_kind == "keep" and l_kind == "keep" and _norm(r_value) == _norm(l_value):
        city = None
    return region, city


def region_norm(value: str | None) -> str:
    return _norm(value)


def locality_norm(value: str | None) -> str:
    return _norm(value)
