"""fal.ai's queue, the boundary to hosted models that bill per call."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Receipt:
    """What one paid call reports: fal's request id, the seconds of video it billed, their price, and the raw response."""

    request_id: str
    duration: float
    usd: float
    response: dict
