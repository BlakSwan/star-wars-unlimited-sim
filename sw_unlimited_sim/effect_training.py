"""Structured effect training schema and draft suggestion boundary."""

from __future__ import annotations

import json
import re
import socket
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path
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
    "when_played_as_upgrade",
    "when_pilot_attached",
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
    "attached_unit",
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
TRIAGE_BUCKETS = ["safe_draft", "needs_review", "unresolved"]

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
    "create_token",
    "modify_stats",
}

ENGINE_EXECUTABLE_TRIGGERS = {
    "when_played",
    "on_attack",
    "when_defeated",
    "action",
    "when_played_as_upgrade",
    "when_pilot_attached",
}

STRICT_REQUIRED_TOP_LEVEL_FIELDS = ["set", "number", "name", "status", "triggers"]
RISKY_RULE_TEXT_TERMS = [
    "another",
    "up to",
    "may",
    "choose",
    "instead",
    "if you do",
    "for each",
    "attach",
    "upgrade",
    "capture",
    "search",
    "look at",
    "until",
    "divided as you choose",
]


class EffectSuggestionError(RuntimeError):
    """User-facing error raised when a draft provider cannot create a draft."""

    def __init__(self, title: str, detail: str, actions: list[str] | None = None):
        super().__init__(detail)
        self.title = title
        self.detail = detail
        self.actions = actions or []


class LocalModelResponseError(RuntimeError):
    """Raised when a local model returns unusable text instead of JSON."""

    def __init__(self, message: str, raw_output: str = ""):
        super().__init__(message)
        self.raw_output = raw_output


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


def prompt_schema_contract() -> dict[str, Any]:
    """Return the exact trigger/step shape local models should emit."""
    return {
        "trigger_object": {
            "event": "one of allowed_triggers",
            "conditions": [{"type": "one of allowed_condition_types", "value": "optional string"}],
            "steps": [
                {
                    "type": "one of allowed_effect_types",
                    "amount": "optional integer",
                    "duration": "one of allowed_durations",
                    "optional": False,
                    "target": {
                        "controller": "one of allowed_target_controllers",
                        "type": "one of allowed_target_types",
                        "filter": "optional allowed_target_filter",
                        "filter_value": "optional string",
                    },
                }
            ],
        },
        "important_rules": [
            "The trigger event field is named event, not type.",
            "Put effect steps inside trigger.steps.",
            "Do not put effect_type, target_controller, or target_type at trigger level.",
            "Use integers for amount, power, and hp when present.",
        ],
    }


def prompt_examples() -> dict[str, Any]:
    """Return small good/bad examples to keep local-model output aligned."""
    return {
        "good_example_for_when_played_draw_a_card": {
            "raw_text": "When Played: Draw a card.",
            "record_fragment": {
                "triggers": [
                    {
                        "event": "when_played",
                        "conditions": [],
                        "steps": [
                            {
                                "type": "draw_cards",
                                "amount": 1,
                                "duration": "instant",
                                "optional": False,
                                "target": {
                                    "controller": "friendly",
                                    "type": "player",
                                },
                            }
                        ],
                    }
                ]
            },
        },
        "legacy_shape_to_avoid": {
            "not_allowed": {
                "triggers": [
                    {
                        "type": "when_played",
                        "effect_type": "draw_cards",
                        "target_controller": "self",
                        "target_type": "card",
                    }
                ]
            }
        },
        "good_example_for_when_played_create_token": {
            "raw_text": "When Played: Create an X-Wing token.",
            "record_fragment": {
                "triggers": [
                    {
                        "event": "when_played",
                        "conditions": [],
                        "steps": [
                            {
                                "type": "create_token",
                                "token_name": "X-Wing token",
                                "amount": 1,
                                "duration": "instant",
                                "optional": False,
                                "target": {
                                    "controller": "friendly",
                                    "type": "player",
                                },
                            }
                        ],
                    }
                ]
            },
        },
        "good_example_for_when_played_exhaust_attached_unit": {
            "raw_text": "When Played: Exhaust attached unit.",
            "record_fragment": {
                "triggers": [
                    {
                        "event": "when_played",
                        "conditions": [],
                        "steps": [
                            {
                                "type": "exhaust_unit",
                                "amount": 1,
                                "duration": "instant",
                                "optional": False,
                                "target": {
                                    "controller": "self",
                                    "type": "unit",
                                    "filter": "attached_unit",
                                },
                            }
                        ],
                    }
                ]
            },
        },
    }


def prompt_swu_primer() -> dict[str, Any]:
    """Return compact SWU-specific rules context for local drafting."""
    return {
        "core_terms": [
            "'When Played' triggers when the card enters play.",
            "'On Attack' triggers when the unit declares an attack.",
            "'When Defeated' triggers when the unit is defeated.",
            "'Action [Exhaust]' is an activated ability and should usually map to trigger event 'action'.",
            "'This unit' refers to the source unit itself.",
            "'Your base' or 'a base' should target target.type 'base'.",
            "Drawing cards affects the acting player, not a card object.",
            "Creating tokens usually affects the friendly player or board state controlled by that player.",
        ],
        "targeting_conventions": [
            "Use target.controller 'self' only when the text explicitly refers to the source, such as 'this unit'.",
            "Use target.controller 'friendly' for 'your' or generally friendly targets.",
            "Use target.controller 'enemy' for opposing units or bases.",
            "Use target.type 'player' for draw or discard effects that affect a player rather than a card.",
            "If the card is an upgrade and the text says 'attached unit', use target.filter 'attached_unit'.",
        ],
        "timing_conventions": [
            "Most immediate card effects use duration 'instant'.",
            "Temporary combat or round modifiers often use 'this_attack' or 'this_phase', but only when the text explicitly gives a temporary duration.",
            "Do not use 'constant' unless the text is a continuous static ability.",
        ],
    }


