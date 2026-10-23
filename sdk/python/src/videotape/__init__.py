"""Videotape's Python SDK: an app as types, places, and decisions (design 05 §6, guide 06).

    import videotape as vt
"""

from .decisions import Context, Reject, UndeclaredOutcome, invoke
from .documents import docs
from .intent import (
    Action, After, App, Destination, Frame, Hub, Show, Tape, Text as TextComponent, action, after, app,
    destination, frame, hub, show, tape, text,
)
from .outcomes import (
    Back, Call, Copy, Done, Download, Goto, Jump, Open, Outcome, Stay, back, call, copy, done, download, goto,
    jump, open, stay,
)
from .records import Field, FieldRef, Record, RecordError, State, pick
from .values import Audio, Image, Money, Page, Phrase, RichText, Secret, Series, Text, Video, t

__all__ = [
    "Context", "Reject", "UndeclaredOutcome", "invoke",
    "Action", "After", "App", "Audio", "Back", "Call", "Copy", "Destination", "Done", "Download", "Field",
    "FieldRef", "Frame", "Goto", "Hub", "Image", "Jump", "Money", "Open", "Outcome", "Page", "Phrase", "Record",
    "RecordError", "RichText", "Secret", "Series", "Show", "State", "Stay", "Tape", "Text", "TextComponent",
    "Video", "action", "after", "app", "back", "call", "copy", "destination", "docs", "done", "download",
    "frame", "goto", "hub", "jump", "open", "pick", "show", "stay", "t", "tape", "text",
]  # fmt: skip
