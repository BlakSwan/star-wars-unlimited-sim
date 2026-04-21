"""Star Wars Unlimited - Sample Card Database
Sample cards from the Spark of Rebellion set for simulation testing
"""

from models import *


def create_sample_decks():
    """Create two sample decks for testing"""
    
    # ==================== REBEL ALLIANCE DECK ====================
    rebel_cards = [
        # Units - Ground
        UnitCard("U01", "Alliance X-Wing", 3, power=2, hp=3, arena=Arena.SPACE, 
                 traits=["Starfighter"], abilities=["Ambush"], has_ambush=True),
        UnitCard("U02", "Rebel Pathfinders", 2, power=2, hp=2, arena=Arena.GROUND,
                 traits=["Rebel", "Soldier"]),
        UnitCard("U03", "Luke Skywalker (Jedi Knight)", 4, power=4, hp=4, arena=Arena.GROUND,
                 traits=["Jedi", "Hero"], abilities=["Shield"]),
        UnitCard("U04", "Chewbacca", 4, power=4, hp=5, arena=Arena.GROUND,
                 traits=["Wookiee", "Hero"]),
        UnitCard("U05", "Snowspeeder", 3, power=2, hp=2, arena=Arena.GROUND,
                 traits=["Vehicle"], abilities=["Ambush"], has_ambush=True),
        UnitCard("U06", "Rebel Commando", 2, power=2, hp=2, arena=Arena.GROUND,
                 traits=["Rebel", "Soldier"]),
        UnitCard("U07", "T-65 X-Wing", 4, power=3, hp=4, arena=Arena.SPACE,
                 traits=["Starfighter"]),
        UnitCard("U08", "R2-D2", 1, power=1, hp=1, arena=Arena.SPACE,
                 traits=["Droid"], abilities=["When Played: Draw a card"]),
        UnitCard("U09", "Gold Leader", 3, power=3, hp=3, arena=Arena.SPACE,
                 traits=["Pilot", "Rebel"]),
        UnitCard("U10", "Wedge Antilles", 3, power=3, hp=2, arena=Arena.SPACE,
                 traits=["Pilot", "Rebel"], abilities=["Ambush"], has_ambush=True),
        
        # Upgrades
        UpgradeCard("UP01", "Luke's Lightsaber", 2, power_bonus=3, hp_bonus=1,
                    abilities=["When attached to Luke: Heal fully, gain Shield"]),
        UpgradeCard("UP02", "Blaster Rifle", 2, power_bonus=2, hp_bonus=0),
        UpgradeCard("UP03", "Combat Shield", 2, power_bonus=0, hp_bonus=2),
        UpgradeCard("UP04", "Flight Helmet", 1, power_bonus=1, hp_bonus=1),
        
        # Events
        EventCard("E01", "Rebel Assault", 3, effect="Deal 2 damage to all enemy units in one arena"),
        EventCard("E02", "Inspiring Speech", 2, effect="Give +1/+1 to all your units"),
        EventCard("E03", "Tactical Strike", 2, effect="Deal 3 damage to a unit"),
        EventCard("E04", "Cover Fire", 1, effect="Give a unit +2 power this turn"),
        EventCard("E05", "Energy Discharge", 2, effect="Deal 2 damage"),
    ]
    
    # Duplicate cards to make a proper deck size (40+ cards)
    rebel_deck = rebel_cards.copy()
    # Add more copies of key cards
    for copy_num in range(2):
        suffix = copy_num + 1
        rebel_deck.append(UnitCard(f"U01b{suffix}", "Alliance X-Wing", 3, power=2, hp=3, arena=Arena.SPACE, 
                                   traits=["Starfighter"], abilities=["Ambush"], has_ambush=True))
        rebel_deck.append(UnitCard(f"U02b{suffix}", "Rebel Pathfinders", 2, power=2, hp=2, arena=Arena.GROUND,
                                   traits=["Rebel", "Soldier"]))
        rebel_deck.append(UnitCard(f"U06b{suffix}", "Rebel Commando", 2, power=2, hp=2, arena=Arena.GROUND,
                                   traits=["Rebel", "Soldier"]))
        rebel_deck.append(EventCard(f"E04b{suffix}", "Cover Fire", 1, effect="Give a unit +2 power this turn"))
        rebel_deck.append(EventCard(f"E05b{suffix}", "Energy Discharge", 2, effect="Deal 2 damage"))
    
    # ==================== IMPERIAL DECK ====================
    imperial_cards = [
        # Units - Space
        UnitCard("IU01", "TIE/ln Fighter", 1, power=1, hp=1, arena=Arena.SPACE,
                 traits=["TIE"], abilities=["Swarm"]),
        UnitCard("IU02", "TIE Interceptor", 3, power=3, hp=2, arena=Arena.SPACE,
                 traits=["TIE"], abilities=["Ambush"], has_ambush=True),
        UnitCard("IU03", "Imperial Interceptor", 3, power=3, hp=2, arena=Arena.SPACE,
                 traits=["TIE"], abilities=["When Played: Deal 3 damage to a space unit"]),
        UnitCard("IU04", "Darth Vader (Sith Lord)", 5, power=5, hp=5, arena=Arena.GROUND,
                 traits=["Sith", "Villain"]),
        UnitCard("IU05", "Stormtrooper", 2, power=2, hp=2, arena=Arena.GROUND,
                 traits=["Imperial", "Soldier"]),
        UnitCard("IU06", "Snowtrooper", 2, power=2, hp=3, arena=Arena.GROUND,
                 traits=["Imperial", "Soldier"]),
        UnitCard("IU07", "AT-ST", 4, power=4, hp=4, arena=Arena.GROUND,
                 traits=["Vehicle"]),
        UnitCard("IU08", "Viper Probe Droid", 1, power=1, hp=1, arena=Arena.SPACE,
                 traits=["Droid"], abilities=["When Played: Look at opponent's hand"]),
        UnitCard("IU09", "Admiral Ozzel", 3, power=2, hp=3, arena=Arena.SPACE,
                 traits=["Imperial", "Officer"],
                 abilities=["Action: Exhaust to play Imperial unit ready"]),
        UnitCard("IU10", "Grand Admiral Thrawn", 4, power=3, hp=4, arena=Arena.SPACE,
                 traits=["Imperial", "Officer"]),
        
        # Upgrades
        UpgradeCard("IUP01", "Vader's Lightsaber", 3, power_bonus=4, hp_bonus=0,
                    abilities=["When attached to Vader: Deal 4 damage to a ground unit"]),
        UpgradeCard("IUP02", "Dark Force", 2, power_bonus=2, hp_bonus=1),
        UpgradeCard("IUP03", "Targeting Computer", 2, power_bonus=2, hp_bonus=0),
        UpgradeCard("IUP04", "Armor Plating", 2, power_bonus=0, hp_bonus=3),
        
        # Events
        EventCard("IE01", "Imperial Assault", 3, effect="Deal 2 damage to all enemy units in one arena"),
        EventCard("IE02", "Force Choke", 3, effect="Deal 4 damage to a unit"),
        EventCard("IE03", "Tractor Beam", 2, effect="Exhaust a unit"),
        EventCard("IE04", "Precision Strike", 2, effect="Deal 3 damage to a unit"),
        EventCard("IE05", "Power Surge", 2, effect="Give a unit +2 power this turn"),
    ]
    
    # Duplicate cards for imperial deck
    imperial_deck = imperial_cards.copy()
    for copy_num in range(2):
        suffix = copy_num + 1
        imperial_deck.append(UnitCard(f"IU01b{suffix}", "TIE/ln Fighter", 1, power=1, hp=1, arena=Arena.SPACE,
                                      traits=["TIE"]))
        imperial_deck.append(UnitCard(f"IU05b{suffix}", "Stormtrooper", 2, power=2, hp=2, arena=Arena.GROUND,
                                      traits=["Imperial", "Soldier"]))
        imperial_deck.append(UnitCard(f"IU06b{suffix}", "Snowtrooper", 2, power=2, hp=3, arena=Arena.GROUND,
                                      traits=["Imperial", "Soldier"]))
        imperial_deck.append(EventCard(f"IE04b{suffix}", "Precision Strike", 2, effect="Deal 3 damage to a unit"))
        imperial_deck.append(EventCard(f"IE05b{suffix}", "Power Surge", 2, effect="Give a unit +2 power this turn"))
    
    return rebel_deck, imperial_deck


def get_rebel_leader():
    """Get the default Rebel leader"""
    return LeaderCard("L01", "Luke Skywalker", 4,
                      action_cost=1, action_effect="Heal 1 from a unit",
                      epic_action_cost=6, epic_action_effect="Deploy as 4/4 unit")


def get_imperial_leader():
    """Get the default Imperial leader"""
    return LeaderCard("LI01", "Darth Vader", 5,
                      action_cost=2, action_effect="Deal 2 damage to a unit",
                      epic_action_cost=8, epic_action_effect="Deploy as 5/5 unit")


# Card lookup by ID for debugging
CARD_REGISTRY = {}


def register_cards():
    """Register all cards for lookup"""
    rebel, imperial = create_sample_decks()
    for card in rebel + imperial:
        CARD_REGISTRY[card.id] = card


register_cards()