def prompt_effect_mapping_guide() -> dict[str, Any]:
    """Return a compact phrase-to-schema lexicon for common supported effects."""
    return {
        "phrase_to_step_type": {
            "draw a card": "draw_cards",
            "draw 2 cards": "draw_cards",
            "deal damage": "deal_damage",
            "heal damage": "heal_damage",
            "exhaust a unit": "exhaust_unit",
            "ready a unit": "ready_unit",
            "defeat a unit": "defeat_unit",
            "give a shield token": "give_shield",
            "give an experience token": "give_experience",
            "create a token": "create_token",
            "gets +X/+Y for this phase": "modify_stats",
        },
        "normalization_hints": [
            "'Draw a card' should usually become amount 1 and target friendly player.",
            "'Create an X-Wing token' should use type 'create_token' and token_name 'X-Wing token'.",
            "'Deal 3 damage to this unit' should target self unit with amount 3.",
            "'Exhaust attached unit' should use type 'exhaust_unit' and target.filter 'attached_unit'.",
            "If text names a ground or space restriction, prefer a target filter instead of prose notes when possible.",
        ],
    }


def prompt_engine_review_rules() -> dict[str, Any]:
    """Return repo-specific guidance for conservative drafts."""
    return {
        "review_boundary": [
            "Output a draft only. Never mark status approved.",
            "If the text needs unsupported mechanics, keep the structure conservative and note uncertainty.",
            "If you cannot express the card cleanly in the schema, leave fewer triggers and add notes instead of inventing new fields.",
        ],
        "engine_bias": [
            "Prefer currently executable step types when the card text clearly matches them.",
            "Do not invent composite steps when a single known step type is enough.",
            "Never use legacy flat trigger fields like effect_type or target_controller at trigger level.",
        ],
        "risky_terms": RISKY_RULE_TEXT_TERMS,
    }


