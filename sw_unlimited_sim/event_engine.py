"""Event resolution helpers for the simulator engine."""

from __future__ import annotations

from typing import Any

from models import EventCard, LeaderCard, Player


def resolve_event(game: Any, player: Player, event: EventCard) -> None:
    enemy = game._get_enemy(player)
    game._resolve_structured_effects(player, event, "when_played")

    if event.name == "Heroic Sacrifice":
        game._draw_cards(player, 1, "Heroic Sacrifice")
        unit = game._choose_friendly_unit(player)
        if unit:
            defeated = game._attack_with_unit(player, unit, power_bonus=2)
            if defeated and unit in player.units:
                game._remove_unit(player, unit)
        return

    if event.name == "Karabast":
        friendly = game._choose_friendly_unit(player, damaged=True) or game._choose_friendly_unit(player)
        target = game._choose_enemy_unit(player)
        if friendly and target:
            game._damage_unit(enemy, target, friendly.damage + 1)
        return

    if game._is_card(event, "LOF", "041"):
        targets = enemy.units or player.units
        if targets:
            target = min(targets, key=lambda unit: (unit.current_hp, -unit.power))
            target_owner = enemy if target in enemy.units else player
            game._damage_unit(target_owner, target, 2)
        game._gain_force(player, "Drain Essence")
        return

    if event.name == "Improvised Detonation":
        unit = game._choose_friendly_unit(player)
        if unit:
            game._attack_with_unit_tuning(player, unit, power_bonus=2)
        return

    if game._is_card(event, "JTL", "123"):
        unit = game._choose_friendly_unit(player)
        if unit:
            game._attack_with_unit_tuning(player, unit, allow_exhausted=True, can_attack_base=False)
        return

    if game._is_card(event, "SOR", "168"):
        unit = game._choose_friendly_unit(player)
        if unit:
            power_bonus = 2 if game._has_trait(unit, "TROOPER") else 0
            game._attack_with_unit_tuning(player, unit, power_bonus=power_bonus, keywords={"saboteur"})
        return

    if game._is_card(event, "LAW", "202"):
        unit = game._choose_friendly_unit(player)
        if unit:
            power_bonus = 2 if len(player.resources) < len(enemy.resources) else 0
            game._attack_with_unit_tuning(player, unit, power_bonus=power_bonus, keywords={"saboteur"})
        return

    if game._is_card(event, "TWI", "224"):
        unit = game._choose_friendly_unit(player)
        if unit:
            game._attack_with_unit_tuning(player, unit, power_bonus=2, keywords={"saboteur"})
        return

    if game._is_card(event, "LOF", "221"):
        if not game._use_force(player):
            return
        unit = game._choose_friendly_unit(player)
        if unit:
            game._attack_with_unit_tuning(player, unit, power_bonus=2, combat_damage_before_defender=True)
        return

    if game._is_card(event, "LAW", "205"):
        unit = game._choose_friendly_unit(player)
        if unit:
            game._attack_with_unit_tuning(
                player,
                unit,
                power_bonus=2,
                keywords={"overwhelm"},
                defeat_self_if_damaged_base=True,
            )
        return

    if game._is_card(event, "SEC", "157"):
        unit = game._choose_friendly_unit(player)
        if unit:
            game._attack_with_unit_tuning(
                player,
                unit,
                power_bonus=1,
                keywords={"overwhelm"},
                strip_defender_abilities=True,
            )
        return

    if event.name == "Rebel Assault":
        rebels = [
            unit for unit in player.units
            if game._has_trait(unit, "REBEL") and not getattr(unit, "is_exhausted", False)
        ]
        for unit in rebels[:2]:
            game._attack_with_unit(player, unit, power_bonus=1)
        return

    if event.name == "Medal Ceremony":
        rebels = [
            unit for unit in player.units
            if game._has_trait(unit, "REBEL") and getattr(unit, "attacked_this_phase", False)
        ]
        for unit in rebels[:3]:
            unit.experience_tokens += 1
            unit.power += 1
            unit.hp += 1
            unit.current_hp += 1
        return

    if event.name == "Force Choke":
        target = game._choose_enemy_unit(player, non_vehicle=True)
        if target:
            game._damage_unit(enemy, target, 5)
            game._draw_cards(enemy, 1, "Force Choke")
        return

    if event.name == "Force Lightning":
        target = game._choose_enemy_unit(player)
        if target:
            target.abilities_lost_until_ready = True
            resources = len(player.get_ready_resources())
            if game._friendly_force_unit(player) and resources:
                player.pay_cost(resources)
                game._damage_unit(enemy, target, 2 * resources)
        return

    if game._is_card(event, "JTL", "144"):
        targets = [unit for unit in enemy.units if not isinstance(unit, LeaderCard)]
        if targets:
            target = max(targets, key=lambda unit: (unit.current_hp, unit.power))
            amount = max(0, target.current_hp - 1)
            if amount:
                game._damage_unit(enemy, target, amount)
        return

    if game._is_card(event, "LAW", "133"):
        targets = [
            unit for unit in enemy.units
            if not isinstance(unit, LeaderCard) and not game._blocks_enemy_defeat_or_bounce(unit)
        ]
        if targets:
            target = max(targets, key=lambda unit: (unit.cost, unit.power, unit.current_hp))
            game._remove_unit(enemy, target)
            game._heal_base(player, 3, "Lost and Forgotten")
        return

    if game._is_card(event, "SEC", "233"):
        targets = [
            unit for unit in enemy.units
            if not isinstance(unit, LeaderCard)
            and unit.cost <= 6
            and not game._blocks_enemy_defeat_or_bounce(unit)
        ]
        if targets:
            target = max(targets, key=lambda unit: (unit.cost, unit.power + unit.hp))
            game._return_unit_to_hand(enemy, target, "Beguile")
        return

    if game._is_card(event, "JTL", "229"):
        target = game._choose_friendly_unit(player) or game._choose_enemy_unit(player)
        if target:
            game._apply_temporary_modifier(target, keywords={"sentinel"}, duration="this_phase")
        return
