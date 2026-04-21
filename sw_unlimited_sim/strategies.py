"""Star Wars Unlimited - AI Player Strategies"""

import random
from typing import List, Callable
from models import *
from engine import GameState


# Strategy type: (game_state, player, legal_actions) -> action
Strategy = Callable[[GameState, Player, List[str]], str]


def random_strategy(game: GameState, player: Player, actions: List[str]) -> str:
    """Randomly select a legal action"""
    valid = [a for a in actions if a != "pass" and a != "take_initiative"]
    if valid:
        return random.choice(valid)
    return "pass"


def aggressive_strategy(game: GameState, player: Player, actions: List[str]) -> str:
    """Aggressive strategy - prioritize attacks and playing units"""
    # First, attack if possible
    for action in actions:
        if action.startswith("attack_") and "_base" in action:
            return action
    
    # Then play units
    for action in actions:
        if action.startswith("play_"):
            card_id = action[5:]
            for card in player.hand:
                if card.id == card_id and isinstance(card, UnitCard):
                    return action
    
    # Attack units if can't play cards
    for action in actions:
        if action.startswith("attack_"):
            return action
    
    # Take initiative if available
    if "take_initiative" in actions:
        return "take_initiative"
    
    return "pass"


def control_strategy(game: GameState, player: Player, actions: List[str]) -> str:
    """Control strategy - prioritize card advantage and efficient removal"""
    # First, use leader action if available
    for action in actions:
        if action.startswith("leader_action_"):
            return action
    
    # Play events for card draw/effects
    for action in actions:
        if action.startswith("play_"):
            card_id = action[5:]
            for card in player.hand:
                if card.id == card_id and isinstance(card, EventCard):
                    return action
    
    # Play units
    for action in actions:
        if action.startswith("play_"):
            return action
    
    # Attack enemy units (trade favorably)
    for action in actions:
        if action.startswith("attack_") and "_base" not in action:
            return action
    
    # Take initiative
    if "take_initiative" in actions:
        return "take_initiative"
    
    return "pass"


def balanced_strategy(game: GameState, player: Player, actions: List[str]) -> str:
    """Balanced strategy - mix of aggression and control"""
    # 30% aggressive, 30% control, 40% random
    roll = random.random()
    
    if roll < 0.3:
        return aggressive_strategy(game, player, actions)
    elif roll < 0.6:
        return control_strategy(game, player, actions)
    else:
        return random_strategy(game, player, actions)


def greedy_value_strategy(game: GameState, player: Player, actions: List[str]) -> str:
    """Greedy strategy - maximize immediate value"""
    best_action = "pass"
    best_value = 0
    
    for action in actions:
        value = 0
        
        if action.startswith("play_"):
            card_id = action[5:]
            for card in player.hand:
                if card.id == card_id:
                    # Value = cost of card (playing expensive cards is good)
                    if isinstance(card, UnitCard):
                        value = card.cost + card.power + card.hp
                    elif isinstance(card, UpgradeCard):
                        value = card.cost + card.power_bonus + card.hp_bonus
                    elif isinstance(card, EventCard):
                        value = card.cost + 2  # Events are valuable
                    break
        
        elif action.startswith("attack_"):
            if "_base" in action:
                value = 10  # Attacking base is very valuable
            else:
                # Attack unit - value if we can kill it
                parts = action[7:].split("_")
                unit_id = parts[0]
                target = "_".join(parts[1:])
                
                for unit in player.units:
                    if unit.id == unit_id:
                        enemy = game._get_enemy(player)
                        for eunit in enemy.units:
                            if eunit.id == target:
                                # Value if we kill them and survive
                                if unit.power >= eunit.current_hp:
                                    value = eunit.power + eunit.hp
                                else:
                                    value = unit.power // 2
                        break
        
        elif action == "take_initiative":
            value = 1
        
        if value > best_value:
            best_value = value
            best_action = action
    
    return best_action


def economic_strategy(game: GameState, player: Player, actions: List[str]) -> str:
    """Economic strategy - prioritize resource management"""
    # Always resource if possible
    # Play cards that give good value
    # Save resources for bigger plays
    
    # First, take initiative to ensure first action next round
    if "take_initiative" in actions and random.random() < 0.7:
        return "take_initiative"
    
    # Play higher cost cards first (better value)
    play_actions = [a for a in actions if a.startswith("play_")]
    if play_actions:
        # Find highest cost card to play
        best_play = None
        best_cost = -1
        for action in play_actions:
            card_id = action[5:]
            for card in player.hand:
                if card.id == card_id and card.cost > best_cost:
                    best_cost = card.cost
                    best_play = action
        if best_play:
            return best_play
    
    # Attack base if we have a strong unit
    for action in actions:
        if action.startswith("attack_") and "_base" in action:
            return action
    
    return "pass"


# Strategy registry
STRATEGIES = {
    "random": random_strategy,
    "aggressive": aggressive_strategy,
    "control": control_strategy,
    "balanced": balanced_strategy,
    "greedy": greedy_value_strategy,
    "economic": economic_strategy,
}


def get_strategy(name: str) -> Strategy:
    """Get strategy by name"""
    return STRATEGIES.get(name, random_strategy)


def list_strategies() -> List[str]:
    """List available strategies"""
    return list(STRATEGIES.keys())