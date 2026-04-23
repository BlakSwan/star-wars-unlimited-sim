"""Play, attachment, and piloting helpers for the simulator engine."""

from __future__ import annotations

from typing import Any, Optional

from models import Arena, Card, EventCard, LeaderCard, Player, UnitCard, UpgradeCard


def play_card(game: Any, player: Player, card_id: str) -> bool:
    card = next((candidate for candidate in player.hand if candidate.id == card_id), None)
    effective_cost = game._effective_cost(player, card) if card else 0
    if not card or not player.can_afford(effective_cost):
        return False

    player.pay_cost(effective_cost)
    player.hand.remove(card)

    if isinstance(card, UnitCard):
        played = game._play_unit(player, card)
    elif isinstance(card, UpgradeCard):
        played = game._play_upgrade(player, card)
    elif isinstance(card, EventCard):
        played = game._play_event(player, card)
    else:
        return False

    if played:
        game._record_played_card(player, card)
    return played


def play_unit(game: Any, player: Player, unit: UnitCard) -> bool:
    if unit.arena == Arena.GROUND:
        player.ground_arena.append(unit)
    else:
        player.space_arena.append(unit)

    player.units.append(unit)
    unit.is_exhausted = True

    if game._has_keyword(unit, "shielded"):
        unit.shield_tokens += 1
        game.log(f"Turn {game.turn_count}: {unit.name} gains a Shield token")
        game._emit(f"  {unit.name} gains a Shield token")

    if unit.has_ambush:
        unit.is_exhausted = False
        game.log(f"Turn {game.turn_count}: Player {player.id} plays {unit.name} ready with Ambush")
        game._emit(f"  Player {player.id} plays {unit.name} (cost {unit.cost}) - AMBUSH, ready to attack")
    else:
        game.log(f"Turn {game.turn_count}: Player {player.id} plays {unit.name} exhausted")
        game._emit(f"  Player {player.id} plays {unit.name} (cost {unit.cost}) - enters exhausted")

    game._resolve_when_played_unit(player, unit)
    return True


def play_upgrade(game: Any, player: Player, upgrade: UpgradeCard) -> bool:
    target = next(iter(player.units), None)
    if not target:
        player.discard_pile.append(upgrade)
        game.log(f"Turn {game.turn_count}: Player {player.id} plays {upgrade.name} but has no unit - discarded")
        return True

    game._attach_upgrade(upgrade, target)
    game.log(f"Turn {game.turn_count}: Player {player.id} plays {upgrade.name} on {target.name}")
    game._resolve_when_played_upgrade(player, upgrade, target)
    return True


def attach_upgrade(game: Any, upgrade: Card, target: UnitCard) -> None:
    upgrade.attached_to = target
    upgrade.structured_power_bonus = 0
    upgrade.structured_hp_bonus = 0
    if not hasattr(target, "attached_upgrades"):
        target.attached_upgrades = []
    target.attached_upgrades.append(upgrade)
    game._modify_unit_stats(
        target,
        game._printed_attached_power_bonus(upgrade),
        game._printed_attached_hp_bonus(upgrade),
    )
    if game._upgrade_grants_keyword(upgrade, "shielded"):
        target.shield_tokens += 1
        game.log(f"Turn {game.turn_count}: {upgrade.name} gives {target.name} a Shield token")


def discard_attached_upgrades(game: Any, owner: Player, unit: UnitCard) -> None:
    attached = list(getattr(unit, "attached_upgrades", []) or [])
    for upgrade in attached:
        game._modify_unit_stats(
            unit,
            -game._upgrade_total_power_bonus(upgrade),
            -game._upgrade_total_hp_bonus(upgrade),
        )
        upgrade.attached_to = None
        upgrade.played_as_pilot = False
        upgrade.structured_power_bonus = 0
        upgrade.structured_hp_bonus = 0
        owner.discard_pile.append(upgrade)
        game.log(f"Turn {game.turn_count}: {upgrade.name} is discarded from {unit.name}")
    unit.attached_upgrades = []


def detach_upgrade_to_hand(game: Any, owner: Player, unit: UnitCard, upgrade: Card, source_name: str) -> bool:
    attached = getattr(unit, "attached_upgrades", []) or []
    if upgrade not in attached:
        return False
    game._modify_unit_stats(
        unit,
        -game._upgrade_total_power_bonus(upgrade),
        -game._upgrade_total_hp_bonus(upgrade),
    )
    attached.remove(upgrade)
    upgrade.attached_to = None
    upgrade.played_as_pilot = False
    upgrade.structured_power_bonus = 0
    upgrade.structured_hp_bonus = 0
    owner.hand.append(upgrade)
    game.log(f"Turn {game.turn_count}: {source_name} returns {upgrade.name} to Player {owner.id}'s hand")
    return True


def unit_has_pilot(game: Any, unit: UnitCard) -> bool:
    for upgrade in getattr(unit, "attached_upgrades", []) or []:
        if getattr(upgrade, "played_as_pilot", False) or game._has_trait(upgrade, "PILOT"):
            return True
    return False


def eligible_pilot_targets(game: Any, player: Player) -> list[UnitCard]:
    return [
        unit for unit in player.units
        if game._has_trait(unit, "VEHICLE") and not game._unit_has_pilot(unit)
    ]


def choose_pilot_target(game: Any, player: Player) -> Optional[UnitCard]:
    targets = game._eligible_pilot_targets(player)
    if not targets:
        return None
    return max(targets, key=lambda unit: (unit.power + unit.current_hp, unit.power))


def can_play_as_pilot(game: Any, player: Player, card: Card) -> bool:
    if not isinstance(card, UnitCard) or isinstance(card, LeaderCard):
        return False
    cost = game._piloting_cost(card)
    return cost is not None and player.can_afford(cost) and bool(game._eligible_pilot_targets(player))


def play_card_as_pilot(game: Any, player: Player, card_id: str) -> bool:
    card = next((candidate for candidate in player.hand if candidate.id == card_id), None)
    if not card or not game._can_play_as_pilot(player, card):
        return False

    target = game._choose_pilot_target(player)
    cost = game._piloting_cost(card)
    if target is None or cost is None or not player.pay_cost(cost):
        return False

    player.hand.remove(card)
    card.played_as_pilot = True
    card.is_exhausted = False
    card.damage = 0
    card.current_hp = getattr(card, "hp", 0)
    game._attach_upgrade(card, target)
    game.log(f"Turn {game.turn_count}: Player {player.id} plays {card.name} as a Pilot on {target.name}")
    game._resolve_when_pilot_attached(player, card, target)
    game._resolve_structured_effects(player, card, "when_played_as_upgrade", defender=target)
    game._resolve_structured_effects(player, card, "when_played", defender=target)
    game._record_played_card(player, card)
    return True
