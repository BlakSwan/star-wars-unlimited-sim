"""Load simulator decks from JSON decklists backed by SWU DB card data."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from card_profiles import compile_card_profile
from effect_store import effect_key, load_effects
from models import Arena, Base, Card, EventCard, LeaderCard, UnitCard, UpgradeCard
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


def _aspects(card_data: dict[str, Any]) -> list[str]:
    return [str(aspect) for aspect in (card_data.get("Aspects") or [])]


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


def card_from_data(
    card_data: dict[str, Any],
    copy_index: int = 1,
    effect_record: dict[str, Any] | None = None,
) -> Card:
    """Convert one SWU DB card record into a simulator card object."""
    card_type = str(card_data.get("Type") or "").lower()
    card_id = _card_id(card_data, copy_index)
    name = str(card_data.get("Name") or "Unknown Card")
    cost = _to_int(card_data.get("Cost"))

    if card_type == "unit":
        card = UnitCard(
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
        card.aspects = _aspects(card_data)
        card.profile = compile_card_profile(card_data, effect_record)
        return card

    if card_type == "upgrade":
        card = UpgradeCard(
            card_id,
            name,
            cost,
            power_bonus=_to_int(card_data.get("Power")),
            hp_bonus=_to_int(card_data.get("HP")),
            abilities=_abilities(card_data),
        )
        card.aspects = _aspects(card_data)
        card.profile = compile_card_profile(card_data, effect_record)
        return card

    if card_type == "event":
        card = EventCard(
            card_id,
            name,
            cost,
            effect=str(card_data.get("FrontText") or ""),
        )
        card.aspects = _aspects(card_data)
        card.profile = compile_card_profile(card_data, effect_record)
        return card

    raise DeckLoadError(f"Unsupported maindeck card type '{card_data.get('Type')}' for {name}")


def leader_from_data(card_data: dict[str, Any], effect_record: dict[str, Any] | None = None) -> LeaderCard:
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
    leader.aspects = _aspects(card_data)
    leader.deployed_arena = _arena_from_card(card_data)
    leader.profile = compile_card_profile(card_data, effect_record)
    return leader


def base_from_data(card_data: dict[str, Any], effect_record: dict[str, Any] | None = None) -> Base:
    """Convert one SWU DB base record into a simulator base."""
    if str(card_data.get("Type") or "").lower() != "base":
        raise DeckLoadError(f"{card_data.get('Set')} {card_data.get('Number')} is not a base")

    return Base(
        name=str(card_data.get("Name") or "Unknown Base"),
        hp=_to_int(card_data.get("HP"), default=25),
        set_code=str(card_data.get("Set") or ""),
        number=str(card_data.get("Number") or ""),
        subtitle=str(card_data.get("Subtitle") or ""),
        aspects=_aspects(card_data),
        abilities=_abilities(card_data),
        profile=compile_card_profile(card_data, effect_record),
    )


def load_deck(
    deck_ref: str | Path,
    card_data_path: str | Path = DEFAULT_GAMEPLAY_OUTPUT_PATH,
) -> tuple[list[Card], LeaderCard, Base, dict[str, Any]]:
    """Load a decklist and return simulator deck cards, leader, base, and metadata."""
    deck_path = resolve_deck_path(deck_ref)
    decklist = json.loads(deck_path.read_text(encoding="utf-8"))
    card_index = _load_card_cache(card_data_path)
    effect_records = load_effects()

    leader_data = _lookup_card(card_index, decklist["leader"])
    leader_effect = effect_records.get(effect_key(str(leader_data.get("Set") or ""), str(leader_data.get("Number") or "")))
    leader = leader_from_data(leader_data, effect_record=leader_effect)
    if decklist.get("base"):
        base_data = _lookup_card(card_index, decklist["base"])
        base_effect = effect_records.get(effect_key(str(base_data.get("Set") or ""), str(base_data.get("Number") or "")))
        base = base_from_data(base_data, effect_record=base_effect)
    else:
        base = Base()
    deck_cards: list[Card] = []
    copy_index = 1

    for entry in decklist.get("cards", []):
        card_data = _lookup_card(card_index, entry)
        record = effect_records.get(effect_key(str(card_data.get("Set") or ""), str(card_data.get("Number") or "")))
        count = _to_int(entry.get("count"), default=1)
        for _ in range(count):
            deck_cards.append(card_from_data(card_data, copy_index=copy_index, effect_record=record))
            copy_index += 1

    metadata = {
        "name": decklist.get("name") or deck_path.stem,
        "path": str(deck_path),
        "card_count": len(deck_cards),
        "leader": leader.name,
        "base": base.name,
        "base_hp": base.hp,
    }
    return deck_cards, leader, base, metadata
