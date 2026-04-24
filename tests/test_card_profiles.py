from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sw_unlimited_sim"))

from card_profiles import compact_profile_payload, compile_card_profile  # noqa: E402
from deck_loader import base_from_data, card_from_data, leader_from_data  # noqa: E402
from engine import GameState  # noqa: E402
from effect_store import effect_key  # noqa: E402
from models import Base, CardProfile, LeaderCard  # noqa: E402


UNIT_CARD_DATA = {
    "Set": "TST",
    "Number": "010",
    "Name": "Profiled Trooper",
    "Type": "Unit",
    "Cost": 2,
    "Power": 2,
    "HP": 3,
    "Arenas": ["Ground"],
    "Traits": ["TROOPER"],
    "Aspects": ["Command"],
    "Keywords": ["Sentinel"],
    "FrontText": "When Played: Deal 2 damage to an enemy unit.",
}

LEADER_CARD_DATA = {
    "Set": "TST",
    "Number": "001",
    "Name": "Profiled Leader",
    "Type": "Leader",
    "Arenas": ["Ground"],
    "Cost": 5,
    "Power": 3,
    "HP": 6,
    "Traits": ["JEDI"],
    "Aspects": ["Heroism"],
    "FrontText": "Action [C=1, Exhaust]: Heal 1 damage from a friendly unit.",
    "EpicAction": "Deploy as 3/6 unit",
}

BASE_CARD_DATA = {
    "Set": "TST",
    "Number": "020",
    "Name": "Profiled Base",
    "Type": "Base",
    "HP": 30,
    "Subtitle": "Test World",
    "Aspects": ["Command"],
    "FrontText": "Epic Action: Test something base-shaped.",
}

APPROVED_EFFECT = {
    "set": "TST",
    "number": "010",
    "name": "Profiled Trooper",
    "status": "approved",
    "execution_status": "executable",
    "review": {"llm_suggested": True, "human_verified": True},
    "triggers": [
        {
            "event": "when_played",
            "conditions": [],
            "steps": [
                {
                    "type": "deal_damage",
                    "amount": 2,
                    "duration": "instant",
                    "target": {"controller": "enemy", "type": "unit"},
                }
            ],
        }
    ],
}


class CardProfileTests(unittest.TestCase):
    def test_compile_card_profile_captures_rules_metadata(self):
        profile = compile_card_profile(UNIT_CARD_DATA, APPROVED_EFFECT)

        self.assertIsInstance(profile, CardProfile)
        self.assertEqual(profile.set_code, "TST")
        self.assertEqual(profile.number, "010")
        self.assertIn("When Played", profile.mechanic_tags)
        self.assertIn("Sentinel", profile.mechanic_tags)
        self.assertTrue(profile.llm_augmented)
        self.assertEqual(profile.effect_execution_status, "executable")
        self.assertEqual(profile.effect_validation["execution_analysis"]["status"], "executable")

    def test_card_from_data_attaches_compiled_profile(self):
        card = card_from_data(UNIT_CARD_DATA, copy_index=1, effect_record=APPROVED_EFFECT)

        self.assertEqual(card.profile.set_code, "TST")
        self.assertEqual(card.profile.number, "010")
        self.assertEqual(card.profile.card_type, "Unit")
        self.assertEqual(card.profile.effect_record["status"], "approved")
        self.assertEqual(card.profile.effect_validation["execution_analysis"]["status"], "executable")

    def test_compact_profile_payload_is_token_efficient(self):
        profile = compile_card_profile(UNIT_CARD_DATA, APPROVED_EFFECT)

        payload = compact_profile_payload(UNIT_CARD_DATA, profile, copy_count=3)

        self.assertEqual(payload["card_ref"], "TST-010")
        self.assertEqual(payload["count"], 3)
        self.assertEqual(payload["effect_execution_status"], "executable")
        self.assertEqual(payload["effect_validation_status"], "executable")
        self.assertNotIn("source_fields", payload)

    def test_leader_from_data_attaches_profile(self):
        leader = leader_from_data(LEADER_CARD_DATA)

        self.assertEqual(leader.profile.set_code, "TST")
        self.assertEqual(leader.profile.number, "001")
        self.assertEqual(leader.profile.card_type, "Leader")
        self.assertIn("Action", leader.profile.mechanic_tags)
        self.assertEqual(leader.action_cost, 1)
        self.assertEqual(leader.deployed_arena.name, "GROUND")

    def test_leader_from_data_preserves_space_deploy_arena(self):
        leader_data = dict(LEADER_CARD_DATA, Arenas=["Space"])

        leader = leader_from_data(leader_data)

        self.assertEqual(leader.deployed_arena.name, "SPACE")

    def test_base_from_data_uses_printed_hp_and_profile(self):
        base = base_from_data(BASE_CARD_DATA)

        self.assertIsInstance(base, Base)
        self.assertEqual(base.name, "Profiled Base")
        self.assertEqual(base.hp, 30)
        self.assertEqual(base.current_hp, 30)
        self.assertEqual(base.profile.card_type, "Base")

    def test_game_prefers_effect_record_embedded_in_card_profile(self):
        card = card_from_data(UNIT_CARD_DATA, copy_index=1, effect_record=APPROVED_EFFECT)
        game = GameState(
            player1_deck=[],
            player2_deck=[],
            player1_leader=LeaderCard("LDR_001", "Leader One", 6, epic_action_effect="Deploy as 4/4 unit"),
            player2_leader=LeaderCard("LDR_002", "Leader Two", 6, epic_action_effect="Deploy as 4/4 unit"),
            verbose=False,
        )
        game.card_effects = {}

        record = game._card_effect_record(card)

        self.assertEqual(effect_key("TST", "010"), game._card_effect_key(card))
        self.assertIs(record, card.profile.effect_record)

    def test_game_state_uses_selected_base_hp(self):
        base = base_from_data(BASE_CARD_DATA)
        game = GameState(
            player1_deck=[],
            player2_deck=[],
            player1_leader=LeaderCard("LDR_001", "Leader One", 6, epic_action_effect="Deploy as 4/4 unit"),
            player2_leader=LeaderCard("LDR_002", "Leader Two", 6, epic_action_effect="Deploy as 4/4 unit"),
            verbose=False,
            player1_base=base,
        )

        self.assertEqual(game.player1.base.name, "Profiled Base")
        self.assertEqual(game.player1.base.hp, 30)


if __name__ == "__main__":
    unittest.main()
