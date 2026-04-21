"""Audit decklists for card text support in the simulator."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from deck_loader import _load_card_cache, _lookup_card, _to_int, resolve_deck_path
from swu_db_client import DEFAULT_GAMEPLAY_OUTPUT_PATH


SUPPORTED_KEYWORDS = {
    "Ambush",
    "Overwhelm",
    "Raid",
    "Saboteur",
    "Sentinel",
}

SUPPORTED_CARD_NAMES = {
    "Darth Vader",
    "Admiral Ozzel",
    "Fighters For Freedom",
    "Fifth Brother",
    "Force Choke",
    "Force Lightning",
    "First Legion Snowtrooper",
    "Green Squadron A-Wing",
    "Heroic Sacrifice",
    "Imperial Interceptor",
    "K-2SO",
    "Karabast",
    "Medal Ceremony",
    "Rebel Assault",
    "Red Three",
    "Sabine Wren",
    "Seventh Sister",
    "SpecForce Soldier",
    "Vader's Lightsaber",
}


@dataclass
class CardAudit:
    set_code: str
    number: str
    name: str
    card_type: str
    count: int
    status: str
    reasons: list[str] = field(default_factory=list)
    text: str = ""


@dataclass
class DeckAudit:
    deck_name: str
    deck_path: str
    leader: CardAudit
    cards: list[CardAudit]

    @property
    def all_cards(self) -> list[CardAudit]:
        return [self.leader] + self.cards

    @property
    def counts_by_status(self) -> Counter:
        counts = Counter()
        for card in self.all_cards:
            counts[card.status] += card.count
        return counts

    @property
    def unique_counts_by_status(self) -> Counter:
        counts = Counter()
        for card in self.all_cards:
            counts[card.status] += 1
        return counts

    @property
    def unsupported_count(self) -> int:
        return self.counts_by_status["unsupported"]

    @property
    def partial_count(self) -> int:
        return self.counts_by_status["partial"]


def _text(card_data: dict[str, Any]) -> str:
    fields = [
        card_data.get("FrontText"),
        card_data.get("BackText"),
        card_data.get("EpicAction"),
    ]
    return "\n".join(str(value) for value in fields if value)


def _keywords(card_data: dict[str, Any]) -> set[str]:
    return {str(keyword) for keyword in (card_data.get("Keywords") or [])}


def _has_stats_only_text(card_data: dict[str, Any]) -> bool:
    return not _text(card_data).strip() and not _keywords(card_data)


def _unsupported_keywords(card_data: dict[str, Any]) -> list[str]:
    return sorted(keyword for keyword in _keywords(card_data) if keyword not in SUPPORTED_KEYWORDS)


def _audit_card(card_data: dict[str, Any], count: int) -> CardAudit:
    reasons: list[str] = []
    text = _text(card_data)
    name = str(card_data.get("Name") or "Unknown Card")

    if _has_stats_only_text(card_data):
        status = "supported"
        reasons.append("stat-only card")
    elif name in SUPPORTED_CARD_NAMES:
        unsupported_keywords = _unsupported_keywords(card_data)
        if unsupported_keywords:
            status = "partial"
            reasons.append(f"unsupported keywords: {', '.join(unsupported_keywords)}")
        else:
            status = "supported"
            reasons.append("card-specific handler implemented")
    else:
        unsupported_keywords = _unsupported_keywords(card_data)
        if unsupported_keywords:
            status = "unsupported"
            reasons.append(f"unsupported keywords: {', '.join(unsupported_keywords)}")
        else:
            status = "unsupported"
            reasons.append("rules text has no simulator handler")

    return CardAudit(
        set_code=str(card_data.get("Set") or ""),
        number=str(card_data.get("Number") or ""),
        name=name,
        card_type=str(card_data.get("Type") or ""),
        count=count,
        status=status,
        reasons=reasons,
        text=text,
    )


def audit_deck(
    deck_ref: str | Path,
    card_data_path: str | Path = DEFAULT_GAMEPLAY_OUTPUT_PATH,
) -> DeckAudit:
    """Audit a decklist against the simulator's supported effect subset."""
    deck_path = resolve_deck_path(deck_ref)
    decklist = json.loads(deck_path.read_text(encoding="utf-8"))
    card_index = _load_card_cache(card_data_path)

    leader_data = _lookup_card(card_index, decklist["leader"])
    leader = _audit_card(leader_data, count=1)

    card_audits = []
    for entry in decklist.get("cards", []):
        card_data = _lookup_card(card_index, entry)
        card_audits.append(_audit_card(card_data, count=_to_int(entry.get("count"), default=1)))

    return DeckAudit(
        deck_name=decklist.get("name") or deck_path.stem,
        deck_path=str(deck_path),
        leader=leader,
        cards=card_audits,
    )


def format_deck_audit(audit: DeckAudit, show_supported: bool = False) -> str:
    """Format a deck audit for CLI output."""
    counts = audit.counts_by_status
    unique_counts = audit.unique_counts_by_status
    total_cards = sum(card.count for card in audit.cards)
    lines = [
        f"Deck: {audit.deck_name}",
        f"Path: {audit.deck_path}",
        f"Leader: {audit.leader.set_code} {audit.leader.number} {audit.leader.name} [{audit.leader.status}]",
        f"Main deck cards: {total_cards}",
        (
            "Support by copies: "
            f"supported={counts['supported']}, "
            f"partial={counts['partial']}, "
            f"unsupported={counts['unsupported']}"
        ),
        (
            "Support by unique cards: "
            f"supported={unique_counts['supported']}, "
            f"partial={unique_counts['partial']}, "
            f"unsupported={unique_counts['unsupported']}"
        ),
    ]

    def add_section(title: str, status: str):
        cards = [card for card in audit.all_cards if card.status == status]
        if not cards:
            return
        lines.append("")
        lines.append(title)
        for card in cards:
            lines.append(
                f"- {card.count}x {card.set_code} {card.number} {card.name} "
                f"({card.card_type}): {'; '.join(card.reasons)}"
            )
            if card.text:
                compact_text = " ".join(card.text.split())
                lines.append(f"  Text: {compact_text}")

    add_section("Unsupported", "unsupported")
    add_section("Partially Supported", "partial")
    if show_supported:
        add_section("Supported", "supported")

    return "\n".join(lines)
