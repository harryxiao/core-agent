"""宠物人格与角色库（pet-library）：pet.md 人格 + 角色库闭环。"""

from .library import CharacterLibrary
from .loader import load_persona, load_personas, parse_persona
from .persona import Persona

__all__ = ["CharacterLibrary", "Persona", "load_persona", "load_personas", "parse_persona"]
