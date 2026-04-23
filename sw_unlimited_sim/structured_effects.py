"""Structured effect execution helpers for the simulator engine."""

from __future__ import annotations

from typing import Any, Optional

from effect_training import should_execute_record
from models import Card, Player, UnitCard, UpgradeCard


def card_effect_record(game: Any, card: Card) -> Optional[dict[str, Any]]:
    key = game._card_effect_key(card)
    if not key:
        return None
    record = game.card_effects.get(key)
    if not record or not should_execute_record(record):
        return None
    return record


def has_approved_structured_trigger(game: Any, card: Card, trigger: str) -> bool:
    record = card_effect_record(game, card)
    if not record:
        return False
    return any(trigger_record.get("event") == trigger for trigger_record in record.get("triggers", []))


def resolve_structured_effects(
    game: Any,
    player: Player,
    source: Card,
    trigger: str,
    defender: Optional[UnitCard] = None,
) -> None:
    record = card_effect_record(game, source)
    if not record:
        return

    for trigger_record in record.get("triggers", []):
        if trigger_record.get("event") != trigger:
            continue
        if trigger_record.get("conditions"):
            game.log(f"Turn {game.turn_count}: {source.name} skipped trained effect with unsupported conditions")
            continue
        for step in trigger_record.get("steps", []):
            if not can_execute_structured_step(game, source, step):
                continue
            apply_structured_step(game, player, source, step, defender)


def can_execute_structured_step(game: Any, source: Card, step: dict[str, Any]) -> bool:
    target = step.get("target") or {}
    if target.get("filter"):
        game.log(f"Turn {game.turn_count}: {source.name} skipped trained effect with unsupported target filter")
        return False
    duration = step.get("duration")
    if step.get("type") == "modify_stats" and duration == "while_attached" and isinstance(source, UpgradeCard):
        pass
    elif duration not in (None, "", "instant"):
        game.log(f"Turn {game.turn_count}: {source.name} skipped trained effect with unsupported duration")
        return False
    if step.get("optional") or step.get("choice_group"):
        game.log(f"Turn {game.turn_count}: {source.name} skipped trained effect that needs a choice")
        return False
    return True


def target_player(game: Any, player: Player, target_spec: dict[str, Any]) -> Player:
    controller = str(target_spec.get("controller") or "self").lower()
    if controller in {"enemy", "opponent"}:
        return game._get_enemy(player)
    return player


def target_unit(
    game: Any,
    player: Player,
    target_spec: dict[str, Any],
    defender: Optional[UnitCard] = None,
) -> tuple[Optional[Player], Optional[UnitCard]]:
    controller = str(target_spec.get("controller") or "enemy").lower()
    if controller == "self":
        candidates = player.units
        owner = player
    elif controller == "friendly":
        candidates = player.units
        owner = player
    elif controller == "any":
        enemy = game._get_enemy(player)
        candidates = enemy.units + player.units
        owner = enemy if candidates and candidates[0] in enemy.units else player
    else:
        owner = game._get_enemy(player)
        candidates = owner.units

    if defender and defender in candidates:
        return owner, defender
    if not candidates:
        return None, None
    if controller in {"friendly", "self"}:
        unit = game._choose_friendly_unit(player, damaged=True) or game._choose_friendly_unit(player)
        return player, unit
    unit = min(candidates, key=lambda candidate: (candidate.current_hp, -candidate.power))
    if controller == "any" and unit in player.units:
        owner = player
    return owner, unit


def structured_stat_deltas(step: dict[str, Any]) -> tuple[int, int]:
    if "power" in step or "hp" in step:
        return int(step.get("power") or 0), int(step.get("hp") or 0)
    if "power_bonus" in step or "hp_bonus" in step:
        return int(step.get("power_bonus") or 0), int(step.get("hp_bonus") or 0)
    amount = int(step.get("amount") or 0)
    return amount, amount


def apply_structured_step(
    game: Any,
    player: Player,
    source: Card,
    step: dict[str, Any],
    defender: Optional[UnitCard] = None,
) -> None:
    effect_type = str(step.get("type") or "").lower()
    target_spec = step.get("target") or {}
    amount = int(step.get("amount") or 1)
    target_type = str(target_spec.get("type") or "unit").lower()
    source_name = source.name

    if effect_type == "draw_cards":
        step_target_player = target_player(game, player, target_spec)
        game._draw_cards(step_target_player, amount, source_name)
        return

    if effect_type == "discard_cards":
        step_target_player = target_player(game, player, target_spec)
        game._discard_cards(step_target_player, amount, source_name)
        return

    if effect_type == "create_token":
        step_target_player = target_player(game, player, target_spec)
        game._create_tokens(
            step_target_player,
            str(step.get("token_name") or "Battle Droid"),
            amount,
            source_name,
            ready=game._step_bool(step.get("ready", False)),
        )
        return

    if target_type in {"base", "player"}:
        step_target_player = target_player(game, player, target_spec)
        if effect_type == "deal_damage":
            game._damage_base(step_target_player, amount, source_name)
        elif effect_type == "heal_damage":
            game._heal_base(step_target_player, amount, source_name)
        else:
            game.log(f"Turn {game.turn_count}: {source_name} skipped unsupported base effect {effect_type}")
        return

    owner, unit = target_unit(game, player, target_spec, defender)
    if not owner or not unit:
        game.log(f"Turn {game.turn_count}: {source_name} found no target for {effect_type}")
        return

    if effect_type == "deal_damage":
        game._damage_unit(owner, unit, amount)
    elif effect_type == "heal_damage":
        before = unit.current_hp
        unit.heal(amount)
        game.log(f"Turn {game.turn_count}: {source_name} heals {unit.current_hp - before} damage from {unit.name}")
    elif effect_type == "exhaust_unit":
        unit.is_exhausted = True
        game.log(f"Turn {game.turn_count}: {source_name} exhausts {unit.name}")
    elif effect_type == "ready_unit":
        unit.is_exhausted = False
        game.log(f"Turn {game.turn_count}: {source_name} readies {unit.name}")
    elif effect_type == "defeat_unit":
        game._remove_unit(owner, unit)
        game.log(f"Turn {game.turn_count}: {source_name} defeats {unit.name}")
    elif effect_type == "give_shield":
        unit.shield_tokens += amount
        game.log(f"Turn {game.turn_count}: {source_name} gives {amount} Shield token(s) to {unit.name}")
    elif effect_type == "give_experience":
        unit.experience_tokens += amount
        game._modify_unit_stats(unit, amount, amount)
        game.log(f"Turn {game.turn_count}: {source_name} gives {amount} Experience token(s) to {unit.name}")
    elif effect_type == "modify_stats":
        power_delta, hp_delta = structured_stat_deltas(step)
        if not power_delta and not hp_delta:
            game.log(f"Turn {game.turn_count}: {source_name} skipped empty stat modifier")
            return
        game._modify_unit_stats(unit, power_delta, hp_delta)
        if isinstance(source, UpgradeCard) and step.get("duration") == "while_attached":
            source.structured_power_bonus = int(getattr(source, "structured_power_bonus", 0) or 0) + power_delta
            source.structured_hp_bonus = int(getattr(source, "structured_hp_bonus", 0) or 0) + hp_delta
        game.log(f"Turn {game.turn_count}: {source_name} modifies {unit.name} by {power_delta:+}/{hp_delta:+}")
    elif effect_type == "capture_unit":
        game.log(f"Turn {game.turn_count}: {source_name} skipped capture effect; capture zones are not modeled yet")
    else:
        game.log(f"Turn {game.turn_count}: {source_name} skipped unknown structured effect {effect_type}")
