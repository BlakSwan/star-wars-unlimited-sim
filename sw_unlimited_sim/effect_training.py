"""Structured effect training schema and draft suggestion boundary."""

from __future__ import annotations

import json
import urllib.request
from abc import ABC, abstractmethod
from typing import Any

from settings import get_setting


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


class OpenAIEffectSuggestionProvider(EffectSuggestionProvider):
    """LLM-backed draft provider using the OpenAI Responses API."""

    name = "openai"

    def __init__(self, model: str | None = None):
        self.model = model or get_setting("SWU_LLM_MODEL", "gpt-5.4-mini")
        self.api_key = get_setting("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required. Put it in an untracked .env file or shell environment.")

    def suggest_effect(self, card: dict[str, Any]) -> dict[str, Any]:
        prompt = {
            "task": "Draft a Star Wars Unlimited simulator effect record for human review.",
            "constraints": [
                "Return only valid JSON.",
                "Use the schema shown in the blank_record.",
                "Set status to draft.",
                "Set execution_status to manual unless every trigger and step is clearly executable by the current engine.",
                "Prefer explicit conditions, target filters, durations, optional flags, and choice groups over prose notes.",
                "Do not invent card text.",
            ],
            "engine_executable_triggers": sorted(ENGINE_EXECUTABLE_TRIGGERS),
            "engine_executable_effects": sorted(ENGINE_EXECUTABLE_EFFECTS),
            "allowed_triggers": TRIGGERS,
            "allowed_effect_types": EFFECT_TYPES,
            "allowed_target_filters": TARGET_FILTERS,
            "allowed_condition_types": CONDITION_TYPES,
            "allowed_durations": DURATIONS,
            "blank_record": blank_effect_record(card),
            "card": {
                "set": card.get("Set"),
                "number": card.get("Number"),
                "name": card.get("Name"),
                "type": card.get("Type"),
                "traits": card.get("Traits") or [],
                "aspects": card.get("Aspects") or [],
                "keywords": card.get("Keywords") or [],
                "rules_text": rules_text(card),
            },
        }
        request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps({
                "model": self.model,
                "input": [
                    {
                        "role": "developer",
                        "content": "You convert trading card rules text into conservative simulator JSON drafts.",
                    },
                    {
                        "role": "user",
                        "content": json.dumps(prompt),
                    },
                ],
            }).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))

        record = self._parse_response_json(payload)
        record["status"] = "draft"
        record["source"] = f"openai:{self.model}"
        record.setdefault("review", {})
        record["review"]["llm_suggested"] = True
        record["review"]["human_verified"] = False
        record["execution_status"] = "manual"
        return record

    def _parse_response_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        text = payload.get("output_text") or ""
        if not text:
            for item in payload.get("output", []) or []:
                for content in item.get("content", []) or []:
                    if content.get("type") in {"output_text", "text"}:
                        text += content.get("text") or ""
        text = text.strip()
        if not text:
            raise ValueError("OpenAI response did not include text output")
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()
        return json.loads(text)


def get_effect_suggestion_provider(provider_name: str = "heuristic") -> EffectSuggestionProvider:
    if provider_name == "heuristic":
        return RuleTextHeuristicProvider()
    if provider_name == "openai":
        return OpenAIEffectSuggestionProvider()
    raise ValueError(f"Effect suggestion provider '{provider_name}' is not configured")
