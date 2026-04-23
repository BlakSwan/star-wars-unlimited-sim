from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sw_unlimited_sim"))

from deck_loader import available_decks, load_deck  # noqa: E402
from simulator import run_single_game  # noqa: E402
from strategies import get_strategy  # noqa: E402


class PilotingDeckSmokeTests(unittest.TestCase):
    def test_vehicle_piloting_test_deck_loads(self):
        self.assertIn("vehicle_piloting_test", available_decks())
        deck, leader, metadata = load_deck("vehicle_piloting_test")

        self.assertEqual(metadata["name"], "Vehicle Piloting Test")
        self.assertEqual(leader.name, "Wedge Antilles")
        self.assertGreaterEqual(len(deck), 50)

    def test_vehicle_piloting_test_deck_produces_piloting_actions(self):
        found_piloting = False
        for seed in range(1, 8):
            random.seed(seed)
            _, turns, log = run_single_game(
                get_strategy("aggressive"),
                get_strategy("random"),
                deck1_ref="vehicle_piloting_test",
                deck2_ref="vehicle_piloting_test",
            )
            self.assertGreater(turns, 0)
            if any(" as a Pilot on " in line for line in log):
                found_piloting = True
                break

        self.assertTrue(found_piloting, "Expected at least one game to play a card using Piloting")


if __name__ == "__main__":
    unittest.main()
