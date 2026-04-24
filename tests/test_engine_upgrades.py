from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sw_unlimited_sim"))

from effect_store import effect_key  # noqa: E402
from effect_training import execution_status_for_record  # noqa: E402
from engine import GameState  # noqa: E402
from models import Arena, Base, EventCard, LeaderCard, Resource, UnitCard, UpgradeCard  # noqa: E402


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
    def test_patrolling_v_wing_structured_effect_draws_a_card_when_played(self):
        game = game_state()
        unit_card = UnitCard("TWI_107_1", "Patrolling V-Wing", 2, 2, 2, Arena.SPACE)
        draw_card = EventCard("DRAW_1", "Test Draw", 1, effect="")
        game.player1.deck = [draw_card]
        game.card_effects = {
            effect_key("TWI", "107"): {
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

        self.assertTrue(game._play_unit(game.player1, unit_card))
        self.assertIn(draw_card, game.player1.hand)

    def test_veteran_fleet_officer_structured_effect_creates_x_wing_token(self):
        game = game_state()
        unit_card = UnitCard("JTL_099_1", "Veteran Fleet Officer", 3, 2, 2, Arena.GROUND)
        game.card_effects = {
            effect_key("JTL", "099"): {
                "status": "approved",
                "execution_status": "executable",
                "triggers": [
                    {
                        "event": "when_played",
                        "conditions": [],
                        "steps": [
                            {
                                "type": "create_token",
                                "token_name": "X-Wing token",
                                "amount": 1,
                                "duration": "instant",
                                "target": {"controller": "friendly", "type": "player"},
                            }
                        ],
                    }
                ],
            }
        }

        self.assertTrue(game._play_unit(game.player1, unit_card))
        self.assertTrue(any(token.name == "X-Wing" for token in game.player1.space_arena))

    def test_dilapidated_ski_speeder_structured_effect_damages_itself_when_played(self):
        game = game_state()
        unit_card = UnitCard("JTL_248_1", "Dilapidated Ski Speeder", 3, 3, 7, Arena.GROUND)
        game.card_effects = {
            effect_key("JTL", "248"): {
                "status": "approved",
                "execution_status": "executable",
                "triggers": [
                    {
                        "event": "when_played",
                        "conditions": [],
                        "steps": [
                            {
                                "type": "deal_damage",
                                "amount": 3,
                                "duration": "instant",
                                "target": {"controller": "self", "type": "unit"},
                            }
                        ],
                    }
                ],
            }
        }

        self.assertTrue(game._play_unit(game.player1, unit_card))
        self.assertEqual(unit_card.current_hp, 4)

    def test_swoop_bike_marauder_structured_effect_draws_on_attack(self):
        game = game_state()
        attacker = UnitCard("LAW_107_1", "Swoop Bike Marauder", 2, 2, 2, Arena.GROUND)
        attacker.is_exhausted = False
        draw_card = EventCard("DRAW_2", "Test Draw", 1, effect="")
        game.player1.deck = [draw_card]
        game.player1.units.append(attacker)
        game.player1.ground_arena.append(attacker)
        game.card_effects = {
            effect_key("LAW", "107"): {
                "status": "approved",
                "execution_status": "executable",
                "triggers": [
                    {
                        "event": "on_attack",
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

        self.assertTrue(game._attack(game.player1, attacker.id, "base"))
        self.assertIn(draw_card, game.player1.hand)

    def test_cloud_rider_veteran_structured_effect_damages_base_on_attack(self):
        game = game_state()
        attacker = UnitCard("LAW_181_1", "Cloud-Rider Veteran", 4, 3, 3, Arena.GROUND)
        attacker.is_exhausted = False
        game.player1.units.append(attacker)
        game.player1.ground_arena.append(attacker)
        game.card_effects = {
            effect_key("LAW", "181"): {
                "status": "approved",
                "execution_status": "executable",
                "triggers": [
                    {
                        "event": "on_attack",
                        "conditions": [],
                        "steps": [
                            {
                                "type": "deal_damage",
                                "amount": 2,
                                "duration": "instant",
                                "target": {"controller": "enemy", "type": "base"},
                            }
                        ],
                    }
                ],
            }
        }

        before = game.player2.base.current_hp
        self.assertTrue(game._attack(game.player1, attacker.id, "base"))
        self.assertEqual(game.player2.base.current_hp, before - 2 - attacker.power)

    def test_kintan_intimidator_structured_effect_exhausts_defender_on_attack(self):
        game = game_state()
        attacker = UnitCard("SHD_183_1", "Kintan Intimidator", 3, 3, 4, Arena.GROUND)
        defender = UnitCard("DEFENDER_1", "Target Unit", 2, 2, 4, Arena.GROUND)
        attacker.is_exhausted = False
        defender.is_exhausted = False
        game.player1.units.append(attacker)
        game.player1.ground_arena.append(attacker)
        game.player2.units.append(defender)
        game.player2.ground_arena.append(defender)
        game.card_effects = {
            effect_key("SHD", "183"): {
                "status": "approved",
                "execution_status": "executable",
                "triggers": [
                    {
                        "event": "on_attack",
                        "conditions": [],
                        "steps": [
                            {
                                "type": "exhaust_unit",
                                "amount": 1,
                                "duration": "instant",
                                "target": {"controller": "enemy", "type": "unit"},
                            }
                        ],
                    }
                ],
            }
        }

        self.assertTrue(game._attack(game.player1, attacker.id, defender.id))
        self.assertTrue(defender.is_exhausted)

    def test_security_complex_epic_action_gives_shield_to_friendly_non_leader(self):
        game = game_state()
        game.player1.base = Base(name="Security Complex", hp=25, set_code="SOR", number="019")
        target = unit("Friendly Trooper")
        game.player1.units.append(target)
        game.player1.ground_arena.append(target)

        self.assertIn("base_epic", game.get_legal_actions(game.player1))
        self.assertTrue(game.execute_action(game.player1, "base_epic"))
        self.assertEqual(target.shield_tokens, 1)
        self.assertTrue(game.player1.base.epic_action_used)

    def test_tarkintown_epic_action_damages_damaged_enemy_non_leader(self):
        game = game_state()
        game.player1.base = Base(name="Tarkintown", hp=25, set_code="SOR", number="025")
        enemy = UnitCard("ENEMY_1", "Enemy Trooper", 3, 4, 5, Arena.GROUND)
        enemy.damage = 1
        enemy.current_hp = 4
        game.player2.units.append(enemy)
        game.player2.ground_arena.append(enemy)

        self.assertIn("base_epic", game.get_legal_actions(game.player1))
        self.assertTrue(game.execute_action(game.player1, "base_epic"))
        self.assertEqual(enemy.current_hp, 1)
        self.assertTrue(game.player1.base.epic_action_used)

    def test_jedha_city_epic_action_applies_negative_power_for_phase(self):
        game = game_state()
        game.player1.base = Base(name="Jedha City", hp=25, set_code="SOR", number="028")
        enemy = UnitCard("ENEMY_2", "Enemy Trooper", 3, 5, 5, Arena.GROUND)
        game.player2.units.append(enemy)
        game.player2.ground_arena.append(enemy)

        self.assertTrue(game.execute_action(game.player1, "base_epic"))
        self.assertEqual(enemy.power, 1)
        game._clear_phase_modifiers(game.player2)
        self.assertEqual(enemy.power, 5)

    def test_energy_conversion_lab_epic_action_plays_unit_with_ambush(self):
        game = game_state()
        game.player1.base = Base(name="Energy Conversion Lab", hp=25, set_code="SOR", number="022")
        card = UnitCard("HAND_1", "Test Fighter", 5, 4, 4, Arena.SPACE)
        game.player1.hand.append(card)

        self.assertIn("base_epic", game.get_legal_actions(game.player1))
        self.assertTrue(game.execute_action(game.player1, "base_epic"))
        self.assertIn(card, game.player1.units)
        self.assertTrue(card.is_exhausted is False)
        self.assertTrue(game.player1.base.epic_action_used)

    def test_deployed_space_leader_uses_space_arena_and_resets_when_defeated(self):
        leader = LeaderCard("LDR_SPACE", "Space Leader", 0, epic_action_cost=0, epic_action_effect="Deploy as 3/4 unit")
        leader.deployed_arena = Arena.SPACE
        game = GameState(
            player1_deck=[],
            player2_deck=[],
            player1_leader=leader,
            player2_leader=LeaderCard("LDR_002", "Leader Two", 6, epic_action_effect="Deploy as 4/4 unit"),
            verbose=False,
        )

        self.assertTrue(game._deploy_leader(game.player1))
        self.assertIn(leader, game.player1.space_arena)
        self.assertNotIn(leader, game.player1.ground_arena)
        self.assertEqual(leader.arena, Arena.SPACE)

        game._remove_unit(game.player1, leader)
        self.assertFalse(leader.is_deployed)
        self.assertEqual(leader.arena, Arena.NONE)

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

    def test_structured_upgrade_can_target_attached_unit_when_played(self):
        game = game_state()
        target = unit("Host Vehicle")
        target.is_exhausted = False
        upgrade = UpgradeCard("LAW_127_1", "Kill Switch", 2)
        game.player1.units.append(target)
        game.player1.ground_arena.append(target)
        game.card_effects = {
            effect_key("LAW", "127"): {
                "status": "approved",
                "execution_status": "executable",
                "triggers": [
                    {
                        "event": "when_played",
                        "conditions": [],
                        "steps": [
                            {
                                "type": "exhaust_unit",
                                "amount": 1,
                                "duration": "instant",
                                "target": {"controller": "self", "type": "unit", "filter": "attached_unit"},
                            }
                        ],
                    }
                ],
            }
        }

        self.assertTrue(game._play_upgrade(game.player1, upgrade))
        self.assertIs(upgrade.attached_to, target)
        self.assertTrue(target.is_exhausted)

    def test_structured_ground_filter_targets_ground_unit_not_space_unit(self):
        game = game_state()
        source = UnitCard("LOF_259_1", "Ravening Gundark", 5, 5, 4, Arena.GROUND)
        ground_enemy = UnitCard("ENEMY_G_1", "Ground Target", 2, 2, 3, Arena.GROUND)
        space_enemy = UnitCard("ENEMY_S_1", "Space Target", 2, 2, 3, Arena.SPACE)
        game.player2.units.extend([ground_enemy, space_enemy])
        game.player2.ground_arena.append(ground_enemy)
        game.player2.space_arena.append(space_enemy)
        game.card_effects = {
            effect_key("LOF", "259"): {
                "status": "approved",
                "execution_status": "executable",
                "triggers": [
                    {
                        "event": "when_played",
                        "conditions": [],
                        "steps": [
                            {
                                "type": "deal_damage",
                                "amount": 1,
                                "duration": "instant",
                                "target": {"controller": "enemy", "type": "unit", "filter": "ground"},
                            }
                        ],
                    }
                ],
            }
        }

        self.assertTrue(game._play_unit(game.player1, source))
        self.assertEqual(ground_enemy.current_hp, 2)
        self.assertEqual(space_enemy.current_hp, 3)

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

    def test_temporary_phase_modifier_applies_and_clears(self):
        game = game_state()
        target = unit()
        game.player1.units.append(target)
        game.player1.ground_arena.append(target)

        game._apply_temporary_modifier(target, power_delta=2, hp_delta=1, keywords={"saboteur"}, duration="this_phase")
        self.assertEqual(target.power, 4)
        self.assertEqual(target.hp, 4)
        self.assertEqual(target.current_hp, 4)
        self.assertTrue(game._has_keyword(target, "saboteur"))

        game._clear_phase_modifiers(game.player1)
        self.assertEqual(target.power, 2)
        self.assertEqual(target.hp, 3)
        self.assertEqual(target.current_hp, 3)
        self.assertFalse(game._has_keyword(target, "saboteur"))

    def test_temporary_attack_modifier_changes_attack_power_and_clears(self):
        game = game_state()
        attacker = UnitCard("ATK_TMP_1", "Raider", 2, 2, 3, Arena.GROUND)
        defender = UnitCard("DEF_TMP_1", "Blocker", 2, 4, 5, Arena.GROUND)
        game.player1.units.append(attacker)
        game.player1.ground_arena.append(attacker)
        game.player2.units.append(defender)
        game.player2.ground_arena.append(defender)

        game._apply_temporary_modifier(attacker, power_delta=3, keywords={"saboteur"}, duration="this_attack")
        self.assertEqual(game._attack_power(game.player1, attacker, defender), 5)
        self.assertTrue(game._has_keyword(attacker, "saboteur"))

        self.assertTrue(game._attack(game.player1, attacker.id, defender.id))
        self.assertEqual(attacker.temporary_attack_power_bonus, 0)
        self.assertFalse(game._has_keyword(attacker, "saboteur"))

    def test_structured_modify_stats_this_phase_executes_and_clears(self):
        game = game_state()
        target = unit()
        game.player1.units.append(target)
        game.player1.ground_arena.append(target)
        step = {
            "type": "modify_stats",
            "power": 2,
            "hp": 1,
            "duration": "this_phase",
            "target": {"controller": "friendly", "type": "unit"},
        }

        game._apply_structured_step(game.player1, target, step)
        self.assertEqual(target.power, 4)
        self.assertEqual(target.hp, 4)

        game._clear_phase_modifiers(game.player1)
        self.assertEqual(target.power, 2)
        self.assertEqual(target.hp, 3)

    def test_structured_modify_stats_this_attack_executes_for_combat_only(self):
        game = game_state()
        attacker = UnitCard("ATK_STRUCT_1", "Clone Trooper", 2, 2, 4, Arena.GROUND)
        defender = UnitCard("DEF_STRUCT_1", "Battle Droid", 1, 1, 4, Arena.GROUND)
        game.player1.units.append(attacker)
        game.player1.ground_arena.append(attacker)
        game.player2.units.append(defender)
        game.player2.ground_arena.append(defender)
        step = {
            "type": "modify_stats",
            "power": 2,
            "duration": "this_attack",
            "target": {"controller": "friendly", "type": "unit"},
        }

        game._apply_structured_step(game.player1, attacker, step)
        self.assertEqual(game._attack_power(game.player1, attacker, defender), 4)
        self.assertTrue(game._attack(game.player1, attacker.id, defender.id))
        self.assertEqual(attacker.temporary_attack_power_bonus, 0)

    def test_improvised_detonation_attacks_with_bonus(self):
        game = game_state()
        attacker = UnitCard("IBH_021_UNIT", "Rebel Trooper", 2, 2, 4, Arena.GROUND)
        defender = UnitCard("IBH_021_DEF", "Stormtrooper", 2, 1, 4, Arena.GROUND)
        event = EventCard("IBH_021_1", "Improvised Detonation", 2, effect="Attack with a unit. It gets +2/+0 for this attack.")
        game.player1.units.append(attacker)
        game.player1.ground_arena.append(attacker)
        game.player2.units.append(defender)
        game.player2.ground_arena.append(defender)

        game._resolve_event(game.player1, event)
        self.assertEqual(defender.current_hp, 0)

    def test_general_rieekan_action_attacks_with_other_heroism_unit(self):
        game = game_state()
        rieekan = UnitCard("IBH_023_1", "General Rieekan", 4, 2, 6, Arena.GROUND, traits=["REBEL", "OFFICIAL"])
        hero = UnitCard("IBH_023_H", "Hero Unit", 3, 2, 4, Arena.GROUND)
        hero.aspects = ["Heroism"]
        defender = UnitCard("IBH_023_D", "Enemy Unit", 2, 1, 4, Arena.GROUND)
        game.player1.units.extend([rieekan, hero])
        game.player1.ground_arena.extend([rieekan, hero])
        game.player2.units.append(defender)
        game.player2.ground_arena.append(defender)

        self.assertTrue(game.execute_action(game.player1, f"unit_action_{rieekan.id}"))
        self.assertEqual(defender.current_hp, 0)

    def test_hoth_lieutenant_attacks_with_bonus_on_play(self):
        game = game_state()
        lieutenant = UnitCard("IBH_064_1", "Hoth Lieutenant", 3, 2, 4, Arena.GROUND)
        ally = UnitCard("IBH_064_A", "Echo Trooper", 2, 2, 4, Arena.GROUND)
        defender = UnitCard("IBH_064_D", "Enemy Unit", 2, 1, 4, Arena.GROUND)
        game.player1.units.append(ally)
        game.player1.ground_arena.append(ally)
        game.player2.units.append(defender)
        game.player2.ground_arena.append(defender)

        self.assertTrue(game._play_unit(game.player1, lieutenant))
        self.assertEqual(defender.current_hp, 0)

    def test_diversion_grants_sentinel_for_phase(self):
        game = game_state()
        target = UnitCard("JTL_229_T", "Guard", 2, 2, 4, Arena.GROUND)
        event = EventCard("JTL_229_1", "Diversion", 1, effect="Give a unit Sentinel for this phase.")
        game.player1.units.append(target)
        game.player1.ground_arena.append(target)

        game._resolve_event(game.player1, event)
        self.assertTrue(game._has_keyword(target, "sentinel"))
        game._clear_phase_modifiers(game.player1)
        self.assertFalse(game._has_keyword(target, "sentinel"))

    def test_desperate_commando_gives_negative_phase_modifier_on_defeat(self):
        game = game_state()
        commando = UnitCard("JTL_060_1", "Desperate Commando", 2, 2, 2, Arena.GROUND)
        target = UnitCard("JTL_060_T", "Target Unit", 2, 3, 3, Arena.GROUND)
        game.player1.units.append(commando)
        game.player1.ground_arena.append(commando)
        game.player2.units.append(target)
        game.player2.ground_arena.append(target)

        game._remove_unit(game.player1, commando)
        self.assertEqual(target.power, 2)
        self.assertEqual(target.hp, 2)

    def test_captain_phasma_buffs_another_first_order_unit(self):
        game = game_state()
        phasma = UnitCard("JTL_088_1", "Captain Phasma", 5, 5, 6, Arena.GROUND, traits=["FIRST ORDER", "TROOPER"])
        ally = UnitCard("JTL_088_A", "First Order Scout", 2, 2, 3, Arena.GROUND, traits=["FIRST ORDER"])
        game.player1.units.append(ally)
        game.player1.ground_arena.append(ally)

        self.assertTrue(game._play_unit(game.player1, phasma))
        self.assertEqual(ally.power, 4)
        self.assertEqual(ally.hp, 5)

    def test_ibh_han_solo_reduces_defender_power_for_this_attack(self):
        game = game_state()
        han = UnitCard("IBH_10_1", "Han Solo", 4, 3, 4, Arena.GROUND, traits=["REBEL"])
        defender = UnitCard("IBH_10_D", "Guard", 2, 3, 5, Arena.GROUND)
        game.player1.units.append(han)
        game.player1.ground_arena.append(han)
        game.player2.units.append(defender)
        game.player2.ground_arena.append(defender)

        self.assertTrue(game._attack(game.player1, han.id, defender.id))
        self.assertEqual(han.current_hp, 3)

    def test_attack_with_unit_tuning_can_grant_keyword_and_block_base_attack(self):
        game = game_state()
        attacker = UnitCard("ATK_TUNE_1", "Raider", 2, 2, 4, Arena.GROUND)
        game.player1.units.append(attacker)
        game.player1.ground_arena.append(attacker)

        self.assertFalse(game._attack_with_unit_tuning(
            game.player1,
            attacker,
            power_bonus=2,
            keywords={"saboteur"},
            can_attack_base=False,
        ))
        self.assertEqual(attacker.temporary_attack_power_bonus, 0)
        self.assertFalse(game._has_keyword(attacker, "saboteur"))

    def test_attack_with_unit_tuning_can_attack_exhausted_unit(self):
        game = game_state()
        attacker = UnitCard("ATK_TUNE_2", "Tired Fighter", 2, 2, 4, Arena.GROUND)
        defender = UnitCard("ATK_TUNE_2_D", "Blocker", 2, 1, 3, Arena.GROUND)
        attacker.is_exhausted = True
        game.player1.units.append(attacker)
        game.player1.ground_arena.append(attacker)
        game.player2.units.append(defender)
        game.player2.ground_arena.append(defender)

        self.assertTrue(game._attack_with_unit_tuning(game.player1, attacker, allow_exhausted=True))
        self.assertTrue(attacker.is_exhausted)

    def test_structured_attack_with_unit_supports_combined_mechanics(self):
        game = game_state()
        attacker = UnitCard("ATK_STRUCT_2", "Space Ace", 2, 2, 4, Arena.SPACE)
        defender = UnitCard("ATK_STRUCT_2_D", "Enemy Ace", 2, 1, 4, Arena.SPACE)
        game.player1.units.append(attacker)
        game.player1.space_arena.append(attacker)
        game.player2.units.append(defender)
        game.player2.space_arena.append(defender)
        step = {
            "type": "attack_with_unit",
            "power": 2,
            "target": {"controller": "friendly", "type": "unit"},
            "keywords": ["saboteur"],
            "combat_damage_before_defender": True,
        }

        game._apply_structured_step(game.player1, attacker, step)
        self.assertNotIn(defender, game.player2.units)
        self.assertEqual(attacker.current_hp, 4)

    def test_dogfight_attacks_exhausted_unit_and_cannot_hit_base(self):
        game = game_state()
        fighter = UnitCard("JTL_123_F", "Dogfighter", 2, 2, 4, Arena.SPACE)
        enemy = UnitCard("JTL_123_E", "Enemy Ship", 2, 1, 2, Arena.SPACE)
        event = EventCard("JTL_123_1", "Dogfight", 1, effect="Attack with a unit, even if it's exhausted. That unit can't attack bases for this attack.")
        fighter.is_exhausted = True
        game.player1.units.append(fighter)
        game.player1.space_arena.append(fighter)
        game.player2.units.append(enemy)
        game.player2.space_arena.append(enemy)

        game._resolve_event(game.player1, event)
        self.assertNotIn(enemy, game.player2.units)
        self.assertTrue(fighter.is_exhausted)

    def test_rio_durant_action_attacks_space_unit_with_saboteur_bonus(self):
        leader = LeaderCard(
            "JTL_015",
            "Rio Durant",
            5,
            action_cost=1,
            action_effect="Action [C=1, Exhaust]: Attack with a space unit. It gets +1/+0 and gains Saboteur for this attack.",
            epic_action_cost=5,
            epic_action_effect="Deploy as 3/5 unit",
        )
        game = GameState([], [], leader, LeaderCard("LDR_002", "Leader Two", 6), verbose=False)
        ship = UnitCard("JTL_015_S", "Scout Craft", 2, 2, 4, Arena.SPACE)
        enemy = UnitCard("JTL_015_E", "Enemy Ship", 2, 1, 3, Arena.SPACE)
        game.player1.units.append(ship)
        game.player1.space_arena.append(ship)
        game.player2.units.append(enemy)
        game.player2.space_arena.append(enemy)
        game.player1.resources = [Resource(CardStub("R1"))]

        self.assertTrue(game.execute_action(game.player1, "leader_action_JTL_015"))
        self.assertNotIn(enemy, game.player2.units)

    def test_precision_fire_gives_trooper_bonus_and_saboteur(self):
        game = game_state()
        trooper = UnitCard("SOR_168_T", "Trooper", 2, 2, 4, Arena.GROUND, traits=["TROOPER"])
        enemy = UnitCard("SOR_168_E", "Enemy", 2, 1, 4, Arena.GROUND)
        event = EventCard("SOR_168_1", "Precision Fire", 1, effect="Attack with a unit. It gains Saboteur for this attack. If it's a TROOPER, it also gains +2/+0 for this attack.")
        game.player1.units.append(trooper)
        game.player1.ground_arena.append(trooper)
        game.player2.units.append(enemy)
        game.player2.ground_arena.append(enemy)

        game._resolve_event(game.player1, event)
        self.assertNotIn(enemy, game.player2.units)

    def test_commence_the_festivities_uses_resource_gap_for_bonus(self):
        game = game_state()
        attacker = UnitCard("LAW_202_A", "Attacker", 2, 2, 4, Arena.GROUND)
        enemy = UnitCard("LAW_202_E", "Enemy", 2, 1, 4, Arena.GROUND)
        event = EventCard("LAW_202_1", "Commence the Festivities", 1, effect="Attack with a unit. It gains Saboteur for this attack. If you control fewer resources than an opponent, it gets +2/+0 for this attack.")
        game.player1.units.append(attacker)
        game.player1.ground_arena.append(attacker)
        game.player2.units.append(enemy)
        game.player2.ground_arena.append(enemy)
        game.player1.resources = [Resource(CardStub("R1"))]
        game.player2.resources = [Resource(CardStub("R2")), Resource(CardStub("R3"))]

        game._resolve_event(game.player1, event)
        self.assertNotIn(enemy, game.player2.units)

    def test_breaking_in_attacks_with_bonus_and_saboteur(self):
        game = game_state()
        attacker = UnitCard("TWI_224_A", "Infiltrator", 2, 2, 4, Arena.GROUND)
        enemy = UnitCard("TWI_224_E", "Enemy", 2, 1, 4, Arena.GROUND)
        event = EventCard("TWI_224_1", "Breaking In", 2, effect="Attack with a unit. It gets +2/+0 and gains Saboteur for this attack.")
        game.player1.units.append(attacker)
        game.player1.ground_arena.append(attacker)
        game.player2.units.append(enemy)
        game.player2.ground_arena.append(enemy)

        game._resolve_event(game.player1, event)
        self.assertNotIn(enemy, game.player2.units)

    def test_trust_your_instincts_requires_force_token(self):
        game = game_state()
        attacker = UnitCard("LOF_221_A", "Jedi", 2, 2, 4, Arena.GROUND)
        enemy = UnitCard("LOF_221_E", "Enemy", 2, 4, 4, Arena.GROUND)
        event = EventCard("LOF_221_1", "Trust Your Instincts", 1, effect="Use the Force. If you do, attack with a unit. It gets +2/+0 for this attack and deals combat damage before the defender.")
        game.player1.units.append(attacker)
        game.player1.ground_arena.append(attacker)
        game.player2.units.append(enemy)
        game.player2.ground_arena.append(enemy)

        game._resolve_event(game.player1, event)
        self.assertIn(enemy, game.player2.units)

        game.player1.has_force_token = True
        game._resolve_event(game.player1, event)
        self.assertNotIn(enemy, game.player2.units)
        self.assertFalse(game.player1.has_force_token)

    def test_jtl_han_solo_leader_action_checks_odd_costs(self):
        leader = LeaderCard(
            "JTL_017",
            "Han Solo",
            5,
            action_cost=0,
            action_effect="Action [Exhaust]: Reveal the top card of your deck, then attack with a unit. If the revealed card and that unit have different odd costs, that unit gets +1/+0 for this attack.",
            epic_action_cost=5,
            epic_action_effect="Deploy as 3/7 unit",
        )
        leader.traits = ["REBEL", "PILOT"]
        game = GameState([], [], leader, LeaderCard("LDR_002", "Leader Two", 6), verbose=False)
        attacker = UnitCard("JTL_017_A", "Smuggler", 2, 2, 4, Arena.GROUND)
        enemy = UnitCard("JTL_017_E", "Enemy", 2, 1, 3, Arena.GROUND)
        revealed = EventCard("TOP_1", "Top Card", 1, effect="")
        game.player1.units.append(attacker)
        game.player1.ground_arena.append(attacker)
        game.player2.units.append(enemy)
        game.player2.ground_arena.append(enemy)
        game.player1.deck = [revealed]

        self.assertTrue(game.execute_action(game.player1, "leader_action_JTL_017"))
        self.assertNotIn(enemy, game.player2.units)

    def test_saw_gerrera_action_defeats_attacking_unit_after_attack(self):
        leader = LeaderCard(
            "LAW_001",
            "Saw Gerrera",
            6,
            action_cost=0,
            action_effect="Action [Exhaust]: Attack with a unit. It gets +2/+0 and gains Overwhelm for this attack. After completing this attack, defeat it.",
            epic_action_cost=6,
            epic_action_effect="Deploy as 4/7 unit",
        )
        game = GameState([], [], leader, LeaderCard("LDR_002", "Leader Two", 6), verbose=False)
        attacker = UnitCard("LAW_001_A", "Rebel Fighter", 2, 2, 4, Arena.GROUND)
        enemy = UnitCard("LAW_001_E", "Enemy", 2, 1, 4, Arena.GROUND)
        game.player1.units.append(attacker)
        game.player1.ground_arena.append(attacker)
        game.player2.units.append(enemy)
        game.player2.ground_arena.append(enemy)

        self.assertTrue(game.execute_action(game.player1, "leader_action_LAW_001"))
        self.assertNotIn(attacker, game.player1.units)

    def test_flash_the_vents_defeats_attacker_if_base_was_damaged(self):
        game = game_state()
        attacker = UnitCard("LAW_205_A", "Bruiser", 2, 2, 4, Arena.GROUND)
        event = EventCard("LAW_205_1", "Flash the Vents", 1, effect="Attack with a unit. It gets +2/+0 and gains Overwhelm for this attack. After completing this attack, if that unit damaged a base, defeat that unit.")
        game.player1.units.append(attacker)
        game.player1.ground_arena.append(attacker)

        game._resolve_event(game.player1, event)
        self.assertNotIn(attacker, game.player1.units)

    def test_one_way_out_strips_defender_abilities_for_attack(self):
        game = game_state()
        attacker = UnitCard("SEC_157_A", "Hero", 2, 2, 4, Arena.GROUND)
        defender = UnitCard("SEC_157_D", "Sentinel Defender", 2, 1, 4, Arena.GROUND, abilities=["Sentinel"])
        event = EventCard("SEC_157_1", "One Way Out", 1, effect="Attack with a unit. It gets +1/+0 and gains Overwhelm for this attack. If it attacks a unit, the defender loses all abilities for this attack.")
        game.player1.units.append(attacker)
        game.player1.ground_arena.append(attacker)
        game.player2.units.append(defender)
        game.player2.ground_arena.append(defender)

        game._resolve_event(game.player1, event)
        self.assertFalse(defender.temporary_attack_abilities_suppressed)

    def test_maul_action_grants_overwhelm_for_attack(self):
        leader = LeaderCard(
            "TWI_009",
            "Maul",
            6,
            action_cost=0,
            action_effect="Action [Exhaust]: Attack with a unit. It gains Overwhelm for this attack.",
            epic_action_cost=6,
            epic_action_effect="Deploy as 6/6 unit",
        )
        game = GameState([], [], leader, LeaderCard("LDR_002", "Leader Two", 6), verbose=False)
        attacker = UnitCard("TWI_009_A", "Bruiser", 2, 2, 4, Arena.GROUND)
        defender = UnitCard("TWI_009_D", "Wall", 2, 1, 1, Arena.GROUND)
        game.player1.units.append(attacker)
        game.player1.ground_arena.append(attacker)
        game.player2.units.append(defender)
        game.player2.ground_arena.append(defender)

        self.assertTrue(game.execute_action(game.player1, "leader_action_TWI_009"))
        self.assertLess(game.player2.base.current_hp, 25)

    def test_asajj_action_uses_event_phase_bonus(self):
        leader = LeaderCard(
            "TWI_014",
            "Asajj Ventress",
            4,
            action_cost=0,
            action_effect="Action [Exhaust]: Attack with a unit. If you played an event this phase, it gets +1/+0 for this attack.",
            epic_action_cost=4,
            epic_action_effect="Deploy as 3/4 unit",
        )
        game = GameState([], [], leader, LeaderCard("LDR_002", "Leader Two", 6), verbose=False)
        attacker = UnitCard("TWI_014_A", "Assassin", 2, 2, 4, Arena.GROUND)
        enemy = UnitCard("TWI_014_E", "Enemy", 2, 1, 3, Arena.GROUND)
        event = EventCard("TWI_014_EVT", "Setup Event", 1, effect="No-op")
        game.player1.units.append(attacker)
        game.player1.ground_arena.append(attacker)
        game.player2.units.append(enemy)
        game.player2.ground_arena.append(enemy)
        game._record_played_card(game.player1, event)

        self.assertTrue(game.execute_action(game.player1, "leader_action_TWI_014"))
        self.assertNotIn(enemy, game.player2.units)

    def test_obi_wan_action_requires_force_and_gives_experience(self):
        leader = LeaderCard(
            "LOF_008",
            "Obi-Wan Kenobi",
            5,
            action_cost=0,
            action_effect="Action [Exhaust, use the Force]: Give an Experience token to a unit without an Experience token on it.",
            epic_action_cost=5,
            epic_action_effect="Deploy as 3/6 unit",
        )
        leader.traits = ["FORCE", "JEDI", "REPUBLIC"]
        leader.abilities = [
            "Action [Exhaust, use the Force]: Give an Experience token to a unit without an Experience token on it.",
            "On Attack: You may give an Experience token to another unit without an Experience token on it.",
        ]
        game = GameState([], [], leader, LeaderCard("LDR_002", "Leader Two", 6), verbose=False)
        ally = UnitCard("LOF_008_A", "Clone Trooper", 2, 2, 2, Arena.GROUND)
        game.player1.units.append(ally)
        game.player1.ground_arena.append(ally)

        self.assertNotIn("leader_action_LOF_008", game.get_legal_actions(game.player1))

        game.player1.has_force_token = True
        self.assertIn("leader_action_LOF_008", game.get_legal_actions(game.player1))
        self.assertTrue(game.execute_action(game.player1, "leader_action_LOF_008"))
        self.assertFalse(game.player1.has_force_token)
        self.assertEqual(ally.experience_tokens, 1)
        self.assertEqual(ally.power, 3)
        self.assertEqual(ally.hp, 3)

    def test_obi_wan_on_attack_gives_experience_to_another_unit(self):
        leader = LeaderCard(
            "LOF_008",
            "Obi-Wan Kenobi",
            5,
            action_cost=0,
            action_effect="Action [Exhaust, use the Force]: Give an Experience token to a unit without an Experience token on it.",
            epic_action_cost=5,
            epic_action_effect="Deploy as 3/6 unit",
        )
        leader.traits = ["FORCE", "JEDI", "REPUBLIC"]
        leader.abilities = [
            "Action [Exhaust, use the Force]: Give an Experience token to a unit without an Experience token on it.",
            "On Attack: You may give an Experience token to another unit without an Experience token on it.",
        ]
        game = GameState([], [], leader, LeaderCard("LDR_002", "Leader Two", 6), verbose=False)
        ally = UnitCard("LOF_008_B", "Padawan", 2, 2, 3, Arena.GROUND)
        defender = UnitCard("LOF_008_D", "Enemy Unit", 2, 1, 1, Arena.GROUND)
        game.player1.units.append(ally)
        game.player1.ground_arena.append(ally)
        game.player2.units.append(defender)
        game.player2.ground_arena.append(defender)
        game.player1.resources = [Resource(CardStub("R1")), Resource(CardStub("R2")), Resource(CardStub("R3")), Resource(CardStub("R4")), Resource(CardStub("R5"))]

        self.assertTrue(game.execute_action(game.player1, "leader_epic_LOF_008"))
        self.assertTrue(game._attack(game.player1, leader.id, defender.id))
        self.assertEqual(ally.experience_tokens, 1)
        self.assertEqual(ally.power, 3)

    def test_kanan_leader_action_shields_creature_or_spectre(self):
        leader = LeaderCard(
            "LOF_004",
            "Kanan Jarrus",
            6,
            action_cost=1,
            action_effect="Action [C=1, Exhaust]: Give a Shield token to a Creature or Spectre unit.",
            epic_action_cost=6,
            epic_action_effect="Deploy as 3/6 unit",
        )
        leader.traits = ["FORCE", "JEDI", "REBEL", "SPECTRE"]
        leader.abilities = [
            "Action [C=1, Exhaust]: Give a Shield token to a Creature or Spectre unit.",
            "Shielded",
            "While you control another Creature or Spectre unit, this unit gets +2/+2.",
        ]
        game = GameState([], [], leader, LeaderCard("LDR_002", "Leader Two", 6), verbose=False)
        spectre = UnitCard("LOF_004_S", "Spectre Ally", 2, 2, 3, Arena.GROUND, traits=["SPECTRE"])
        game.player1.units.append(spectre)
        game.player1.ground_arena.append(spectre)
        game.player1.resources = [Resource(CardStub("R1"))]

        self.assertIn("leader_action_LOF_004", game.get_legal_actions(game.player1))
        self.assertTrue(game.execute_action(game.player1, "leader_action_LOF_004"))
        self.assertEqual(spectre.shield_tokens, 1)

    def test_kanan_deploy_gets_shield_and_continuous_bonus(self):
        leader = LeaderCard(
            "LOF_004",
            "Kanan Jarrus",
            6,
            action_cost=1,
            action_effect="Action [C=1, Exhaust]: Give a Shield token to a Creature or Spectre unit.",
            epic_action_cost=6,
            epic_action_effect="Deploy as 3/6 unit",
        )
        leader.traits = ["FORCE", "JEDI", "REBEL", "SPECTRE"]
        leader.abilities = [
            "Action [C=1, Exhaust]: Give a Shield token to a Creature or Spectre unit.",
            "Shielded",
            "While you control another Creature or Spectre unit, this unit gets +2/+2.",
        ]
        game = GameState([], [], leader, LeaderCard("LDR_002", "Leader Two", 6), verbose=False)
        ally = UnitCard("LOF_004_A", "Creature Ally", 2, 1, 1, Arena.GROUND, traits=["CREATURE"])
        game.player1.units.append(ally)
        game.player1.ground_arena.append(ally)
        game.player1.resources = [
            Resource(CardStub("R1")), Resource(CardStub("R2")), Resource(CardStub("R3")),
            Resource(CardStub("R4")), Resource(CardStub("R5")), Resource(CardStub("R6")),
        ]

        self.assertTrue(game.execute_action(game.player1, "leader_epic_LOF_004"))
        self.assertEqual(leader.shield_tokens, 1)
        self.assertEqual(leader.power, 5)
        self.assertEqual(leader.hp, 8)

        game._remove_unit(game.player1, ally)
        self.assertEqual(leader.power, 3)
        self.assertEqual(leader.hp, 6)

    def test_aurra_sing_action_defeats_weakened_unit(self):
        leader = LeaderCard(
            "LAW_004",
            "Aurra Sing",
            7,
            action_cost=0,
            action_effect="Action [Exhaust]: Defeat a non-leader unit with 1 or less remaining HP.",
            epic_action_cost=7,
            epic_action_effect="Deploy as 3/7 unit",
        )
        leader.traits = ["UNDERWORLD", "BOUNTY HUNTER"]
        leader.abilities = [
            "Action [Exhaust]: Defeat a non-leader unit with 1 or less remaining HP.",
            "When Deployed: You may defeat a non-leader unit with 5 or less remaining HP.",
        ]
        game = GameState([], [], leader, LeaderCard("LDR_002", "Leader Two", 6), verbose=False)
        target = UnitCard("LAW_004_T", "Wounded Enemy", 4, 4, 4, Arena.GROUND)
        target.current_hp = 1
        target.damage = 3
        game.player2.units.append(target)
        game.player2.ground_arena.append(target)

        self.assertIn("leader_action_LAW_004", game.get_legal_actions(game.player1))
        self.assertTrue(game.execute_action(game.player1, "leader_action_LAW_004"))
        self.assertNotIn(target, game.player2.units)

    def test_aurra_sing_deploy_defeats_unit_with_five_or_less_hp(self):
        leader = LeaderCard(
            "LAW_004",
            "Aurra Sing",
            7,
            action_cost=0,
            action_effect="Action [Exhaust]: Defeat a non-leader unit with 1 or less remaining HP.",
            epic_action_cost=7,
            epic_action_effect="Deploy as 3/7 unit",
        )
        leader.traits = ["UNDERWORLD", "BOUNTY HUNTER"]
        leader.abilities = [
            "Action [Exhaust]: Defeat a non-leader unit with 1 or less remaining HP.",
            "When Deployed: You may defeat a non-leader unit with 5 or less remaining HP.",
        ]
        game = GameState([], [], leader, LeaderCard("LDR_002", "Leader Two", 6), verbose=False)
        target = UnitCard("LAW_004_D", "Enemy Unit", 5, 5, 5, Arena.GROUND)
        game.player2.units.append(target)
        game.player2.ground_arena.append(target)
        game.player1.resources = [
            Resource(CardStub("R1")), Resource(CardStub("R2")), Resource(CardStub("R3")),
            Resource(CardStub("R4")), Resource(CardStub("R5")), Resource(CardStub("R6")),
            Resource(CardStub("R7")),
        ]

        self.assertTrue(game.execute_action(game.player1, "leader_epic_LAW_004"))
        self.assertNotIn(target, game.player2.units)

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

    def test_drain_essence_deals_damage_and_gains_force_token(self):
        game = game_state()
        target = UnitCard("LOF_041_T", "Enemy Unit", 2, 3, 3, Arena.GROUND)
        larger = UnitCard("LOF_041_L", "Large Enemy", 4, 5, 6, Arena.GROUND)
        event = EventCard("LOF_041_1", "Drain Essence", 2, effect="Deal 2 damage to a unit. The Force is with you.")
        game.player2.units.extend([target, larger])
        game.player2.ground_arena.extend([target, larger])

        game._resolve_event(game.player1, event)

        self.assertEqual(target.current_hp, 1)
        self.assertEqual(larger.current_hp, 6)
        self.assertTrue(game.player1.has_force_token)

    def test_no_disintegrations_leaves_non_leader_unit_at_one_hp(self):
        game = game_state()
        target = UnitCard("JTL_144_T", "Target Unit", 4, 4, 5, Arena.GROUND)
        smaller = UnitCard("JTL_144_S", "Smaller Unit", 2, 2, 3, Arena.GROUND)
        event = EventCard("JTL_144_1", "No Disintegrations", 3, effect="Deal damage to a non-leader unit equal to 1 less than its remaining HP.")
        game.player2.units.extend([target, smaller])
        game.player2.ground_arena.extend([target, smaller])

        game._resolve_event(game.player1, event)

        self.assertEqual(target.current_hp, 1)
        self.assertEqual(smaller.current_hp, 3)

    def test_lost_and_forgotten_defeats_enemy_unit_and_heals_base(self):
        game = game_state()
        target = UnitCard("LAW_133_T", "Enemy Unit", 5, 4, 6, Arena.GROUND)
        event = EventCard("LAW_133_1", "Lost and Forgotten", 6, effect="Defeat a non-leader unit. If you do, heal 3 damage from your base.")
        game.player1.base.current_hp = 20
        game.player2.units.append(target)
        game.player2.ground_arena.append(target)

        game._resolve_event(game.player1, event)

        self.assertNotIn(target, game.player2.units)
        self.assertEqual(game.player1.base.current_hp, 23)

    def test_jyn_erso_prefers_exhausting_ready_enemy_unit(self):
        game = game_state()
        jyn = UnitCard("LAW_067_1", "Jyn Erso", 2, 2, 2, Arena.GROUND)
        enemy = UnitCard("LAW_067_E", "Enemy Unit", 3, 4, 4, Arena.GROUND)
        game.player2.units.append(enemy)
        game.player2.ground_arena.append(enemy)

        game._play_unit(game.player1, jyn)

        self.assertTrue(enemy.is_exhausted)
        self.assertEqual(jyn.experience_tokens, 0)

    def test_jyn_erso_falls_back_to_experience_when_no_ready_enemy_exists(self):
        game = game_state()
        jyn = UnitCard("LAW_067_1", "Jyn Erso", 2, 2, 2, Arena.GROUND)
        ally = UnitCard("LAW_067_A", "Friendly Unit", 2, 3, 3, Arena.GROUND)
        enemy = UnitCard("LAW_067_E", "Tired Enemy", 4, 5, 5, Arena.GROUND)
        enemy.is_exhausted = True
        game.player1.units.append(ally)
        game.player1.ground_arena.append(ally)
        game.player2.units.append(enemy)
        game.player2.ground_arena.append(enemy)

        game._play_unit(game.player1, jyn)

        self.assertEqual(ally.experience_tokens, 1)
        self.assertEqual(ally.power, 4)
        self.assertEqual(ally.hp, 4)

    def test_kanan_jarrus_bounces_larger_unit_with_command_or_aggression_support(self):
        game = game_state()
        kanan = UnitCard("LAW_089_1", "Kanan Jarrus", 4, 3, 4, Arena.GROUND)
        support = UnitCard("LAW_089_S", "Command Support", 2, 2, 3, Arena.GROUND)
        support.aspects = ["Command"]
        target = UnitCard("LAW_089_T", "Enemy Unit", 4, 4, 4, Arena.GROUND)
        game.player1.units.append(support)
        game.player1.ground_arena.append(support)
        game.player2.units.append(target)
        game.player2.ground_arena.append(target)

        game._play_unit(game.player1, kanan)

        self.assertNotIn(target, game.player2.units)
        self.assertIn(target, game.player2.hand)

    def test_red_five_deals_on_attack_damage_to_damaged_unit(self):
        game = game_state()
        red_five = UnitCard("JTL_151_1", "Red Five", 3, 3, 4, Arena.SPACE)
        defender = UnitCard("JTL_151_D", "Defender", 2, 2, 4, Arena.SPACE)
        damaged = UnitCard("JTL_151_X", "Damaged Enemy", 2, 1, 2, Arena.SPACE)
        damaged.damage = 1
        damaged.current_hp = 1
        game.player1.units.append(red_five)
        game.player1.space_arena.append(red_five)
        game.player2.units.extend([defender, damaged])
        game.player2.space_arena.extend([defender, damaged])

        self.assertTrue(game._attack(game.player1, red_five.id, defender.id))
        self.assertNotIn(damaged, game.player2.units)

    def test_karis_uses_force_token_on_defeat_to_weaken_a_unit(self):
        game = game_state()
        karis = UnitCard("LOF_031_1", "Karis", 2, 2, 4, Arena.GROUND)
        target = UnitCard("LOF_031_T", "Enemy Unit", 3, 4, 4, Arena.GROUND)
        game.player1.has_force_token = True
        game.player1.units.append(karis)
        game.player1.ground_arena.append(karis)
        game.player2.units.append(target)
        game.player2.ground_arena.append(target)

        game._remove_unit(game.player1, karis)

        self.assertFalse(game.player1.has_force_token)
        self.assertEqual(target.power, 2)
        self.assertEqual(target.hp, 2)

    def test_nightsister_warrior_draws_on_defeat(self):
        game = game_state()
        warrior = UnitCard("LOF_059_1", "Nightsister Warrior", 2, 2, 2, Arena.GROUND)
        draw_card = UnitCard("DRAW_059", "Drawn Card", 1, 1, 1, Arena.GROUND)
        game.player1.deck = [draw_card]
        game.player1.units.append(warrior)
        game.player1.ground_arena.append(warrior)

        game._remove_unit(game.player1, warrior)

        self.assertIn(draw_card, game.player1.hand)


class CardStub:
    def __init__(self, card_id: str):
        self.id = card_id
        self.name = card_id
        self.cost = 0


if __name__ == "__main__":
    unittest.main()
