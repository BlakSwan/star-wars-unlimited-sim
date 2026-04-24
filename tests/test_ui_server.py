from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sw_unlimited_sim"))

from effect_training import blank_effect_record  # noqa: E402
from ui_server import approval_blockers, approve_batch_records  # noqa: E402


class UIServerTests(unittest.TestCase):
    def test_approval_blockers_reject_self_unit_mismatch(self):
        card = {
            "Set": "JTL",
            "Number": "248",
            "Name": "Dilapidated Ski Speeder",
            "FrontText": "When Played: Deal 3 damage to this unit.",
        }
        record = blank_effect_record(card)
        record["status"] = "approved"
        record["execution_status"] = "executable"
        record["triggers"] = [
            {
                "event": "when_played",
                "conditions": [],
                "steps": [
                    {
                        "type": "deal_damage",
                        "amount": 3,
                        "duration": "instant",
                        "optional": False,
                        "target": {"controller": "enemy", "type": "unit"},
                    }
                ],
            }
        ]

        blockers = approval_blockers(record)

        self.assertTrue(any("this unit" in blocker.lower() for blocker in blockers))

    def test_batch_approve_only_promotes_unblocked_drafts(self):
        clean_card = {
            "Set": "TWI",
            "Number": "107",
            "Name": "Patrolling V-Wing",
            "FrontText": "When Played: Draw a card.",
        }
        blocked_card = {
            "Set": "JTL",
            "Number": "248",
            "Name": "Dilapidated Ski Speeder",
            "FrontText": "When Played: Deal 3 damage to this unit.",
        }
        clean_record = blank_effect_record(clean_card)
        clean_record["status"] = "draft"
        clean_record["execution_status"] = "executable"
        clean_record["triggers"] = [
            {
                "event": "when_played",
                "conditions": [],
                "steps": [
                    {
                        "type": "draw_cards",
                        "amount": 1,
                        "duration": "instant",
                        "optional": False,
                        "target": {"controller": "friendly", "type": "player"},
                    }
                ],
            }
        ]

        blocked_record = blank_effect_record(blocked_card)
        blocked_record["status"] = "draft"
        blocked_record["execution_status"] = "executable"
        blocked_record["triggers"] = [
            {
                "event": "when_played",
                "conditions": [],
                "steps": [
                    {
                        "type": "deal_damage",
                        "amount": 3,
                        "duration": "instant",
                        "optional": False,
                        "target": {"controller": "enemy", "type": "unit"},
                    }
                ],
            }
        ]

        effects = {
            "TWI-107": clean_record,
            "JTL-248": blocked_record,
        }
        saved_records: list[dict] = []

        with mock.patch("ui_server.load_effects", return_value=effects), \
             mock.patch("ui_server.save_draft_artifact") as archive_mock, \
             mock.patch("ui_server.save_effect", side_effect=lambda record: saved_records.append(record)):
            result = approve_batch_records(["TWI-107", "JTL-248", "MISSING-001"])

        self.assertEqual(result["approved"], ["TWI-107"])
        self.assertIn("JTL-248", result["blocked"])
        self.assertEqual(result["missing"], ["MISSING-001"])
        self.assertEqual(len(saved_records), 1)
        self.assertEqual(saved_records[0]["status"], "approved")
        self.assertTrue(saved_records[0]["review"]["human_verified"])
        archive_mock.assert_called_once()

    def test_approval_blockers_reject_attached_unit_without_attached_filter(self):
        card = {
            "Set": "LAW",
            "Number": "127",
            "Name": "Kill Switch",
            "Type": "Upgrade",
            "FrontText": "When Played: Exhaust attached unit.",
        }
        record = blank_effect_record(card)
        record["status"] = "approved"
        record["execution_status"] = "executable"
        record["triggers"] = [
            {
                "event": "when_played",
                "conditions": [],
                "steps": [
                    {
                        "type": "exhaust_unit",
                        "amount": 1,
                        "duration": "instant",
                        "optional": False,
                        "target": {"controller": "self", "type": "unit"},
                    }
                ],
            }
        ]

        blockers = approval_blockers(record)

        self.assertTrue(any("attached_unit" in blocker for blocker in blockers))

    def test_approval_blockers_reject_all_ground_units_single_target_record(self):
        card = {
            "Set": "SOR",
            "Number": "039",
            "Name": "AT-AT Suppressor",
            "Type": "Unit",
            "FrontText": "When Played: Exhaust all ground units.",
        }
        record = blank_effect_record(card)
        record["status"] = "approved"
        record["execution_status"] = "executable"
        record["triggers"] = [
            {
                "event": "when_played",
                "conditions": [],
                "steps": [
                    {
                        "type": "exhaust_unit",
                        "amount": 1,
                        "duration": "instant",
                        "optional": False,
                        "target": {"controller": "any", "type": "unit", "filter": "ground"},
                    }
                ],
            }
        ]

        blockers = approval_blockers(record)

        self.assertTrue(any("all units in an arena" in blocker.lower() for blocker in blockers))


if __name__ == "__main__":
    unittest.main()
