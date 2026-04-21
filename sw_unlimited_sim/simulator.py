"""Star Wars Unlimited - Simulation Runner and Analysis"""

import random
from typing import List, Dict, Tuple, Optional
from collections import defaultdict
import time

from models import *
from engine import GameState
from cards import create_sample_decks, get_rebel_leader, get_imperial_leader
from deck_loader import load_deck
from effect_audit import audit_deck
from strategies import get_strategy, STRATEGIES, Strategy


class SimulationResult:
    """Results from a simulation run"""
    
    def __init__(self):
        self.total_games: int = 0
        self.player1_wins: int = 0
        self.player2_wins: int = 0
        self.draws: int = 0
        self.player1_win_rate: float = 0.0
        self.player2_win_rate: float = 0.0
        self.avg_turns: float = 0.0
        self.turns_list: List[int] = []
        self.strategy1_name: str = ""
        self.strategy2_name: str = ""
        self.errors: int = 0
        self.error_messages: List[str] = []
    
    def add_game(self, winner: Optional[int], turns: int):
        """Add a game result"""
        self.total_games += 1
        self.turns_list.append(turns)
        
        if winner == 1:
            self.player1_wins += 1
        elif winner == 2:
            self.player2_wins += 1
        else:
            self.draws += 1
        
        # Update rates
        self.player1_win_rate = self.player1_wins / self.total_games
        self.player2_win_rate = self.player2_wins / self.total_games
        self.avg_turns = sum(self.turns_list) / len(self.turns_list)
    
    def add_error(self, message: str):
        """Record an error"""
        self.errors += 1
        self.error_messages.append(message)
    
    def summary(self) -> str:
        """Get summary string"""
        return (
            f"=== Simulation Results ===\n"
            f"Total Games: {self.total_games}\n"
            f"Player 1 ({self.strategy1_name}): {self.player1_wins} wins ({self.player1_win_rate:.1%})\n"
            f"Player 2 ({self.strategy2_name}): {self.player2_wins} wins ({self.player2_win_rate:.1%})\n"
            f"Draws: {self.draws}\n"
            f"Average Turns: {self.avg_turns:.1f}\n"
            f"Errors: {self.errors}"
        )


def run_single_game(strategy1: Strategy, strategy2: Strategy, 
                    verbose: bool = False,
                    deck1_ref: Optional[str] = None,
                    deck2_ref: Optional[str] = None) -> Tuple[Optional[int], int, List[str]]:
    """Run a single game and return winner, turns, and log"""
    try:
        if deck1_ref and deck2_ref:
            rebel_deck, rebel_leader, _ = load_deck(deck1_ref)
            imperial_deck, imperial_leader, _ = load_deck(deck2_ref)
        else:
            # Create fresh sample decks for each game.
            rebel_deck, imperial_deck = create_sample_decks()
            rebel_leader = get_rebel_leader()
            imperial_leader = get_imperial_leader()
        
        # Create game
        game = GameState(rebel_deck, imperial_deck, rebel_leader, imperial_leader, verbose=verbose)
        
        # Run game
        winner = game.run_to_completion(strategy1, strategy2)
        
        turns = game.turn_count
        
        if verbose:
            print(f"  Game ended: Player {winner} wins in ~{turns} turns")
            print("  Game log:")
            for entry in game.game_log[:10]:  # Show first 10 entries
                print(f"    {entry}")
            if len(game.game_log) > 10:
                print(f"    ... and {len(game.game_log) - 10} more entries")
        
        return winner, turns, game.game_log
    
    except Exception as e:
        return None, 0, [str(e)]


