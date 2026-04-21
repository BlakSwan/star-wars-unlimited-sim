# Star Wars Unlimited Simulator

A statistical simulator for the Star Wars: Unlimited card game to analyze strategies and win rates.

## Quick Start

```bash
cd sw_unlimited_sim
python main.py --test
```

## Available Commands

| Command | Description |
|---------|-------------|
| `python main.py --list` | List available strategies |
| `python main.py --test` | Quick test (10 games) |
| `python main.py --sim STRAT1 STRAT2 N` | Simulate strat1 vs strat2 for N games |
| `python main.py --compare` | Compare all strategies (50 games each) |
| `python main.py --tournament` | Round-robin tournament |
| `python main.py --analyze STRAT` | Analyze strategy against all opponents |
| `python main.py --list-decks` | List bundled JSON decklists |
| `python main.py --sim STRAT1 STRAT2 N --deck1 DECK --deck2 DECK` | Simulate with explicit decklists |
| `python main.py --audit-deck DECK` | Report unsupported card effects for a decklist |
| `python main.py --fetch-cards` | Download SWU DB card data |
| `python main.py --filter-gameplay-cards` | Remove cosmetic card variants from fetched data |

## Available Strategies

- **random** - Random legal actions
- **aggressive** - Prioritize attacks and playing units
- **control** - Prioritize card advantage and removal
- **balanced** - Mix of aggression and control
- **greedy** - Maximize immediate value
- **economic** - Prioritize resource management

## Project Structure

```
sw_unlimited_sim/
├── models.py      # Card and game state classes
├── engine.py      # Game logic and rules
├── cards.py       # Sample card database
├── deck_loader.py # JSON decklist loader backed by SWU DB data
├── strategies.py  # AI player strategies
├── simulator.py   # Simulation runner
├── main.py        # CLI entry point
├── data/decks/    # Bundled decklists
└── README.md      # This file
```

## Decklists

Bundled decks can be listed with:

```bash
python main.py --list-decks
```

Run a simulation with explicit decks:

```bash
python main.py --sim aggressive control 100 --deck1 rebel_heroism --deck2 imperial_villainy
```

Use the 50-card tournament-shaped starter lists:

```bash
python main.py --sim aggressive aggressive 100 --deck1 rebel_heroism_50 --deck2 imperial_villainy_50
```

Audit effect support before trusting tournament results:

```bash
python main.py --audit-deck rebel_heroism
```

Deck JSON files reference SWU DB gameplay cards by set and card number:

```json
{
  "name": "Example Deck",
  "leader": {"set": "SOR", "number": "014"},
  "cards": [
    {"set": "SOR", "number": "140", "count": 3}
  ]
}
```

## Game Rules Implemented

- Action phase (play cards, attack, use abilities, take initiative, pass)
- Regroup phase (draw 2 cards, resource a card, ready all)
- Combat (simultaneous damage, ambush, sentinel, saboteur, raid, overwhelm)
- Resource management
- Win condition (destroy opponent's base)
- A focused set of card effects used by bundled decks, including selected
  When Played, On Attack, When Defeated, leader action, and event effects

## Notes

- Uses sample cards from the Spark of Rebellion set
- Card effects are implemented as a growing supported subset, not a complete
  parser for every SWU card text
- Run thousands of games for statistically significant results