def prompt_repo_approved_examples(limit: int = 6) -> list[dict[str, Any]]:
    """Return a compact set of approved executable in-repo examples for local prompting."""
    effects_path = Path(__file__).resolve().parent / "data" / "effects" / "card_effects.json"
    if not effects_path.exists():
        return []
    try:
        payload = json.loads(effects_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    examples: list[dict[str, Any]] = []
    for key, record in sorted(payload.items()):
        if record.get("status") != "approved":
            continue
        if record.get("execution_status") != "executable":
            continue
        triggers = record.get("triggers") or []
        if not triggers:
            continue
        first_trigger = triggers[0] if isinstance(triggers[0], dict) else {}
        first_steps = first_trigger.get("steps") or []
        primary_step = first_steps[0] if first_steps and isinstance(first_steps[0], dict) else {}
        examples.append(
            {
                "card_ref": key,
                "name": record.get("name"),
                "raw_text": record.get("raw_text", ""),
                "primary_event": first_trigger.get("event"),
                "primary_step_type": primary_step.get("type"),
                "record_fragment": {
                    "triggers": triggers,
                },
            }
        )
    examples.sort(key=lambda entry: (str(entry.get("primary_step_type") or ""), str(entry.get("card_ref") or "")))
    return examples[:limit]


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
    return execution_analysis_for_record(record)["status"]


def execution_analysis_for_record(record: dict[str, Any]) -> dict[str, Any]:
    """Explain why a record is executable, partial, or manual."""
    triggers = record.get("triggers") or []
    raw_text = str(record.get("raw_text") or "").lower()
    blockers: list[str] = []
    metrics = {
        "trigger_count": len(triggers),
        "condition_count": 0,
        "step_count": 0,
        "unsupported_trigger_count": 0,
        "unsupported_step_count": 0,
        "filtered_target_count": 0,
        "optional_step_count": 0,
        "choice_step_count": 0,
        "non_instant_duration_count": 0,
    }
    status = "executable"

    if not isinstance(triggers, list) or not triggers:
        return {
            "status": "manual",
            "blockers": ["record has no triggers"],
            "metrics": metrics,
        }

    for trigger_index, trigger in enumerate(triggers, start=1):
        if not isinstance(trigger, dict):
            blockers.append(f"trigger {trigger_index} is not an object")
            status = "manual"
            continue
        event = trigger.get("event")
        if event not in TRIGGERS:
            blockers.append(f"trigger {trigger_index} has invalid event {event!r}")
            status = "manual"
            continue
        if event not in ENGINE_EXECUTABLE_TRIGGERS:
            blockers.append(f"trigger {trigger_index} uses unsupported runtime event {event}")
            metrics["unsupported_trigger_count"] += 1
            status = "manual"
        conditions = trigger.get("conditions") or []
        metrics["condition_count"] += len(conditions)
        if conditions:
            blockers.append(f"trigger {trigger_index} has conditions that the runtime does not evaluate")
            if status != "manual":
                status = "partial"
        steps = trigger.get("steps") or []
        metrics["step_count"] += len(steps)
        if not isinstance(steps, list):
            blockers.append(f"trigger {trigger_index} steps are not a list")
            status = "manual"
            continue
        for step_index, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                blockers.append(f"trigger {trigger_index} step {step_index} is not an object")
                status = "manual"
                continue
            effect_type = step.get("type")
            if effect_type not in EFFECT_TYPES:
                blockers.append(f"trigger {trigger_index} step {step_index} has invalid type {effect_type!r}")
                status = "manual"
                continue
            if effect_type not in ENGINE_EXECUTABLE_EFFECTS:
                blockers.append(f"trigger {trigger_index} step {step_index} uses unsupported runtime effect {effect_type}")
                metrics["unsupported_step_count"] += 1
                if status != "manual":
                    status = "partial"
            duration = step.get("duration")
            if effect_type == "modify_stats" and duration in ("while_attached", "this_attack", "this_phase"):
                pass
            elif duration not in (None, "", "instant"):
                blockers.append(f"trigger {trigger_index} step {step_index} uses unsupported duration {duration!r}")
                metrics["non_instant_duration_count"] += 1
                if status != "manual":
                    status = "partial"
            target = step.get("target") or {}
            if not isinstance(target, dict):
                blockers.append(f"trigger {trigger_index} step {step_index} target is not an object")
                status = "manual"
                continue
            if target.get("controller") not in (None, *TARGET_CONTROLLERS):
                blockers.append(
                    f"trigger {trigger_index} step {step_index} has invalid target controller {target.get('controller')!r}"
                )
                status = "manual"
            if target.get("type") not in (None, *TARGET_TYPES):
                blockers.append(
                    f"trigger {trigger_index} step {step_index} has invalid target type {target.get('type')!r}"
                )
                status = "manual"
            target_filter = target.get("filter")
            if target_filter and target_filter not in {"attached_unit", "ground", "space"}:
                blockers.append(f"trigger {trigger_index} step {step_index} uses unsupported target filters")
                metrics["filtered_target_count"] += 1
                if status != "manual":
                    status = "partial"
            if target_filter in {"ground", "space"} and f"all {target_filter} units" in raw_text:
                blockers.append(
                    f"trigger {trigger_index} step {step_index} targets only one {target_filter} unit but card text affects all {target_filter} units"
                )
                if status != "manual":
                    status = "partial"
            if step.get("optional"):
                blockers.append(f"trigger {trigger_index} step {step_index} requires an optional choice")
                metrics["optional_step_count"] += 1
                if status != "manual":
                    status = "partial"
            if step.get("choice_group"):
                blockers.append(f"trigger {trigger_index} step {step_index} belongs to a choice group")
                metrics["choice_step_count"] += 1
                if status != "manual":
                    status = "partial"
    return {"status": status, "blockers": blockers, "metrics": metrics}


def validate_effect_record(record: dict[str, Any]) -> dict[str, Any]:
    """Validate a structured effect record and explain runtime gaps."""
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(record, dict):
        return {
            "valid": False,
            "errors": ["record is not a JSON object"],
            "warnings": [],
            "execution_analysis": {"status": "manual", "blockers": ["record is not a JSON object"], "metrics": {}},
            "metrics": {},
        }

    for field in STRICT_REQUIRED_TOP_LEVEL_FIELDS:
        if field not in record:
            errors.append(f"missing required top-level field {field!r}")

    status = record.get("status")
    if status not in (None, "draft", "approved"):
        errors.append(f"invalid record status {status!r}")

    review = record.get("review")
    if review is not None and not isinstance(review, dict):
        errors.append("review must be an object when present")

    raw_text = str(record.get("raw_text") or "").lower()
    for term in RISKY_RULE_TEXT_TERMS:
        if term in raw_text:
            warnings.append(f"rules text contains ambiguity term {term!r}")

    triggers = record.get("triggers") or []
    if not isinstance(triggers, list):
        errors.append("triggers must be a list")
        triggers = []

    for trigger_index, trigger in enumerate(triggers, start=1):
        if not isinstance(trigger, dict):
            errors.append(f"trigger {trigger_index} is not an object")
            continue
        event = trigger.get("event")
        if event not in TRIGGERS:
            errors.append(f"trigger {trigger_index} has invalid event {event!r}")
        conditions = trigger.get("conditions") or []
        if not isinstance(conditions, list):
            errors.append(f"trigger {trigger_index} conditions must be a list")
            conditions = []
        for condition_index, condition in enumerate(conditions, start=1):
            if not isinstance(condition, dict):
                errors.append(f"trigger {trigger_index} condition {condition_index} is not an object")
                continue
            condition_type = condition.get("type")
            if condition_type not in CONDITION_TYPES:
                errors.append(
                    f"trigger {trigger_index} condition {condition_index} has invalid type {condition_type!r}"
                )
        steps = trigger.get("steps") or []
        if not isinstance(steps, list):
            errors.append(f"trigger {trigger_index} steps must be a list")
            steps = []
        if not steps:
            warnings.append(f"trigger {trigger_index} has no effect steps")
        for step_index, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                errors.append(f"trigger {trigger_index} step {step_index} is not an object")
                continue
            effect_type = step.get("type")
            if effect_type not in EFFECT_TYPES:
                errors.append(f"trigger {trigger_index} step {step_index} has invalid type {effect_type!r}")
                continue
            duration = step.get("duration")
            if duration not in (None, *DURATIONS):
                errors.append(f"trigger {trigger_index} step {step_index} has invalid duration {duration!r}")
            target = step.get("target")
            if not isinstance(target, dict):
                errors.append(f"trigger {trigger_index} step {step_index} target must be an object")
                continue
            controller = target.get("controller")
            if controller not in (None, *TARGET_CONTROLLERS):
                errors.append(
                    f"trigger {trigger_index} step {step_index} has invalid target controller {controller!r}"
                )
            target_type = target.get("type")
            if target_type not in (None, *TARGET_TYPES):
                errors.append(
                    f"trigger {trigger_index} step {step_index} has invalid target type {target_type!r}"
                )
            target_filter = target.get("filter")
            if target_filter not in (None, "", *TARGET_FILTERS):
                errors.append(
                    f"trigger {trigger_index} step {step_index} has invalid target filter {target_filter!r}"
                )
            if effect_type == "create_token" and not step.get("token_name"):
                errors.append(f"trigger {trigger_index} step {step_index} create_token is missing token_name")
            if effect_type == "modify_stats" and not any(field in step for field in ("power", "hp", "power_bonus", "hp_bonus", "amount")):
                errors.append(f"trigger {trigger_index} step {step_index} modify_stats is missing stat deltas")

    execution_analysis = execution_analysis_for_record(record)
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "execution_analysis": execution_analysis,
        "metrics": execution_analysis.get("metrics", {}),
    }