def run_simulation(strategy1_name: str, strategy2_name: str, 
                   num_games: int = 100, verbose: bool = False,
                   seed: Optional[int] = None,
                   deck1_ref: Optional[str] = None,
                   deck2_ref: Optional[str] = None) -> SimulationResult:
    """Run multiple simulations between two strategies"""
    
    if seed is not None:
        random.seed(seed)
    
    strategy1 = get_strategy(strategy1_name)
    strategy2 = get_strategy(strategy2_name)
    
    result = SimulationResult()
    result.strategy1_name = strategy1_name
    result.strategy2_name = strategy2_name
    
    print(f"\n{'='*50}")
    print(f"Starting Simulation")
    print(f"{'='*50}")
    print(f"Player 1: {strategy1_name} ({deck1_ref or 'sample Rebel deck'})")
    print(f"Player 2: {strategy2_name} ({deck2_ref or 'sample Imperial deck'})")
    print(f"Games to play: {num_games}")
    print(f"{'='*50}\n")

    if deck1_ref and deck2_ref:
        warned = False
        for label, deck_ref in (("Player 1", deck1_ref), ("Player 2", deck2_ref)):
            audit = audit_deck(deck_ref)
            if audit.unsupported_count or audit.partial_count:
                warned = True
                print(
                    f"Warning: {label} deck '{audit.deck_name}' has "
                    f"{audit.unsupported_count} unsupported and "
                    f"{audit.partial_count} partially supported card copies."
                )
                print("Run `python main.py --audit-deck DECK` for details.")
        if warned:
            print()
    
    start_time = time.time()
    
    for i in range(num_games):
        if (i + 1) % max(1, num_games // 10) == 0 or i == 0:
            elapsed = time.time() - start_time
            print(f"[{i+1}/{num_games}] Playing game... ({(i+1)/num_games*100:.0f}% complete, {elapsed:.1f}s elapsed)")
        
        # Run with verbose for first game only
        show_verbose = verbose and i == 0
        winner, turns, log = run_single_game(
            strategy1,
            strategy2,
            verbose=show_verbose,
            deck1_ref=deck1_ref,
            deck2_ref=deck2_ref,
        )
        
        if winner is None and turns == 0:
            result.add_error(f"Game {i+1} had an error: {log[0] if log else 'Unknown'}")
            print(f"  ❌ Error in game {i+1}: {log[0] if log else 'Unknown'}")
        else:
            result.add_game(winner, turns)
    
    elapsed = time.time() - start_time
    print(f"\n{'='*50}")
    print(f"Simulation Complete!")
    print(f"{'='*50}")
    print(f"Total time: {elapsed:.1f} seconds")
    print(f"Average time per game: {elapsed/num_games:.2f} seconds")
    print()
    print(result.summary())
    print(f"{'='*50}\n")
    
    return result


def compare_strategies(strategy_names: List[str], num_games: int = 100) -> Dict:
    """Compare all strategies against each other"""
    
    results = {}
    
    print("=== Strategy Comparison ===")
    print(f"Testing {len(strategy_names)} strategies with {num_games} games each\n")
    
    for s1 in strategy_names:
        for s2 in strategy_names:
            if s1 == s2:
                continue
            
            key = f"{s1}_vs_{s2}"
            result = run_simulation(s1, s2, num_games)
            results[key] = result
    
    # Print summary table
    print("\n=== Win Rate Summary ===")
    print(f"{'Strategy':<15} vs {'Opponent':<15} {'Win %':<10}")
    print("-" * 45)
    
    for key, result in results.items():
        parts = key.split("_vs_")
        print(f"{parts[0]:<15} vs {parts[1]:<15} {result.player1_win_rate:.1%}")
    
    return results


def run_tournament(strategy_names: List[str], games_per_match: int = 50) -> Dict:
    """Run a round-robin tournament"""
    
    standings = {name: {"wins": 0, "losses": 0, "games": 0} for name in strategy_names}
    
    print("=== Tournament Standings ===\n")
    
    for s1 in strategy_names:
        for s2 in strategy_names:
            if s1 >= s2:
                continue
            
            print(f"Match: {s1} vs {s2}")
            result = run_simulation(s1, s2, games_per_match)
            
            standings[s1]["wins"] += result.player1_wins
            standings[s1]["losses"] += result.player2_wins
            standings[s1]["games"] += result.total_games
            
            standings[s2]["wins"] += result.player2_wins
            standings[s2]["losses"] += result.player1_wins
            standings[s2]["games"] += result.total_games
    
    # Sort by win rate
    sorted_standings = sorted(
        standings.items(), 
        key=lambda x: x[1]["wins"] / max(1, x[1]["games"]),
        reverse=True
    )
    
    print("\n=== Final Standings ===")
    print(f"{'Rank':<5} {'Strategy':<15} {'Wins':<8} {'Losses':<8} {'Win %':<10}")
    print("-" * 50)
    
    for i, (name, stats) in enumerate(sorted_standings, 1):
        win_rate = stats["wins"] / max(1, stats["games"])
        print(f"{i:<5} {name:<15} {stats['wins']:<8} {stats['losses']:<8} {win_rate:.1%}")
    
    return standings


def analyze_strategy_performance(strategy_name: str, opponents: List[str], 
                                  num_games: int = 100) -> Dict:
    """Analyze how a strategy performs against different opponents"""
    
    results = {}
    
    print(f"Analyzing {strategy_name} vs each opponent ({num_games} games each)\n")
    
    for opponent in opponents:
        result = run_simulation(strategy_name, opponent, num_games)
        results[opponent] = {
            "win_rate": result.player1_win_rate,
            "avg_turns": result.avg_turns,
            "wins": result.player1_wins,
            "losses": result.player2_wins
        }
    
    # Summary
    print(f"\n=== {strategy_name} Performance Summary ===")
    print(f"{'Opponent':<15} {'Win %':<10} {'Avg Turns':<12} {'Record':<10}")
    print("-" * 50)
    
    for opp, stats in results.items():
        record = f"{stats['wins']}-{stats['losses']}"
        print(f"{opp:<15} {stats['win_rate']:.1%}     {stats['avg_turns']:.1f}          {record}")
    
    return results


def quick_test():
    """Quick test run with 10 games"""
    print("=== Quick Test (10 games) ===\n")
    return run_simulation("aggressive", "control", num_games=10)


if __name__ == "__main__":
    # Run quick test
    quick_test()
