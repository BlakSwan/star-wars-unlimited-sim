from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sw_unlimited_sim"))

from effect_store import effect_key  # noqa: E402
from effect_training import execution_status_for_record  # noqa: E402
from engine import GameState  # noqa: E402
from models import Arena, LeaderCard, Resource, UnitCard, UpgradeCard  # noqa: E402


def game_state() -> GameState:
    return GameState(
        player1_deck=[],
        player2_deck=[],
        player1_leader=LeaderCard("LDR_001", "Leader One", 6, epic_action_effect="Deploy as 4/4 unit"),
        player2_leader=LeaderCard("LDR_002", "Leader Two", 6, epic_action_effect="Deploy as 4/4 unit"),
        verbose=False,
    )


def unit(name: str = "Test Unit") -> UnitCard:
    return UnitCard("TST_001_1", name, 2, power=2, hp=3, arena=Arena.GROUND)


class EngineUpgradeTests(unittest.TestCase):
    def test_played_upgrade_tracks_attachment_and_printed_stats(self):
        game = game_state()
        target = unit()
        upgrade = UpgradeCard("TST_100_1", "Training Blade", 1, power_bonus=1, hp_bonus=1)
        game.player1.units.append(target)
        game.player1.ground_arena.append(target)

        self.assertTrue(game._play_upgrade(game.player1, upgrade))

        self.assertIs(upgrade.attached_to, target)
        self.assertIn(upgrade, target.attached_upgrades)
        self.assertEqual(target.power, 3)
        self.assertEqual(target.hp, 4)
        self.assertEqual(target.current_hp, 4)

    def test_attached_upgrades_are_discarded_when_unit_leaves_play(self):
        game = game_state()
        target = unit()
        upgrade = UpgradeCard("TST_100_1", "Training Blade", 1, power_bonus=1, hp_bonus=1)
        game.player1.units.append(target)
        game.player1.ground_arena.append(target)
        game._play_upgrade(game.player1, upgrade)

        game._return_unit_to_hand(game.player1, target, "Test Return")

        self.assertIsNone(upgrade.attached_to)
        self.assertIn(upgrade, game.player1.discard_pile)
        self.assertEqual(target.attached_upgrades, [])
        self.assertEqual(target.power, 2)
        self.assertEqual(target.hp, 3)
        self.assertEqual(target.current_hp, 3)

    def test_while_attached_modify_stats_executes_and_cleans_up(self):
        game = game_state()
        target = unit()
        upgrade = UpgradeCard("TST_200_1", "Trained Modifier", 1)
        game.player1.units.append(target)
        game.player1.ground_arena.append(target)
        record = {
            "status": "approved",
            "execution_status": "executable",
            "triggers": [
                {
                    "event": "when_played",
                    "conditions": [],
                    "steps": [
                        {
                            "type": "modify_stats",
                            "power": 2,
                            "hp": 1,
                            "duration": "while_attached",
                            "target": {"controller": "friendly", "type": "unit"},
                        }
                    ],
                }
            ],
        }
        game.card_effects = {effect_key("TST", "200"): record}

        self.assertEqual(execution_status_for_record(record), "executable")
        self.assertTrue(game._play_upgrade(game.player1, upgrade))
        self.assertEqual(target.power, 4)
        self.assertEqual(target.hp, 4)
        self.assertEqual(target.current_hp, 4)

        game._return_unit_to_hand(game.player1, target, "Test Return")

        self.assertIsNone(upgrade.attached_to)
        self.assertEqual(target.power, 2)
        self.assertEqual(target.hp, 3)
        self.assertEqual(target.current_hp, 3)

    def test_piloting_card_can_be_played_as_upgrade_on_vehicle(self):
        game = game_state()
        vehicle = unit("Alliance Shuttle")
        vehicle.traits = ["VEHICLE", "TRANSPORT"]
        pilot = UnitCard(
            "JTL_999_1",
            "Test Pilot",
            4,
            power=2,
            hp=3,
            arena=Arena.GROUND,
            traits=["PILOT"],
            abilities=["Piloting [C=2 Heroism] (You may play this as an upgrade on a friendly Vehicle without a Pilot.)"],
        )
        game.player1.units.append(vehicle)
        game.player1.ground_arena.append(vehicle)
        game.player1.hand.append(pilot)
        game.player1.resources = [
            Resource(CardStub("R1")),
            Resource(CardStub("R2")),
        ]

        actions = game.get_legal_actions(game.player1)
        self.assertIn("pilot_JTL_999_1", actions)
        self.assertTrue(game.execute_action(game.player1, "pilot_JTL_999_1"))

        self.assertNotIn(pilot, game.player1.hand)
        self.assertIs(pilot.attached_to, vehicle)
        self.assertTrue(pilot.played_as_pilot)
        self.assertIn(pilot, vehicle.attached_upgrades)
        self.assertEqual(vehicle.power, 4)
        self.assertEqual(vehicle.hp, 6)
        self.assertEqual(vehicle.current_hp, 6)

    def test_vehicle_with_pilot_cannot_take_second_pilot(self):
        game = game_state()
        vehicle = unit("Alliance Shuttle")
        vehicle.traits = ["VEHICLE"]
        first_pilot = UnitCard("JTL_999_1", "First Pilot", 2, 1, 1, Arena.GROUND, traits=["PILOT"])
        first_pilot.played_as_pilot = True
        vehicle.attached_upgrades.append(first_pilot)
        second_pilot = UnitCard(
            "JTL_998_1",
            "Second Pilot",
            2,
            power=1,
            hp=1,
            arena=Arena.GROUND,
            traits=["PILOT"],
            abilities=["Piloting [C=1]"],
        )
        game.player1.units.append(vehicle)
        game.player1.ground_arena.append(vehicle)
        game.player1.hand.append(second_pilot)
        game.player1.resources = [Resource(CardStub("R1"))]

        self.assertNotIn("pilot_JTL_998_1", game.get_legal_actions(game.player1))

    def test_attached_pilot_grants_supported_keywords(self):
        game = game_state()
        vehicle = unit("Alliance Shuttle")
        vehicle.traits = ["VEHICLE"]
        pilot = UnitCard(
            "JTL_997_1",
            "Sentinel Pilot",
            2,
            power=1,
            hp=1,
            arena=Arena.GROUND,
            traits=["PILOT"],
            abilities=[
                "Piloting [C=1]",
                "Attached unit gains Sentinel.",
            ],
        )
        game.player1.units.append(vehicle)
        game.player1.ground_arena.append(vehicle)
        game.player1.hand.append(pilot)
        game.player1.resources = [Resource(CardStub("R1"))]

        self.assertTrue(game.execute_action(game.player1, "pilot_JTL_997_1"))

        self.assertTrue(game._has_keyword(vehicle, "sentinel"))

    def test_when_played_as_upgrade_trained_effect_fires_for_piloting(self):
        game = game_state()
        vehicle = unit("Alliance Shuttle")
        vehicle.traits = ["VEHICLE"]
        pilot = UnitCard(
            "JTL_996_1",
            "Shield Pilot",
            2,
            power=1,
            hp=1,
            arena=Arena.GROUND,
            traits=["PILOT"],
            abilities=["Piloting [C=1]"],
        )
        game.player1.units.append(vehicle)
        game.player1.ground_arena.append(vehicle)
        game.player1.hand.append(pilot)
        game.player1.resources = [Resource(CardStub("R1"))]
        game.card_effects = {
            effect_key("JTL", "996"): {
                "status": "approved",
                "execution_status": "executable",
                "triggers": [
                    {
                        "event": "when_played_as_upgrade",
                        "conditions": [],
                        "steps": [
                            {
                                "type": "give_shield",
                                "amount": 1,
                                "duration": "instant",
                                "target": {"controller": "friendly", "type": "unit"},
                            }
                        ],
                    }
                ],
            }
        }

        self.assertTrue(game.execute_action(game.player1, "pilot_JTL_996_1"))

        self.assertEqual(vehicle.shield_tokens, 1)

    def test_create_token_structured_effect_adds_token_unit(self):
        game = game_state()
        source = UnitCard("TST_300_1", "Token Maker", 2, 1, 3, Arena.GROUND)
        game.player1.hand.append(source)
        game.player1.resources = [Resource(CardStub("R1")), Resource(CardStub("R2"))]
        record = {
            "status": "approved",
            "execution_status": "executable",
            "triggers": [
                {
                    "event": "when_played",
                    "conditions": [],
                    "steps": [
                        {
                            "type": "create_token",
                            "amount": 2,
                            "token_name": "X-Wing",
                            "duration": "instant",
                            "target": {"controller": "friendly", "type": "player"},
                        }
                    ],
                }
            ],
        }
        game.card_effects = {effect_key("TST", "300"): record}

        self.assertEqual(execution_status_for_record(record), "executable")
        self.assertTrue(game.execute_action(game.player1, "play_TST_300_1"))

        tokens = [unit for unit in game.player1.units if getattr(unit, "is_token", False)]
        self.assertEqual(len(tokens), 2)
        self.assertTrue(all(token.name == "X-Wing" for token in tokens))
        self.assertTrue(all(token.arena == Arena.SPACE for token in tokens))
        self.assertTrue(all(token.is_exhausted for token in tokens))

    def test_create_token_can_target_opponent_and_enter_ready(self):
        game = game_state()
        source = UnitCard("TST_301_1", "Enemy Token Maker", 2, 1, 3, Arena.GROUND)
        step = {
            "type": "create_token",
            "amount": 1,
            "token_name": "Battle Droid token",
            "ready": "true",
            "target": {"controller": "opponent", "type": "player"},
        }

        game._apply_structured_step(game.player1, source, step)

        self.assertEqual(len(game.player1.units), 0)
        self.assertEqual(len(game.player2.units), 1)
        self.assertEqual(game.player2.units[0].name, "Battle Droid")
        self.assertFalse(game.player2.units[0].is_exhausted)

    def test_token_units_are_removed_from_game_when_defeated(self):
        game = game_state()
        game._create_tokens(game.player1, "Battle Droid", 1, "Test Source")
        token = next(unit for unit in game.player1.units if getattr(unit, "is_token", False))

        game._damage_unit(game.player1, token, 1)

        self.assertNotIn(token, game.player1.units)
        self.assertNotIn(token, game.player1.discard_pile)


class CardStub:
    def __init__(self, card_id: str):
        self.id = card_id
        self.name = card_id
        self.cost = 0


if __name__ == "__main__":
    unittest.main()