def format_validation_report(report: dict[str, Any]) -> str:
    lines = [
        f"Valid: {'yes' if report.get('valid') else 'no'}",
        f"Runtime status: {report.get('execution_analysis', {}).get('status', 'manual')}",
    ]
    metrics = report.get("metrics") or {}
    if metrics:
        lines.append(
            "Metrics: "
            + ", ".join(
                f"{key}={value}" for key, value in metrics.items()
            )
        )
    blockers = report.get("execution_analysis", {}).get("blockers") or []
    if blockers:
        lines.append("Runtime blockers:")
        lines.extend(f"  - {blocker}" for blocker in blockers)
    errors = report.get("errors") or []
    if errors:
        lines.append("Schema errors:")
        lines.extend(f"  - {error}" for error in errors)
    warnings = report.get("warnings") or []
    if warnings:
        lines.append("Warnings:")
        lines.extend(f"  - {warning}" for warning in warnings)
    return "\n".join(lines)


def should_execute_record(record: dict[str, Any]) -> bool:
    if record.get("status") != "approved":
        return False
    execution_status = record.get("execution_status")
    return execution_status in (None, "", "executable")


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object from model output, tolerating markdown fences."""
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()

    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        payload = json.loads(cleaned[start : end + 1])

    if not isinstance(payload, dict):
        raise ValueError("Model output JSON must be an object")
    return payload


def _coerce_int(value: Any, warnings: list[str], field_name: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        warnings.append(f"Dropped non-numeric {field_name}: {value!r}")
        return None


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _normalize_target(target: Any, warnings: list[str]) -> dict[str, Any]:
    target = target if isinstance(target, dict) else {}
    controller = target.get("controller", "enemy")
    target_type = target.get("type", "unit")
    normalized = {
        "controller": controller if controller in TARGET_CONTROLLERS else "enemy",
        "type": target_type if target_type in TARGET_TYPES else "unit",
    }
    if controller not in TARGET_CONTROLLERS:
        warnings.append(f"Replaced invalid target controller: {controller!r}")
    if target_type not in TARGET_TYPES:
        warnings.append(f"Replaced invalid target type: {target_type!r}")

    target_filter = target.get("filter")
    if target_filter and target_filter != "none":
        if target_filter in TARGET_FILTERS:
            normalized["filter"] = target_filter
        else:
            warnings.append(f"Dropped invalid target filter: {target_filter!r}")
    if target.get("filter_value") not in (None, ""):
        normalized["filter_value"] = str(target.get("filter_value"))
    return normalized


def _infer_token_name_from_text(raw_text: str) -> str | None:
    match = re.search(r"\bcreate\s+(?:an?|one|two|\d+)?\s*([A-Za-z0-9' -]+?)\s+token\b", raw_text, re.IGNORECASE)
    if not match:
        return None
    token_name = " ".join(match.group(1).split()).strip()
    if not token_name:
        return None
    return f"{token_name} token"


def _normalize_step(step: Any, warnings: list[str], raw_text: str = "") -> dict[str, Any] | None:
    if not isinstance(step, dict):
        warnings.append("Dropped non-object effect step")
        return None
    effect_type = step.get("type")
    if effect_type not in EFFECT_TYPES:
        warnings.append(f"Dropped invalid effect step type: {effect_type!r}")
        return None

    duration = step.get("duration") or "instant"
    if duration not in DURATIONS:
        warnings.append(f"Replaced invalid duration: {duration!r}")
        duration = "instant"

    target = step.get("target")
    if effect_type == "draw_cards" and not isinstance(target, dict):
        target = {"controller": "friendly", "type": "player"}
        warnings.append("Inferred friendly player target for draw_cards step without an explicit target")
    if effect_type == "create_token" and not isinstance(target, dict):
        target = {"controller": "friendly", "type": "player"}
        warnings.append("Inferred friendly player target for create_token step without an explicit target")

    normalized: dict[str, Any] = {
        "type": effect_type,
        "duration": duration,
        "optional": _coerce_bool(step.get("optional", False)),
        "target": _normalize_target(target, warnings),
    }
    amount = _coerce_int(step.get("amount"), warnings, "amount")
    if amount is not None:
        normalized["amount"] = amount
    for source_key, normalized_key in (
        ("power", "power"),
        ("hp", "hp"),
        ("power_bonus", "power"),
        ("hp_bonus", "hp"),
    ):
        value = _coerce_int(step.get(source_key), warnings, source_key)
        if value is not None:
            normalized[normalized_key] = value
    if step.get("choice_group"):
        normalized["choice_group"] = str(step.get("choice_group"))
    if effect_type == "create_token":
        token_name = step.get("token_name") or step.get("token") or step.get("name")
        if token_name in (None, ""):
            token_name = _infer_token_name_from_text(raw_text)
            if token_name:
                warnings.append(f"Inferred token_name {token_name!r} from card rules text")
        if token_name not in (None, ""):
            normalized["token_name"] = str(token_name)
        if step.get("ready") not in (None, ""):
            normalized["ready"] = _coerce_bool(step.get("ready"))
    return normalized


def _normalize_condition(condition: Any, warnings: list[str]) -> dict[str, Any] | None:
    if not isinstance(condition, dict):
        warnings.append("Dropped non-object condition")
        return None
    condition_type = condition.get("type")
    if condition_type in (None, "", "none"):
        return None
    if condition_type not in CONDITION_TYPES:
        warnings.append(f"Dropped invalid condition type: {condition_type!r}")
        return None
    normalized = {"type": condition_type}
    if condition.get("value") not in (None, ""):
        normalized["value"] = str(condition.get("value"))
    return normalized


def _coerce_legacy_trigger(trigger: dict[str, Any], warnings: list[str]) -> dict[str, Any] | None:
    """Translate the older flat trigger schema into the canonical steps schema."""
    legacy_event = trigger.get("type")
    step_type = trigger.get("effect_type") or trigger.get("step_type")
    if legacy_event not in TRIGGERS or step_type in (None, ""):
        return None

    coerced_step: dict[str, Any] = {
        "type": step_type,
        "duration": trigger.get("duration") or "instant",
        "optional": trigger.get("optional", False),
        "target": {
            "controller": trigger.get("target_controller") or trigger.get("controller") or "enemy",
            "type": trigger.get("target_type") or "unit",
        },
    }
    for source_key in ("amount", "power", "hp", "power_bonus", "hp_bonus", "choice_group", "token_name", "token", "name"):
        if trigger.get(source_key) not in (None, ""):
            coerced_step[source_key] = trigger.get(source_key)
    target_filter = trigger.get("target_filter") or trigger.get("filter")
    if target_filter not in (None, ""):
        coerced_step["target"]["filter"] = target_filter
    if trigger.get("filter_value") not in (None, ""):
        coerced_step["target"]["filter_value"] = trigger.get("filter_value")
    if trigger.get("ready") not in (None, ""):
        coerced_step["ready"] = trigger.get("ready")

    warnings.append("Coerced legacy flat trigger format into trigger.event plus trigger.steps")
    return {
        "event": legacy_event,
        "conditions": trigger.get("conditions") or [],
        "steps": [coerced_step],
    }


def _normalize_trigger(trigger: Any, warnings: list[str], raw_text: str = "") -> dict[str, Any] | None:
    if not isinstance(trigger, dict):
        warnings.append("Dropped non-object trigger")
        return None
    event = trigger.get("event")
    if event not in TRIGGERS:
        coerced = _coerce_legacy_trigger(trigger, warnings)
        if coerced:
            trigger = coerced
            event = trigger.get("event")
    if event not in TRIGGERS:
        warnings.append(f"Dropped invalid trigger event: {event!r}")
        return None

    conditions = [
        condition
        for condition in (_normalize_condition(condition, warnings) for condition in trigger.get("conditions") or [])
        if condition
    ]
    steps = [
        step
        for step in (_normalize_step(step, warnings, raw_text=raw_text) for step in trigger.get("steps") or [])
        if step
    ]
    return {"event": event, "conditions": conditions, "steps": steps}


def triage_effect_record(record: dict[str, Any], warnings: list[str] | None = None) -> str:
    """Conservatively bucket a draft for review priority."""
    warnings = warnings or []
    triggers = record.get("triggers") or []
    if warnings or not triggers:
        return "unresolved" if not triggers else "needs_review"

    execution_status = execution_status_for_record(record)
    risky_text = (record.get("raw_text") or "").lower()
    attached_unit_only = "attached unit" in risky_text
    if any(term in risky_text for term in RISKY_RULE_TEXT_TERMS if not (attached_unit_only and term == "attach")):
        return "needs_review"

    for trigger in triggers:
        if trigger.get("conditions"):
            return "needs_review"
        steps = trigger.get("steps") or []
        if len(steps) != 1:
            return "needs_review"
        for step in steps:
            if step.get("optional") or step.get("choice_group"):
                return "needs_review"
            if step.get("duration") not in (None, "", "instant"):
                return "needs_review"
            target_filter = (step.get("target") or {}).get("filter")
            if target_filter and target_filter != "attached_unit":
                return "needs_review"

    return "safe_draft" if execution_status == "executable" else "needs_review"


def normalize_effect_record(
    card: dict[str, Any],
    candidate: dict[str, Any],
    source: str,
    raw_output: str = "",
    extra_warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Normalize model output into the canonical draft effect schema."""
    warnings = list(extra_warnings or [])
    record = blank_effect_record(card)
    record["status"] = "draft"
    record["source"] = source
    record["review"]["llm_suggested"] = True
    record["review"]["human_verified"] = False

    review = candidate.get("review") if isinstance(candidate.get("review"), dict) else {}
    confidence = review.get("confidence") or candidate.get("confidence") or "medium"
    record["review"]["confidence"] = confidence if confidence in {"low", "medium", "high"} else "medium"
    notes = []
    if review.get("notes"):
        notes.append(str(review.get("notes")))
    if candidate.get("notes"):
        notes.append(str(candidate.get("notes")))

    triggers = candidate.get("triggers") if isinstance(candidate.get("triggers"), list) else []
    record["triggers"] = [
        trigger
        for trigger in (_normalize_trigger(trigger, warnings, raw_text=record["raw_text"]) for trigger in triggers)
        if trigger
    ]

    deterministic_status = execution_status_for_record(record)
    triage = triage_effect_record(record, warnings)
    if triage == "unresolved":
        record["execution_status"] = "manual"
        record["review"]["confidence"] = "low"
    elif deterministic_status == "executable" and triage == "safe_draft":
        record["execution_status"] = "executable"
    else:
        record["execution_status"] = deterministic_status if deterministic_status != "executable" else "partial"

    if warnings:
        notes.append("Parse warnings: " + "; ".join(warnings))
    if triage == "safe_draft":
        notes.append("Local model draft looks structurally simple, but still requires human approval.")
    elif triage == "needs_review":
        notes.append("Local model draft needs human review before simulator use.")
    else:
        notes.append("Local model output could not be converted into a reliable effect draft.")

    record["review"]["notes"] = "\n".join(note for note in notes if note).strip()
    record["review"]["triage"] = triage
    record["review"]["parse_warnings"] = warnings
    if raw_output:
        record["review"]["raw_model_output"] = raw_output[:4000]
    record["validation"] = validate_effect_record(record)
    return record


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
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise self._friendly_http_error(exc) from exc
        except urllib.error.URLError as exc:
            raise EffectSuggestionError(
                "Could not reach OpenAI",
                "The app could not connect to OpenAI. Check your internet connection and try again.",
                ["Confirm you are online.", "Try again in a minute."],
            ) from exc

        record = self._parse_response_json(payload)
        record["status"] = "draft"
        record["source"] = f"openai:{self.model}"
        record.setdefault("review", {})
        record["review"]["llm_suggested"] = True
        record["review"]["human_verified"] = False
        record["execution_status"] = "manual"
        return record

    def _friendly_http_error(self, exc: urllib.error.HTTPError) -> EffectSuggestionError:
        if exc.code == 401:
            return EffectSuggestionError(
                "OpenAI key was rejected",
                "The API key loaded from .env is not valid for OpenAI.",
                ["Check that OPENAI_API_KEY is copied correctly.", "Rotate the key in OpenAI and update .env if needed."],
            )
        if exc.code == 403:
            return EffectSuggestionError(
                "OpenAI project does not have access",
                f"The project for this key cannot use {self.model}.",
                ["Check model access in the OpenAI project.", "Try a different SWU_LLM_MODEL in .env."],
            )
        if exc.code == 429:
            return EffectSuggestionError(
                "OpenAI rate limit or quota reached",
                "The key is readable, but OpenAI is refusing the request because the project is out of quota, billing is not active, or too many requests were sent.",
                [
                    "Check billing and credits in the OpenAI dashboard.",
                    "Check rate limits for the selected model.",
                    "Wait a few minutes and try again.",
                    "Try a different SWU_LLM_MODEL in .env if your project has access to it.",
                ],
            )
        if 500 <= exc.code < 600:
            return EffectSuggestionError(
                "OpenAI service error",
                "OpenAI returned a temporary server error.",
                ["Wait a minute and try again."],
            )
        return EffectSuggestionError(
            "OpenAI request failed",
            f"OpenAI returned HTTP {exc.code}.",
            ["Check the OpenAI dashboard for project status and model access."],
        )

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
        return parse_json_object(text)


