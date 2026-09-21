"""T10 — conformal risk control for the pothole miss rate.

What is certified is an **image-level** quantity: over calibration images that
contain at least one ground-truth pothole, the expected fraction of potholes
missed at confidence threshold tau. That is the number CRC bounds, and it is not
the same as the instance-level miss rate — both are reported, only the first is
guaranteed.

The guarantee is distribution-free but *exchangeability*-dependent. Calibrating
on one geography and deploying on another breaks it, which is exactly the
experiment T10 runs: calibrate on non-India, evaluate on India, and show the
bound fail.
"""

from collections.abc import Sequence

import numpy as np

NEVER_MATCHED = -np.inf


def iou_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Pairwise IoU between two sets of xyxy boxes, shape (len(a), len(b))."""
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)))
    x1 = np.maximum(a[:, None, 0], b[None, :, 0])
    y1 = np.maximum(a[:, None, 1], b[None, :, 1])
    x2 = np.minimum(a[:, None, 2], b[None, :, 2])
    y2 = np.minimum(a[:, None, 3], b[None, :, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    area_a = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    area_b = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    union = area_a[:, None] + area_b[None, :] - inter
    return np.where(union > 0, inter / np.maximum(union, 1e-12), 0.0)


def matched_confidences(
    gt: np.ndarray, pred: np.ndarray, scores: np.ndarray, *, iou_threshold: float = 0.5
) -> np.ndarray:
    """Confidence of the prediction matched to each GT box, or -inf if unmatched.

    Greedy in descending confidence: the most confident prediction claims the
    unmatched GT it overlaps most, provided IoU >= the threshold. Because the
    order is by confidence alone, thresholding at tau keeps a *prefix* of this
    same sequence — which is what makes `image_loss` exact rather than an
    approximation. `test_prefix_equivalence` pins that property.
    """
    out = np.full(len(gt), NEVER_MATCHED, dtype=float)
    if len(gt) == 0 or len(pred) == 0:
        return out

    ious = iou_matrix(pred, gt)
    taken = np.zeros(len(gt), dtype=bool)
    for p in np.argsort(-scores, kind="stable"):
        candidates = np.where(~taken & (ious[p] >= iou_threshold))[0]
        if candidates.size:
            best = candidates[np.argmax(ious[p, candidates])]
            taken[best] = True
            out[best] = scores[p]
    return out


def image_loss(confs: np.ndarray, tau: float) -> float:
    """Fraction of this image's GT potholes missed once predictions below tau go."""
    return 0.0 if len(confs) == 0 else float(np.mean(confs < tau))


def default_tau_grid(step: float = 0.001) -> np.ndarray:
    return np.arange(0.001, 0.990 + step / 2, step)


def crc_threshold(
    per_image: Sequence[np.ndarray], alpha: float, tau_grid: np.ndarray | None = None
) -> float | None:
    """Largest tau with `(sum_i L_i(tau) + 1) / (n + 1) <= alpha`, else None.

    The `+1` in both places is the finite-sample correction that makes this a
    genuine bound rather than a point estimate: it charges for the unseen test
    image. Dropping it would look almost identical on large n and be wrong.

    Returning the *largest* passing tau is deliberate — tau is a detection
    threshold, so a larger value means fewer false positives at the same
    certified miss rate. The risk is monotone non-decreasing in tau, so the
    passing set is a prefix of the grid.
    """
    grid = default_tau_grid() if tau_grid is None else np.asarray(tau_grid, dtype=float)
    n = len(per_image)
    if n == 0:
        return None

    # Per image, the count of GT below each tau via searchsorted on sorted
    # confidences: O(n * G log k) instead of re-scanning every box per tau.
    fractions = np.empty((n, len(grid)))
    for i, confs in enumerate(per_image):
        if len(confs) == 0:
            fractions[i] = 0.0
            continue
        fractions[i] = np.searchsorted(np.sort(confs), grid, side="left") / len(confs)

    risk = (fractions.sum(axis=0) + 1.0) / (n + 1.0)
    passing = np.where(risk <= alpha)[0]
    return float(grid[passing[-1]]) if passing.size else None


def empirical_risk(per_image: Sequence[np.ndarray], tau: float) -> float:
    """Plain mean image-level loss — the quantity the guarantee is about."""
    return float(np.mean([image_loss(c, tau) for c in per_image])) if per_image else 0.0


def instance_miss_rate(per_image: Sequence[np.ndarray], tau: float) -> float:
    """Pooled over boxes, not images. Reported alongside, never certified."""
    confs = np.concatenate(list(per_image)) if len(per_image) else np.array([])
    return float(np.mean(confs < tau)) if confs.size else 0.0
