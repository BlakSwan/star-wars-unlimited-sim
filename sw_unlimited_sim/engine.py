"""Star Wars Unlimited - Game Engine"""

from typing import Any, Optional, List, Tuple
import random
import re
from effect_store import effect_key, load_effects
from models import *
import combat_engine
import event_engine
import leader_engine
import play_engine
import rules as game_rules
import structured_effects as structured_runtime


TOKEN_TEMPLATES = {
    "battle droid": {
        "name": "Battle Droid",
        "power": 1,
        "hp": 1,
        "arena": Arena.GROUND,
        "traits": ["DROID", "SEPARATIST"],
    },
    "clone trooper": {
        "name": "Clone Trooper",
        "power": 2,
        "hp": 2,
        "arena": Arena.GROUND,
        "traits": ["CLONE", "TROOPER", "REPUBLIC"],
    },
    "spy": {
        "name": "Spy",
        "power": 1,
        "hp": 1,
        "arena": Arena.GROUND,
        "traits": ["SPY"],
    },
    "tie fighter": {
        "name": "TIE Fighter",
        "power": 1,
        "hp": 1,
        "arena": Arena.SPACE,
        "traits": ["IMPERIAL", "VEHICLE", "FIGHTER"],
    },
    "x wing": {
        "name": "X-Wing",
        "power": 2,
        "hp": 2,
        "arena": Arena.SPACE,
        "traits": ["REBEL", "VEHICLE", "FIGHTER"],
    },
}


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
        self.token_counter = 0
        self.strategy_tuning = {
            "han_pilot_attack_with_attached_unit": True,
            "anakin_return_after_attached_attack": True,
        }

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
            if self._can_play_as_pilot(player, card):
                actions.append(f"pilot_{card.id}")
        
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

        if action.startswith("pilot_"):
            card_id = action[6:]
            return self._play_card_as_pilot(player, card_id)
        
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
        return play_engine.play_card(self, player, card_id)
    
    def _play_unit(self, player: Player, unit: UnitCard):
        """Play a unit card"""
        return play_engine.play_unit(self, player, unit)
    
    def _play_upgrade(self, player: Player, upgrade: UpgradeCard):
        """Play an upgrade card"""
        return play_engine.play_upgrade(self, player, upgrade)

    def _attach_upgrade(self, upgrade: Card, target: UnitCard):
        """Attach an upgrade and apply its printed stat bonuses."""
        play_engine.attach_upgrade(self, upgrade, target)

    def _printed_attached_power_bonus(self, upgrade: Card) -> int:
        return game_rules.printed_attached_power_bonus(self, upgrade)

    def _printed_attached_hp_bonus(self, upgrade: Card) -> int:
        return game_rules.printed_attached_hp_bonus(self, upgrade)

    def _conditional_attached_hp_bonus(self, upgrade: Card, target: Optional[UnitCard]) -> int:
        return game_rules.conditional_attached_hp_bonus(self, upgrade, target)

    def _modify_unit_stats(self, unit: UnitCard, power_delta: int = 0, hp_delta: int = 0):
        unit.power += power_delta
        unit.hp += hp_delta
        if hp_delta > 0:
            unit.current_hp += hp_delta
        elif hp_delta < 0:
            unit.current_hp = min(unit.current_hp, unit.hp)
            if unit.current_hp <= 0:
                unit.current_hp = 0
            unit.damage = max(0, unit.hp - unit.current_hp)

    def _upgrade_total_power_bonus(self, upgrade: UpgradeCard) -> int:
        return game_rules.upgrade_total_power_bonus(self, upgrade)

    def _upgrade_total_hp_bonus(self, upgrade: UpgradeCard) -> int:
        return game_rules.upgrade_total_hp_bonus(self, upgrade)

    def _discard_attached_upgrades(self, owner: Player, unit: UnitCard):
        play_engine.discard_attached_upgrades(self, owner, unit)

    def _detach_upgrade_to_hand(self, owner: Player, unit: UnitCard, upgrade: Card, source_name: str) -> bool:
        return play_engine.detach_upgrade_to_hand(self, owner, unit, upgrade, source_name)

    def _piloting_cost(self, card: Card) -> Optional[int]:
        return game_rules.piloting_cost(self, card)

    def _unit_has_pilot(self, unit: UnitCard) -> bool:
        return play_engine.unit_has_pilot(self, unit)

    def _eligible_pilot_targets(self, player: Player) -> list[UnitCard]:
        return play_engine.eligible_pilot_targets(self, player)

    def _choose_pilot_target(self, player: Player) -> Optional[UnitCard]:
        return play_engine.choose_pilot_target(self, player)

    def _can_play_as_pilot(self, player: Player, card: Card) -> bool:
        return play_engine.can_play_as_pilot(self, player, card)

    def _can_play_as_pilot_with_discount(self, player: Player, card: Card, discount: int = 0) -> bool:
        return play_engine.can_play_as_pilot_with_discount(self, player, card, discount)

    def _play_card_as_pilot(self, player: Player, card_id: str) -> bool:
        return play_engine.play_card_as_pilot(self, player, card_id)

    def _play_specific_card_as_pilot(self, player: Player, card: Card, cost_discount: int = 0) -> bool:
        return play_engine.play_specific_card_as_pilot(self, player, card, cost_discount)
    
    def _play_event(self, player: Player, event: EventCard):
        """Play an event card"""
        self.log(f"Turn {self.turn_count}: Player {player.id} plays {event.name}")
        self._resolve_event(player, event)
        player.discard_pile.append(event)
        return True
    
    def _attack(self, player: Player, unit_id: str, target: str) -> bool:
        """Execute an attack"""
        return combat_engine.attack(self, player, unit_id, target)
    
    def _remove_unit(self, player: Player, unit: UnitCard):
        """Remove defeated unit"""
        combat_engine.remove_unit(self, player, unit)

    def _return_unit_to_hand(self, owner: Player, unit: UnitCard, source_name: str):
        combat_engine.return_unit_to_hand(self, owner, unit, source_name)

    # ==================== CARD TEXT / KEYWORDS ====================

    def _text(self, card: Card) -> str:
        return game_rules.text(self, card)

    def _attached_upgrade_texts(self, unit: UnitCard) -> list[str]:
        return [self._text(upgrade) for upgrade in getattr(unit, "attached_upgrades", []) or []]

    def _effective_cost(self, player: Player, card: Card) -> int:
        return game_rules.effective_cost(self, player, card)

    def _pilot_discount(self, player: Player, card: Card) -> int:
        return game_rules.pilot_discount(self, player, card)

    def _is_pilot_card(self, card: Card) -> bool:
        return game_rules.is_pilot_card(self, card)

    def _friendly_pilot_count(self, player: Player) -> int:
        return game_rules.friendly_pilot_count(self, player)

    def _has_trait(self, card: Card, trait: str) -> bool:
        return game_rules.has_trait(self, card, trait)

    def _has_aspect(self, card: Card, aspect: str) -> bool:
        return game_rules.has_aspect(self, card, aspect)

    def _is_card(self, card: Card, set_code: str, number: str) -> bool:
        return game_rules.is_card(self, card, set_code, number)

    def _has_keyword(self, unit: UnitCard, keyword: str) -> bool:
        return game_rules.has_keyword(self, unit, keyword)

    def _upgrade_grants_keyword(self, upgrade: Card, keyword: str) -> bool:
        return game_rules.upgrade_grants_keyword(self, upgrade, keyword)

    def _raid_bonus(self, player: Player, attacker: UnitCard, defender: Optional[UnitCard]) -> int:
        return game_rules.raid_bonus(self, player, attacker, defender)

    def _attack_power(self, player: Player, attacker: UnitCard, defender: Optional[UnitCard]) -> int:
        return game_rules.attack_power(self, player, attacker, defender)

    def _unit_power(self, player: Player, unit: UnitCard) -> int:
        return game_rules.unit_power(self, player, unit)

    def _has_overwhelm(self, player: Player, attacker: UnitCard, defender: Optional[UnitCard]) -> bool:
        return game_rules.has_overwhelm(self, player, attacker, defender)

    def _sentinel_units(self, player: Player, arena: Arena) -> List[UnitCard]:
        return game_rules.sentinel_units(self, player, arena)

    def _can_ignore_sentinel(self, attacker: UnitCard) -> bool:
        return game_rules.can_ignore_sentinel(self, attacker)

    def _attackable_enemy_units(self, player: Player, attacker: UnitCard) -> List[UnitCard]:
        return game_rules.attackable_enemy_units(self, player, attacker)

    def _can_attack_unit(self, player: Player, attacker: UnitCard, defender: UnitCard) -> bool:
        return game_rules.can_attack_unit(self, player, attacker, defender)

    def _can_attack_base(self, player: Player, attacker: UnitCard) -> bool:
        return game_rules.can_attack_base(self, player, attacker)

    def _defensive_attack_penalty(self, defender: UnitCard) -> int:
        return game_rules.defensive_attack_penalty(self, defender)

    def _blocks_enemy_defeat_or_bounce(self, unit: UnitCard) -> bool:
        return game_rules.blocks_enemy_defeat_or_bounce(self, unit)

    def _record_played_card(self, player: Player, card: Card):
        if not hasattr(player, "played_aspects_this_phase"):
            player.played_aspects_this_phase = set()
        for aspect in getattr(card, "aspects", []) or []:
            player.played_aspects_this_phase.add(str(aspect).upper())

        self._resolve_on_played_card(player, card)

    def _grant_next_pilot_discount_this_phase(self, player: Player, amount: int = 1):
        player.pilot_discount_this_phase = int(getattr(player, "pilot_discount_this_phase", 0) or 0) + amount

    def _consume_pilot_discount(self, player: Player, card: Card):
        if self._is_pilot_card(card) and getattr(player, "pilot_discount_this_phase", 0):
            player.pilot_discount_this_phase = max(0, int(player.pilot_discount_this_phase) - 1)

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

        if self._is_card(unit, "JTL", "051") and unit.current_hp > 2:
            self._damage_unit(player, unit, 2)
            if unit in player.units:
                self._draw_cards(player, 1, "Red Squadron X-Wing")

    def _resolve_when_played_upgrade(self, player: Player, upgrade: UpgradeCard, target: UnitCard):
        self._resolve_structured_effects(player, upgrade, "when_played", defender=target)

        if upgrade.name == "Vader's Lightsaber" and "Darth Vader" in target.name:
            enemy = self._get_enemy(player)
            if enemy.ground_arena:
                self._damage_unit(enemy, enemy.ground_arena[0], 4)
                self._emit("  Vader's Lightsaber deals 4 damage to a ground unit")

    def _resolve_when_pilot_attached(self, player: Player, pilot: UnitCard, target: UnitCard):
        combat_engine.resolve_when_pilot_attached(self, player, pilot, target)

    def _resolve_after_attack_completed(self, player: Player, attacker: UnitCard):
        combat_engine.resolve_after_attack_completed(self, player, attacker)

    def _resolve_on_attack(self, player: Player, attacker: UnitCard, defender: Optional[UnitCard]):
        combat_engine.resolve_on_attack(self, player, attacker, defender)

    def _resolve_base_combat_damage(self, player: Player, attacker: UnitCard, damage: int):
        combat_engine.resolve_base_combat_damage(self, player, attacker, damage)

    def _resolve_when_defeated(self, owner: Player, unit: UnitCard, enemy: Player):
        combat_engine.resolve_when_defeated(self, owner, unit, enemy)

    def _restore_amount(self, unit: UnitCard) -> int:
        return game_rules.restore_amount(self, unit)

    def _damage_unit(self, owner: Player, unit: UnitCard, amount: int):
        combat_engine.damage_unit(self, owner, unit, amount)

    def _card_effect_record(self, card: Card) -> Optional[dict[str, Any]]:
        return structured_runtime.card_effect_record(self, card)

    def _has_approved_structured_trigger(self, card: Card, trigger: str) -> bool:
        return structured_runtime.has_approved_structured_trigger(self, card, trigger)

    def _resolve_structured_effects(
        self,
        player: Player,
        source: Card,
        trigger: str,
        defender: Optional[UnitCard] = None,
    ):
        structured_runtime.resolve_structured_effects(self, player, source, trigger, defender)

    def _can_execute_structured_step(self, source: Card, step: dict[str, Any]) -> bool:
        return structured_runtime.can_execute_structured_step(self, source, step)

    def _target_player(self, player: Player, target_spec: dict[str, Any]) -> Player:
        return structured_runtime.target_player(self, player, target_spec)

    def _target_unit(self, player: Player, target_spec: dict[str, Any], defender: Optional[UnitCard] = None) -> tuple[Optional[Player], Optional[UnitCard]]:
        return structured_runtime.target_unit(self, player, target_spec, defender)

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
        structured_runtime.apply_structured_step(self, player, source, step, defender)

    def _create_tokens(self, player: Player, token_name: str, amount: int, source_name: str, ready: bool = False) -> list[UnitCard]:
        template = self._token_template(token_name)
        if not template:
            self.log(f"Turn {self.turn_count}: {source_name} skipped unknown token type {token_name!r}")
            return []

        created = []
        for _ in range(max(0, amount)):
            self.token_counter += 1
            token = UnitCard(
                f"TOKEN_{self.token_counter}",
                template["name"],
                0,
                int(template["power"]),
                int(template["hp"]),
                template["arena"],
                traits=list(template["traits"]),
            )
            token.is_token = True
            token.is_exhausted = not ready
            player.units.append(token)
            if token.arena == Arena.SPACE:
                player.space_arena.append(token)
            else:
                player.ground_arena.append(token)
            created.append(token)

        state = "ready" if ready else "exhausted"
        self.log(f"Turn {self.turn_count}: {source_name} creates {len(created)} {template['name']} token(s) {state}")
        return created

    def _token_template(self, token_name: str) -> Optional[dict[str, Any]]:
        normalized = re.sub(r"\s+token(s)?\b", "", str(token_name).strip().lower()).strip()
        normalized = normalized.replace("-", " ")
        return TOKEN_TEMPLATES.get(normalized)

    def _step_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y"}
        return bool(value)

    def _strategy_setting(self, name: str, default: Any = None) -> Any:
        settings = getattr(self, "strategy_tuning", {}) or {}
        return settings.get(name, default)

    def _structured_stat_deltas(self, step: dict[str, Any]) -> tuple[int, int]:
        return structured_runtime.structured_stat_deltas(step)

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

    def _choose_damaged_unit(self, player: Player) -> Optional[tuple[Player, UnitCard]]:
        enemy = self._get_enemy(player)
        candidates = [
            (owner, unit)
            for owner in (player, enemy)
            for unit in owner.units
            if getattr(unit, "damage", 0) > 0
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda entry: (entry[1].damage, entry[1].power, entry[0].id == player.id))

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
        return self._attack_with_unit_tuning(player, unit, power_bonus=power_bonus, combat_damage_before_defender=False)

    def _attack_with_unit_tuning(
        self,
        player: Player,
        unit: UnitCard,
        power_bonus: int = 0,
        combat_damage_before_defender: bool = False,
    ):
        if unit not in player.units or getattr(unit, "is_exhausted", False):
            return False

        unit.power += power_bonus
        previous_flag = getattr(unit, "combat_damage_before_defender_once", False)
        unit.combat_damage_before_defender_once = combat_damage_before_defender
        try:
            target = "base"
            attackable = self._attackable_enemy_units(player, unit)
            if attackable:
                target = attackable[0].id
            return self._attack(player, unit.id, target)
        finally:
            unit.combat_damage_before_defender_once = previous_flag
            unit.power -= power_bonus

    def _resolve_event(self, player: Player, event: EventCard):
        event_engine.resolve_event(self, player, event)

    def _unit_action_has_target(self, player: Player, unit: UnitCard) -> bool:
        return leader_engine.unit_action_has_target(self, player, unit)

    def _use_unit_action(self, player: Player, unit_id: str) -> bool:
        return leader_engine.use_unit_action(self, player, unit_id)

    def _use_admiral_ozzel_action(self, player: Player, unit: UnitCard) -> bool:
        return leader_engine.use_admiral_ozzel_action(self, player, unit)
    
    def _use_leader_action(self, player: Player) -> bool:
        """Use leader action ability"""
        return leader_engine.use_leader_action(self, player)

    def _leader_action_has_target(self, player: Player) -> bool:
        """Check whether the simplified leader action can affect game state."""
        return leader_engine.leader_action_has_target(self, player)

    def _resolve_leader_action(self, player: Player):
        """Resolve a small subset of sample leader actions."""
        leader_engine.resolve_leader_action(self, player)

    def _deploy_leader(self, player: Player) -> bool:
        """Use the leader's once-per-game epic action to deploy it ready."""
        return leader_engine.deploy_leader(self, player)

    def _leader_deployed_stats(self, leader: LeaderCard) -> Tuple[int, int]:
        """Parse sample epic action text like 'Deploy as 4/4 unit'."""
        return leader_engine.leader_deployed_stats(self, leader)
    
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
            player.pilot_discount_this_phase = 0
            for unit in player.units:
                unit.attacked_this_phase = False
