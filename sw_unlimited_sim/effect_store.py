"""Structured human-approved card effect storage."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from effect_training import execution_status_for_record


EFFECT_DIR = Path(__file__).resolve().parent / "data" / "effects"
CARD_EFFECTS_PATH = EFFECT_DIR / "card_effects.json"
UNRESOLVED_EFFECTS_PATH = EFFECT_DIR / "unresolved_effects.json"


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def effect_key(set_code: str, number: str) -> str:
    return f"{set_code.upper()}-{number}"


def load_effects() -> dict[str, Any]:
    return _read_json(CARD_EFFECTS_PATH, {})


def save_effect(card_effect: dict[str, Any]):
    effects = load_effects()
    key = effect_key(card_effect["set"], str(card_effect["number"]))
    if "schema_version" not in card_effect:
        card_effect["schema_version"] = 1
    if "execution_status" not in card_effect:
        card_effect["execution_status"] = execution_status_for_record(card_effect)
    card_effect["updated_at"] = datetime.now(timezone.utc).isoformat()
    effects[key] = card_effect
    _write_json(CARD_EFFECTS_PATH, effects)


def get_effect(set_code: str, number: str) -> dict[str, Any] | None:
    return load_effects().get(effect_key(set_code, str(number)))


def load_unresolved() -> dict[str, Any]:
    return _read_json(UNRESOLVED_EFFECTS_PATH, {})


def save_unresolved_card(card: dict[str, Any], reason: str):
    unresolved = load_unresolved()
    key = effect_key(str(card.get("Set") or ""), str(card.get("Number") or ""))
    unresolved[key] = {
        "set": card.get("Set"),
        "number": card.get("Number"),
        "name": card.get("Name"),
        "type": card.get("Type"),
        "text": "\n".join(
            str(card.get(field) or "")
            for field in ("FrontText", "BackText", "EpicAction")
            if card.get(field)
        ),
        "reason": reason,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_json(UNRESOLVED_EFFECTS_PATH, unresolved)
