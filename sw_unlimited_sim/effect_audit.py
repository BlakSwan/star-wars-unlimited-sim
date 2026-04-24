"""Audit decklists for card text support in the simulator."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from deck_loader import _load_card_cache, _lookup_card, _to_int, resolve_deck_path
from effect_store import effect_key, load_effects
from effect_training import should_execute_record
from swu_db_client import DEFAULT_GAMEPLAY_OUTPUT_PATH


SUPPORTED_KEYWORDS = {
    "Ambush",
    "Grit",
    "Overwhelm",
    "Raid",
    "Restore",
    "Saboteur",
    "Shielded",
    "Sentinel",
}

SUPPORTED_CARD_NAMES = {
    "General Rieekan",
    "Darth Vader",
    "Admiral Ozzel",
    "Cantina Braggart",
    "Corellian Freighter",
    "Fighters For Freedom",
    "Fifth Brother",
    "Force Choke",
    "Force Lightning",
    "First Legion Snowtrooper",
    "Green Squadron A-Wing",
    "Heroic Sacrifice",
    "Hoth Lieutenant",
    "Improvised Detonation",
    "Imperial Interceptor",
    "K-2SO",
    "Karabast",
    "Medal Ceremony",
    "Partisan Insurgent",
    "Rebel Assault",
    "Red Three",
    "Sabine Wren",
    "Seventh Sister",
    "SpecForce Soldier",
    "Vader's Lightsaber",
    "Volunteer Soldier",
    "Wampa",
}

SUPPORTED_CARD_KEYS = {
    "IBH-10",  # Han Solo
    "JTL-017",  # Han Solo leader
    "JTL-123",  # Dogfight
    "JTL-088",  # Captain Phasma
    "JTL-060",  # Desperate Commando
    "LAW-202",  # Commence the Festivities
    "LAW-205",  # Flash the Vents
    "LAW-004",  # Aurra Sing leader
    "LAW-067",  # Jyn Erso
    "LAW-089",  # Kanan Jarrus
    "LAW-133",  # Lost and Forgotten
    "LOF-004",  # Kanan Jarrus leader
    "LOF-008",  # Obi-Wan Kenobi leader
    "LOF-221",  # Trust Your Instincts
    "LOF-031",  # Karis
    "LOF-041",  # Drain Essence
    "LOF-059",  # Nightsister Warrior
    "SOR-168",  # Precision Fire
    "SEC-157",  # One Way Out
    "TWI-014",  # Asajj Ventress leader
    "TWI-224",  # Breaking In
    "JTL-008",  # Wedge Antilles
    "JTL-050",  # Phantom II
    "JTL-051",  # Red Squadron X-Wing
    "JTL-054",  # Gold Leader
    "JTL-071",  # CR90 Relief Runner
    "JTL-096",  # Blue Leader
    "JTL-101",  # Red Leader
    "JTL-103",  # Chewbacca
    "JTL-045",  # Hera Syndulla
    "JTL-057",  # Astromech Pilot
    "JTL-058",  # Academy Graduate
    "JTL-093",  # Nien Nunb
    "JTL-108",  # Clone Pilot
    "JTL-150",  # Biggs Darklighter
    "JTL-144",  # No Disintegrations
    "JTL-151",  # Red Five
    "JTL-196",  # Dagger Squadron Pilot
    "JTL-197",  # Anakin Skywalker
    "JTL-203",  # Han Solo
    "JTL-229",  # Diversion
    "JTL-143",  # Devastator
    "LOF-046",  # Ezra Bridger
    "SEC-094",  # Mina Bonteri
    "SEC-233",  # Beguile
    "SOR-019",  # Security Complex
    "SOR-022",  # Energy Conversion Lab
    "SOR-025",  # Tarkintown
    "SOR-028",  # Jedha City
}

PARTIAL_CARD_KEYS = set()


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
    keywords: list[str] = field(default_factory=list)

    @property
    def has_piloting(self) -> bool:
        return "Piloting" in self.keywords or "piloting" in self.text.lower()

    @property
    def mechanic_tags(self) -> list[str]:
        tags = []
        text = self.text.lower()
        if self.has_piloting:
            tags.append("Piloting")
        if "when played" in text:
            tags.append("When Played")
        if "on attack" in text:
            tags.append("On Attack")
        if "when defeated" in text:
            tags.append("When Defeated")
        if "action [" in text:
            tags.append("Action")
        if "restore" in text or "Restore" in self.keywords:
            tags.append("Restore")
        return tags


@dataclass
class DeckAudit:
    deck_name: str
    deck_path: str
    leader: CardAudit
    base: CardAudit
    cards: list[CardAudit]
    validation_errors: list[str] = field(default_factory=list)

    @property
    def all_cards(self) -> list[CardAudit]:
        return [self.leader, self.base] + self.cards

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

    @property
    def piloting_cards(self) -> list[CardAudit]:
        return [card for card in self.all_cards if card.has_piloting]

    @property
    def piloting_counts_by_status(self) -> Counter:
        counts = Counter()
        for card in self.piloting_cards:
            counts[card.status] += card.count
        return counts

    @property
    def piloting_unique_counts_by_status(self) -> Counter:
        counts = Counter()
        for card in self.piloting_cards:
            counts[card.status] += 1
        return counts

    @property
    def is_valid_tournament_shape(self) -> bool:
        return not self.validation_errors

    @property
    def issue_mechanic_counts_by_status(self) -> dict[str, Counter]:
        counts: dict[str, Counter] = {"partial": Counter(), "unsupported": Counter()}
        for card in self.all_cards:
            if card.status not in counts:
                continue
            for tag in card.mechanic_tags:
                counts[card.status][tag] += card.count
        return counts


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


def _is_supported_keyword_only(card_data: dict[str, Any]) -> bool:
    keywords = _keywords(card_data)
    if not keywords or _unsupported_keywords(card_data):
        return False

    text = _text(card_data).lower()
    unsupported_triggers = [
        "when played",
        "when defeated",
        "action [",
        "attach",
        "draw",
        "discard",
        "search",
        "capture",
        "bounty",
        "smuggle",
        "exploit",
        "coordinate",
        "plot",
        "piloting",
        "hidden",
    ]
    if any(trigger in text for trigger in unsupported_triggers):
        return False

    # Supported keyword reminder text may contain phrases such as
    # "when this unit attacks" for Restore, Raid, and Saboteur.
    return True


def _audit_card(card_data: dict[str, Any], count: int, trained_effects: dict[str, Any] | None = None) -> CardAudit:
    reasons: list[str] = []
    text = _text(card_data)
    name = str(card_data.get("Name") or "Unknown Card")
    card_key = effect_key(str(card_data.get("Set") or ""), str(card_data.get("Number") or ""))
    trained_effects = trained_effects or {}
    trained_record = trained_effects.get(card_key)

    if trained_record and should_execute_record(trained_record):
        status = "supported"
        reasons.append("approved trained effect is executable")
    elif trained_record and trained_record.get("status") == "approved":
        status = "partial"
        reasons.append(f"approved trained effect is {trained_record.get('execution_status', 'manual')}")
    elif _has_stats_only_text(card_data):
        status = "supported"
        reasons.append("stat-only card")
    elif _is_supported_keyword_only(card_data):
        status = "supported"
        reasons.append("supported keyword-only card")
    elif card_key in PARTIAL_CARD_KEYS:
        status = "partial"
        reasons.append("card-specific handler implemented with known remaining gaps")
    elif name in SUPPORTED_CARD_NAMES or card_key in SUPPORTED_CARD_KEYS:
        unsupported_keywords = _unsupported_keywords(card_data)
        unsupported_keywords = [keyword for keyword in unsupported_keywords if keyword != "Piloting"]
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
        keywords=sorted(_keywords(card_data)),
    )


def audit_deck(
    deck_ref: str | Path,
    card_data_path: str | Path = DEFAULT_GAMEPLAY_OUTPUT_PATH,
) -> DeckAudit:
    """Audit a decklist against the simulator's supported effect subset."""
    deck_path = resolve_deck_path(deck_ref)
    decklist = json.loads(deck_path.read_text(encoding="utf-8"))
    card_index = _load_card_cache(card_data_path)
    trained_effects = load_effects()

    leader_data = _lookup_card(card_index, decklist["leader"])
    leader = _audit_card(leader_data, count=1, trained_effects=trained_effects)
    if decklist.get("base"):
        base_data = _lookup_card(card_index, decklist["base"])
        base = _audit_card(base_data, count=1, trained_effects=trained_effects)
    else:
        base = CardAudit(
            set_code="",
            number="",
            name="Generic Base",
            card_type="Base",
            count=1,
            status="supported",
            reasons=["using default 25 HP base"],
            text="",
            keywords=[],
        )

    card_audits = []
    validation_errors: list[str] = []
    total_cards = 0
    for entry in decklist.get("cards", []):
        card_data = _lookup_card(card_index, entry)
        count = _to_int(entry.get("count"), default=1)
        total_cards += count
        card_audits.append(_audit_card(card_data, count=count, trained_effects=trained_effects))

        if count > 3:
            validation_errors.append(
                f"{card_data.get('Set')} {card_data.get('Number')} {card_data.get('Name')} has {count} copies; max is 3."
            )

    min_cards = _to_int(decklist.get("minimum_cards"), default=50)
    if total_cards < min_cards:
        validation_errors.append(f"Main deck has {total_cards} cards; minimum is {min_cards}.")

    return DeckAudit(
        deck_name=decklist.get("name") or deck_path.stem,
        deck_path=str(deck_path),
        leader=leader,
        base=base,
        cards=card_audits,
        validation_errors=validation_errors,
    )


