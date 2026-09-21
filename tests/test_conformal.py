"""T10 — the CRC guarantee is only worth as much as these tests.

The prefix-equivalence test is the load-bearing one: `image_loss` is cheap
because it assumes thresholding at tau keeps a prefix of the confidence-sorted
matching. If that assumption is wrong the loss is wrong, the threshold is wrong,
and the guarantee is decoration. It is checked against brute-force re-matching.
"""

import numpy as np
import pytest

from certain_road.assess.conformal import (
    NEVER_MATCHED,
    crc_threshold,
    empirical_risk,
    image_loss,
    matched_confidences,
)

RNG = np.random.default_rng(0)


def random_case(n_gt, n_pred, rng):
    gt = np.zeros((n_gt, 4))
    gt[:, :2] = rng.uniform(0, 80, size=(n_gt, 2))
    gt[:, 2:] = gt[:, :2] + rng.uniform(5, 25, size=(n_gt, 2))
    pred = np.zeros((n_pred, 4))
    pred[:, :2] = rng.uniform(0, 80, size=(n_pred, 2))
    pred[:, 2:] = pred[:, :2] + rng.uniform(5, 25, size=(n_pred, 2))
    return gt, pred, rng.uniform(0, 1, size=n_pred)


def brute_force_loss(gt, pred, scores, tau, iou_threshold=0.5):
    """Re-run the whole match using only predictions at or above tau."""
    keep = scores >= tau
    confs = matched_confidences(gt, pred[keep], scores[keep], iou_threshold=iou_threshold)
    return float(np.mean(confs == NEVER_MATCHED)) if len(gt) else 0.0


@pytest.mark.parametrize("trial", range(40))
def test_prefix_equivalence_against_brute_force(trial):
    rng = np.random.default_rng(trial)
    gt, pred, scores = random_case(rng.integers(1, 6), rng.integers(0, 10), rng)
    confs = matched_confidences(gt, pred, scores)
    for tau in (0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0):
        assert image_loss(confs, tau) == pytest.approx(
            brute_force_loss(gt, pred, scores, tau), abs=1e-12
        ), f"tau={tau}"


def test_loss_is_monotone_non_decreasing_in_tau():
    confs = np.array([0.1, 0.4, 0.55, 0.9, NEVER_MATCHED])
    losses = [image_loss(confs, t) for t in np.linspace(0, 1, 101)]
    # Deliberately offset, so the lengths differ by one: no strict= here.
    assert all(b >= a for a, b in zip(losses, losses[1:]))  # noqa: B905


def test_unmatched_gt_counts_as_missed_at_every_tau():
    confs = np.array([NEVER_MATCHED, NEVER_MATCHED])
    assert image_loss(confs, 0.0) == 1.0
    assert image_loss(confs, 0.999) == 1.0


def test_higher_iou_gt_wins_the_match():
    gt = np.array([[0, 0, 10, 10], [0, 0, 100, 100]], dtype=float)
    pred = np.array([[0, 0, 10, 10]], dtype=float)
    confs = matched_confidences(gt, pred, np.array([0.8]))
    assert confs[0] == 0.8 and confs[1] == NEVER_MATCHED


def test_more_confident_prediction_claims_the_box_first():
    gt = np.array([[0, 0, 10, 10]], dtype=float)
    pred = np.array([[0, 0, 10, 10], [0, 0, 10, 10]], dtype=float)
    assert matched_confidences(gt, pred, np.array([0.3, 0.9]))[0] == 0.9


def test_threshold_is_the_largest_passing_tau():
    per_image = [np.array([0.9]), np.array([0.8]), np.array([0.7])]
    grid = np.array([0.1, 0.5, 0.75, 0.85, 0.95])
    tau = crc_threshold(per_image, alpha=0.5, tau_grid=grid)
    # risk at 0.75 is (1 + 1)/4 = 0.50 -> passes; at 0.85 it is (2 + 1)/4 = 0.75.
    assert tau == 0.75


def test_returns_none_when_no_tau_satisfies_alpha():
    # The +1 correction alone exceeds a small alpha on few images.
    assert crc_threshold([np.array([0.9])], alpha=0.01) is None


def test_finite_sample_correction_is_present():
    """With every pothole found at tau, risk is 1/(n+1), not 0."""
    per_image = [np.array([0.99]) for _ in range(9)]
    assert crc_threshold(per_image, alpha=0.09, tau_grid=np.array([0.5])) is None
    assert crc_threshold(per_image, alpha=0.10, tau_grid=np.array([0.5])) == 0.5


@pytest.mark.parametrize("alpha", [0.05, 0.10, 0.20])
def test_exchangeable_data_respects_alpha_over_many_trials(alpha):
    """The guarantee itself: calibrate and test on exchangeable draws, 2000 times.

    Mean test risk must not exceed alpha (allowing 0.01 for Monte Carlo noise).
    This is the check that would catch a dropped +1 or an off-by-one in the grid.
    """
    rng = np.random.default_rng(12345)
    grid = np.arange(0.01, 0.99, 0.01)
    risks = []
    for _ in range(2000):
        pool = [rng.uniform(0, 1, size=rng.integers(1, 4)) for _ in range(120)]
        rng.shuffle(pool)
        cal, test = pool[:60], pool[60:]
        tau = crc_threshold(cal, alpha, grid)
        risks.append(0.0 if tau is None else empirical_risk(test, tau))
    assert np.mean(risks) <= alpha + 0.01, f"mean risk {np.mean(risks):.4f} > {alpha}"
