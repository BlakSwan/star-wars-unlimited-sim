from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sw_unlimited_sim"))

from effect_store import effect_key  # noqa: E402
from effect_training import execution_status_for_record  # noqa: E402
from engine import GameState  # noqa: E402
from models import Arena, EventCard, LeaderCard, Resource, UnitCard, UpgradeCard  # noqa: E402


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
    def test_basic_piloting_cards_are_now_supported_by_generic_pilot_flow(self):
        game = game_state()
        vehicle = unit("Alliance Shuttle")
        vehicle.traits = ["VEHICLE", "TRANSPORT"]
        clone_pilot = UnitCard("JTL_108_1", "Clone Pilot", 2, 1, 2, Arena.GROUND, traits=["PILOT"], abilities=["Piloting [C=2 Command]"])
        dagger_pilot = UnitCard("JTL_196_1", "Dagger Squadron Pilot", 1, 1, 1, Arena.GROUND, traits=["PILOT"], abilities=["Piloting [C=1 Cunning Heroism]"])
        game.player1.units.append(vehicle)
        game.player1.ground_arena.append(vehicle)
        game.player1.hand.extend([clone_pilot, dagger_pilot])
        game.player1.resources = [Resource(CardStub("R1")), Resource(CardStub("R2"))]

        self.assertIn("pilot_JTL_108_1", game.get_legal_actions(game.player1))
        self.assertTrue(game.execute_action(game.player1, "pilot_JTL_108_1"))
        self.assertNotIn("pilot_JTL_196_1", game.get_legal_actions(game.player1))

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

    def test_hera_attached_upgrade_grants_restore(self):
        game = game_state()
        vehicle = UnitCard("SHIP_045_1", "Ghost Shuttle", 2, 2, 3, Arena.SPACE)
        vehicle.traits = ["VEHICLE", "TRANSPORT"]
        hera = UnitCard(
            "JTL_045_1",
            "Hera Syndulla",
            3,
            power=2,
            hp=4,
            arena=Arena.SPACE,
            traits=["PILOT"],
            abilities=[
                "Restore 1",
                "Piloting [C=2 Vigilance Heroism]",
                "Attached unit gains Restore 1.",
            ],
        )
        game.player1.base.current_hp = 20
        game.player1.units.append(vehicle)
        game.player1.space_arena.append(vehicle)
        game.player1.hand.append(hera)
        game.player1.resources = [Resource(CardStub("R1")), Resource(CardStub("R2"))]

        self.assertTrue(game.execute_action(game.player1, "pilot_JTL_045_1"))
        self.assertEqual(game._restore_amount(vehicle), 1)

        enemy_defender = UnitCard("ENEMY_1", "Enemy Ship", 2, 1, 2, Arena.SPACE)
        game.player2.units.append(enemy_defender)
        game.player2.space_arena.append(enemy_defender)

        self.assertTrue(game._attack(game.player1, vehicle.id, enemy_defender.id))
        self.assertEqual(game.player1.base.current_hp, 21)

    def test_nien_nunb_pilot_bonus_scales_with_other_friendly_pilots(self):
        game = game_state()
        ship = UnitCard("SHIP_1", "Freighter", 2, 2, 4, Arena.SPACE, traits=["VEHICLE"])
        other_pilot = UnitCard("JTL_108_1", "Clone Pilot", 2, 1, 2, Arena.GROUND, traits=["PILOT"], abilities=["Piloting [C=2 Command]"])
        nien = UnitCard(
            "JTL_093_1",
            "Nien Nunb",
            2,
            power=1,
            hp=3,
            arena=Arena.GROUND,
            traits=["PILOT"],
            abilities=["Piloting [C=1 Command Heroism]", "Attached unit gets +1/+0 for each other friendly Pilot unit and upgrade."],
        )
        game.player1.units.extend([ship, other_pilot])
        game.player1.space_arena.append(ship)
        game.player1.ground_arena.append(other_pilot)
        game.player1.hand.append(nien)
        game.player1.resources = [Resource(CardStub("R1"))]

        self.assertTrue(game.execute_action(game.player1, "pilot_JTL_093_1"))
        self.assertEqual(game._unit_power(game.player1, ship), 4)

    def test_red_squadron_x_wing_self_damages_to_draw_on_play(self):
        game = game_state()
        x_wing = UnitCard("JTL_051_1", "Red Squadron X-Wing", 3, 3, 4, Arena.SPACE, traits=["VEHICLE", "FIGHTER"])
        x_wing.abilities = ["When Played: You may deal 2 damage to this unit. If you do, draw a card."]
        draw_card = UnitCard("DRAW_1", "Spare Ship", 1, 1, 1, Arena.SPACE)
        game.player1.deck = [draw_card]

        self.assertTrue(game._play_unit(game.player1, x_wing))
        self.assertEqual(x_wing.current_hp, 2)
        self.assertIn(draw_card, game.player1.hand)

    def test_gold_leader_reduces_attacker_power_while_defending(self):
        game = game_state()
        gold_leader = UnitCard("JTL_054_1", "Gold Leader", 6, 5, 5, Arena.SPACE, traits=["VEHICLE", "TRANSPORT"])
        gold_leader.abilities = ["Shielded", "While this unit is defending, the attacker gets -1/-0."]
        attacker = UnitCard("ATK_1", "TIE Fighter", 2, 4, 3, Arena.SPACE)
        game.player1.units.append(gold_leader)
        game.player1.space_arena.append(gold_leader)
        game.player2.units.append(attacker)
        game.player2.space_arena.append(attacker)
        attacker.is_exhausted = False

        self.assertTrue(game._attack(game.player2, attacker.id, gold_leader.id))
        self.assertEqual(gold_leader.current_hp, 2)

    def test_cr90_relief_runner_heals_base_when_defeated(self):
        game = game_state()
        cr90 = UnitCard("JTL_071_1", "CR90 Relief Runner", 6, 4, 6, Arena.SPACE, traits=["VEHICLE", "CAPITAL SHIP"])
        cr90.abilities = ["Restore 2", "When Defeated: Heal up to 3 damage from a unit or base."]
        game.player1.base.current_hp = 20
        game.player1.units.append(cr90)
        game.player1.space_arena.append(cr90)

        game._remove_unit(game.player1, cr90)
        self.assertEqual(game.player1.base.current_hp, 23)

    def test_phantom_two_action_attaches_to_the_ghost(self):
        game = game_state()
        ghost = UnitCard("JTL_053_1", "The Ghost", 5, 5, 6, Arena.SPACE, traits=["VEHICLE", "TRANSPORT", "SPECTRE"])
        phantom = UnitCard("JTL_050_1", "Phantom II", 3, 3, 3, Arena.SPACE, traits=["VEHICLE", "TRANSPORT", "SPECTRE"], abilities=[
            "Grit",
            "Action [C=1]: If this card is a unit, attach it as an upgrade to The Ghost.",
            "Attached unit gets +3/+3 and gains Grit.",
        ])
        game.player1.units.extend([ghost, phantom])
        game.player1.space_arena.extend([ghost, phantom])
        game.player1.resources = [Resource(CardStub("R1"))]

        self.assertIn(f"unit_action_{phantom.id}", game.get_legal_actions(game.player1))
        self.assertTrue(game.execute_action(game.player1, f"unit_action_{phantom.id}"))
        self.assertNotIn(phantom, game.player1.units)
        self.assertIs(phantom.attached_to, ghost)
        self.assertEqual(ghost.power, 8)
        self.assertEqual(ghost.hp, 9)
        self.assertTrue(game._has_keyword(ghost, "grit"))

    def test_wedge_leader_action_plays_pilot_with_discount(self):
        leader = LeaderCard(
            "JTL_008",
            "Wedge Antilles",
            5,
            action_cost=0,
            action_effect="Action [Exhaust]: Play a card from your hand using Piloting. It costs 1 less.",
            epic_action_cost=5,
            epic_action_effect="Deploy as 3/6 unit",
        )
        leader.traits = ["REBEL", "PILOT"]
        leader.abilities = [
            "Action [Exhaust]: Play a card from your hand using Piloting. It costs 1 less.",
            'Attached unit is a leader unit. It gains: "On Attack: The next Pilot card you play this phase costs 1 less. (This includes Piloting costs.)"',
            "Epic Action: Deploy this leader or deploy this leader as an upgrade on a friendly Vehicle unit without a Pilot on it.",
        ]
        game = GameState([], [], leader, LeaderCard("LDR_002", "Leader Two", 6), verbose=False)
        vehicle = UnitCard("SHIP_008_1", "Red Squadron Craft", 3, 2, 4, Arena.SPACE, traits=["VEHICLE", "FIGHTER"])
        pilot = UnitCard("JTL_196_1", "Dagger Squadron Pilot", 1, 1, 1, Arena.GROUND, traits=["PILOT"], abilities=["Piloting [C=1 Cunning Heroism]"])
        game.player1.units.append(vehicle)
        game.player1.space_arena.append(vehicle)
        game.player1.hand.append(pilot)

        self.assertIn("leader_action_JTL_008", game.get_legal_actions(game.player1))
        self.assertTrue(game.execute_action(game.player1, "leader_action_JTL_008"))
        self.assertIs(pilot.attached_to, vehicle)

    def test_wedge_attached_on_attack_reduces_next_pilot_cost_this_phase(self):
        leader = LeaderCard(
            "JTL_008",
            "Wedge Antilles",
            5,
            action_cost=0,
            action_effect="Action [Exhaust]: Play a card from your hand using Piloting. It costs 1 less.",
            epic_action_cost=5,
            epic_action_effect="Deploy as 3/6 unit",
        )
        leader.traits = ["REBEL", "PILOT"]
        leader.abilities = [
            "Action [Exhaust]: Play a card from your hand using Piloting. It costs 1 less.",
            'Attached unit is a leader unit. It gains: "On Attack: The next Pilot card you play this phase costs 1 less. (This includes Piloting costs.)"',
            "Epic Action: Deploy this leader or deploy this leader as an upgrade on a friendly Vehicle unit without a Pilot on it.",
        ]
        game = GameState([], [], leader, LeaderCard("LDR_002", "Leader Two", 6), verbose=False)
        attacker = UnitCard("SHIP_100_1", "Wedge Carrier", 3, 3, 6, Arena.SPACE, traits=["VEHICLE"])
        second_vehicle = UnitCard("SHIP_100_2", "Reserve Craft", 3, 2, 4, Arena.SPACE, traits=["VEHICLE"])
        enemy = UnitCard("ENEMY_100", "Enemy Fighter", 2, 1, 1, Arena.SPACE)
        pilot = UnitCard("JTL_196_1", "Dagger Squadron Pilot", 1, 1, 1, Arena.GROUND, traits=["PILOT"], abilities=["Piloting [C=1 Cunning Heroism]"])
        game.player1.units.extend([attacker, second_vehicle])
        game.player1.space_arena.extend([attacker, second_vehicle])
        game.player2.units.append(enemy)
        game.player2.space_arena.append(enemy)
        game.player1.hand.append(pilot)
        game.player1.resources = [Resource(CardStub("R1")), Resource(CardStub("R2")), Resource(CardStub("R3")), Resource(CardStub("R4")), Resource(CardStub("R5"))]

        self.assertTrue(game.execute_action(game.player1, "leader_epic_JTL_008"))
        self.assertTrue(game._attack(game.player1, attacker.id, enemy.id))
        self.assertIn("pilot_JTL_196_1", game.get_legal_actions(game.player1))
        self.assertTrue(game.execute_action(game.player1, "pilot_JTL_196_1"))
        self.assertIs(pilot.attached_to, second_vehicle)

    def test_chewbacca_blocks_enemy_bounce_effects(self):
        game = game_state()
        chewie = UnitCard("JTL_103_1", "Chewbacca", 5, 5, 6, Arena.GROUND, traits=["WOOKIEE", "PILOT"], abilities=[
            "This unit can't be defeated or returned to hand by enemy card abilities.",
            "Piloting [C=3 Command Heroism]",
        ])
        enemy_event = EventCard("SEC_233_1", "Beguile", 3, effect="Return a unit to hand")
        game.player1.units.append(chewie)
        game.player1.ground_arena.append(chewie)

        game._resolve_event(game.player2, enemy_event)
        self.assertIn(chewie, game.player1.units)

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

    def test_when_pilot_attached_structured_effect_fires_on_target(self):
        game = game_state()
        vehicle = UnitCard("TST_400_1", "Carrier", 3, 2, 5, Arena.SPACE, traits=["VEHICLE"])
        pilot = UnitCard(
            "JTL_995_1",
            "Token Pilot",
            2,
            power=1,
            hp=1,
            arena=Arena.GROUND,
            traits=["PILOT"],
            abilities=["Piloting [C=1]"],
        )
        game.player1.units.append(vehicle)
        game.player1.space_arena.append(vehicle)
        game.player1.hand.append(pilot)
        game.player1.resources = [Resource(CardStub("R1"))]
        record = {
            "status": "approved",
            "execution_status": "executable",
            "triggers": [
                {
                    "event": "when_pilot_attached",
                    "conditions": [],
                    "steps": [
                        {
                            "type": "create_token",
                            "amount": 1,
                            "token_name": "X-Wing",
                            "duration": "instant",
                            "target": {"controller": "friendly", "type": "player"},
                        }
                    ],
                }
            ],
        }
        game.card_effects = {effect_key("TST", "400"): record}

        self.assertEqual(execution_status_for_record(record), "executable")
        self.assertTrue(game.execute_action(game.player1, "pilot_JTL_995_1"))

        tokens = [unit for unit in game.player1.units if getattr(unit, "is_token", False)]
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0].name, "X-Wing")

    def test_red_leader_costs_less_for_friendly_pilots(self):
        game = game_state()
        pilot_unit = UnitCard("JTL_900_1", "Pilot Unit", 2, 1, 2, Arena.GROUND, traits=["PILOT"])
        vehicle = UnitCard("JTL_901_1", "Vehicle", 2, 1, 2, Arena.SPACE, traits=["VEHICLE"])
        attached_pilot = UnitCard("JTL_902_1", "Attached Pilot", 2, 1, 1, Arena.GROUND, traits=["PILOT"])
        attached_pilot.played_as_pilot = True
        vehicle.attached_upgrades.append(attached_pilot)
        red_leader = UnitCard("JTL_101_1", "Red Leader", 5, 3, 4, Arena.SPACE, traits=["VEHICLE"])
        game.player1.units.extend([pilot_unit, vehicle])
        game.player1.ground_arena.append(pilot_unit)
        game.player1.space_arena.append(vehicle)

        self.assertEqual(game._effective_cost(game.player1, red_leader), 3)

    def test_red_leader_creates_x_wing_when_pilot_attaches(self):
        game = game_state()
        red_leader = UnitCard("JTL_101_1", "Red Leader", 5, 3, 4, Arena.SPACE, traits=["VEHICLE"])
        pilot = UnitCard(
            "JTL_994_1",
            "Rebel Pilot",
            2,
            power=1,
            hp=1,
            arena=Arena.GROUND,
            traits=["PILOT"],
            abilities=["Piloting [C=1]"],
        )
        game.player1.units.append(red_leader)
        game.player1.space_arena.append(red_leader)
        game.player1.hand.append(pilot)
        game.player1.resources = [Resource(CardStub("R1"))]

        self.assertTrue(game.execute_action(game.player1, "pilot_JTL_994_1"))

        tokens = [unit for unit in game.player1.units if getattr(unit, "is_token", False)]
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0].name, "X-Wing")
        self.assertEqual(tokens[0].arena, Arena.SPACE)

    def test_astromech_pilot_heals_damaged_unit_when_attached(self):
        game = game_state()
        vehicle = UnitCard("JTL_920_1", "Carrier", 2, 2, 5, Arena.SPACE, traits=["VEHICLE"])
        damaged = UnitCard("JTL_921_1", "Damaged Unit", 2, 2, 5, Arena.GROUND)
        astromech = UnitCard(
            "JTL_057_1",
            "Astromech Pilot",
            2,
            power=1,
            hp=1,
            arena=Arena.GROUND,
            traits=["PILOT"],
            abilities=["Piloting [C=2 Vigilance]"],
        )
        damaged.take_damage(3)
        game.player1.units.extend([vehicle, damaged])
        game.player1.space_arena.append(vehicle)
        game.player1.ground_arena.append(damaged)
        game.player1.hand.append(astromech)
        game.player1.resources = [Resource(CardStub("R1")), Resource(CardStub("R2"))]

        self.assertTrue(game.execute_action(game.player1, "pilot_JTL_057_1"))

        self.assertEqual(damaged.damage, 1)
        self.assertEqual(damaged.current_hp, 4)

    def test_han_pilot_attacks_with_ready_attached_unit_by_default(self):
        game = game_state()
        vehicle = UnitCard("JTL_930_1", "Ready Vehicle", 2, 3, 5, Arena.SPACE, traits=["VEHICLE"])
        enemy = UnitCard("JTL_931_1", "Enemy Space Unit", 2, 1, 3, Arena.SPACE)
        han = UnitCard(
            "JTL_203_1",
            "Han Solo",
            2,
            power=2,
            hp=1,
            arena=Arena.GROUND,
            traits=["PILOT"],
            abilities=["Ambush", "Piloting [C=2 Cunning Heroism]"],
            has_ambush=True,
        )
        game.player1.units.append(vehicle)
        game.player1.space_arena.append(vehicle)
        game.player2.units.append(enemy)
        game.player2.space_arena.append(enemy)
        game.player1.hand.append(han)
        game.player1.resources = [Resource(CardStub("R1")), Resource(CardStub("R2"))]

        self.assertTrue(game.execute_action(game.player1, "pilot_JTL_203_1"))

        self.assertTrue(vehicle.is_exhausted)
        self.assertTrue(vehicle.attacked_this_phase)
        self.assertEqual(enemy.current_hp, 0)

    def test_han_pilot_on_millennium_falcon_deals_combat_damage_first(self):
        game = game_state()
        falcon = UnitCard("JTL_249_1", "Millennium Falcon", 4, 3, 5, Arena.SPACE, traits=["VEHICLE", "TRANSPORT"])
        enemy = UnitCard("ENEMY_FALCON_1", "Enemy Gunship", 4, 5, 4, Arena.SPACE)
        han = UnitCard(
            "JTL_203_1",
            "Han Solo",
            2,
            power=2,
            hp=1,
            arena=Arena.GROUND,
            traits=["PILOT"],
            abilities=["Ambush", "Piloting [C=2 Cunning Heroism]"],
            has_ambush=True,
        )
        game.player1.units.append(falcon)
        game.player1.space_arena.append(falcon)
        game.player2.units.append(enemy)
        game.player2.space_arena.append(enemy)
        game.player1.hand.append(han)
        game.player1.resources = [Resource(CardStub("R1")), Resource(CardStub("R2"))]

        self.assertTrue(game.execute_action(game.player1, "pilot_JTL_203_1"))
        self.assertNotIn(enemy, game.player2.units)
        self.assertEqual(falcon.current_hp, 6)

    def test_han_pilot_attack_can_be_disabled_by_strategy_tuning(self):
        game = game_state()
        vehicle = UnitCard("JTL_932_1", "Ready Vehicle", 2, 3, 5, Arena.SPACE, traits=["VEHICLE"])
        enemy = UnitCard("JTL_933_1", "Enemy Space Unit", 2, 1, 3, Arena.SPACE)
        han = UnitCard(
            "JTL_203_1",
            "Han Solo",
            2,
            power=2,
            hp=1,
            arena=Arena.GROUND,
            traits=["PILOT"],
            abilities=["Ambush", "Piloting [C=2 Cunning Heroism]"],
            has_ambush=True,
        )
        game.strategy_tuning["han_pilot_attack_with_attached_unit"] = False
        game.player1.units.append(vehicle)
        game.player1.space_arena.append(vehicle)
        game.player2.units.append(enemy)
        game.player2.space_arena.append(enemy)
        game.player1.hand.append(han)
        game.player1.resources = [Resource(CardStub("R1")), Resource(CardStub("R2"))]

        self.assertTrue(game.execute_action(game.player1, "pilot_JTL_203_1"))

        self.assertFalse(getattr(vehicle, "is_exhausted", False))
        self.assertFalse(vehicle.attacked_this_phase)
        self.assertEqual(enemy.current_hp, 3)

    def test_anakin_returns_to_hand_after_attached_unit_attacks_and_survives(self):
        game = game_state()
        vehicle = UnitCard("JTL_940_1", "Ready Vehicle", 2, 3, 5, Arena.SPACE, traits=["VEHICLE"])
        enemy = UnitCard("JTL_941_1", "Enemy Space Unit", 2, 1, 2, Arena.SPACE)
        anakin = UnitCard(
            "JTL_197_1",
            "Anakin Skywalker",
            2,
            power=2,
            hp=1,
            arena=Arena.GROUND,
            traits=["PILOT"],
            abilities=["Piloting [C=2 Cunning Heroism]"],
        )
        anakin.played_as_pilot = True
        game.player1.units.append(vehicle)
        game.player1.space_arena.append(vehicle)
        game.player2.units.append(enemy)
        game.player2.space_arena.append(enemy)
        game._attach_upgrade(anakin, vehicle)

        self.assertTrue(game._attack(game.player1, vehicle.id, enemy.id))

        self.assertIn(anakin, game.player1.hand)
        self.assertNotIn(anakin, vehicle.attached_upgrades)
        self.assertIsNone(anakin.attached_to)
        self.assertEqual(vehicle.power, 3)
        self.assertEqual(vehicle.hp, 5)

    def test_anakin_does_not_return_if_attached_unit_is_defeated(self):
        game = game_state()
        vehicle = UnitCard("JTL_942_1", "Fragile Vehicle", 2, 1, 1, Arena.SPACE, traits=["VEHICLE"])
        enemy = UnitCard("JTL_943_1", "Enemy Space Unit", 2, 3, 3, Arena.SPACE)
        anakin = UnitCard(
            "JTL_197_1",
            "Anakin Skywalker",
            2,
            power=2,
            hp=1,
            arena=Arena.GROUND,
            traits=["PILOT"],
            abilities=["Piloting [C=2 Cunning Heroism]"],
        )
        anakin.played_as_pilot = True
        game.player1.units.append(vehicle)
        game.player1.space_arena.append(vehicle)
        game.player2.units.append(enemy)
        game.player2.space_arena.append(enemy)
        game._attach_upgrade(anakin, vehicle)

        self.assertTrue(game._attack(game.player1, vehicle.id, enemy.id))

        self.assertNotIn(anakin, game.player1.hand)
        self.assertIn(anakin, game.player1.discard_pile)
        self.assertNotIn(vehicle, game.player1.units)

    def test_anakin_return_can_be_disabled_by_strategy_tuning(self):
        game = game_state()
        vehicle = UnitCard("JTL_944_1", "Ready Vehicle", 2, 3, 5, Arena.SPACE, traits=["VEHICLE"])
        enemy = UnitCard("JTL_945_1", "Enemy Space Unit", 2, 1, 2, Arena.SPACE)
        anakin = UnitCard(
            "JTL_197_1",
            "Anakin Skywalker",
            2,
            power=2,
            hp=1,
            arena=Arena.GROUND,
            traits=["PILOT"],
            abilities=["Piloting [C=2 Cunning Heroism]"],
        )
        anakin.played_as_pilot = True
        game.strategy_tuning["anakin_return_after_attached_attack"] = False
        game.player1.units.append(vehicle)
        game.player1.space_arena.append(vehicle)
        game.player2.units.append(enemy)
        game.player2.space_arena.append(enemy)
        game._attach_upgrade(anakin, vehicle)

        self.assertTrue(game._attack(game.player1, vehicle.id, enemy.id))

        self.assertNotIn(anakin, game.player1.hand)
        self.assertIn(anakin, vehicle.attached_upgrades)
        self.assertIs(anakin.attached_to, vehicle)

    def test_biggs_grants_overwhelm_to_attached_fighter(self):
        game = game_state()
        fighter = UnitCard("JTL_910_1", "Fighter", 2, 2, 3, Arena.SPACE, traits=["VEHICLE", "FIGHTER"])
        biggs = UnitCard(
            "JTL_150_1",
            "Biggs Darklighter",
            2,
            power=1,
            hp=1,
            arena=Arena.GROUND,
            traits=["PILOT"],
            abilities=["Piloting [C=1 Aggression Heroism]"],
        )
        game.player1.units.append(fighter)
        game.player1.space_arena.append(fighter)
        game.player1.hand.append(biggs)
        game.player1.resources = [Resource(CardStub("R1"))]

        self.assertTrue(game.execute_action(game.player1, "pilot_JTL_150_1"))

        self.assertTrue(game._has_keyword(fighter, "overwhelm"))

    def test_biggs_grants_extra_hp_to_attached_transport_and_cleans_up(self):
        game = game_state()
        transport = UnitCard("JTL_911_1", "Transport", 2, 2, 3, Arena.SPACE, traits=["VEHICLE", "TRANSPORT"])
        biggs = UnitCard(
            "JTL_150_1",
            "Biggs Darklighter",
            2,
            power=1,
            hp=1,
            arena=Arena.GROUND,
            traits=["PILOT"],
            abilities=["Piloting [C=1 Aggression Heroism]"],
        )
        game.player1.units.append(transport)
        game.player1.space_arena.append(transport)
        game.player1.hand.append(biggs)
        game.player1.resources = [Resource(CardStub("R1"))]

        self.assertTrue(game.execute_action(game.player1, "pilot_JTL_150_1"))
        self.assertEqual(transport.power, 3)
        self.assertEqual(transport.hp, 5)
        self.assertEqual(transport.current_hp, 5)

        game._return_unit_to_hand(game.player1, transport, "Test Return")

        self.assertEqual(transport.power, 2)
        self.assertEqual(transport.hp, 3)
        self.assertEqual(transport.current_hp, 3)

    def test_biggs_grants_grit_to_attached_speeder(self):
        game = game_state()
        speeder = UnitCard("JTL_912_1", "Speeder", 2, 2, 3, Arena.GROUND, traits=["VEHICLE", "SPEEDER"])
        biggs = UnitCard(
            "JTL_150_1",
            "Biggs Darklighter",
            2,
            power=1,
            hp=1,
            arena=Arena.GROUND,
            traits=["PILOT"],
            abilities=["Piloting [C=1 Aggression Heroism]"],
        )
        game.player1.units.append(speeder)
        game.player1.ground_arena.append(speeder)
        game.player1.hand.append(biggs)
        game.player1.resources = [Resource(CardStub("R1"))]

        self.assertTrue(game.execute_action(game.player1, "pilot_JTL_150_1"))

        self.assertTrue(game._has_keyword(speeder, "grit"))

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
