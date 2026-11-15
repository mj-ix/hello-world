"""Everything the pet can spend a tick doing."""
from __future__ import annotations

from .base import Activity, Outcome
from .art import ArtActivity
from .dream import DreamActivity
from .hobbies import HobbiesActivity
from .letters import LettersActivity
from .music import MusicActivity
from .redecorate import RedecorateActivity
from .research import ResearchActivity
from .shop import ShopActivity
from .simulation import SimulationActivity
from .writing import WritingActivity

ALL: list[Activity] = [
    MusicActivity(),
    ArtActivity(),
    WritingActivity(),
    SimulationActivity(),
    HobbiesActivity(),
    ResearchActivity(),
    LettersActivity(),
    ShopActivity(),
    RedecorateActivity(),
    DreamActivity(),
]
BY_NAME: dict[str, Activity] = {a.name: a for a in ALL}

__all__ = ["ALL", "BY_NAME", "Activity", "Outcome"]
