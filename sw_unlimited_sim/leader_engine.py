"""Leader and unit-action helpers for the simulator engine."""

from __future__ import annotations

from typing import Any

from models import Arena, LeaderCard, Player, UnitCard


def unit_action_has_target(game: Any, player: Player, unit: UnitCard) -> bool:
    if getattr(unit, "abilities_lost_until_ready", False):
        return False
    record = game._card_effect_record(unit)
    if record and any(trigger.get("event") == "action" for trigger in record.get("triggers", [])):
        return True
    if unit.name == "Admiral Ozzel":
        return any(
            game._has_trait(card, "IMPERIAL") and isinstance(card, UnitCard) and player.can_afford(card.cost)
            for card in player.hand
        )
    return False


def use_unit_action(game: Any, player: Player, unit_id: str) -> bool:
    unit = next((candidate for candidate in player.units if candidate.id == unit_id), None)
    if not unit or getattr(unit, "is_exhausted", False):
        return False
    if not game._unit_action_has_target(player, unit):
        return False

    if unit.name == "Admiral Ozzel":
        return use_admiral_ozzel_action(game, player, unit)

    if game._card_effect_record(unit):
        unit.is_exhausted = True
        game._resolve_structured_effects(player, unit, "action")
        game.log(f"Turn {game.turn_count}: Player {player.id} uses {unit.name}'s trained action")
        return True

    return False


def use_admiral_ozzel_action(game: Any, player: Player, unit: UnitCard) -> bool:
    imperial_units = [
        card for card in player.hand
        if isinstance(card, UnitCard) and game._has_trait(card, "IMPERIAL") and player.can_afford(card.cost)
    ]
    if not imperial_units:
        return False

    unit.is_exhausted = True
    card = max(imperial_units, key=lambda candidate: (candidate.cost, candidate.power + candidate.hp))
    player.pay_cost(card.cost)
    player.hand.remove(card)
    game._play_unit(player, card)
    card.is_exhausted = False
    game._record_played_card(player, card)

    enemy = game._get_enemy(player)
    exhausted_enemy_units = [enemy_unit for enemy_unit in enemy.units if getattr(enemy_unit, "is_exhausted", False)]
    if exhausted_enemy_units:
        exhausted_enemy_units[0].is_exhausted = False

    game.log(f"Turn {game.turn_count}: Player {player.id} uses Admiral Ozzel's action")
    game._emit(f"  Player {player.id} uses Admiral Ozzel to play {card.name} ready")
    return True


def use_leader_action(game: Any, player: Player) -> bool:
    if not player.leader or player.leader.is_deployed or player.leader.is_exhausted:
        return False
    if not player.can_afford(player.leader.action_cost):
        return False
    if not game._leader_action_has_target(player):
        return False

    player.pay_cost(player.leader.action_cost)
    player.leader.is_exhausted = True
    game._resolve_leader_action(player)
    game.log(f"Turn {game.turn_count}: Player {player.id} uses {player.leader.name}'s action")
    game._emit(f"  Player {player.id} uses {player.leader.name}'s action")
    return True


def leader_action_has_target(game: Any, player: Player) -> bool:
    if not player.leader:
        return False

    record = game._card_effect_record(player.leader)
    if record and any(trigger.get("event") == "action" for trigger in record.get("triggers", [])):
        return True

    effect = player.leader.action_effect.lower()
    enemy = game._get_enemy(player)

    if "heal" in effect:
        return any(unit.current_hp < unit.hp for unit in player.units)
    if "played a villainy card this phase" in effect:
        return "VILLAINY" in getattr(player, "played_aspects_this_phase", set())
    if "deal" in effect and "damage" in effect and "base" in effect:
        return True
    if "deal" in effect and "damage" in effect:
        return bool(enemy.units)
    if "draw" in effect:
        return bool(player.deck or player.discard_pile)
    if "look at opponent" in effect:
        return bool(enemy.hand)

    return True


def resolve_leader_action(game: Any, player: Player) -> None:
    effect = player.leader.action_effect.lower()
    enemy = game._get_enemy(player)

    game._resolve_structured_effects(player, player.leader, "action")

    if "heal" in effect:
        damaged_units = [unit for unit in player.units if unit.current_hp < unit.hp]
        if damaged_units:
            damaged_units[0].heal(1)
        return

    if "played a villainy card this phase" in effect:
        if "VILLAINY" not in getattr(player, "played_aspects_this_phase", set()):
            return
        target = game._choose_enemy_unit(player)
        if target:
            game._damage_unit(enemy, target, 1)
        enemy.base.take_damage(1)
        return

    if "each base" in effect and "deal" in effect and "damage" in effect:
        game.player1.base.take_damage(1)
        game.player2.base.take_damage(1)
        return

    if "deal" in effect and "damage" in effect and "base" in effect:
        enemy.base.take_damage(1)
        return

    if "deal" in effect and "damage" in effect and enemy.units:
        target = min(enemy.units, key=lambda unit: unit.current_hp)
        target.take_damage(2)
        if target.is_defeated():
            game._remove_unit(enemy, target)
        return

    if "draw" in effect:
        game._draw_cards(player, 1, f"{player.leader.name}'s action")


def deploy_leader(game: Any, player: Player) -> bool:
    leader = player.leader
    if not leader or leader.is_deployed or leader.epic_action_used:
        return False
    if not player.can_afford(leader.epic_action_cost):
        return False

    player.pay_cost(leader.epic_action_cost)
    leader.epic_action_used = True
    leader.is_deployed = True
    leader.is_exhausted = False

    power, hp = game._leader_deployed_stats(leader)
    leader.power = power
    leader.hp = hp
    leader.current_hp = hp
    leader.damage = 0
    leader.arena = Arena.GROUND

    player.units.append(leader)
    player.ground_arena.append(leader)
    game.log(f"Turn {game.turn_count}: Player {player.id} deploys {leader.name}")
    game._emit(f"  Player {player.id} deploys {leader.name} ready")
    return True


def leader_deployed_stats(game: Any, leader: LeaderCard) -> tuple[int, int]:
    for token in leader.epic_action_effect.split():
        if "/" in token:
            power, hp = token.split("/", 1)
            if power.isdigit() and hp.isdigit():
                return int(power), int(hp)
    return 3, 3