class LocalModelBackend(ABC):
    """Transport boundary for local text-generation runtimes."""

    name = "local"

    def __init__(self, model: str | None = None, host: str | None = None, timeout: int | None = None):
        self.model = model or get_setting("SWU_LOCAL_MODEL", "qwen2.5:7b-instruct")
        self.host = (host or get_setting("SWU_LOCAL_HOST", "http://127.0.0.1:11434")).rstrip("/")
        self.timeout = timeout or int(get_setting("SWU_LOCAL_TIMEOUT", "60"))

    @abstractmethod
    def generate_json(self, prompt: dict[str, Any]) -> str:
        """Return model text that should contain a JSON object."""

    @abstractmethod
    def test(self) -> dict[str, Any]:
        """Return runtime status, or raise EffectSuggestionError with setup guidance."""

    @property
    def source(self) -> str:
        return f"local:{self.name}:{self.model}"


class OllamaBackend(LocalModelBackend):
    """Local backend using Ollama's HTTP API."""

    name = "ollama"

    def _request_json(self, path: str, payload: dict[str, Any] | None = None, timeout: int | None = None) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            f"{self.host}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST" if payload is not None else "GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except socket.timeout as exc:
            raise EffectSuggestionError(
                "Ollama request timed out",
                f"Ollama did not respond within {timeout or self.timeout} seconds.",
                ["Try a smaller local model.", "Increase SWU_LOCAL_TIMEOUT in .env."],
            ) from exc
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise EffectSuggestionError(
                    "Ollama model is not installed",
                    f"Ollama could not find model '{self.model}'.",
                    [f"Run `ollama pull {self.model}`.", "Or set SWU_LOCAL_MODEL to an installed model."],
                ) from exc
            raise EffectSuggestionError(
                "Ollama request failed",
                f"Ollama returned HTTP {exc.code}.",
                ["Check the Ollama terminal output.", "Confirm SWU_LOCAL_HOST is correct."],
            ) from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, socket.timeout) or "timed out" in str(exc.reason).lower():
                raise EffectSuggestionError(
                    "Ollama request timed out",
                    f"Ollama did not respond within {timeout or self.timeout} seconds.",
                    ["Try a smaller local model.", "Increase SWU_OLLAMA_TIMEOUT or SWU_LOCAL_TIMEOUT in .env."],
                ) from exc
            raise EffectSuggestionError(
                "Ollama is not running",
                f"The app could not reach Ollama at {self.host}.",
                ["Start Ollama.", "Confirm `ollama list` works in a terminal.", "Check SWU_LOCAL_HOST in .env."],
            ) from exc
        except json.JSONDecodeError as exc:
            raise EffectSuggestionError(
                "Ollama returned invalid JSON",
                "The Ollama API response was not valid JSON.",
                ["Restart Ollama and try again.", "Check whether another service is using SWU_LOCAL_HOST."],
            ) from exc

    def _installed_models(self) -> set[str]:
        payload = self._request_json("/api/tags", timeout=min(self.timeout, 10))
        return {
            str(model.get("name") or model.get("model") or "")
            for model in payload.get("models", []) or []
        }

    def test(self) -> dict[str, Any]:
        models = self._installed_models()
        if self.model not in models:
            raise EffectSuggestionError(
                "Ollama model is not installed",
                f"Ollama is running, but '{self.model}' is not installed.",
                [f"Run `ollama pull {self.model}`.", f"Installed models: {', '.join(sorted(models)) or 'none'}"],
            )
        return {"backend": self.name, "host": self.host, "model": self.model, "available_models": sorted(models)}

    def generate_json(self, prompt: dict[str, Any]) -> str:
        payload = self._request_json(
            "/api/generate",
            {
                "model": self.model,
                "prompt": json.dumps(prompt, indent=2),
                "stream": False,
                "format": "json",
                "options": {"temperature": 0},
            },
        )
        text = str(payload.get("response") or "").strip()
        if not text:
            raise LocalModelResponseError("Ollama response did not include generated text", raw_output=json.dumps(payload))
        return text


