from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sw_unlimited_sim"))

from deck_loader import available_decks, load_deck  # noqa: E402
from effect_audit import audit_deck, format_deck_audit  # noqa: E402
from simulator import run_single_game  # noqa: E402
from strategies import get_strategy  # noqa: E402


SUPPORTED_PILOTING_DECKS = [
    "rebel_piloting_fighters",
    "rebel_piloting_transports",
]


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

    def test_vehicle_piloting_audit_lists_piloting_support(self):
        audit = audit_deck("vehicle_piloting_test")
        output = format_deck_audit(audit, show_supported=True)

        self.assertIn("Piloting support by copies:", output)
        self.assertIn("Piloting support by unique cards:", output)
        self.assertIn("Piloting Support", output)
        self.assertIn("JTL 197 Anakin Skywalker [partial]", output)
        self.assertIn("JTL 196 Dagger Squadron Pilot [unsupported]", output)
        self.assertGreater(audit.piloting_counts_by_status["partial"], 0)
        self.assertGreater(audit.piloting_counts_by_status["unsupported"], 0)

    def test_supported_piloting_decks_load_and_audit_cleanly(self):
        for deck_name in SUPPORTED_PILOTING_DECKS:
            with self.subTest(deck=deck_name):
                self.assertIn(deck_name, available_decks())
                deck, _, metadata = load_deck(deck_name)
                audit = audit_deck(deck_name)

                self.assertEqual(50, metadata["card_count"])
                self.assertEqual(50, len(deck))
                self.assertTrue(audit.is_valid_tournament_shape)
                self.assertEqual(0, audit.counts_by_status["unsupported"])
                self.assertGreater(audit.piloting_counts_by_status["partial"], 0)
                self.assertEqual(0, audit.piloting_counts_by_status["unsupported"])


if __name__ == "__main__":
    unittest.main()
