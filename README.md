# Star Wars Unlimited Simulator

A Python simulator and training lab for experimenting with Star Wars: Unlimited decks, strategies, and card-effect support.

The main project documentation lives here:

[sw_unlimited_sim/README.md](sw_unlimited_sim/README.md)

## Quick Start

```bash
cd sw_unlimited_sim
python main.py --test
```

Start the local browser UI:

```bash
cd sw_unlimited_sim
python main.py --ui
```

Then open `http://127.0.0.1:8765`.

## Current Focus

The simulator supports a growing subset of gameplay mechanics, plus a human-review workflow for training structured card effects. Recent work added local LLM drafting, upgrade attachment cleanup, and Piloting support.
