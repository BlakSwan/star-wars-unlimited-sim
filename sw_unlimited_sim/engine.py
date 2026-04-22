"""Star Wars Unlimited - Game Engine"""

from typing import Any, Optional, List, Tuple
import random
from effect_store import effect_key, load_effects
from effect_training import should_execute_record
from models import *


class GameState:
    """Complete game state"""
    
    def __init__(self, player1_deck: List[Card], player2_deck: List[Card],
                 player1_leader: LeaderCard, player2_leader: LeaderCard,
                 verbose: bool = True):
        self.player1 = Player(id=1, deck=player1_deck, leader=player1_leader)
        self.player2 = Player(id=2, deck=player2_deck, leader=player2_leader)
        self.current_player: Player = self.player1
        self.initiative_holder: Optional[Player] = None
        self.initiative_taken_this_round = False
        self.phase = Phase.ACTION
        self.action_count = 0
        self.turn_count = 0
        self.winner: Optional[int] = None
        self.game_log: List[str] = []
        self.verbose = verbose
        self.card_effects = load_effects()

    def _emit(self, message: str):
        """Print a message only for verbose runs."""
        if self.verbose:
            print(message)

    def _card_names(self, cards: List[Card]) -> str:
        return ", ".join(card.name for card in cards) if cards else "none"

    def _draw_cards(self, player: Player, count: int, reason: str):
        drawn = player.draw_cards(count)
        self.log(f"Turn {self.turn_count}: Player {player.id} draws {self._card_names(drawn)} ({reason})")
        return drawn

    def _card_effect_key(self, card: Card) -> Optional[str]:
        parts = str(card.id).split("_")
        if len(parts) < 2:
            return None
        return effect_key(parts[0], parts[1])
    
    def setup(self):
        """Initialize game setup"""
        self._emit("\nSetting up game...")
        
        # Shuffle decks
        random.shuffle(self.player1.deck)
        random.shuffle(self.player2.deck)
        
        # Draw initial hands
        self._draw_cards(self.player1, 6, "opening hand")
        self._draw_cards(self.player2, 6, "opening hand")
        
        # Determine first initiative (random)
        if random.random() < 0.5:
            self.initiative_holder = self.player1
            self.player1.has_initiative = True
            self.log("Setup: Player 1 wins initiative roll")
            self._emit("  Player 1 (Rebels) wins initiative roll")
        else:
            self.initiative_holder = self.player2
            self.player2.has_initiative = True
            self.log("Setup: Player 2 wins initiative roll")
            self._emit("  Player 2 (Imperial) wins initiative roll")
        
        # Select resources (simplified - just pick 2 lowest cost cards)
        self._select_resources(self.player1)
        self._select_resources(self.player2)
        
        self.current_player = self.initiative_holder
        self._emit("  Game ready to start!")
        self._emit(f"  First action: Player {self.current_player.id}")
    
    def _select_resources(self, player: Player):
        """Select 2 cards as resources (simplified strategy)"""
        # Sort by cost ascending, take 2 lowest
        sorted_hand = sorted(player.hand, key=lambda c: c.cost)
        for i in range(min(2, len(sorted_hand))):
            card = sorted_hand[i]
            player.hand.remove(card)
            player.resources.append(Resource(card=card))
            self.log(f"Setup: Player {player.id} resources {card.name}")
    
    def log(self, message: str):
        """Add message to game log"""
        self.game_log.append(message)
    
    def is_game_over(self) -> bool:
        """Check if game has ended"""
        return self.player1.base.is_defeated() or self.player2.base.is_defeated()
    
    def get_winner(self) -> Optional[int]:
        """Get winner player ID"""
        if self.player1.base.is_defeated():
            return 2
        elif self.player2.base.is_defeated():
            return 1
        return None
    
    # ==================== ACTION PHASE ====================
    
    def get_legal_actions(self, player: Player) -> List[str]:
        """Get list of legal actions for player"""
        actions = []
        
        # Can always pass
        actions.append("pass")
        
        # One player may claim initiative each round, even if they already hold it.
        if not self.initiative_taken_this_round:
            actions.append("take_initiative")
        
        # Can play cards if can afford
        for card in player.hand:
            if player.can_afford(self._effective_cost(player, card)):
                actions.append(f"play_{card.id}")
        
        # Can attack with ready units
        for unit in player.units:
            if not hasattr(unit, 'is_exhausted') or not unit.is_exhausted:
                # Can attack enemy units in same arena
                enemy_units = self._attackable_enemy_units(player, unit)
                for enemy in enemy_units:
                    actions.append(f"attack_{unit.id}_{enemy.id}")
                # Can attack enemy base
                if self._can_attack_base(player, unit):
                    actions.append(f"attack_{unit.id}_base")
        
        # Can use action abilities (simplified)
        for unit in player.units:
            if not getattr(unit, 'is_exhausted', False):
                if self._unit_action_has_target(player, unit):
                    actions.append(f"unit_action_{unit.id}")

        if player.leader and not player.leader.is_deployed and not player.leader.is_exhausted:
            if player.can_afford(player.leader.action_cost):
                if self._leader_action_has_target(player):
                    actions.append(f"leader_action_{player.leader.id}")

        if player.leader and not player.leader.is_deployed and not player.leader.epic_action_used:
            if player.can_afford(player.leader.epic_action_cost):
                actions.append(f"leader_epic_{player.leader.id}")
        
        return actions
    
    def _get_enemy_units(self, player: Player, arena: Arena) -> List[UnitCard]:
        """Get enemy units in specified arena"""
        enemy = self._get_enemy(player)
        if arena == Arena.GROUND:
            return enemy.ground_arena
        elif arena == Arena.SPACE:
            return enemy.space_arena
        return []
    
    def _get_enemy(self, player: Player) -> Player:
        """Get opponent player"""
        return self.player2 if player.id == 1 else self.player1
    
    def execute_action(self, player: Player, action: str) -> bool:
        """Execute an action. Returns True if action was valid."""
        if action == "pass":
            self.log(f"Turn {self.turn_count}: Player {player.id} passes")
            return True
        
        if action == "take_initiative":
            self._take_initiative(player)
            return True
        
        if action.startswith("play_"):
            card_id = action[5:]
            return self._play_card(player, card_id)
        
        if action.startswith("attack_"):
            parsed_attack = self._parse_attack_action(player, action)
            if not parsed_attack:
                return False
            unit_id, target = parsed_attack
            return self._attack(player, unit_id, target)
        
        if action.startswith("leader_action_"):
            return self._use_leader_action(player)

        if action.startswith("leader_epic_"):
            return self._deploy_leader(player)

        if action.startswith("unit_action_"):
            unit_id = action[12:]
            return self._use_unit_action(player, unit_id)
        
        return False

    def _parse_attack_action(self, player: Player, action: str) -> Optional[Tuple[str, str]]:
        """Parse attack actions even when card IDs contain underscores."""
        payload = action[7:]
        if payload.endswith("_base"):
            return payload[:-5], "base"

        for unit in player.units:
            prefix = f"{unit.id}_"
            if payload.startswith(prefix):
                target = payload[len(prefix):]
                if target:
                    return unit.id, target

        return None
    
    def _take_initiative(self, player: Player):
        """Take the initiative"""
        if self.initiative_taken_this_round:
            return

        # Give initiative to player.
        if self.initiative_holder:
            self.initiative_holder.has_initiative = False
        player.has_initiative = True
        self.initiative_holder = player
        self.initiative_taken_this_round = True
        self.log(f"Turn {self.turn_count}: Player {player.id} takes initiative")
        self._emit(f"  Player {player.id} takes INITIATIVE and passes for the rest of this phase")
        
        self.current_player = self._get_enemy(player)
    
    def _play_card(self, player: Player, card_id: str) -> bool:
        """Play a card from hand"""
        # Find card
        card = None
        for c in player.hand:
            if c.id == card_id:
                card = c
                break
        
        effective_cost = self._effective_cost(player, card) if card else 0
        if not card or not player.can_afford(effective_cost):
            return False
        
        # Pay cost
        player.pay_cost(effective_cost)
        player.hand.remove(card)
        
        if isinstance(card, UnitCard):
            played = self._play_unit(player, card)
        elif isinstance(card, UpgradeCard):
            played = self._play_upgrade(player, card)
        elif isinstance(card, EventCard):
            played = self._play_event(player, card)
        else:
            return False
        
        if played:
            self._record_played_card(player, card)
        return played
    
    def _play_unit(self, player: Player, unit: UnitCard):
        """Play a unit card"""
        # Determine arena if first unit
        if player.ground_arena and not player.space_arena:
            # First unit determines arena
            pass  # Simplified - use unit's declared arena
        
        # Add to appropriate arena
        if unit.arena == Arena.GROUND:
            player.ground_arena.append(unit)
        else:
            player.space_arena.append(unit)
        
        player.units.append(unit)
        unit.is_exhausted = True  # Units enter exhausted

        if self._has_keyword(unit, "shielded"):
            unit.shield_tokens += 1
            self.log(f"Turn {self.turn_count}: {unit.name} gains a Shield token")
            self._emit(f"  {unit.name} gains a Shield token")
        
        # Check for Ambush
        if unit.has_ambush:
            unit.is_exhausted = False  # Ready to attack immediately
            self.log(f"Turn {self.turn_count}: Player {player.id} plays {unit.name} ready with Ambush")
            self._emit(f"  Player {player.id} plays {unit.name} (cost {unit.cost}) - AMBUSH, ready to attack")
        else:
            self.log(f"Turn {self.turn_count}: Player {player.id} plays {unit.name} exhausted")
            self._emit(f"  Player {player.id} plays {unit.name} (cost {unit.cost}) - enters exhausted")

        self._resolve_when_played_unit(player, unit)
        
        return True
    
    def _play_upgrade(self, player: Player, upgrade: UpgradeCard):
        """Play an upgrade card"""
        # Find a unit to attach to (simplified - first unit in arena)
        target = None
        for unit in player.units:
            target = unit
            break
        
        if not target:
            # No units - discard upgrade
            player.discard_pile.append(upgrade)
            self.log(f"Turn {self.turn_count}: Player {player.id} plays {upgrade.name} but has no unit - discarded")
            return True
        
        upgrade.attached_to = target
        target.power += upgrade.power_bonus
        target.hp += upgrade.hp_bonus
        target.current_hp += upgrade.hp_bonus
        
        self.log(f"Turn {self.turn_count}: Player {player.id} plays {upgrade.name} on {target.name}")
        self._resolve_when_played_upgrade(player, upgrade, target)
        return True
    
    def _play_event(self, player: Player, event: EventCard):
        """Play an event card"""
        self.log(f"Turn {self.turn_count}: Player {player.id} plays {event.name}")
        self._resolve_event(player, event)
        player.discard_pile.append(event)
        return True
    
    def _attack(self, player: Player, unit_id: str, target: str) -> bool:
        """Execute an attack"""
        # Find attacker
        attacker = None
        for unit in player.units:
            if unit.id == unit_id:
                attacker = unit
                break
        
        if not attacker or getattr(attacker, 'is_exhausted', False):
            return False
        
        enemy = self._get_enemy(player)
        
        if target == "base":
            # Attack base
            self._resolve_on_attack(player, attacker, None)
            damage = self._attack_power(player, attacker, None)
            enemy.base.take_damage(damage)
            attacker.is_exhausted = True
            attacker.attacked_this_phase = True
            self._resolve_base_combat_damage(player, attacker, damage)
            self.log(
                f"Turn {self.turn_count}: Player {player.id}'s {attacker.name} attacks Player {enemy.id}'s base "
                f"for {damage} damage; base HP {enemy.base.current_hp}/25"
            )
            self._emit(f"  Player {player.id}'s {attacker.name} attacks BASE for {damage} damage")
            self._emit(f"     Base HP: {enemy.base.current_hp}/25")
            
        else:
            # Attack enemy unit
            defender = None
            for unit in enemy.units:
                if unit.id == target:
                    defender = unit
                    break
            
            if not defender:
                return False

            if not self._can_attack_unit(player, attacker, defender):
                return False
            
            # Simultaneous damage
            defender_hp_before_damage = defender.current_hp
            self._resolve_on_attack(player, attacker, defender)
            if attacker not in player.units:
                return True
            if defender not in enemy.units:
                attacker.is_exhausted = True
                attacker.attacked_this_phase = True
                return True
            attack_damage = self._attack_power(player, attacker, defender)
            defender_damage = defender.power
            attacker.take_damage(defender_damage)
            defender.take_damage(attack_damage)
            attacker.is_exhausted = True
            attacker.attacked_this_phase = True
            self.log(
                f"Turn {self.turn_count}: Player {player.id}'s {attacker.name} attacks {defender.name}; "
                f"{attacker.name} takes {defender_damage}, {defender.name} takes {attack_damage}"
            )
            
            self._emit(f"  {attacker.name} ({attack_damage} power) attacks {defender.name} ({defender.power} power)")
            self._emit(f"     Simultaneous damage: both take {defender_damage}/{attack_damage}")

            if defender.is_defeated() and self._has_overwhelm(player, attacker, defender):
                excess = max(0, attack_damage - defender_hp_before_damage)
                if excess:
                    enemy.base.take_damage(excess)
                    self.log(f"Turn {self.turn_count}: Overwhelm deals {excess} excess damage to Player {enemy.id}'s base")
                    self._emit(f"     Overwhelm deals {excess} excess damage to base")
            
            # Remove defeated units
            if attacker.is_defeated() and attacker in player.units:
                self._remove_unit(player, attacker)
                self._emit(f"     {attacker.name} was defeated")
            if defender.is_defeated() and defender in enemy.units:
                self._remove_unit(enemy, defender)
                self._emit(f"     {defender.name} was defeated")
        
        return True
    
    def _remove_unit(self, player: Player, unit: UnitCard):
        """Remove defeated unit"""
        enemy = self._get_enemy(player)
        self._resolve_when_defeated(player, unit, enemy)
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
            self.log(f"Turn {self.turn_count}: {unit.name} was defeated and returned to leader side")
            return

        player.discard_pile.append(unit)
        self.log(f"Turn {self.turn_count}: {unit.name} was defeated")

    def _return_unit_to_hand(self, owner: Player, unit: UnitCard, source_name: str):
        if unit not in owner.units:
            return
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
        owner.hand.append(unit)
        self.log(f"Turn {self.turn_count}: {source_name} returns {unit.name} to Player {owner.id}'s hand")

    # ==================== CARD TEXT / KEYWORDS ====================

    def _text(self, card: Card) -> str:
        pieces = []
        if isinstance(card, EventCard):
            pieces.append(card.effect)
        pieces.extend(getattr(card, "abilities", []) or [])
        if isinstance(card, LeaderCard):
            pieces.append(card.action_effect)
            pieces.append(card.epic_action_effect)
        return "\n".join(piece for piece in pieces if piece).lower()

    def _effective_cost(self, player: Player, card: Card) -> int:
        if card.name == "Force Choke" and self._friendly_force_unit(player):
            return max(0, card.cost - 1)
        return card.cost

    def _has_trait(self, card: Card, trait: str) -> bool:
        return trait.upper() in {str(value).upper() for value in getattr(card, "traits", [])}

    def _has_aspect(self, card: Card, aspect: str) -> bool:
        return aspect.upper() in {str(value).upper() for value in getattr(card, "aspects", [])}

    def _is_card(self, card: Card, set_code: str, number: str) -> bool:
        return self._card_effect_key(card) == effect_key(set_code, number)

    def _has_keyword(self, unit: UnitCard, keyword: str) -> bool:
        if getattr(unit, "abilities_lost_until_ready", False):
            return False
        return keyword.lower() in self._text(unit)

    def _raid_bonus(self, player: Player, attacker: UnitCard, defender: Optional[UnitCard]) -> int:
        if getattr(attacker, "abilities_lost_until_ready", False):
            return 0

        text = self._text(attacker)
        bonus = 0

        if "raid 2" in text:
            bonus += 2
        elif "raid 1" in text:
            bonus += 1

        if attacker.name == "Partisan Insurgent":
            if any(unit is not attacker and self._has_aspect(unit, "Aggression") for unit in player.units):
                bonus += 2

        if attacker.name == "Fifth Brother":
            bonus += attacker.damage

        for unit in player.units:
            if unit is attacker or getattr(unit, "abilities_lost_until_ready", False):
                continue
            if unit.name == "Red Three" and self._has_aspect(attacker, "Heroism"):
                bonus += 1

        if attacker.name == "First Legion Snowtrooper" and defender and defender.damage > 0:
            bonus += 2

        return bonus

    def _attack_power(self, player: Player, attacker: UnitCard, defender: Optional[UnitCard]) -> int:
        grit_bonus = attacker.damage if self._has_keyword(attacker, "grit") else 0
        return attacker.power + self._raid_bonus(player, attacker, defender) + grit_bonus

    def _has_overwhelm(self, player: Player, attacker: UnitCard, defender: Optional[UnitCard]) -> bool:
        if getattr(attacker, "abilities_lost_until_ready", False):
            return False
        if "overwhelm" in self._text(attacker):
            if attacker.name == "First Legion Snowtrooper":
                return bool(defender and defender.damage > 0)
            return True
        return False

    def _sentinel_units(self, player: Player, arena: Arena) -> List[UnitCard]:
        return [
            unit for unit in self._get_enemy_units(player, arena)
            if self._has_keyword(unit, "sentinel")
        ]

    def _can_ignore_sentinel(self, attacker: UnitCard) -> bool:
        return self._has_keyword(attacker, "saboteur")

    def _attackable_enemy_units(self, player: Player, attacker: UnitCard) -> List[UnitCard]:
        enemy_units = self._get_enemy_units(player, attacker.arena)
        sentinels = self._sentinel_units(player, attacker.arena)
        if sentinels and not self._can_ignore_sentinel(attacker):
            return sentinels
        return enemy_units

    def _can_attack_unit(self, player: Player, attacker: UnitCard, defender: UnitCard) -> bool:
        return defender in self._attackable_enemy_units(player, attacker)

    def _can_attack_base(self, player: Player, attacker: UnitCard) -> bool:
        return not self._sentinel_units(player, attacker.arena) or self._can_ignore_sentinel(attacker)

    def _record_played_card(self, player: Player, card: Card):
        if not hasattr(player, "played_aspects_this_phase"):
            player.played_aspects_this_phase = set()
        for aspect in getattr(card, "aspects", []) or []:
            player.played_aspects_this_phase.add(str(aspect).upper())

        self._resolve_on_played_card(player, card)

    def _resolve_on_played_card(self, player: Player, card: Card):
        """Resolve simple triggers that care about played card aspects."""
        if not self._has_aspect(card, "Aggression"):
            return

        enemy = self._get_enemy(player)
        for unit in player.units:
            if unit is card or getattr(unit, "abilities_lost_until_ready", False):
                continue
            if unit.name == "Fighters For Freedom":
                enemy.base.take_damage(1)
                self.log(f"Turn {self.turn_count}: Fighters For Freedom deals 1 damage to Player {enemy.id}'s base")
                self._emit("  Fighters For Freedom deals 1 damage to enemy base")

    def _resolve_when_played_unit(self, player: Player, unit: UnitCard):
        enemy = self._get_enemy(player)
        self._resolve_structured_effects(player, unit, "when_played")

        if unit.name == "SpecForce Soldier":
            targets = [
                target for target in enemy.units + player.units
                if self._has_keyword(target, "sentinel")
            ]
            if targets:
                targets[0].abilities_lost_until_ready = True
                self._emit(f"  {targets[0].name} loses Sentinel for this phase")

        if unit.name == "Imperial Interceptor":
            targets = enemy.space_arena or player.space_arena
            if targets:
                target = targets[0]
                self._damage_unit(enemy if target in enemy.units else player, target, 3)
                self._emit(f"  Imperial Interceptor deals 3 damage to {target.name}")

        if self._is_card(unit, "JTL", "143"):
            self._damage_base(enemy, 4, "Devastator")

        if self._is_card(unit, "JTL", "096") and player.can_afford(2):
            player.pay_cost(2)
            if unit in player.space_arena:
                player.space_arena.remove(unit)
            if unit not in player.ground_arena:
                player.ground_arena.append(unit)
            unit.arena = Arena.GROUND
            unit.experience_tokens += 2
            unit.power += 2
            unit.hp += 2
            unit.current_hp += 2
            self.log("Turn {0}: Blue Leader pays 2, moves to ground, and gains 2 Experience tokens".format(self.turn_count))

    def _resolve_when_played_upgrade(self, player: Player, upgrade: UpgradeCard, target: UnitCard):
        self._resolve_structured_effects(player, upgrade, "when_played", defender=target)

        if upgrade.name == "Vader's Lightsaber" and "Darth Vader" in target.name:
            enemy = self._get_enemy(player)
            if enemy.ground_arena:
                self._damage_unit(enemy, enemy.ground_arena[0], 4)
                self._emit("  Vader's Lightsaber deals 4 damage to a ground unit")

    def _resolve_on_attack(self, player: Player, attacker: UnitCard, defender: Optional[UnitCard]):
        enemy = self._get_enemy(player)

        if getattr(attacker, "abilities_lost_until_ready", False):
            return

        self._resolve_structured_effects(player, attacker, "on_attack", defender=defender)

        if attacker.name == "Sabine Wren":
            if defender:
                self._damage_unit(enemy, defender, 1)
            else:
                enemy.base.take_damage(1)
            self._emit("  Sabine Wren deals 1 on-attack damage")

        if attacker.name == "Fifth Brother":
            self._damage_unit(player, attacker, 1)
            targets = [unit for unit in enemy.ground_arena if unit is not defender]
            if targets:
                self._damage_unit(enemy, targets[0], 1)
            self._emit("  Fifth Brother deals 1 damage to himself on attack")

        if self._is_card(attacker, "LOF", "046"):
            targets = [
                unit for unit in player.units
                if unit is not attacker and (self._has_trait(unit, "CREATURE") or self._has_trait(unit, "SPECTRE"))
            ]
            if targets:
                target = max(targets, key=lambda unit: (unit.power, unit.current_hp))
                target.experience_tokens += 1
                target.power += 1
                target.hp += 1
                target.current_hp += 1
                self.log(f"Turn {self.turn_count}: Ezra Bridger gives an Experience token to {target.name}")

        restore_amount = self._restore_amount(attacker)
        if restore_amount:
            before = player.base.current_hp
            player.base.current_hp = min(player.base.hp, player.base.current_hp + restore_amount)
            healed = player.base.current_hp - before
            self.log(f"Turn {self.turn_count}: {attacker.name} restores {healed} damage from Player {player.id}'s base")
            self._emit(f"  {attacker.name} restores {restore_amount} base HP")

    def _resolve_base_combat_damage(self, player: Player, attacker: UnitCard, damage: int):
        enemy = self._get_enemy(player)

        if getattr(attacker, "abilities_lost_until_ready", False):
            return

        if attacker.name == "Seventh Sister" and enemy.ground_arena:
            self._damage_unit(enemy, enemy.ground_arena[0], 3)
            self._emit("  Seventh Sister deals 3 damage to a ground unit")

    def _resolve_when_defeated(self, owner: Player, unit: UnitCard, enemy: Player):
        if getattr(unit, "abilities_lost_until_ready", False):
            return
        self._resolve_structured_effects(owner, unit, "when_defeated")
        if unit.name == "K-2SO":
            enemy.base.take_damage(3)
            self.log(f"Turn {self.turn_count}: K-2SO deals 3 damage to Player {enemy.id}'s base when defeated")
            self._emit("  K-2SO deals 3 damage to enemy base when defeated")

        if self._is_card(unit, "SEC", "094") and self._can_disclose_aspects(owner, ["COMMAND", "COMMAND", "HEROISM"]):
            self._draw_cards(owner, 1, "Mina Bonteri")

    def _restore_amount(self, unit: UnitCard) -> int:
        if getattr(unit, "abilities_lost_until_ready", False):
            return 0
        text = self._text(unit)
        if "restore" not in text:
            return 0
        import re
        match = re.search(r"restore\\s+(\\d+)", text)
        return int(match.group(1)) if match else 0

    def _damage_unit(self, owner: Player, unit: UnitCard, amount: int):
        actual = unit.take_damage(amount)
        self.log(
            f"Turn {self.turn_count}: {unit.name} takes {actual} damage "
            f"({unit.current_hp}/{unit.hp} HP remaining)"
        )
        if unit.is_defeated() and unit in owner.units:
            self._remove_unit(owner, unit)

    def _card_effect_record(self, card: Card) -> Optional[dict[str, Any]]:
        key = self._card_effect_key(card)
        if not key:
            return None
        record = self.card_effects.get(key)
        if not record or not should_execute_record(record):
            return None
        return record

    def _resolve_structured_effects(
        self,
        player: Player,
        source: Card,
        trigger: str,
        defender: Optional[UnitCard] = None,
    ):
        record = self._card_effect_record(source)
        if not record:
            return

        for trigger_record in record.get("triggers", []):
            if trigger_record.get("event") != trigger:
                continue
            if trigger_record.get("conditions"):
                self.log(f"Turn {self.turn_count}: {source.name} skipped trained effect with unsupported conditions")
                continue
            for step in trigger_record.get("steps", []):
                if not self._can_execute_structured_step(source, step):
                    continue
                self._apply_structured_step(player, source, step, defender)

    def _can_execute_structured_step(self, source: Card, step: dict[str, Any]) -> bool:
        target = step.get("target") or {}
        if target.get("filter"):
            self.log(f"Turn {self.turn_count}: {source.name} skipped trained effect with unsupported target filter")
            return False
        if step.get("duration") not in (None, "", "instant"):
            self.log(f"Turn {self.turn_count}: {source.name} skipped trained effect with unsupported duration")
            return False
        if step.get("optional") or step.get("choice_group"):
            self.log(f"Turn {self.turn_count}: {source.name} skipped trained effect that needs a choice")
            return False
        return True

    def _target_player(self, player: Player, target_spec: dict[str, Any]) -> Player:
        controller = str(target_spec.get("controller") or "self").lower()
        if controller == "enemy":
            return self._get_enemy(player)
        return player

    def _target_unit(self, player: Player, target_spec: dict[str, Any], defender: Optional[UnitCard] = None) -> tuple[Optional[Player], Optional[UnitCard]]:
        controller = str(target_spec.get("controller") or "enemy").lower()
        if controller == "self":
            candidates = player.units
            owner = player
        elif controller == "friendly":
            candidates = player.units
            owner = player
        elif controller == "any":
            enemy = self._get_enemy(player)
            candidates = enemy.units + player.units
            owner = enemy if candidates and candidates[0] in enemy.units else player
        else:
            owner = self._get_enemy(player)
            candidates = owner.units

        if defender and defender in candidates:
            return owner, defender
        if not candidates:
            return None, None
        if controller in {"friendly", "self"}:
            unit = self._choose_friendly_unit(player, damaged=True) or self._choose_friendly_unit(player)
            return player, unit
        unit = min(candidates, key=lambda candidate: (candidate.current_hp, -candidate.power))
        if controller == "any" and unit in player.units:
            owner = player
        return owner, unit

    def _damage_base(self, player: Player, amount: int, source_name: str):
        before = player.base.current_hp
        player.base.take_damage(amount)
        actual = before - player.base.current_hp
        self.log(f"Turn {self.turn_count}: {source_name} deals {actual} damage to Player {player.id}'s base")

    def _heal_base(self, player: Player, amount: int, source_name: str):
        before = player.base.current_hp
        player.base.current_hp = min(player.base.hp, player.base.current_hp + amount)
        actual = player.base.current_hp - before
        self.log(f"Turn {self.turn_count}: {source_name} heals {actual} damage from Player {player.id}'s base")

    def _discard_cards(self, player: Player, count: int, source_name: str):
        discarded = []
        for _ in range(min(count, len(player.hand))):
            card = min(player.hand, key=lambda candidate: (candidate.cost, candidate.name))
            player.hand.remove(card)
            player.discard_pile.append(card)
            discarded.append(card)
        self.log(f"Turn {self.turn_count}: Player {player.id} discards {self._card_names(discarded)} ({source_name})")

    def _can_disclose_aspects(self, player: Player, required_aspects: list[str]) -> bool:
        available = []
        for card in player.hand:
            available.extend(str(aspect).upper() for aspect in getattr(card, "aspects", []) or [])
        for aspect in required_aspects:
            if aspect not in available:
                return False
            available.remove(aspect)
        return True

    def _apply_structured_step(
        self,
        player: Player,
        source: Card,
        step: dict[str, Any],
        defender: Optional[UnitCard] = None,
    ):
        effect_type = str(step.get("type") or "").lower()
        target_spec = step.get("target") or {}
        amount = int(step.get("amount") or 1)
        target_type = str(target_spec.get("type") or "unit").lower()
        source_name = source.name

        if effect_type == "draw_cards":
            target_player = self._target_player(player, target_spec)
            self._draw_cards(target_player, amount, source_name)
            return

        if effect_type == "discard_cards":
            target_player = self._target_player(player, target_spec)
            self._discard_cards(target_player, amount, source_name)
            return

        if target_type in {"base", "player"}:
            target_player = self._target_player(player, target_spec)
            if effect_type == "deal_damage":
                self._damage_base(target_player, amount, source_name)
            elif effect_type == "heal_damage":
                self._heal_base(target_player, amount, source_name)
            else:
                self.log(f"Turn {self.turn_count}: {source_name} skipped unsupported base effect {effect_type}")
            return

        owner, unit = self._target_unit(player, target_spec, defender)
        if not owner or not unit:
            self.log(f"Turn {self.turn_count}: {source_name} found no target for {effect_type}")
            return

        if effect_type == "deal_damage":
            self._damage_unit(owner, unit, amount)
        elif effect_type == "heal_damage":
            before = unit.current_hp
            unit.heal(amount)
            self.log(f"Turn {self.turn_count}: {source_name} heals {unit.current_hp - before} damage from {unit.name}")
        elif effect_type == "exhaust_unit":
            unit.is_exhausted = True
            self.log(f"Turn {self.turn_count}: {source_name} exhausts {unit.name}")
        elif effect_type == "ready_unit":
            unit.is_exhausted = False
            self.log(f"Turn {self.turn_count}: {source_name} readies {unit.name}")
        elif effect_type == "defeat_unit":
            self._remove_unit(owner, unit)
            self.log(f"Turn {self.turn_count}: {source_name} defeats {unit.name}")
        elif effect_type == "give_shield":
            unit.shield_tokens += amount
            self.log(f"Turn {self.turn_count}: {source_name} gives {amount} Shield token(s) to {unit.name}")
        elif effect_type == "give_experience":
            unit.experience_tokens += amount
            unit.power += amount
            unit.hp += amount
            unit.current_hp += amount
            self.log(f"Turn {self.turn_count}: {source_name} gives {amount} Experience token(s) to {unit.name}")
        elif effect_type == "capture_unit":
            self.log(f"Turn {self.turn_count}: {source_name} skipped capture effect; capture zones are not modeled yet")
        else:
            self.log(f"Turn {self.turn_count}: {source_name} skipped unknown structured effect {effect_type}")

    def _friendly_force_unit(self, player: Player) -> Optional[UnitCard]:
        for unit in player.units:
            if self._has_trait(unit, "FORCE"):
                return unit
        if player.leader and player.leader.is_deployed and self._has_trait(player.leader, "FORCE"):
            return player.leader
        return None

    def _choose_enemy_unit(self, player: Player, *, arena: Optional[Arena] = None, non_vehicle: bool = False) -> Optional[UnitCard]:
        enemy = self._get_enemy(player)
        units = enemy.units
        if arena:
            units = [unit for unit in units if unit.arena == arena]
        if non_vehicle:
            units = [unit for unit in units if not self._has_trait(unit, "VEHICLE")]
        if not units:
            return None
        return min(units, key=lambda unit: (unit.current_hp, -unit.power))

    def _choose_friendly_unit(self, player: Player, *, damaged: bool = False, trait: Optional[str] = None) -> Optional[UnitCard]:
        units = player.units
        if damaged:
            units = [unit for unit in units if unit.damage > 0]
        if trait:
            units = [unit for unit in units if self._has_trait(unit, trait)]
        if not units:
            return None
        return max(units, key=lambda unit: (unit.power, unit.current_hp))

    def _attack_with_unit(self, player: Player, unit: UnitCard, power_bonus: int = 0):
        if unit not in player.units or getattr(unit, "is_exhausted", False):
            return False

        unit.power += power_bonus
        try:
            target = "base"
            attackable = self._attackable_enemy_units(player, unit)
            if attackable:
                target = attackable[0].id
            return self._attack(player, unit.id, target)
        finally:
            unit.power -= power_bonus

    def _resolve_event(self, player: Player, event: EventCard):
        enemy = self._get_enemy(player)
        self._resolve_structured_effects(player, event, "when_played")

        if event.name == "Heroic Sacrifice":
            self._draw_cards(player, 1, "Heroic Sacrifice")
            unit = self._choose_friendly_unit(player)
            if unit:
                defeated = self._attack_with_unit(player, unit, power_bonus=2)
                if defeated and unit in player.units:
                    self._remove_unit(player, unit)
            return

        if event.name == "Karabast":
            friendly = self._choose_friendly_unit(player, damaged=True) or self._choose_friendly_unit(player)
            target = self._choose_enemy_unit(player)
            if friendly and target:
                self._damage_unit(enemy, target, friendly.damage + 1)
            return

        if event.name == "Rebel Assault":
            rebels = [unit for unit in player.units if self._has_trait(unit, "REBEL") and not getattr(unit, "is_exhausted", False)]
            for unit in rebels[:2]:
                self._attack_with_unit(player, unit, power_bonus=1)
            return

        if event.name == "Medal Ceremony":
            rebels = [
                unit for unit in player.units
                if self._has_trait(unit, "REBEL") and getattr(unit, "attacked_this_phase", False)
            ]
            for unit in rebels[:3]:
                unit.experience_tokens += 1
                unit.power += 1
                unit.hp += 1
                unit.current_hp += 1
            return

        if event.name == "Force Choke":
            target = self._choose_enemy_unit(player, non_vehicle=True)
            if target:
                self._damage_unit(enemy, target, 5)
                self._draw_cards(enemy, 1, "Force Choke")
            return

        if event.name == "Force Lightning":
            target = self._choose_enemy_unit(player)
            if target:
                target.abilities_lost_until_ready = True
                resources = len(player.get_ready_resources())
                if self._friendly_force_unit(player) and resources:
                    player.pay_cost(resources)
                    self._damage_unit(enemy, target, 2 * resources)
            return

        if self._is_card(event, "SEC", "233"):
            targets = [unit for unit in enemy.units if not isinstance(unit, LeaderCard) and unit.cost <= 6]
            if targets:
                target = max(targets, key=lambda unit: (unit.cost, unit.power + unit.hp))
                self._return_unit_to_hand(enemy, target, "Beguile")
            return

    def _unit_action_has_target(self, player: Player, unit: UnitCard) -> bool:
        if getattr(unit, "abilities_lost_until_ready", False):
            return False
        record = self._card_effect_record(unit)
        if record and any(trigger.get("event") == "action" for trigger in record.get("triggers", [])):
            return True
        if unit.name == "Admiral Ozzel":
            return any(
                self._has_trait(card, "IMPERIAL") and isinstance(card, UnitCard) and player.can_afford(card.cost)
                for card in player.hand
            )
        return False

    def _use_unit_action(self, player: Player, unit_id: str) -> bool:
        unit = next((candidate for candidate in player.units if candidate.id == unit_id), None)
        if not unit or getattr(unit, "is_exhausted", False):
            return False
        if not self._unit_action_has_target(player, unit):
            return False

        if unit.name == "Admiral Ozzel":
            return self._use_admiral_ozzel_action(player, unit)

        if self._card_effect_record(unit):
            unit.is_exhausted = True
            self._resolve_structured_effects(player, unit, "action")
            self.log(f"Turn {self.turn_count}: Player {player.id} uses {unit.name}'s trained action")
            return True

        return False

    def _use_admiral_ozzel_action(self, player: Player, unit: UnitCard) -> bool:
        imperial_units = [
            card for card in player.hand
            if isinstance(card, UnitCard) and self._has_trait(card, "IMPERIAL") and player.can_afford(card.cost)
        ]
        if not imperial_units:
            return False

        unit.is_exhausted = True
        card = max(imperial_units, key=lambda candidate: (candidate.cost, candidate.power + candidate.hp))
        player.pay_cost(card.cost)
        player.hand.remove(card)
        self._play_unit(player, card)
        card.is_exhausted = False
        self._record_played_card(player, card)

        enemy = self._get_enemy(player)
        exhausted_enemy_units = [enemy_unit for enemy_unit in enemy.units if getattr(enemy_unit, "is_exhausted", False)]
        if exhausted_enemy_units:
            exhausted_enemy_units[0].is_exhausted = False

        self.log(f"Turn {self.turn_count}: Player {player.id} uses Admiral Ozzel's action")
        self._emit(f"  Player {player.id} uses Admiral Ozzel to play {card.name} ready")
        return True
    
    def _use_leader_action(self, player: Player) -> bool:
        """Use leader action ability"""
        if not player.leader or player.leader.is_deployed or player.leader.is_exhausted:
            return False
        
        if not player.can_afford(player.leader.action_cost):
            return False

        if not self._leader_action_has_target(player):
            return False
        
        player.pay_cost(player.leader.action_cost)
        player.leader.is_exhausted = True
        self._resolve_leader_action(player)
        self.log(f"Turn {self.turn_count}: Player {player.id} uses {player.leader.name}'s action")
        self._emit(f"  Player {player.id} uses {player.leader.name}'s action")
        return True

    def _leader_action_has_target(self, player: Player) -> bool:
        """Check whether the simplified leader action can affect game state."""
        if not player.leader:
            return False

        record = self._card_effect_record(player.leader)
        if record and any(trigger.get("event") == "action" for trigger in record.get("triggers", [])):
            return True

        effect = player.leader.action_effect.lower()
        enemy = self._get_enemy(player)

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

    def _resolve_leader_action(self, player: Player):
        """Resolve a small subset of sample leader actions."""
        effect = player.leader.action_effect.lower()
        enemy = self._get_enemy(player)

        self._resolve_structured_effects(player, player.leader, "action")

        if "heal" in effect:
            damaged_units = [unit for unit in player.units if unit.current_hp < unit.hp]
            if damaged_units:
                damaged_units[0].heal(1)
            return

        if "played a villainy card this phase" in effect:
            if "VILLAINY" not in getattr(player, "played_aspects_this_phase", set()):
                return
            target = self._choose_enemy_unit(player)
            if target:
                self._damage_unit(enemy, target, 1)
            enemy.base.take_damage(1)
            return

        if "each base" in effect and "deal" in effect and "damage" in effect:
            self.player1.base.take_damage(1)
            self.player2.base.take_damage(1)
            return

        if "deal" in effect and "damage" in effect and "base" in effect:
            enemy.base.take_damage(1)
            return

        if "deal" in effect and "damage" in effect and enemy.units:
            target = min(enemy.units, key=lambda unit: unit.current_hp)
            target.take_damage(2)
            if target.is_defeated():
                self._remove_unit(enemy, target)
            return

        if "draw" in effect:
            self._draw_cards(player, 1, f"{player.leader.name}'s action")

    def _deploy_leader(self, player: Player) -> bool:
        """Use the leader's once-per-game epic action to deploy it ready."""
        leader = player.leader
        if not leader or leader.is_deployed or leader.epic_action_used:
            return False

        if not player.can_afford(leader.epic_action_cost):
            return False

        player.pay_cost(leader.epic_action_cost)
        leader.epic_action_used = True
        leader.is_deployed = True
        leader.is_exhausted = False

        power, hp = self._leader_deployed_stats(leader)
        leader.power = power
        leader.hp = hp
        leader.current_hp = hp
        leader.damage = 0
        leader.arena = Arena.GROUND

        player.units.append(leader)
        player.ground_arena.append(leader)
        self.log(f"Turn {self.turn_count}: Player {player.id} deploys {leader.name}")
        self._emit(f"  Player {player.id} deploys {leader.name} ready")
        return True

    def _leader_deployed_stats(self, leader: LeaderCard) -> Tuple[int, int]:
        """Parse sample epic action text like 'Deploy as 4/4 unit'."""
        for token in leader.epic_action_effect.split():
            if "/" in token:
                power, hp = token.split("/", 1)
                if power.isdigit() and hp.isdigit():
                    return int(power), int(hp)
        return 3, 3
    
    def _pass_phase(self, player: Player):
        """Player passes their action"""
        self.log(f"Turn {self.turn_count}: Player {player.id} passes")
        self._emit(f"  Player {player.id} passes")
        enemy = self._get_enemy(player)
        
        # Check if both players have passed
        # Simplified: just switch to other player
        self.current_player = enemy
    
    # ==================== REGROUP PHASE ====================
    
    def execute_regroup_phase(self):
        """Execute the regroup phase"""
        self._emit("\n=== REGROUP PHASE ===")
        
        # Step 1: Draw cards
        self._draw_cards(self.player1, 2, "regroup")
        self._draw_cards(self.player2, 2, "regroup")
        self._emit("  Both players draw 2 cards")
        
        # Step 2: Resource a card (optional)
        self._resource_card(self.player1)
        self._resource_card(self.player2)
        self._emit("  Both players may resource a card")
        
        # Step 3: Ready all cards
        self._ready_cards(self.player1)
        self._ready_cards(self.player2)
        self._emit("  All cards ready")
        
        # Show board state
        self._emit(f"  Player 1: {len(self.player1.units)} units, {len(self.player1.hand)} in hand, base HP: {self.player1.base.current_hp}")
        self._emit(f"  Player 2: {len(self.player2.units)} units, {len(self.player2.hand)} in hand, base HP: {self.player2.base.current_hp}")
        
        # Back to action phase
        self.phase = Phase.ACTION
        self.current_player = self.initiative_holder
        self._emit(f"  Back to Action Phase - Player {self.current_player.id} starts")
    
    def _resource_card(self, player: Player):
        """Player resources a card (simplified - lowest cost)"""
        if not player.hand:
            return
        
        # Find lowest cost card
        card = min(player.hand, key=lambda c: c.cost)
        player.hand.remove(card)
        player.resources.append(Resource(card=card))
        self.log(f"Turn {self.turn_count}: Player {player.id} resources {card.name}")
    
    def _ready_cards(self, player: Player):
        """Ready all exhausted cards"""
        for r in player.resources:
            r.ready()
        for unit in player.units:
            if hasattr(unit, 'is_exhausted'):
                unit.is_exhausted = False
            unit.abilities_lost_until_ready = False
        if player.leader and hasattr(player.leader, 'is_exhausted'):
            player.leader.is_exhausted = False
            player.leader.abilities_lost_until_ready = False
    
    # ==================== GAME LOOP ====================
    
    def play_turn(self, player: Player, action: str) -> bool:
        """Play one action during action phase"""
        return self.execute_action(player, action)
    
    def end_action_phase(self):
        """End action phase and start regroup"""
        self.phase = Phase.REGROUP
        self.execute_regroup_phase()
    
    def run_to_completion(self, player1_strategy, player2_strategy):
        """Run game to completion with given strategies"""
        self.setup()
        
        turn_count = 0
        max_turns = 50  # Safety limit
        
        while not self.is_game_over() and turn_count < max_turns:
            turn_count += 1
            self.turn_count = turn_count
            self.log(f"Turn {turn_count}: Action phase starts")
            self._emit(f"\n{'='*40}")
            self._emit(f"TURN {turn_count}")
            self._emit(f"{'='*40}")
            
            # Action phase
            self.phase = Phase.ACTION
            self.initiative_taken_this_round = False
            self._start_action_phase()
            passed = {1: False, 2: False}
            locked_passed = set()
            actions_this_round = 0
            max_actions = 20  # Prevent infinite loops
            
            while (
                self.phase == Phase.ACTION
                and not all(passed.values())
                and not self.is_game_over()
                and actions_this_round < max_actions
            ):
                player = self.current_player

                if passed[player.id] and player.id in locked_passed:
                    self.current_player = self._get_enemy(player)
                    continue

                actions_this_round += 1
                strategy = player1_strategy if player.id == 1 else player2_strategy
                
                # Get legal actions
                actions = self.get_legal_actions(player)
                
                if not actions:
                    actions = ["pass"]
                
                # Strategy chooses action
                action = strategy(self, player, actions)
                
                if action == "pass":
                    passed[player.id] = True
                    self._pass_phase(player)
                    self._emit(f"     (passed={passed}, current={self.current_player.id})")
                elif action == "take_initiative" and action in actions:
                    self._take_initiative(player)
                    passed[player.id] = True
                    locked_passed.add(player.id)
                elif action in actions and self.execute_action(player, action):
                    # A state-changing action allows non-locked players to act again.
                    for pid in passed:
                        if pid not in locked_passed:
                            passed[pid] = False
                    self.current_player = self._get_enemy(player)
                    self._emit(f"     (action taken, passed={passed}, now player {self.current_player.id})")
                else:
                    self.log(f"Turn {self.turn_count}: Player {player.id} selected invalid action: {action}")
                    passed[player.id] = True
                    self._pass_phase(player)
            
            # End action phase if not already ended
            if self.phase == Phase.ACTION:
                self._emit("  Action phase complete")
                self.phase = Phase.REGROUP
            
            # Regroup phase
            if not self.is_game_over():
                self.execute_regroup_phase()
            
            if self.is_game_over():
                break
        
        self.winner = self.get_winner()
        
        # Game over output
        self._emit("\n" + "="*50)
        if self.winner == 1:
            self._emit("GAME OVER: Player 1 (Rebels) wins")
        elif self.winner == 2:
            self._emit("GAME OVER: Player 2 (Imperial) wins")
        else:
            self._emit("GAME OVER: Draw (max turns reached)")
        self._emit(f"   Final Base HP - P1: {self.player1.base.current_hp}/25, P2: {self.player2.base.current_hp}/25")
        self._emit("="*50 + "\n")
        
        return self.winner

    def _start_action_phase(self):
        """Reset per-action-phase tracking."""
        for player in (self.player1, self.player2):
            player.played_aspects_this_phase = set()
            for unit in player.units:
                unit.attacked_this_phase = False
