"""N-of-M temporal confirmation.

**The problem it solves.** A detector fires a false positive on one frame — a
shadow, a wet patch, a drain cover. Without confirmation the robot swerves. In a
live demo, in front of an examiner, at nothing.

**What it confirms.** A *condition* ("a hazard is in my path"), not an *object*.
Confirming objects would need cross-frame association — a tracker — and D006
already rejected trackers as fragile on shaky footage. Confirming the predicate
needs no association at all, and the predicate is exactly what the state machine
consumes.

The cost is real and should be stated: at ~15 fps, 3-of-5 delays intervention by
roughly 0.2 s. That comes out of the corridor's look-ahead budget.
"""

from __future__ import annotations

from collections import deque


class Confirmer:
    """Sliding window over a boolean condition."""

    def __init__(self, required: int, window: int) -> None:
        if required > window:
            raise ValueError(f"required ({required}) cannot exceed window ({window})")
        if required < 1:
            raise ValueError("required must be at least 1")
        self.required = required
        self.window = window
        self._history: deque[bool] = deque(maxlen=window)

    def update(self, present: bool) -> bool:
        """Record one frame's observation and return whether the hazard is confirmed."""
        self._history.append(present)
        return self.confirmed

    @property
    def confirmed(self) -> bool:
        return sum(self._history) >= self.required

    def reset(self) -> None:
        self._history.clear()
