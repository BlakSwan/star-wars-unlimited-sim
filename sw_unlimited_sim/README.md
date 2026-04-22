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
| `python main.py --fetch-competitive-decks` | Cache top hot SWUDB deck usage for training priority |
| `python main.py --test-local-provider` | Check Ollama or MLX setup for local card-effect drafting |
| `python main.py --draft-card SET NUMBER` | Draft one card effect with a local model |
| `python main.py --draft-missing-cards` | Bulk-draft missing effect records with a local model |

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

Fetch hot competitive deck usage from SWUDB:

```bash
python main.py --fetch-competitive-decks --competitive-limit 20
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
- Simulation stats window with win rates, turn length, initiative conversion,
  per-game draw/play/attack/resource averages, base pressure, and most-played
  cards
- Optional per-game simulation logs showing opening hands, cards drawn, resource
  choices, plays, attacks, and passes. Detailed log mode is capped at 50 games
  to keep the browser responsive.
- Full-card database coverage analysis
- Unsupported-card training queue that ranks cards needing simulator support,
  shows bundled deck usage, hot SWUDB deck usage, unsupported text patterns,
  audit status, training status, and links directly to Train or Draft actions
- Human-in-the-loop effect training with a guided form for common effects and
  an advanced JSON editor for complex cards. Effects saved with `approved`
  status are loaded and executed by the simulator.
- Complex effect training with multiple steps, conditions, target filters,
  durations, optional effects, reviewer confidence, and explicit engine
  execution status.
- Draft generation boundary for future LLM-assisted unsupported-card training.
  The current offline provider creates manual review drafts from rules text
  heuristics; it does not call an external model.
- Optional OpenAI draft provider for LLM-assisted card training. Set
  `OPENAI_API_KEY` and optionally `SWU_LLM_MODEL`; LLM drafts are saved as
  manual review records and never execute until approved and marked executable.
- Optional local-model draft provider for Ollama or MLX. Local drafts are
  normalized into the same schema, triaged as `safe_draft`, `needs_review`, or
  `unresolved`, and kept in the existing human-review flow.

Local LLM settings are read from shell environment variables or an untracked
`.env` file at the repository root:

```bash
cp .env.example .env
# edit .env and set OPENAI_API_KEY
```

Do not commit real API keys.

## Local Model Drafting

Local-model drafting reduces the amount of manual annotation needed for
unsupported cards. The model creates a draft record, then deterministic
normalization checks triggers, step types, targets, durations, conditions, and
engine execution status. The browser review workflow remains the authority:
drafts do not affect simulations unless they are approved and executable.

### Ollama

Install and start Ollama, then pull a model:

```bash
ollama pull qwen2.5:7b-instruct
```

Add local settings to `.env` or your shell:

```bash
SWU_LOCAL_PROVIDER=ollama
SWU_LOCAL_MODEL=qwen2.5:7b-instruct
SWU_LOCAL_HOST=http://127.0.0.1:11434
SWU_LOCAL_TIMEOUT=60
```

Check setup without drafting a card:

```bash
python main.py --test-local-provider
```

Draft one card:

```bash
python main.py --draft-card SOR 128
```

Bulk-draft missing cards, optionally limited to specific sets:

```bash
python main.py --draft-missing-cards --sets SOR SHD --limit 50
```

By default, bulk drafting skips existing records and never approves drafts.
Use `--overwrite-drafts` only when replacing previous draft records. The
`--approve-safe-drafts` flag exists for experiments, but normal tournament
prep should review drafts in the UI before approval.

### MLX

MLX support is optional and isolated so the simulator still runs without MLX
packages installed. On Apple Silicon, install the runtime and point the
provider at a local model path or Hugging Face model name supported by
`mlx-lm`:

```bash
pip install mlx-lm
SWU_LOCAL_PROVIDER=mlx
SWU_LOCAL_MODEL=mlx-community/Qwen2.5-7B-Instruct-4bit
python main.py --test-local-provider
```

The first MLX path is text-generation only. The backend is structured so vision
support can be added later without changing the UI, store, or training schema.

### Browser Review

Start the UI with:

```bash
python main.py --ui
```

On the Train Effects tab, use `Draft With Local Model`. The saved draft shows
its source, triage bucket, and parse warnings. On the Training Queue tab, use
`Local Draft` to create a draft for a queued card, then review and approve it
only if the structured effect matches the card text and the engine execution
status is appropriate.

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
- Trained effect records marked `execution_status: executable` can affect games.
  More complex records can be stored as `partial` or `manual` until the engine
  supports their conditions, choices, target filters, or durations.

## Notes

- Uses sample cards from the Spark of Rebellion set
- Card effects are implemented as a growing supported subset, not a complete
  parser for every SWU card text
- Capture effects can be recorded in the training UI, but capture zones are not
  executed yet
- Run thousands of games for statistically significant results
