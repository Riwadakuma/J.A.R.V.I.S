"""Utilities for working with the shared stylist package."""
from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from interaction.stylist import Stylist, get_stylist, say, say_key

__all__ = ["Stylist", "get_stylist", "say", "say_key"]

