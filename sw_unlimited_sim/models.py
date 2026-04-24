"""Star Wars Unlimited - Core Game Models"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, List
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
class CardProfile:
    """Compiled metadata attached to a card object.

    This is the augmentation boundary where deterministic loading and any
    offline LLM-produced effect draft can be attached to the runtime card
    without asking a model during gameplay.
    """

    set_code: str = ""
    number: str = ""
    card_type: str = ""
    rules_text: str = ""
    ability_lines: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    traits: List[str] = field(default_factory=list)
    aspects: List[str] = field(default_factory=list)
    mechanic_tags: List[str] = field(default_factory=list)
    source_fields: dict[str, str] = field(default_factory=dict)
    llm_augmented: bool = False
    effect_record: Optional[dict[str, Any]] = None
    effect_execution_status: str = "manual"
    effect_validation: Optional[dict[str, Any]] = None


@dataclass
class Card:
    """Base card class"""
    id: str
    name: str
    cost: int
    card_type: CardType
    aspects: List[str] = field(default_factory=list, init=False)
    profile: CardProfile = field(default_factory=CardProfile, init=False)
    
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
        self.aspects = []
        self.has_ambush = has_ambush
        self.current_hp = hp
        self.damage = 0
        self.experience_tokens = 0
        self.shield_tokens = 0
        self.is_token = False
        self.attacked_this_phase = False
        self.abilities_lost_until_ready = False
        self.attached_upgrades = []
        self.temporary_phase_power_bonus = 0
        self.temporary_phase_hp_bonus = 0
        self.temporary_attack_power_bonus = 0
        self.temporary_attack_hp_bonus = 0
        self.temporary_phase_keywords = set()
        self.temporary_attack_keywords = set()
        self.temporary_phase_cannot_attack_base = False
        self.temporary_attack_cannot_attack_base = False
        self.temporary_attack_strip_defender_abilities = False
        self.temporary_attack_defeat_self_after_attack = False
        self.temporary_attack_defeat_self_if_damaged_base = False
        self.temporary_attack_damaged_base = False
        self.temporary_attack_abilities_suppressed = False
    
    def take_damage(self, amount: int) -> int:
        """Apply damage, return actual damage taken"""
        if amount > 0 and self.shield_tokens > 0:
            self.shield_tokens -= 1
            return 0
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
        self.aspects = []


@dataclass
class EventCard(Card):
    """Event card with immediate effect"""
    effect: str = ""
    
    def __init__(self, id, name, cost, effect=""):
        super().__init__(id, name, cost, CardType.EVENT)
        self.effect = effect
        self.aspects = []


@dataclass
class LeaderCard(Card):
    """Leader card with action and epic action"""
    action_cost: int = 0
    action_effect: str = ""
    epic_action_cost: int = 0
    epic_action_effect: str = ""
    deployed_arena: Arena = Arena.GROUND
    is_deployed: bool = False
    epic_action_used: bool = False
    
    def __init__(self, id, name, cost, action_cost=0, action_effect="", 
                 epic_action_cost=0, epic_action_effect=""):
        super().__init__(id, name, cost, CardType.UNIT)
        self.action_cost = action_cost
        self.action_effect = action_effect
        self.epic_action_cost = epic_action_cost
        self.epic_action_effect = epic_action_effect
        self.deployed_arena = Arena.GROUND
        self.aspects = []
        self.traits = []
        self.abilities = []
        self.is_deployed = False
        self.epic_action_used = False
        self.is_exhausted = False
        self.power = 0
        self.hp = 0
        self.current_hp = 0
        self.damage = 0
        self.arena = Arena.NONE
        self.experience_tokens = 0
        self.shield_tokens = 0
        self.attacked_this_phase = False
        self.abilities_lost_until_ready = False
        self.attached_upgrades = []
        self.temporary_phase_power_bonus = 0
        self.temporary_phase_hp_bonus = 0
        self.temporary_attack_power_bonus = 0
        self.temporary_attack_hp_bonus = 0
        self.temporary_phase_keywords = set()
        self.temporary_attack_keywords = set()
        self.temporary_phase_cannot_attack_base = False
        self.temporary_attack_cannot_attack_base = False
        self.temporary_attack_strip_defender_abilities = False
        self.temporary_attack_defeat_self_after_attack = False
        self.temporary_attack_defeat_self_if_damaged_base = False
        self.temporary_attack_damaged_base = False
        self.temporary_attack_abilities_suppressed = False

    def take_damage(self, amount: int) -> int:
        """Apply damage while deployed as a unit."""
        if amount > 0 and self.shield_tokens > 0:
            self.shield_tokens -= 1
            return 0
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
    """Player's base card and current HP state."""
    name: str = "Base"
    hp: int = 25
    current_hp: Optional[int] = None
    set_code: str = ""
    number: str = ""
    subtitle: str = ""
    aspects: List[str] = field(default_factory=list)
    abilities: List[str] = field(default_factory=list)
    profile: CardProfile = field(default_factory=CardProfile)
    epic_action_used: bool = False

    def __post_init__(self):
        if self.current_hp is None:
            self.current_hp = self.hp
    
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
    has_force_token: bool = False
    
    def draw_cards(self, count: int) -> List[Card]:
        """Draw cards from deck and return the cards drawn."""
        drawn = []
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
                card = self.deck.pop(0)
                self.hand.append(card)
                drawn.append(card)
        return drawn
    
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
