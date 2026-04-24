from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sw_unlimited_sim"))

from effect_training import blank_effect_record  # noqa: E402
from ui_server import approval_blockers, approve_batch_records, batch_draft_safe, batch_review_page, training_queue_page  # noqa: E402


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

    def test_batch_review_page_renders_safe_list_section(self):
        review_item = {
            "key": "LAW-107",
            "record": {"set": "LAW", "number": "107"},
            "card": {"Set": "LAW", "Number": "107"},
            "name": "Swoop Bike Marauder",
            "type": "Unit",
            "bucket": "on_attack",
            "triage": "safe_draft",
            "runtime": "executable",
            "approval_state": "approvable",
            "parse_warning_count": 0,
            "blockers": [],
        }
        safe_item = {
            "key": "TWI-107",
            "title": "Patrolling V-Wing",
            "type": "Unit",
            "bucket": "when_played",
            "words": 4,
            "text": "When Played: Draw a card.",
            "training_status": "missing",
            "card": {
                "Set": "TWI",
                "Number": "107",
                "Name": "Patrolling V-Wing",
                "Type": "Unit",
            },
        }

        with mock.patch("ui_server._load_card_index", return_value={}), \
             mock.patch("ui_server.batch_review_records", return_value=([review_item], {"total": 1}, [("on_attack", 1, 1)])), \
             mock.patch("ui_server.safe_list_items", return_value=[safe_item]):
            html = batch_review_page({}).decode("utf-8")

        self.assertIn("Safe List Generation", html)
        self.assertIn("Configured Local Draft", html)
        self.assertIn("Patrolling V-Wing", html)
        self.assertIn("/train/suggest?card=TWI-107&provider=local", html)
        self.assertIn("Filter Visible Rows", html)
        self.assertIn("Select all shown", html)
        self.assertIn("batch-review-row", html)
        self.assertIn("Swoop Bike Marauder", html)
        self.assertIn("Process Safe List With Configured Local LLM", html)

    def test_batch_draft_safe_processes_current_safe_list(self):
        card = {
            "Set": "TWI",
            "Number": "107",
            "Name": "Patrolling V-Wing",
            "Type": "Unit",
            "FrontText": "When Played: Draw a card.",
        }
        existing = blank_effect_record(card)
        existing["status"] = "draft"
        existing["review"]["notes"] = "old draft"
        new_record = blank_effect_record(card)
        new_record["status"] = "draft"
        new_record["source"] = "local_llm"
        new_record["execution_status"] = "executable"
        new_record["review"]["triage"] = "safe_draft"
        new_record["review"]["notes"] = "new draft"

        class FakeProvider:
            def suggest_effect(self, requested_card):
                self.requested_card = requested_card
                return new_record

        provider = FakeProvider()
        saved_records: list[dict] = []

        with mock.patch("ui_server.safe_list_items", return_value=[{"key": "TWI-107", "card": card}]), \
             mock.patch("ui_server.get_effect_suggestion_provider", return_value=provider), \
             mock.patch("ui_server.get_effect", return_value=existing), \
             mock.patch("ui_server.save_draft_artifact") as archive_mock, \
             mock.patch("ui_server.save_effect", side_effect=lambda record: saved_records.append(record)):
            html = batch_draft_safe("safe_limit=1&safe_max_words=10&safe_only_missing=1").decode("utf-8")

        self.assertEqual(provider.requested_card, card)
        self.assertEqual(saved_records, [new_record])
        archive_mock.assert_called_once()
        self.assertIn("Safe List Drafting Complete", html)
        self.assertIn("TWI-107", html)
        self.assertIn("safe_draft", html)

    def test_training_queue_page_renders_training_filter(self):
        queue_item = {
            "key": "TWI-107",
            "card": {
                "Set": "TWI",
                "Number": "107",
                "Name": "Patrolling V-Wing",
                "Type": "Unit",
            },
            "audit": mock.Mock(status="unsupported", reasons=["stub reason"]),
            "training_status": "missing",
            "deck_count": 0,
            "competitive_main_count": 0,
            "competitive_sideboard_count": 0,
            "competitive_deck_count": 0,
            "patterns": [],
            "priority": (0, 0, 0, 0, 0),
        }

        with mock.patch("ui_server._load_card_index", return_value={}), \
             mock.patch("ui_server.official_filter_values", return_value={"sets": [], "types": [], "aspects": [], "traits": [], "arenas": [], "keywords": [], "rarities": []}), \
             mock.patch("ui_server.training_queue_items_filtered", return_value=[queue_item]), \
             mock.patch("ui_server.load_competitive_decks", return_value={"deck_count": 0}):
            html = training_queue_page({"training": ["draft"]}).decode("utf-8")

        self.assertIn("name=\"training\"", html)
        self.assertIn("value=\"draft\" selected", html)
        self.assertIn("Patrolling V-Wing", html)


if __name__ == "__main__":
    unittest.main()
