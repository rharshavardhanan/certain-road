"""T11 — drift detection with a conformal test martingale.

Wealth against the null. Under exchangeability the martingale is non-negative
with expectation 1, so Ville's inequality bounds the chance it ever reaches C at
1/C: a threshold of 100 buys a <=1% false-alarm rate over an unbounded stream,
with no distribution assumption and no window to tune.

Two details are load-bearing and easy to get wrong:

**The bag grows.** Each score is scored against the bag as it stands, and only
then inserted. Insert first and the score is compared against itself, which
drags p toward the middle and blinds the detector.

**The p-value is randomised.** The `U * (#equal + 1)` term breaks ties uniformly.
Detection confidences are heavily tied (identical rounded values, and the s = 1
of every empty frame), and a deterministic p-value on tied data is not uniform
under the null — the martingale then drifts upward on exchangeable data and
alarms on nothing.
"""

import bisect
import math
import random
from collections.abc import Iterable, Sequence

NO_DETECTION_SCORE = 1.0
MIN_P = 1e-12


def frame_score(confidences: Sequence[float], *, topk: int) -> float:
    """1 - mean of the top-k confidences; 1.0 when the frame has no detections.

    High score means "the detector saw little it was sure about", which is what
    a domain it was not trained on tends to look like.
    """
    if len(confidences) == 0:
        return NO_DETECTION_SCORE
    top = sorted(confidences, reverse=True)[:topk]
    return 1.0 - sum(top) / len(top)


class DriftMartingale:
    """Power martingale over randomised conformal p-values from a growing bag."""

    def __init__(
        self,
        reference: Iterable[float],
        *,
        eps: float,
        alarm_threshold: float,
        seed: int = 0,
        cusum: bool = False,
    ) -> None:
        if not 0.0 < eps < 1.0:
            raise ValueError(f"eps must be in (0, 1), got {eps}")
        self.bag = sorted(reference)
        self.eps = eps
        self.log_threshold = math.log(alarm_threshold)
        self.log_m = 0.0
        self.cusum = cusum
        self._rng = random.Random(seed)

    def p_value(self, score: float) -> float:
        lo = bisect.bisect_left(self.bag, score)
        hi = bisect.bisect_right(self.bag, score)
        greater, equal = len(self.bag) - hi, hi - lo
        u = self._rng.random()
        return (greater + u * (equal + 1)) / (len(self.bag) + 1)

    def update(self, score: float) -> float:
        """Score against the current bag, then absorb it. Returns the p-value."""
        p = max(self.p_value(score), MIN_P)
        bisect.insort(self.bag, score)
        self.log_m += math.log(self.eps) + (self.eps - 1.0) * math.log(p)
        if self.cusum:
            self.log_m = max(0.0, self.log_m)
        return p

    @property
    def alarmed(self) -> bool:
        return self.log_m >= self.log_threshold


def run_stream(
    reference: Sequence[float],
    stream: Sequence[float],
    *,
    eps: float,
    alarm_threshold: float,
    seed: int = 0,
    cusum: bool = False,
) -> tuple[int | None, list[float]]:
    """Feed `stream`; return (index of first alarm or None, log-martingale trace)."""
    m = DriftMartingale(reference, eps=eps, alarm_threshold=alarm_threshold, seed=seed,
                        cusum=cusum)
    trace, alarm = [], None
    for i, score in enumerate(stream):
        m.update(score)
        trace.append(m.log_m)
        if alarm is None and m.alarmed:
            alarm = i
    return alarm, trace
