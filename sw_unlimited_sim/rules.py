"""Rules and keyword helpers for the simulator engine."""

from __future__ import annotations

import re
from typing import Any, Optional

from effect_store import effect_key
from models import Arena, Card, EventCard, LeaderCard, Player, UnitCard, UpgradeCard


def text(game: Any, card: Card) -> str:
    pieces = []
    if isinstance(card, EventCard):
        pieces.append(card.effect)
    pieces.extend(getattr(card, "abilities", []) or [])
    if isinstance(card, LeaderCard):
        pieces.append(card.action_effect)
        pieces.append(card.epic_action_effect)
    return "\n".join(piece for piece in pieces if piece).lower()


def effective_cost(game: Any, player: Player, card: Card) -> int:
    if card.name == "Force Choke" and game._friendly_force_unit(player):
        return max(0, card.cost - 1)
    if is_card(game, card, "JTL", "101"):
        return max(0, card.cost - friendly_pilot_count(game, player))
    return max(0, card.cost - pilot_discount(game, player, card))


def friendly_pilot_count(game: Any, player: Player) -> int:
    total = 0
    for unit in player.units:
        if has_trait(game, unit, "PILOT"):
            total += 1
        for upgrade in getattr(unit, "attached_upgrades", []) or []:
            if getattr(upgrade, "played_as_pilot", False) or has_trait(game, upgrade, "PILOT"):
                total += 1
    return total


def has_trait(game: Any, card: Card, trait: str) -> bool:
    return trait.upper() in {str(value).upper() for value in getattr(card, "traits", [])}


def has_aspect(game: Any, card: Card, aspect: str) -> bool:
    return aspect.upper() in {str(value).upper() for value in getattr(card, "aspects", [])}


def is_card(game: Any, card: Card, set_code: str, number: str) -> bool:
    return game._card_effect_key(card) == effect_key(set_code, number)


def has_keyword(game: Any, unit: UnitCard, keyword: str) -> bool:
    if getattr(unit, "abilities_lost_until_ready", False) or getattr(unit, "temporary_attack_abilities_suppressed", False):
        return False
    keyword = keyword.lower()
    temporary_keywords = {
        str(value).lower()
        for value in (
            set(getattr(unit, "temporary_phase_keywords", set()) or set())
            | set(getattr(unit, "temporary_attack_keywords", set()) or set())
        )
    }
    if keyword in temporary_keywords:
        return True
    if keyword in text(game, unit):
        return True
    return any(
        upgrade_grants_keyword(game, upgrade, keyword)
        for upgrade in getattr(unit, "attached_upgrades", []) or []
    )


def upgrade_grants_keyword(game: Any, upgrade: Card, keyword: str) -> bool:
    keyword = keyword.lower()
    upgrade_text = text(game, upgrade)
    attached_patterns = [
        f"attached unit gains {keyword}",
        f"attached unit gains: {keyword}",
        f"attached unit gains {keyword.capitalize()}".lower(),
    ]
    attached_to = getattr(upgrade, "attached_to", None)
    if is_card(game, upgrade, "JTL", "150"):
        if keyword == "overwhelm" and attached_to and has_trait(game, attached_to, "FIGHTER"):
            return True
        if keyword == "grit" and attached_to and has_trait(game, attached_to, "SPEEDER"):
            return True
    return any(pattern in upgrade_text for pattern in attached_patterns) or bool(
        re.search(rf"attached unit .*gains {re.escape(keyword)}", upgrade_text)
    )


def conditional_attached_hp_bonus(game: Any, upgrade: Card, target: Optional[UnitCard]) -> int:
    if not target:
        return 0
    if is_card(game, upgrade, "JTL", "150") and has_trait(game, target, "TRANSPORT"):
        return 1
    return 0


def printed_attached_power_bonus(game: Any, upgrade: Card) -> int:
    if isinstance(upgrade, UpgradeCard):
        return int(getattr(upgrade, "power_bonus", 0) or 0)
    if getattr(upgrade, "played_as_pilot", False):
        return int(getattr(upgrade, "power", 0) or 0)
    return 0


def printed_attached_hp_bonus(game: Any, upgrade: Card) -> int:
    attached_to = getattr(upgrade, "attached_to", None)
    if isinstance(upgrade, UpgradeCard):
        base_bonus = int(getattr(upgrade, "hp_bonus", 0) or 0)
        return base_bonus + conditional_attached_hp_bonus(game, upgrade, attached_to)
    if getattr(upgrade, "played_as_pilot", False):
        base_bonus = int(getattr(upgrade, "hp", 0) or 0)
        return base_bonus + conditional_attached_hp_bonus(game, upgrade, attached_to)
    return 0


def upgrade_total_power_bonus(game: Any, upgrade: UpgradeCard) -> int:
    return printed_attached_power_bonus(game, upgrade) + int(getattr(upgrade, "structured_power_bonus", 0) or 0)


def upgrade_total_hp_bonus(game: Any, upgrade: UpgradeCard) -> int:
    return printed_attached_hp_bonus(game, upgrade) + int(getattr(upgrade, "structured_hp_bonus", 0) or 0)


