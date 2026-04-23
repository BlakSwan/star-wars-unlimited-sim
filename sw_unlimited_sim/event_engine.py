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
