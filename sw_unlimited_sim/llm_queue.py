"""Shared local-LLM drafting queue helpers."""

from __future__ import annotations

import re
from typing import Any

from deck_loader import _load_card_cache
from effect_audit import _audit_card
from effect_store import load_effects
from swu_db_client import DEFAULT_GAMEPLAY_OUTPUT_PATH


SIMPLE_LLM_BLOCKED_KEYWORDS = {
    "Bounty",
    "Capture",
    "Coordinate",
    "Exploit",
    "Hidden",
    "Plot",
    "Smuggle",
}

SIMPLE_LLM_BLOCKED_PHRASES = (
    "choose",
    "may",
    "another",
    "up to",
    "for each",
    "if you do",
    "instead",
    "search",
    "look at",
    "divided as you choose",
    "attached unit gains",
    "attach to",
    "piloting",
)


def compact_rules_text(card: dict[str, Any]) -> str:
    parts = []
    for field in ("FrontText", "BackText", "EpicAction"):
        value = str(card.get(field) or "").strip()
        if value:
            parts.append(" ".join(value.split()))
    return " ".join(parts)


def rules_word_count(text: str) -> int:
    return len([token for token in re.split(r"\s+", text.strip()) if token])


def simple_llm_bucket(card: dict[str, Any], text: str) -> str:
    lowered = text.lower()
    if lowered.startswith("when played:"):
        return "when_played"
    if lowered.startswith("on attack:"):
        return "on_attack"
    if lowered.startswith("action"):
        return "action"
    if str(card.get("Type") or "").lower() == "event":
        return "event"
    return "other"


def simple_llm_candidates(
    max_words: int = 10,
    limit: int | None = None,
    selected_sets: set[str] | None = None,
) -> list[dict[str, Any]]:
    selected_sets = {set_code.upper() for set_code in (selected_sets or set())}
    cards = sorted(
        _load_card_cache(DEFAULT_GAMEPLAY_OUTPUT_PATH).values(),
        key=lambda card: (
            str(card.get("_source_set_code") or card.get("Set") or ""),
            str(card.get("Number") or ""),
        ),
    )
    effects = load_effects()
    candidates: list[dict[str, Any]] = []

    for card in cards:
        set_code = str(card.get("_source_set_code") or card.get("Set") or "").upper()
        if selected_sets and set_code not in selected_sets:
            continue

        text = compact_rules_text(card)
        if not text:
            continue
        word_count = rules_word_count(text)
        if word_count > max_words:
            continue
        if SIMPLE_LLM_BLOCKED_KEYWORDS.intersection(set(card.get("Keywords") or [])):
            continue

        lowered = text.lower()
        if any(phrase in lowered for phrase in SIMPLE_LLM_BLOCKED_PHRASES):
            continue

        audit = _audit_card(card, count=1, trained_effects=effects)
        if audit.status == "supported":
            continue

        number = str(card.get("Number") or "").zfill(3)
        candidates.append(
            {
                "key": f"{set_code}-{number}",
                "title": str(card.get("Name") or ""),
                "type": str(card.get("Type") or ""),
                "bucket": simple_llm_bucket(card, text),
                "words": word_count,
                "text": text,
                "card": card,
            }
        )

    candidates.sort(
        key=lambda entry: (
            ("when_played", "on_attack", "action", "event", "other").index(entry["bucket"]),
            entry["words"],
            entry["key"],
        )
    )
    if limit is not None:
        candidates = candidates[:limit]
    return candidates
