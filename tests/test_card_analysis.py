from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sw_unlimited_sim"))

from card_analysis import analyze_card_database  # noqa: E402


class CardAnalysisTests(unittest.TestCase):
    def test_approved_executable_effect_counts_as_supported(self):
        cards_payload = {
            "cards": [
                {
                    "Set": "TST",
                    "Number": "001",
                    "Name": "Training Target",
                    "Type": "Unit",
                    "FrontText": "When Played: Draw a card.",
                    "Keywords": [],
                }
            ]
        }
        trained_effects = {
            "TST-001": {
                "set": "TST",
                "number": "001",
                "name": "Training Target",
                "status": "approved",
                "execution_status": "executable",
                "triggers": [
                    {
                        "event": "when_played",
                        "conditions": [],
                        "steps": [
                            {
                                "type": "draw_cards",
                                "amount": 1,
                                "duration": "instant",
                                "target": {"controller": "friendly", "type": "player"},
                            }
                        ],
                    }
                ],
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            cards_path = Path(tmpdir) / "cards.json"
            cards_path.write_text(json.dumps(cards_payload), encoding="utf-8")

            analysis = analyze_card_database(cards_path, trained_effects=trained_effects)

        self.assertEqual(analysis["support_counts"].get("supported"), 1)
        self.assertEqual(analysis["support_counts"].get("unsupported", 0), 0)


if __name__ == "__main__":
    unittest.main()
