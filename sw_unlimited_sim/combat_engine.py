"""Combat and combat-trigger helpers for the simulator engine."""

from __future__ import annotations

from typing import Any, Optional

from models import Arena, LeaderCard, Player, UnitCard


def attack(game: Any, player: Player, unit_id: str, target: str) -> bool:
    attacker = next((unit for unit in player.units if unit.id == unit_id), None)
    if not attacker or getattr(attacker, "is_exhausted", False):
        return False

    enemy = game._get_enemy(player)

    if target == "base":
        game._resolve_on_attack(player, attacker, None)
        damage = game._attack_power(player, attacker, None)
        enemy.base.take_damage(damage)
        attacker.is_exhausted = True
        attacker.attacked_this_phase = True
        game._resolve_base_combat_damage(player, attacker, damage)
        game.log(
            f"Turn {game.turn_count}: Player {player.id}'s {attacker.name} attacks Player {enemy.id}'s base "
            f"for {damage} damage; base HP {enemy.base.current_hp}/25"
        )
        game._emit(f"  Player {player.id}'s {attacker.name} attacks BASE for {damage} damage")
        game._emit(f"     Base HP: {enemy.base.current_hp}/25")
        if attacker in player.units:
            game._resolve_after_attack_completed(player, attacker)
        return True

    defender = next((unit for unit in enemy.units if unit.id == target), None)
    if not defender:
        return False
    if not game._can_attack_unit(player, attacker, defender):
        return False

    defender_hp_before_damage = defender.current_hp
    game._resolve_on_attack(player, attacker, defender)
    if attacker not in player.units:
        return True
    if defender not in enemy.units:
        attacker.is_exhausted = True
        attacker.attacked_this_phase = True
        return True

    attack_damage = game._attack_power(player, attacker, defender)
    defender_damage = defender.power
    attacker.take_damage(defender_damage)
    defender.take_damage(attack_damage)
    attacker.is_exhausted = True
    attacker.attacked_this_phase = True
    game.log(
        f"Turn {game.turn_count}: Player {player.id}'s {attacker.name} attacks {defender.name}; "
        f"{attacker.name} takes {defender_damage}, {defender.name} takes {attack_damage}"
    )
    game._emit(f"  {attacker.name} ({attack_damage} power) attacks {defender.name} ({defender.power} power)")
    game._emit(f"     Simultaneous damage: both take {defender_damage}/{attack_damage}")

    if defender.is_defeated() and game._has_overwhelm(player, attacker, defender):
        excess = max(0, attack_damage - defender_hp_before_damage)
        if excess:
            enemy.base.take_damage(excess)
            game.log(f"Turn {game.turn_count}: Overwhelm deals {excess} excess damage to Player {enemy.id}'s base")
            game._emit(f"     Overwhelm deals {excess} excess damage to base")

    if attacker.is_defeated() and attacker in player.units:
        game._remove_unit(player, attacker)
        game._emit(f"     {attacker.name} was defeated")
    if defender.is_defeated() and defender in enemy.units:
        game._remove_unit(enemy, defender)
        game._emit(f"     {defender.name} was defeated")
    if attacker in player.units:
        game._resolve_after_attack_completed(player, attacker)
    return True


def remove_unit(game: Any, player: Player, unit: UnitCard) -> None:
    enemy = game._get_enemy(player)
    game._resolve_when_defeated(player, unit, enemy)
    game._discard_attached_upgrades(player, unit)
    player.units.remove(unit)
    if unit in player.ground_arena:
        player.ground_arena.remove(unit)
    if unit in player.space_arena:
        player.space_arena.remove(unit)

    if unit is player.leader:
        player.leader.is_deployed = False
        player.leader.is_exhausted = False
        if hasattr(player.leader, "heal"):
            player.leader.heal()
        game.log(f"Turn {game.turn_count}: {unit.name} was defeated and returned to leader side")
        return

    if getattr(unit, "is_token", False):
        game.log(f"Turn {game.turn_count}: {unit.name} token was defeated and removed from the game")
        return

    player.discard_pile.append(unit)
    game.log(f"Turn {game.turn_count}: {unit.name} was defeated")


def return_unit_to_hand(game: Any, owner: Player, unit: UnitCard, source_name: str) -> None:
    if unit not in owner.units:
        return
    game._discard_attached_upgrades(owner, unit)
    owner.units.remove(unit)
    if unit in owner.ground_arena:
        owner.ground_arena.remove(unit)
    if unit in owner.space_arena:
        owner.space_arena.remove(unit)
    unit.damage = 0
    unit.current_hp = unit.hp
    unit.is_exhausted = False
    unit.attacked_this_phase = False
    unit.abilities_lost_until_ready = False
    if getattr(unit, "is_token", False):
        game.log(f"Turn {game.turn_count}: {source_name} removes {unit.name} token from the game")
        return
    owner.hand.append(unit)
    game.log(f"Turn {game.turn_count}: {source_name} returns {unit.name} to Player {owner.id}'s hand")