class MLXBackend(LocalModelBackend):
    """Optional Apple Silicon local backend using mlx-lm when installed."""

    name = "mlx"

    def test(self) -> dict[str, Any]:
        try:
            import mlx_lm  # noqa: F401
        except ImportError as exc:
            raise EffectSuggestionError(
                "MLX runtime is not installed",
                "The MLX local provider was selected, but the optional mlx-lm package is not available.",
                ["Install MLX support with `pip install mlx-lm`.", "Or set SWU_LOCAL_PROVIDER=ollama."],
            ) from exc
        return {"backend": self.name, "model": self.model}

    def generate_json(self, prompt: dict[str, Any]) -> str:
        try:
            from mlx_lm import generate, load
        except ImportError as exc:
            raise EffectSuggestionError(
                "MLX runtime is not installed",
                "The MLX local provider was selected, but the optional mlx-lm package is not available.",
                ["Install MLX support with `pip install mlx-lm`.", "Or set SWU_LOCAL_PROVIDER=ollama."],
            ) from exc

        model, tokenizer = load(self.model)
        prompt_text = json.dumps(prompt, indent=2)
        return str(generate(model, tokenizer, prompt=prompt_text, max_tokens=1200)).strip()


def local_backend_from_settings(
    provider_name: str | None = None,
    model: str | None = None,
    host: str | None = None,
    timeout: int | None = None,
) -> LocalModelBackend:
    provider_name = (provider_name or get_setting("SWU_LOCAL_PROVIDER", "ollama")).lower()
    if provider_name == "ollama":
        return OllamaBackend(model=model, host=host, timeout=timeout)
    if provider_name in {"mlx", "mlx-vlm", "mlx_vlm"}:
        return MLXBackend(model=model, host=host, timeout=timeout)
    raise ValueError(f"Local effect provider '{provider_name}' is not configured")


