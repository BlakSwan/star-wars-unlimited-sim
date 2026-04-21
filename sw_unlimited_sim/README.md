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
| `python main.py --analyze-cards` | Analyze card database mechanics and support coverage |
| `python main.py --fetch-cards` | Download SWU DB card data |
| `python main.py --filter-gameplay-cards` | Remove cosmetic card variants from fetched data |
| `python main.py --ui` | Start the local browser UI |

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
├── effect_store.py # Human-reviewed structured card effect storage
├── ui_server.py   # Local browser UI
├── strategies.py  # AI player strategies
├── simulator.py   # Simulation runner
├── main.py        # CLI entry point
├── data/decks/    # Bundled decklists
├── data/effects/  # Human-reviewed effect records
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

Analyze the full card database to prioritize rules work:

```bash
python main.py --analyze-cards
```

Start the local UI for non-coder workflows:

```bash
python main.py --ui
```

Then open `http://127.0.0.1:8765` in a browser. Use `--ui-port PORT` if
that port is already taken.

The UI includes:

- Dashboard metrics for deck count, strategy count, approved effects, and card
  support coverage
- Deck audit forms for tournament shape and unsupported effect checks
- Simulation forms for choosing both decks, both strategies, and game count
- Optional per-game simulation logs showing opening hands, cards drawn, resource
  choices, plays, attacks, and passes. Detailed log mode is capped at 50 games
  to keep the browser responsive.
- Full-card database coverage analysis
- Human-in-the-loop effect training with a guided form for common effects and
  an advanced JSON editor for complex cards. Effects saved with `approved`
  status are loaded and executed by the simulator.

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
- Human-approved structured effects for When Played, On Attack, When Defeated,
  and action triggers. Supported guided effect steps include damage, healing,
  draw, discard, exhaust, ready, defeat, shield, and experience tokens.

## Notes

- Uses sample cards from the Spark of Rebellion set
- Card effects are implemented as a growing supported subset, not a complete
  parser for every SWU card text
- Capture effects can be recorded in the training UI, but capture zones are not
  executed yet
- Run thousands of games for statistically significant results
