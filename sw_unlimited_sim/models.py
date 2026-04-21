"""Star Wars Unlimited - Core Game Models"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List
import random


class CardType(Enum):
    UNIT = "unit"
    UPGRADE = "upgrade"
    EVENT = "event"


class Arena(Enum):
    GROUND = "ground"
    SPACE = "space"
    NONE = "none"


class Phase(Enum):
    ACTION = "action"
    REGROUP = "regroup"


@dataclass
class Card:
    """Base card class"""
    id: str
    name: str
    cost: int
    card_type: CardType
    
    def __repr__(self):
        return f"{self.name} ({self.cost})"


@dataclass
class UnitCard(Card):
    """Unit card with combat stats"""
    power: int
    hp: int
    arena: Arena
    traits: List[str] = field(default_factory=list)
    abilities: List[str] = field(default_factory=list)
    has_ambush: bool = False
    
    def __init__(self, id, name, cost, power, hp, arena, traits=None, abilities=None, has_ambush=False):
        super().__init__(id, name, cost, CardType.UNIT)
        self.power = power
        self.hp = hp
        self.arena = arena
        self.traits = traits or []
        self.abilities = abilities or []
        self.has_ambush = has_ambush
        self.current_hp = hp
        self.damage = 0
    
    def take_damage(self, amount: int) -> int:
        """Apply damage, return actual damage taken"""
        actual = min(amount, self.current_hp)
        self.damage += actual
        self.current_hp -= actual
        return actual
    
    def is_defeated(self) -> bool:
        return self.current_hp <= 0
    
    def heal(self, amount: int = None):
        """Heal unit (full heal if amount is None)"""
        if amount is None:
            self.damage = 0
            self.current_hp = self.hp
        else:
            self.current_hp = min(self.hp, self.current_hp + amount)
            self.damage = max(0, self.damage - amount)


@dataclass
class UpgradeCard(Card):
    """Upgrade card that attaches to a unit"""
    power_bonus: int = 0
    hp_bonus: int = 0
    attached_to: Optional[UnitCard] = None
    abilities: List[str] = field(default_factory=list)
    
    def __init__(self, id, name, cost, power_bonus=0, hp_bonus=0, abilities=None):
        super().__init__(id, name, cost, CardType.UPGRADE)
        self.power_bonus = power_bonus
        self.hp_bonus = hp_bonus
        self.abilities = abilities or []


@dataclass
class EventCard(Card):
    """Event card with immediate effect"""
    effect: str = ""
    
    def __init__(self, id, name, cost, effect=""):
        super().__init__(id, name, cost, CardType.EVENT)
        self.effect = effect


@dataclass
class LeaderCard(Card):
    """Leader card with action and epic action"""
    action_cost: int = 0
    action_effect: str = ""
    epic_action_cost: int = 0
    epic_action_effect: str = ""
    is_deployed: bool = False
    epic_action_used: bool = False
    
    def __init__(self, id, name, cost, action_cost=0, action_effect="", 
                 epic_action_cost=0, epic_action_effect=""):
        super().__init__(id, name, cost, CardType.UNIT)
        self.action_cost = action_cost
        self.action_effect = action_effect
        self.epic_action_cost = epic_action_cost
        self.epic_action_effect = epic_action_effect
        self.is_deployed = False
        self.epic_action_used = False
        self.is_exhausted = False
        self.power = 0
        self.hp = 0
        self.current_hp = 0
        self.damage = 0
        self.arena = Arena.NONE

    def take_damage(self, amount: int) -> int:
        """Apply damage while deployed as a unit."""
        actual = min(amount, self.current_hp)
        self.damage += actual
        self.current_hp -= actual
        return actual

    def is_defeated(self) -> bool:
        return self.is_deployed and self.current_hp <= 0

    def heal(self, amount: int = None):
        """Heal deployed leader unit."""
        if amount is None:
            self.damage = 0
            self.current_hp = self.hp
        else:
            self.current_hp = min(self.hp, self.current_hp + amount)
            self.damage = max(0, self.damage - amount)


@dataclass
class Base:
    """Player's base"""
    hp: int = 25
    current_hp: int = 25
    
    def take_damage(self, amount: int):
        self.current_hp = max(0, self.current_hp - amount)
    
    def is_defeated(self) -> bool:
        return self.current_hp <= 0


@dataclass
class Resource:
    """Resource card"""
    card: Card
    is_exhausted: bool = False
    
    def ready(self):
        self.is_exhausted = False
    
    def exhaust(self):
        self.is_exhausted = True


@dataclass
class Player:
    """Player in the game"""
    id: int
    deck: List[Card] = field(default_factory=list)
    hand: List[Card] = field(default_factory=list)
    resources: List[Resource] = field(default_factory=list)
    base: Base = field(default_factory=Base)
    leader: Optional[LeaderCard] = None
    units: List[UnitCard] = field(default_factory=list)
    ground_arena: List[UnitCard] = field(default_factory=list)
    space_arena: List[UnitCard] = field(default_factory=list)
    discard_pile: List[Card] = field(default_factory=list)
    has_initiative: bool = False
    
    def draw_cards(self, count: int):
        """Draw cards from deck"""
        for _ in range(count):
            if not self.deck:
                # Deck empty - shuffle discard and create new deck
                if self.discard_pile:
                    random.shuffle(self.discard_pile)
                    self.deck = self.discard_pile.copy()
                    self.discard_pile.clear()
                else:
                    break
            if self.deck:
                self.hand.append(self.deck.pop(0))
    
    def get_ready_resources(self) -> List[Resource]:
        return [r for r in self.resources if not r.is_exhausted]
    
    def get_resource_cost(self, cost: int) -> List[Resource]:
        """Get resources needed to pay for a card"""
        ready = self.get_ready_resources()
        if len(ready) >= cost:
            return ready[:cost]
        return []
    
    def can_afford(self, cost: int) -> bool:
        return len(self.get_ready_resources()) >= cost
    
    def pay_cost(self, cost: int) -> bool:
        """Pay the cost for a card. Returns True if successful."""
        resources = self.get_resource_cost(cost)
        if len(resources) < cost:
            return False
        for r in resources:
            r.exhaust()
        return True
    
    def ready_all(self):
        """Ready all exhausted cards"""
        for r in self.resources:
            r.ready()
        for unit in self.units:
            pass  # Units ready in game engine
        if self.leader:
            pass  # Leader ready in game engine
