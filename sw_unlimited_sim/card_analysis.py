"""Analyze SWU DB card text and simulator support coverage."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from effect_audit import _audit_card
from effect_store import load_effects
from swu_db_client import DEFAULT_GAMEPLAY_OUTPUT_PATH


MECHANIC_PATTERNS = [
    "damage",
    "when played",
    "defeat",
    "on attack",
    "exhaust",
    "sentinel",
    "shield",
    "discard",
    "ready",
    "upgrade",
    "draw",
    "heal",
    "when defeated",
    "experience",
    "raid",
    "ambush",
    "overwhelm",
    "restore",
    "saboteur",
    "capture",
    "search",
    "grit",
    "bounty",
    "smuggle",
    "look at",
    "exploit",
]


def _card_text(card: dict[str, Any]) -> str:
    return "\n".join(str(card.get(field) or "") for field in ("FrontText", "BackText", "EpicAction"))


def analyze_card_database(
    card_data_path: str | Path = DEFAULT_GAMEPLAY_OUTPUT_PATH,
    trained_effects: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return aggregate mechanic and support data for the card database."""
    data = json.loads(Path(card_data_path).read_text(encoding="utf-8"))
    cards = data.get("cards", [])
    trained_effects = trained_effects if trained_effects is not None else load_effects()
    keyword_counts: Counter = Counter()
    pattern_counts: Counter = Counter()
    type_counts: Counter = Counter()
    support_counts: Counter = Counter()
    unsupported_patterns: Counter = Counter()
    unsupported_examples: dict[str, list[str]] = {}

    for card in cards:
        type_counts[str(card.get("Type") or "Unknown")] += 1
        text = _card_text(card)
        lowered = text.lower()

        for keyword in card.get("Keywords") or []:
            keyword_counts[str(keyword)] += 1

        for pattern in MECHANIC_PATTERNS:
            if pattern in lowered:
                pattern_counts[pattern] += 1

        audit = _audit_card(card, count=1, trained_effects=trained_effects)
        support_counts[audit.status] += 1

        if audit.status != "supported":
            for pattern in MECHANIC_PATTERNS:
                if pattern in lowered:
                    unsupported_patterns[pattern] += 1
                    unsupported_examples.setdefault(pattern, [])
                    if len(unsupported_examples[pattern]) < 5:
                        unsupported_examples[pattern].append(
                            f"{card.get('Set')} {card.get('Number')} {card.get('Name')}"
                        )

    return {
        "total_cards": len(cards),
        "type_counts": dict(type_counts.most_common()),
        "keyword_counts": dict(keyword_counts.most_common()),
        "pattern_counts": dict(pattern_counts.most_common()),
        "support_counts": dict(support_counts.most_common()),
        "unsupported_patterns": dict(unsupported_patterns.most_common()),
        "unsupported_examples": unsupported_examples,
    }


def format_card_analysis(analysis: dict[str, Any], limit: int = 15) -> str:
    """Format card database analysis for CLI output."""
    lines = [
        "=== Card Database Analysis ===",
        f"Total gameplay cards: {analysis['total_cards']}",
        "",
        "Card Types:",
    ]

    for name, count in analysis["type_counts"].items():
        lines.append(f"- {name}: {count}")

    lines.append("")
    lines.append("Simulator Support:")
    support_counts = Counter(analysis["support_counts"])
    total = max(1, analysis["total_cards"])
    for status in ("supported", "partial", "unsupported"):
        count = support_counts.get(status, 0)
        lines.append(f"- {status}: {count} ({count / total:.1%})")

    lines.append("")
    lines.append(f"Top Keywords (top {limit}):")
    for name, count in list(analysis["keyword_counts"].items())[:limit]:
        lines.append(f"- {name}: {count}")

    lines.append("")
    lines.append(f"Top Text Patterns (top {limit}):")
    for name, count in list(analysis["pattern_counts"].items())[:limit]:
        lines.append(f"- {name}: {count}")

    lines.append("")
    lines.append(f"Top Unsupported Patterns (top {limit}):")
    for name, count in list(analysis["unsupported_patterns"].items())[:limit]:
        examples = "; ".join(analysis["unsupported_examples"].get(name, []))
        suffix = f" | examples: {examples}" if examples else ""
        lines.append(f"- {name}: {count}{suffix}")

    return "\n".join(lines)
