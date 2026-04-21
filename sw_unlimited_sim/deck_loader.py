"""Load simulator decks from JSON decklists backed by SWU DB card data."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from models import Arena, Card, EventCard, LeaderCard, UnitCard, UpgradeCard
from swu_db_client import DEFAULT_GAMEPLAY_OUTPUT_PATH


DECK_DIR = Path(__file__).resolve().parent / "data" / "decks"


class DeckLoadError(RuntimeError):
    """Raised when a decklist cannot be loaded."""


def available_decks() -> list[str]:
    """Return bundled deck names."""
    if not DECK_DIR.exists():
        return []
    return sorted(path.stem for path in DECK_DIR.glob("*.json"))


def resolve_deck_path(deck_ref: str | Path) -> Path:
    """Resolve either a deck name or a filesystem path."""
    path = Path(deck_ref)
    if path.exists():
        return path

    named_path = DECK_DIR / f"{deck_ref}.json"
    if named_path.exists():
        return named_path

    raise DeckLoadError(f"Deck '{deck_ref}' was not found")


def _load_card_cache(card_data_path: str | Path = DEFAULT_GAMEPLAY_OUTPUT_PATH) -> dict[tuple[str, str], dict[str, Any]]:
    path = Path(card_data_path)
    if not path.exists():
        raise DeckLoadError(
            f"Card data file '{path}' does not exist. Run `python main.py --fetch-cards` "
            "and `python main.py --filter-gameplay-cards` first."
        )

    data = json.loads(path.read_text(encoding="utf-8"))
    cards = data.get("cards", [])
    return {
        (str(card.get("Set")).upper(), str(card.get("Number"))): card
        for card in cards
    }


def _lookup_card(
    index: dict[tuple[str, str], dict[str, Any]],
    ref: dict[str, Any],
) -> dict[str, Any]:
    set_code = str(ref.get("set") or ref.get("Set") or "").upper()
    number = str(ref.get("number") or ref.get("Number") or "")
    key = (set_code, number)

    try:
        return index[key]
    except KeyError as exc:
        raise DeckLoadError(f"Card {set_code} {number} was not found in gameplay card data") from exc


def _to_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _arena_from_card(card_data: dict[str, Any]) -> Arena:
    arenas = card_data.get("Arenas") or []
    normalized = {str(arena).lower() for arena in arenas}
    if "space" in normalized:
        return Arena.SPACE
    if "ground" in normalized:
        return Arena.GROUND
    return Arena.NONE


def _traits(card_data: dict[str, Any]) -> list[str]:
    return [str(trait) for trait in (card_data.get("Traits") or [])]


def _abilities(card_data: dict[str, Any]) -> list[str]:
    abilities = []
    for field in ("FrontText", "BackText", "EpicAction"):
        value = card_data.get(field)
        if value:
            abilities.append(str(value))
    return abilities


def _has_ambush(card_data: dict[str, Any]) -> bool:
    keywords = {str(keyword).lower() for keyword in (card_data.get("Keywords") or [])}
    text = "\n".join(_abilities(card_data)).lower()
    return "ambush" in keywords or "ambush" in text


def _action_cost(front_text: str | None) -> int:
    if not front_text:
        return 0

    match = re.search(r"Action\s+\[C=(\d+)", front_text, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))
    return 0


def _card_id(card_data: dict[str, Any], copy_index: int) -> str:
    return f"{card_data.get('Set')}_{card_data.get('Number')}_{copy_index}"


def card_from_data(card_data: dict[str, Any], copy_index: int = 1) -> Card:
    """Convert one SWU DB card record into a simulator card object."""
    card_type = str(card_data.get("Type") or "").lower()
    card_id = _card_id(card_data, copy_index)
    name = str(card_data.get("Name") or "Unknown Card")
    cost = _to_int(card_data.get("Cost"))

    if card_type == "unit":
        return UnitCard(
            card_id,
            name,
            cost,
            power=_to_int(card_data.get("Power")),
            hp=_to_int(card_data.get("HP")),
            arena=_arena_from_card(card_data),
            traits=_traits(card_data),
            abilities=_abilities(card_data),
            has_ambush=_has_ambush(card_data),
        )

    if card_type == "upgrade":
        return UpgradeCard(
            card_id,
            name,
            cost,
            power_bonus=_to_int(card_data.get("Power")),
            hp_bonus=_to_int(card_data.get("HP")),
            abilities=_abilities(card_data),
        )

    if card_type == "event":
        return EventCard(
            card_id,
            name,
            cost,
            effect=str(card_data.get("FrontText") or ""),
        )

    raise DeckLoadError(f"Unsupported maindeck card type '{card_data.get('Type')}' for {name}")


def leader_from_data(card_data: dict[str, Any]) -> LeaderCard:
    """Convert one SWU DB leader record into a simulator leader."""
    if str(card_data.get("Type") or "").lower() != "leader":
        raise DeckLoadError(f"{card_data.get('Set')} {card_data.get('Number')} is not a leader")

    front_text = str(card_data.get("FrontText") or "")
    power = _to_int(card_data.get("Power"))
    hp = _to_int(card_data.get("HP"))
    leader = LeaderCard(
        f"{card_data.get('Set')}_{card_data.get('Number')}",
        str(card_data.get("Name") or "Unknown Leader"),
        _to_int(card_data.get("Cost")),
        action_cost=_action_cost(front_text),
        action_effect=front_text,
        epic_action_cost=_to_int(card_data.get("Cost")),
        epic_action_effect=f"Deploy as {power}/{hp} unit",
    )
    leader.traits = _traits(card_data)
    leader.abilities = _abilities(card_data)
    return leader


def load_deck(
    deck_ref: str | Path,
    card_data_path: str | Path = DEFAULT_GAMEPLAY_OUTPUT_PATH,
) -> tuple[list[Card], LeaderCard, dict[str, Any]]:
    """Load a decklist and return simulator deck cards, leader, and metadata."""
    deck_path = resolve_deck_path(deck_ref)
    decklist = json.loads(deck_path.read_text(encoding="utf-8"))
    card_index = _load_card_cache(card_data_path)

    leader_data = _lookup_card(card_index, decklist["leader"])
    leader = leader_from_data(leader_data)
    deck_cards: list[Card] = []
    copy_index = 1

    for entry in decklist.get("cards", []):
        card_data = _lookup_card(card_index, entry)
        count = _to_int(entry.get("count"), default=1)
        for _ in range(count):
            deck_cards.append(card_from_data(card_data, copy_index=copy_index))
            copy_index += 1

    metadata = {
        "name": decklist.get("name") or deck_path.stem,
        "path": str(deck_path),
        "card_count": len(deck_cards),
        "leader": leader.name,
    }
    return deck_cards, leader, metadata
