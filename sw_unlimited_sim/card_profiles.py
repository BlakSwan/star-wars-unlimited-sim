"""Compile SWU DB card JSON into compact runtime card profiles."""

from __future__ import annotations

from typing import Any

from effect_training import validate_effect_record
from models import CardProfile


MECHANIC_PATTERNS: list[tuple[str, str]] = [
    ("when played", "When Played"),
    ("on attack", "On Attack"),
    ("when defeated", "When Defeated"),
    ("action [", "Action"),
    ("when deployed", "When Deployed"),
    ("when the regroup phase starts", "Regroup Start"),
    ("piloting", "Piloting"),
    ("plot", "Plot"),
    ("capture", "Capture"),
    ("hidden", "Hidden"),
    ("smuggle", "Smuggle"),
    ("bounty", "Bounty"),
    ("coordinate", "Coordinate"),
    ("exploit", "Exploit"),
]


def rules_text_from_card_data(card_data: dict[str, Any]) -> str:
    return "\n".join(
        str(card_data.get(field) or "")
        for field in ("FrontText", "BackText", "EpicAction")
        if card_data.get(field)
    )


def _ability_lines(card_data: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for field in ("FrontText", "BackText", "EpicAction"):
        value = card_data.get(field)
        if value not in (None, ""):
            lines.append(str(value))
    return lines


def _mechanic_tags(card_data: dict[str, Any]) -> list[str]:
    text = rules_text_from_card_data(card_data).lower()
    tags = []
    for pattern, tag in MECHANIC_PATTERNS:
        if pattern in text:
            tags.append(tag)
    for keyword in card_data.get("Keywords") or []:
        keyword_text = str(keyword).strip()
        if keyword_text and keyword_text not in tags:
            tags.append(keyword_text)
    return tags


def compile_card_profile(card_data: dict[str, Any], effect_record: dict[str, Any] | None = None) -> CardProfile:
    validation = validate_effect_record(effect_record) if effect_record else None
    review = (effect_record or {}).get("review") if isinstance(effect_record, dict) else {}
    llm_augmented = bool((review or {}).get("llm_suggested"))

    return CardProfile(
        set_code=str(card_data.get("Set") or ""),
        number=str(card_data.get("Number") or ""),
        card_type=str(card_data.get("Type") or ""),
        rules_text=rules_text_from_card_data(card_data),
        ability_lines=_ability_lines(card_data),
        keywords=[str(keyword) for keyword in (card_data.get("Keywords") or [])],
        traits=[str(trait) for trait in (card_data.get("Traits") or [])],
        aspects=[str(aspect) for aspect in (card_data.get("Aspects") or [])],
        mechanic_tags=_mechanic_tags(card_data),
        source_fields={
            "front_text": str(card_data.get("FrontText") or ""),
            "back_text": str(card_data.get("BackText") or ""),
            "epic_action": str(card_data.get("EpicAction") or ""),
        },
        llm_augmented=llm_augmented,
        effect_record=effect_record,
        effect_execution_status=str((effect_record or {}).get("execution_status") or "manual"),
        effect_validation=validation,
    )


def compact_profile_payload(
    card_data: dict[str, Any],
    profile: CardProfile,
    *,
    copy_count: int | None = None,
    include_effect_record: bool = False,
) -> dict[str, Any]:
    """Return a token-efficient JSON payload for local LLM workflows."""
    payload: dict[str, Any] = {
        "card_ref": f"{profile.set_code}-{profile.number}",
        "name": str(card_data.get("Name") or ""),
        "type": profile.card_type,
        "cost": card_data.get("Cost"),
        "power": card_data.get("Power"),
        "hp": card_data.get("HP"),
        "arenas": card_data.get("Arenas") or [],
        "traits": profile.traits,
        "aspects": profile.aspects,
        "keywords": profile.keywords,
        "mechanic_tags": profile.mechanic_tags,
        "rules_text": profile.rules_text,
        "llm_augmented": profile.llm_augmented,
        "effect_execution_status": profile.effect_execution_status,
        "effect_validation_status": (profile.effect_validation or {}).get("execution_analysis", {}).get("status", "manual"),
    }
    if copy_count is not None:
        payload["count"] = copy_count
    if include_effect_record and profile.effect_record:
        payload["effect_record"] = profile.effect_record
    return payload