class LocalEffectSuggestionProvider(EffectSuggestionProvider):
    """LLM draft provider that runs against a local model runtime."""

    name = "local"

    def __init__(
        self,
        backend: LocalModelBackend | None = None,
        local_provider: str | None = None,
        model: str | None = None,
        host: str | None = None,
        timeout: int | None = None,
    ):
        self.backend = backend or local_backend_from_settings(local_provider, model=model, host=host, timeout=timeout)

    def suggest_effect(self, card: dict[str, Any]) -> dict[str, Any]:
        prompt = self._build_prompt(card)
        raw_output = ""
        try:
            raw_output = self.backend.generate_json(prompt)
            candidate = parse_json_object(raw_output)
            return normalize_effect_record(card, candidate, self.backend.source, raw_output=raw_output)
        except (json.JSONDecodeError, ValueError, LocalModelResponseError) as exc:
            if isinstance(exc, LocalModelResponseError):
                raw_output = exc.raw_output or raw_output
            return normalize_effect_record(
                card,
                {"triggers": [], "review": {"confidence": "low", "notes": str(exc)}},
                self.backend.source,
                raw_output=raw_output,
                extra_warnings=[f"Could not parse local model output: {exc}"],
            )

    def test(self) -> dict[str, Any]:
        return self.backend.test()

    def _build_prompt(self, card: dict[str, Any]) -> dict[str, Any]:
        return {
            "task": "Draft a Star Wars Unlimited simulator effect record for human review.",
            "constraints": [
                "Return only one valid JSON object.",
                "Use the schema shown in blank_record.",
                "Follow schema_contract exactly.",
                "Do not approve the card. Set status to draft.",
                "Do not invent card text or effects.",
                "Use only allowed enum values.",
                "Each trigger must use the field event and a steps array.",
                "Never use the legacy flat trigger shape shown in examples.legacy_shape_to_avoid.",
                "If the card is ambiguous, include conservative structure and notes rather than guessing.",
            ],
            "allowed_triggers": TRIGGERS,
            "allowed_effect_types": EFFECT_TYPES,
            "allowed_target_controllers": TARGET_CONTROLLERS,
            "allowed_target_types": TARGET_TYPES,
            "allowed_target_filters": TARGET_FILTERS,
            "allowed_condition_types": CONDITION_TYPES,
            "allowed_durations": DURATIONS,
            "engine_executable_triggers": sorted(ENGINE_EXECUTABLE_TRIGGERS),
            "engine_executable_effects": sorted(ENGINE_EXECUTABLE_EFFECTS),
            "blank_record": blank_effect_record(card),
            "swu_primer": prompt_swu_primer(),
            "engine_review_rules": prompt_engine_review_rules(),
            "effect_mapping_guide": prompt_effect_mapping_guide(),
            "repo_approved_examples": prompt_repo_approved_examples(),
            "schema_contract": prompt_schema_contract(),
            "examples": prompt_examples(),
            "card": {
                "set": card.get("Set"),
                "number": card.get("Number"),
                "name": card.get("Name"),
                "subtitle": card.get("Subtitle"),
                "type": card.get("Type"),
                "traits": card.get("Traits") or [],
                "aspects": card.get("Aspects") or [],
                "keywords": card.get("Keywords") or [],
                "arenas": card.get("Arenas") or [],
                "cost": card.get("Cost"),
                "power": card.get("Power"),
                "hp": card.get("HP"),
                "rules_text": rules_text(card),
                "art_url": card.get("ArtFront") or card.get("FrontArt") or card.get("ImageUrl") or card.get("Image"),
            },
        }


