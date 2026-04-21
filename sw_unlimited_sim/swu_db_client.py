"""Client for downloading card data from swu-db.com."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_BASE_URL = "https://api.swu-db.com"
DEFAULT_OUTPUT_PATH = Path(__file__).resolve().parent / "data" / "swu_cards.json"
DEFAULT_GAMEPLAY_OUTPUT_PATH = Path(__file__).resolve().parent / "data" / "swu_gameplay_cards.json"

GAMEPLAY_IDENTITY_FIELDS = (
    "Name",
    "Subtitle",
    "Type",
    "Cost",
    "Power",
    "HP",
    "Arenas",
    "Aspects",
    "Traits",
    "Keywords",
    "FrontText",
    "BackText",
    "EpicAction",
    "DoubleSided",
    "Unique",
)

VARIANT_PREFERENCE = (
    "Normal",
    "OP Promo",
    "Convention Exclusive",
    "Judge Program",
    "Store Showdown",
    "SQ Event Pack",
    "RQ Event Pack",
    "SQ Prize Wall",
    "RQ Prize Wall",
    "GC Silver Pack",
    "GC Black Pack",
    "GC Top 64",
    "Hyperspace",
    "Foil",
    "Hyperspace Foil",
    "Showcase",
    "Prestige",
    "Prestige Foil",
    "Prestige Serialized",
)

# Set codes listed on https://www.swu-db.com/sets as of 2026-04-21.
# SWU DB exposes cards by set, so fetching "all cards" means aggregating sets.
DEFAULT_SET_CODES = [
    "IBH",
    "SEC",
    "SECOP",
    "P25",
    "P26",
    "TWI",
    "TWIOP",
    "PTWI",
    "G25",
    "JTL",
    "JTLOP",
    "LAW",
    "LAWP",
    "SOR",
    "ESOR",
    "SOROP",
    "SOROPJ",
    "PSOR",
    "TSOR",
    "GG",
    "LOF",
    "LOFOP",
    "TS26",
    "SHD",
    "SHDOP",
    "PSHD",
    "C24",
    "C25",
    "J24",
    "J25",
    "SS1",
    "SS1J",
    "SS2",
    "SS2J",
]


class SwuDbError(RuntimeError):
    """Raised when SWU DB returns unexpected data."""


def _get_json(path: str, params: dict[str, Any] | None = None) -> Any:
    query = f"?{urlencode(params)}" if params else ""
    url = f"{API_BASE_URL}{path}{query}"
    request = Request(url, headers={"User-Agent": "sw-unlimited-sim/1.0"})

    with urlopen(request, timeout=30) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return json.loads(response.read().decode(charset))


def _as_card_list(payload: Any, set_code: str) -> list[dict[str, Any]]:
    """Normalize common response shapes into a card list."""
    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        for key in ("cards", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return value

    raise SwuDbError(f"Unexpected response shape for set {set_code}")


def fetch_cards_for_set(set_code: str) -> list[dict[str, Any]]:
    """Fetch all cards for one SWU DB set code."""
    payload = _get_json(
        f"/cards/{set_code.lower()}",
        {"format": "json", "order": "setnumber"},
    )
    cards = _as_card_list(payload, set_code)

    for card in cards:
        if isinstance(card, dict):
            card.setdefault("_source_set_code", set_code.upper())

    return cards


def fetch_all_cards(set_codes: list[str] | None = None) -> dict[str, Any]:
    """Fetch all cards for the configured SWU DB set codes."""
    selected_codes = list(dict.fromkeys(code.upper() for code in (set_codes or DEFAULT_SET_CODES)))
    cards_by_set: dict[str, list[dict[str, Any]]] = {}
    all_cards: list[dict[str, Any]] = []
    failed_sets: dict[str, str] = {}

    for set_code in selected_codes:
        try:
            cards = fetch_cards_for_set(set_code)
        except Exception as exc:
            failed_sets[set_code] = str(exc)
            continue

        cards_by_set[set_code] = cards
        all_cards.extend(cards)

    return {
        "source": "https://api.swu-db.com",
        "set_codes": selected_codes,
        "total_cards": len(all_cards),
        "failed_sets": failed_sets,
        "cards_by_set": cards_by_set,
        "cards": all_cards,
    }


def write_all_cards(
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
    set_codes: list[str] | None = None,
) -> dict[str, Any]:
    """Fetch card data and write it to a JSON file."""
    data = fetch_all_cards(set_codes=set_codes)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return data


def _freeze_value(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, dict):
        return tuple(sorted((key, _freeze_value(item)) for key, item in value.items()))
    return value


def gameplay_identity(card: dict[str, Any]) -> tuple[Any, ...]:
    """Return a key for gameplay-equivalent cards across cosmetic variants."""
    return tuple(_freeze_value(card.get(field)) for field in GAMEPLAY_IDENTITY_FIELDS)


def variant_rank(card: dict[str, Any]) -> int:
    """Rank variants so the retained gameplay record is stable and readable."""
    variant_type = card.get("VariantType")
    try:
        return VARIANT_PREFERENCE.index(variant_type)
    except ValueError:
        return len(VARIANT_PREFERENCE)


def filter_gameplay_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse cosmetic variants into one representative card record."""
    selected: dict[tuple[Any, ...], dict[str, Any]] = {}

    for card in cards:
        key = gameplay_identity(card)
        current = selected.get(key)
        if current is None or variant_rank(card) < variant_rank(current):
            selected[key] = card

    return sorted(
        selected.values(),
        key=lambda card: (
            str(card.get("Set") or ""),
            int(card.get("Number")) if str(card.get("Number") or "").isdigit() else 999999,
            str(card.get("Number") or ""),
            str(card.get("Name") or ""),
        ),
    )


def write_gameplay_cards(
    input_path: str | Path = DEFAULT_OUTPUT_PATH,
    output_path: str | Path = DEFAULT_GAMEPLAY_OUTPUT_PATH,
) -> dict[str, Any]:
    """Read a full SWU DB cache and write a cosmetic-variant-free cache."""
    source_path = Path(input_path)
    data = json.loads(source_path.read_text(encoding="utf-8"))
    cards = data.get("cards", [])
    gameplay_cards = filter_gameplay_cards(cards)

    output = {
        "source": data.get("source", API_BASE_URL),
        "source_file": str(source_path),
        "total_source_cards": len(cards),
        "total_cards": len(gameplay_cards),
        "removed_variants": len(cards) - len(gameplay_cards),
        "identity_fields": list(GAMEPLAY_IDENTITY_FIELDS),
        "variant_preference": list(VARIANT_PREFERENCE),
        "cards": gameplay_cards,
    }

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
    return output
