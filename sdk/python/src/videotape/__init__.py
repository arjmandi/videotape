"""Videotape's Python SDK: an app as types, places, and decisions (design 05 §6, guide 06).

    import videotape as vt
"""

from .records import Field, FieldRef, Record, RecordError, State, pick
from .values import Audio, Image, Money, Page, Phrase, RichText, Secret, Series, Text, Video, t

__all__ = [
    "Audio", "Field", "FieldRef", "Image", "Money", "Page", "Phrase", "Record", "RecordError",
    "RichText", "Secret", "Series", "State", "Text", "Video", "pick", "t",
]  # fmt: skip
