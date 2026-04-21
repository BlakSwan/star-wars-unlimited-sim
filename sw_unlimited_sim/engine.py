"""Star Wars Unlimited - Game Engine"""

from typing import Optional, List, Tuple
import random
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

    def _emit(self, message: str):
        """Print a message only for verbose runs."""
        if self.verbose:
            print(message)
    
    def setup(self):
        """Initialize game setup"""
        self._emit("\nSetting up game...")
        
        # Shuffle decks
        random.shuffle(self.player1.deck)
        random.shuffle(self.player2.deck)
        
        # Draw initial hands
        self.player1.draw_cards(6)
        self.player2.draw_cards(6)
        
        # Determine first initiative (random)
        if random.random() < 0.5:
            self.initiative_holder = self.player1
            self.player1.has_initiative = True
            self._emit("  Player 1 (Rebels) wins initiative roll")
        else:
            self.initiative_holder = self.player2
            self.player2.has_initiative = True
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
            if player.can_afford(card.cost):
                actions.append(f"play_{card.id}")
        
        # Can attack with ready units
        for unit in player.units:
            if not hasattr(unit, 'is_exhausted') or not unit.is_exhausted:
                # Can attack enemy units in same arena
                for enemy in self._get_enemy_units(player, unit.arena):
                    actions.append(f"attack_{unit.id}_{enemy.id}")
                # Can attack enemy base
                actions.append(f"attack_{unit.id}_base")
        
        # Can use action abilities (simplified)
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
            self.log(f"Player {player.id} passes")
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
        
        if not card or not player.can_afford(card.cost):
            return False
        
        # Pay cost
        player.pay_cost(card.cost)
        player.hand.remove(card)
        
        if isinstance(card, UnitCard):
            return self._play_unit(player, card)
        elif isinstance(card, UpgradeCard):
            return self._play_upgrade(player, card)
        elif isinstance(card, EventCard):
            return self._play_event(player, card)
        
        return False
    
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
        
        # Check for Ambush
        if unit.has_ambush:
            unit.is_exhausted = False  # Ready to attack immediately
            self._emit(f"  Player {player.id} plays {unit.name} (cost {unit.cost}) - AMBUSH, ready to attack")
        else:
            self._emit(f"  Player {player.id} plays {unit.name} (cost {unit.cost}) - enters exhausted")
        
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
            self.log(f"Player {player.id} plays {upgrade.name} but has no unit - discarded")
            return True
        
        upgrade.attached_to = target
        target.power += upgrade.power_bonus
        target.hp += upgrade.hp_bonus
        target.current_hp += upgrade.hp_bonus
        
        self.log(f"Player {player.id} plays {upgrade.name} on {target.name}")
        return True
    
    def _play_event(self, player: Player, event: EventCard):
        """Play an event card"""
        self.log(f"Player {player.id} plays {event.name}")
        # Simplified - just discard for now
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
            damage = attacker.power
            enemy.base.take_damage(damage)
            attacker.is_exhausted = True
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
            
            # Simultaneous damage
            attacker.take_damage(defender.power)
            defender.take_damage(attacker.power)
            attacker.is_exhausted = True
            
            self._emit(f"  {attacker.name} ({attacker.power} power) attacks {defender.name} ({defender.power} power)")
            self._emit(f"     Simultaneous damage: both take {defender.power}/{attacker.power}")
            
            # Remove defeated units
            if attacker.is_defeated():
                self._remove_unit(player, attacker)
                self._emit(f"     {attacker.name} was defeated")
            if defender.is_defeated():
                self._remove_unit(enemy, defender)
                self._emit(f"     {defender.name} was defeated")
        
        return True
    
    def _remove_unit(self, player: Player, unit: UnitCard):
        """Remove defeated unit"""
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
            self.log(f"{unit.name} was defeated and returned to leader side")
            return

        player.discard_pile.append(unit)
        self.log(f"{unit.name} was defeated")
    
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
        self.log(f"Player {player.id} uses {player.leader.name}'s action")
        self._emit(f"  Player {player.id} uses {player.leader.name}'s action")
        return True

    def _leader_action_has_target(self, player: Player) -> bool:
        """Check whether the simplified leader action can affect game state."""
        if not player.leader:
            return False

        effect = player.leader.action_effect.lower()
        enemy = self._get_enemy(player)

        if "heal" in effect:
            return any(unit.current_hp < unit.hp for unit in player.units)
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

        if "heal" in effect:
            damaged_units = [unit for unit in player.units if unit.current_hp < unit.hp]
            if damaged_units:
                damaged_units[0].heal(1)
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
            player.draw_cards(1)

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
        self.log(f"Player {player.id} deploys {leader.name}")
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
        self.player1.draw_cards(2)
        self.player2.draw_cards(2)
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
    
    def _ready_cards(self, player: Player):
        """Ready all exhausted cards"""
        for r in player.resources:
            r.ready()
        for unit in player.units:
            if hasattr(unit, 'is_exhausted'):
                unit.is_exhausted = False
        if player.leader and hasattr(player.leader, 'is_exhausted'):
            player.leader.is_exhausted = False
    
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
            self._emit(f"\n{'='*40}")
            self._emit(f"TURN {turn_count}")
            self._emit(f"{'='*40}")
            
            # Action phase
            self.phase = Phase.ACTION
            self.initiative_taken_this_round = False
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
                    self.log(f"Player {player.id} selected invalid action: {action}")
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