class OllamaEffectSuggestionProvider(LocalEffectSuggestionProvider):
    """Minimal Ollama-backed draft provider for human-reviewed effect records."""

    name = "ollama"

    def __init__(self, model: str | None = None, host: str | None = None, timeout: int | None = None):
        model = model or get_setting("SWU_OLLAMA_MODEL", get_setting("SWU_LOCAL_MODEL", "qwen2.5"))
        host = host or get_setting("SWU_OLLAMA_HOST", get_setting("SWU_LOCAL_HOST", "http://localhost:11434"))
        timeout = timeout or int(get_setting("SWU_OLLAMA_TIMEOUT", get_setting("SWU_LOCAL_TIMEOUT", "60")))
        super().__init__(backend=OllamaBackend(model=model, host=host, timeout=timeout))

    def _build_prompt(self, card: dict[str, Any]) -> dict[str, Any]:
        return {
            "task": "Draft a conservative Star Wars Unlimited simulator effect record for human review.",
            "instructions": [
                "Return ONLY valid JSON.",
                "Use the blank_record schema.",
                "Follow schema_contract exactly.",
                "Set status to draft.",
                "Do not approve the record.",
                "Use only the allowed trigger and step values.",
                "Each trigger must use event, conditions, and steps.",
                "Never use trigger.type for the event name.",
                "Never use effect_type, target_controller, or target_type at trigger level.",
                "If uncertain, leave triggers empty or add notes instead of guessing.",
            ],
            "allowed_triggers": TRIGGERS,
            "preferred_step_types": sorted(ENGINE_EXECUTABLE_EFFECTS),
            "allowed_step_types": EFFECT_TYPES,
            "allowed_target_controllers": TARGET_CONTROLLERS,
            "allowed_target_types": TARGET_TYPES,
            "allowed_target_filters": TARGET_FILTERS,
            "allowed_durations": DURATIONS,
            "blank_record": blank_effect_record(card),
            "swu_primer": prompt_swu_primer(),
            "engine_review_rules": prompt_engine_review_rules(),
            "effect_mapping_guide": prompt_effect_mapping_guide(),
            "repo_approved_examples": prompt_repo_approved_examples(),
            "schema_contract": prompt_schema_contract(),
            "examples": prompt_examples(),
            "card": {
                "set": card.get("Set"),
                "number": card.get("Number"),
                "name": card.get("Name"),
                "type": card.get("Type"),
                "rules_text": rules_text(card),
            },
        }


def get_effect_suggestion_provider(provider_name: str = "heuristic", **kwargs: Any) -> EffectSuggestionProvider:
    if provider_name == "heuristic":
        return RuleTextHeuristicProvider()
    if provider_name == "openai":
        return OpenAIEffectSuggestionProvider(model=kwargs.get("model"))
    if provider_name == "ollama":
        return OllamaEffectSuggestionProvider(
            model=kwargs.get("model"),
            host=kwargs.get("host"),
            timeout=kwargs.get("timeout"),
        )
    if provider_name == "local":
        return LocalEffectSuggestionProvider(
            local_provider=kwargs.get("local_provider"),
            model=kwargs.get("model"),
            host=kwargs.get("host"),
            timeout=kwargs.get("timeout"),
        )
    raise ValueError(f"Effect suggestion provider '{provider_name}' is not configured")
