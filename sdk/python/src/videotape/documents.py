"""Documents (05 §6.2): the engine holds each record instance once and syncs it to every screen.

Nothing here runs yet: documents need the engine and the app protocol's `sync`.
"""

from __future__ import annotations

from typing import Any


class _Documents:
    """`vt.docs[Conversation, cid]`: a document by record type and id, from anywhere in the app process."""

    def __getitem__(self, key: tuple[type, Any]) -> Any:
        raise NotImplementedError("vt.docs needs the engine's documents, which are not built yet")


docs = _Documents()
