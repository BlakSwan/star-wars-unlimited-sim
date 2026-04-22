"""Structured effect training schema and draft suggestion boundary."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


TRIGGERS = [
    "when_played",
    "on_attack",
    "when_defeated",
    "action",
    "constant",
    "when_attacked",
    "when_unit_defeated",
    "when_event_played",
    "regroup_start",
]

EFFECT_TYPES = [
    "deal_damage",
    "heal_damage",
    "draw_cards",
    "discard_cards",
    "exhaust_unit",
    "ready_unit",
    "defeat_unit",
    "give_shield",
    "give_experience",
    "capture_unit",
    "search_deck",
    "look_at_cards",
    "move_card",
    "modify_stats",
    "prevent_damage",
    "create_token",
    "attack_with_unit",
    "choose_mode",
]

TARGET_CONTROLLERS = ["enemy", "friendly", "self", "any", "opponent", "active_player"]
TARGET_TYPES = ["unit", "base", "player", "card", "upgrade", "event", "leader", "resource"]
TARGET_FILTERS = [
    "none",
    "damaged",
    "undamaged",
    "non_leader",
    "leader",
    "ground",
    "space",
    "vehicle",
    "non_vehicle",
    "token",
    "non_token",
    "trait",
    "aspect",
    "cost_or_less",
    "power_or_less",
    "remaining_hp_or_less",
]
CONDITION_TYPES = [
    "none",
    "you_control_trait",
    "you_control_aspect",
    "opponent_controls_more_units",
    "you_have_initiative",
    "played_aspect_this_phase",
    "attacked_this_phase",
    "unit_was_defeated_this_phase",
    "base_damage_at_least",
    "cards_drawn_this_phase_at_least",
]
DURATIONS = ["instant", "this_attack", "this_phase", "until_ready", "while_attached", "constant"]
EXECUTION_STATUSES = ["executable", "partial", "manual"]

ENGINE_EXECUTABLE_EFFECTS = {
    "deal_damage",
    "heal_damage",
    "draw_cards",
    "discard_cards",
    "exhaust_unit",
    "ready_unit",
    "defeat_unit",
    "give_shield",
    "give_experience",
}

ENGINE_EXECUTABLE_TRIGGERS = {"when_played", "on_attack", "when_defeated", "action"}


def rules_text(card: dict[str, Any]) -> str:
    return "\n".join(
        str(card.get(field) or "")
        for field in ("FrontText", "BackText", "EpicAction")
        if card.get(field)
    )


def blank_effect_record(card: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "set": card.get("Set"),
        "number": card.get("Number"),
        "name": card.get("Name"),
        "status": "draft",
        "execution_status": "manual",
        "source": "human_review",
        "review": {
            "confidence": "medium",
            "notes": "",
            "llm_suggested": False,
            "human_verified": False,
        },
        "raw_text": rules_text(card),
        "triggers": [],
    }


def build_step(
    effect_type: str,
    amount: str,
    target_controller: str,
    target_type: str,
    target_filter: str = "none",
    filter_value: str = "",
    duration: str = "instant",
    optional: bool = False,
    choice_group: str = "",
) -> dict[str, Any] | None:
    if not effect_type:
        return None
    step: dict[str, Any] = {
        "type": effect_type,
        "duration": duration,
        "optional": optional,
        "target": {
            "controller": target_controller,
            "type": target_type,
        },
    }
    if amount:
        step["amount"] = int(amount)
    if target_filter and target_filter != "none":
        step["target"]["filter"] = target_filter
    if filter_value:
        step["target"]["filter_value"] = filter_value
    if choice_group:
        step["choice_group"] = choice_group
    return step


def build_condition(condition_type: str, value: str = "") -> dict[str, Any] | None:
    if not condition_type or condition_type == "none":
        return None
    condition = {"type": condition_type}
    if value:
        condition["value"] = value
    return condition


def execution_status_for_record(record: dict[str, Any]) -> str:
    """Return whether the current engine should execute this record."""
    triggers = record.get("triggers") or []
    if not triggers:
        return "manual"

    for trigger in triggers:
        if trigger.get("event") not in ENGINE_EXECUTABLE_TRIGGERS:
            return "manual"
        if trigger.get("conditions"):
            return "partial"
        for step in trigger.get("steps") or []:
            if step.get("type") not in ENGINE_EXECUTABLE_EFFECTS:
                return "partial"
            if step.get("duration") not in (None, "", "instant"):
                return "partial"
            target = step.get("target") or {}
            if target.get("filter"):
                return "partial"
            if step.get("optional") or step.get("choice_group"):
                return "partial"
    return "executable"


def should_execute_record(record: dict[str, Any]) -> bool:
    if record.get("status") != "approved":
        return False
    execution_status = record.get("execution_status")
    return execution_status in (None, "", "executable")


class EffectSuggestionProvider(ABC):
    """Boundary for future LLM-backed unsupported-card training."""

    name = "base"

    @abstractmethod
    def suggest_effect(self, card: dict[str, Any]) -> dict[str, Any]:
        """Return a draft structured effect record for human review."""


class RuleTextHeuristicProvider(EffectSuggestionProvider):
    """Offline draft provider used until an LLM provider is configured."""

    name = "heuristic"

    def suggest_effect(self, card: dict[str, Any]) -> dict[str, Any]:
        record = blank_effect_record(card)
        text = rules_text(card).lower()
        if "when played" in text:
            event = "when_played"
        elif "on attack" in text:
            event = "on_attack"
        elif "when defeated" in text:
            event = "when_defeated"
        elif "action" in text:
            event = "action"
        else:
            event = "constant"

        record["source"] = "heuristic_suggestion"
        record["review"]["notes"] = "Drafted from keyword heuristics; requires human review."
        record["review"]["human_verified"] = False
        record["triggers"] = [{"event": event, "conditions": [], "steps": []}]
        record["execution_status"] = "manual"
        return record


def get_effect_suggestion_provider(provider_name: str = "heuristic") -> EffectSuggestionProvider:
    if provider_name != "heuristic":
        raise ValueError(f"Effect suggestion provider '{provider_name}' is not configured")
    return RuleTextHeuristicProvider()