def raid_bonus(game: Any, player: Player, attacker: UnitCard, defender: Optional[UnitCard]) -> int:
    if getattr(attacker, "abilities_lost_until_ready", False):
        return 0

    attacker_text = text(game, attacker)
    bonus = 0

    if "raid 2" in attacker_text:
        bonus += 2
    elif "raid 1" in attacker_text:
        bonus += 1

    if attacker.name == "Partisan Insurgent":
        if any(unit is not attacker and has_aspect(game, unit, "Aggression") for unit in player.units):
            bonus += 2

    if attacker.name == "Fifth Brother":
        bonus += attacker.damage

    for unit in player.units:
        if unit is attacker or getattr(unit, "abilities_lost_until_ready", False):
            continue
        if unit.name == "Red Three" and has_aspect(game, attacker, "Heroism"):
            bonus += 1

    if attacker.name == "First Legion Snowtrooper" and defender and defender.damage > 0:
        bonus += 2

    return bonus


def attack_power(game: Any, player: Player, attacker: UnitCard, defender: Optional[UnitCard]) -> int:
    grit_bonus = attacker.damage if has_keyword(game, attacker, "grit") else 0
    return unit_power(game, player, attacker) + raid_bonus(game, player, attacker, defender) + grit_bonus


def unit_power(game: Any, player: Player, unit: UnitCard) -> int:
    return (
        unit.power
        + int(getattr(unit, "temporary_attack_power_bonus", 0) or 0)
        + pilot_synergy_power_bonus(game, player, unit)
    )


def pilot_synergy_power_bonus(game: Any, player: Player, unit: UnitCard) -> int:
    bonus = 0
    if is_card(game, unit, "JTL", "093"):
        bonus += max(0, friendly_pilot_count(game, player) - 1)
    for upgrade in getattr(unit, "attached_upgrades", []) or []:
        if is_card(game, upgrade, "JTL", "093"):
            bonus += max(0, friendly_pilot_count(game, player) - 1)
    return bonus


def has_overwhelm(game: Any, player: Player, attacker: UnitCard, defender: Optional[UnitCard]) -> bool:
    if getattr(attacker, "abilities_lost_until_ready", False):
        return False
    if has_keyword(game, attacker, "overwhelm"):
        if attacker.name == "First Legion Snowtrooper":
            return bool(defender and defender.damage > 0)
        return True
    return False


def sentinel_units(game: Any, player: Player, arena: Arena) -> list[UnitCard]:
    return [
        unit for unit in game._get_enemy_units(player, arena)
        if has_keyword(game, unit, "sentinel")
    ]


def can_ignore_sentinel(game: Any, attacker: UnitCard) -> bool:
    return has_keyword(game, attacker, "saboteur")


def attackable_enemy_units(game: Any, player: Player, attacker: UnitCard) -> list[UnitCard]:
    enemy_units = game._get_enemy_units(player, attacker.arena)
    sentinels = sentinel_units(game, player, attacker.arena)
    if sentinels and not can_ignore_sentinel(game, attacker):
        return sentinels
    return enemy_units


def can_attack_unit(game: Any, player: Player, attacker: UnitCard, defender: UnitCard) -> bool:
    return defender in attackable_enemy_units(game, player, attacker)


def can_attack_base(game: Any, player: Player, attacker: UnitCard) -> bool:
    if getattr(attacker, "temporary_phase_cannot_attack_base", False):
        return False
    if getattr(attacker, "temporary_attack_cannot_attack_base", False):
        return False
    return not sentinel_units(game, player, attacker.arena) or can_ignore_sentinel(game, attacker)


def defensive_attack_penalty(game: Any, defender: UnitCard) -> int:
    if getattr(defender, "abilities_lost_until_ready", False):
        return 0
    penalty = 0
    if is_card(game, defender, "JTL", "054"):
        penalty += 1
    return penalty


def restore_amount(game: Any, unit: UnitCard) -> int:
    if getattr(unit, "abilities_lost_until_ready", False) or getattr(unit, "temporary_attack_abilities_suppressed", False):
        return 0
    unit_text = text(game, unit)
    amount = 0
    match = re.search(r"restore\s+(\d+)", unit_text)
    if match:
        amount += int(match.group(1))

    for upgrade in getattr(unit, "attached_upgrades", []) or []:
        upgrade_text = text(game, upgrade)
        for attached_match in re.finditer(r"attached unit gains restore\s+(\d+)", upgrade_text):
            amount += int(attached_match.group(1))
    return amount


def blocks_enemy_defeat_or_bounce(game: Any, unit: UnitCard) -> bool:
    protected_text = "can't be defeated or returned to hand by enemy card abilities"
    if protected_text in text(game, unit):
        return True
    return any(
        protected_text in text(game, upgrade)
        for upgrade in getattr(unit, "attached_upgrades", []) or []
    )


def piloting_cost(game: Any, card: Card) -> Optional[int]:
    if "Piloting" not in (getattr(card, "abilities", []) or []) and not has_keyword(game, card, "piloting"):
        return None
    match = re.search(r"piloting\s+\[C=(\d+)", text(game, card), flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def is_pilot_card(game: Any, card: Card) -> bool:
    return has_trait(game, card, "PILOT") or piloting_cost(game, card) is not None


def pilot_discount(game: Any, player: Player, card: Card) -> int:
    available = int(getattr(player, "pilot_discount_this_phase", 0) or 0)
    if available <= 0 or not is_pilot_card(game, card):
        return 0
    return available