def resolve_when_pilot_attached(game: Any, player: Player, pilot: UnitCard, target: UnitCard) -> None:
    if not (getattr(pilot, "played_as_pilot", False) or game._has_trait(pilot, "PILOT")):
        return

    if game._has_approved_structured_trigger(target, "when_pilot_attached"):
        game._resolve_structured_effects(player, target, "when_pilot_attached", defender=target)
        return

    if game._is_card(target, "JTL", "101"):
        game._create_tokens(player, "X-Wing", 1, target.name)

    if game._is_card(pilot, "JTL", "057"):
        heal_target = game._choose_damaged_unit(player)
        if heal_target:
            owner, unit = heal_target
            before = unit.current_hp
            unit.heal(2)
            game.log(f"Turn {game.turn_count}: Astromech Pilot heals {unit.current_hp - before} damage from {unit.name}")

    if game._is_card(pilot, "JTL", "203"):
        if game._strategy_setting("han_pilot_attack_with_attached_unit", True):
            if game._attack_with_unit(player, target):
                game.log(f"Turn {game.turn_count}: Han Solo's pilot effect attacks with {target.name}")
            else:
                game.log(f"Turn {game.turn_count}: Han Solo's pilot effect found no ready attached unit to attack with")
        else:
            game.log("Turn {0}: Han Solo's pilot attack was skipped by strategy tuning".format(game.turn_count))


def resolve_after_attack_completed(game: Any, player: Player, attacker: UnitCard) -> None:
    if attacker not in player.units or attacker.is_defeated():
        return
    for upgrade in list(getattr(attacker, "attached_upgrades", []) or []):
        if game._is_card(upgrade, "JTL", "197"):
            if game._strategy_setting("anakin_return_after_attached_attack", True):
                game._detach_upgrade_to_hand(player, attacker, upgrade, "Anakin Skywalker")
            else:
                game.log(
                    "Turn {0}: Anakin Skywalker's return effect was skipped by strategy tuning".format(
                        game.turn_count
                    )
                )


def resolve_on_attack(game: Any, player: Player, attacker: UnitCard, defender: Optional[UnitCard]) -> None:
    enemy = game._get_enemy(player)
    if getattr(attacker, "abilities_lost_until_ready", False):
        return

    game._resolve_structured_effects(player, attacker, "on_attack", defender=defender)

    if attacker.name == "Sabine Wren":
        if defender:
            game._damage_unit(enemy, defender, 1)
        else:
            enemy.base.take_damage(1)
        game._emit("  Sabine Wren deals 1 on-attack damage")

    if attacker.name == "Fifth Brother":
        game._damage_unit(player, attacker, 1)
        targets = [unit for unit in enemy.ground_arena if unit is not defender]
        if targets:
            game._damage_unit(enemy, targets[0], 1)
        game._emit("  Fifth Brother deals 1 damage to himself on attack")

    if game._is_card(attacker, "LOF", "046"):
        targets = [
            unit for unit in player.units
            if unit is not attacker and (game._has_trait(unit, "CREATURE") or game._has_trait(unit, "SPECTRE"))
        ]
        if targets:
            target = max(targets, key=lambda unit: (unit.power, unit.current_hp))
            target.experience_tokens += 1
            target.power += 1
            target.hp += 1
            target.current_hp += 1
            game.log(f"Turn {game.turn_count}: Ezra Bridger gives an Experience token to {target.name}")

    restore_amount = game._restore_amount(attacker)
    if restore_amount:
        before = player.base.current_hp
        player.base.current_hp = min(player.base.hp, player.base.current_hp + restore_amount)
        healed = player.base.current_hp - before
        game.log(f"Turn {game.turn_count}: {attacker.name} restores {healed} damage from Player {player.id}'s base")
        game._emit(f"  {attacker.name} restores {restore_amount} base HP")


def resolve_base_combat_damage(game: Any, player: Player, attacker: UnitCard, damage: int) -> None:
    enemy = game._get_enemy(player)
    if getattr(attacker, "abilities_lost_until_ready", False):
        return
    if attacker.name == "Seventh Sister" and enemy.ground_arena:
        game._damage_unit(enemy, enemy.ground_arena[0], 3)
        game._emit("  Seventh Sister deals 3 damage to a ground unit")


def resolve_when_defeated(game: Any, owner: Player, unit: UnitCard, enemy: Player) -> None:
    if getattr(unit, "abilities_lost_until_ready", False):
        return
    game._resolve_structured_effects(owner, unit, "when_defeated")
    if unit.name == "K-2SO":
        enemy.base.take_damage(3)
        game.log(f"Turn {game.turn_count}: K-2SO deals 3 damage to Player {enemy.id}'s base when defeated")
        game._emit("  K-2SO deals 3 damage to enemy base when defeated")

    if game._is_card(unit, "SEC", "094") and game._can_disclose_aspects(owner, ["COMMAND", "COMMAND", "HEROISM"]):
        game._draw_cards(owner, 1, "Mina Bonteri")


def damage_unit(game: Any, owner: Player, unit: UnitCard, amount: int) -> None:
    actual = unit.take_damage(amount)
    game.log(
        f"Turn {game.turn_count}: {unit.name} takes {actual} damage "
        f"({unit.current_hp}/{unit.hp} HP remaining)"
    )
    if unit.is_defeated() and unit in owner.units:
        game._remove_unit(owner, unit)