def format_deck_audit(audit: DeckAudit, show_supported: bool = False) -> str:
    """Format a deck audit for CLI output."""
    counts = audit.counts_by_status
    unique_counts = audit.unique_counts_by_status
    piloting_counts = audit.piloting_counts_by_status
    piloting_unique_counts = audit.piloting_unique_counts_by_status
    issue_mechanics = audit.issue_mechanic_counts_by_status
    total_cards = sum(card.count for card in audit.cards)
    lines = [
        f"Deck: {audit.deck_name}",
        f"Path: {audit.deck_path}",
        f"Leader: {audit.leader.set_code} {audit.leader.number} {audit.leader.name} [{audit.leader.status}]",
        f"Base: {audit.base.set_code} {audit.base.number} {audit.base.name} [{audit.base.status}]".strip(),
        f"Main deck cards: {total_cards}",
        f"Tournament shape: {'valid' if audit.is_valid_tournament_shape else 'invalid'}",
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
        (
            "Piloting support by copies: "
            f"supported={piloting_counts['supported']}, "
            f"partial={piloting_counts['partial']}, "
            f"unsupported={piloting_counts['unsupported']}"
        ),
        (
            "Piloting support by unique cards: "
            f"supported={piloting_unique_counts['supported']}, "
            f"partial={piloting_unique_counts['partial']}, "
            f"unsupported={piloting_unique_counts['unsupported']}"
        ),
    ]

    if audit.validation_errors:
        lines.append("")
        lines.append("Validation Issues")
        for issue in audit.validation_errors:
            lines.append(f"- {issue}")

    mechanic_lines = []
    for status in ("partial", "unsupported"):
        if not issue_mechanics[status]:
            continue
        summary = ", ".join(
            f"{name}={count}" for name, count in issue_mechanics[status].most_common()
        )
        mechanic_lines.append(f"{status}: {summary}")
    if mechanic_lines:
        lines.append("")
        lines.append("Mechanic Buckets")
        lines.extend(mechanic_lines)

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

    if audit.piloting_cards:
        lines.append("")
        lines.append("Piloting Support")
        for card in audit.piloting_cards:
            reason = "; ".join(card.reasons)
            lines.append(
                f"- {card.count}x {card.set_code} {card.number} {card.name} "
                f"[{card.status}]: {reason}"
            )

    add_section("Unsupported", "unsupported")
    add_section("Partially Supported", "partial")
    if show_supported:
        add_section("Supported", "supported")

    return "\n".join(lines)
