"""Per-subject calibration of the eyeball-centre anchor.

The one free parameter in the gaze model is where along the eyelid opening the
eyeball's centre of rotation sits (see ``anatomy.OUTER_CORNER_WEIGHT``). Getting
it wrong biases both eyes towards or away from the nose, and since the bias is
mirrored it shows up as the two eyes reporting different horizontal gaze -- an
impossible reading, because a real pair of eyes converges on one point.

That gives a free calibration signal: pick the anchor that makes the two eyes
agree. It needs no ground truth and no cooperation from the subject, just a
handful of frames where both eyes are open, which any clip provides.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np

from .anatomy import EYEBALL_DEPTH_MM, EYEBALL_RADIUS_MM, OUTER_CORNER_WEIGHT
from .geometry import EyeGeometry
from .headpose import HeadPose

#: Anatomical bounds. A fitted value outside this range means the input was
#: degenerate rather than that the subject is unusual, so it is discarded.
WEIGHT_BOUNDS = (0.45, 0.70)
MIN_SAMPLES = 12


@dataclass(frozen=True)
class AnchorCalibration:
    """Result of fitting the anchor weight to a clip."""

    outer_weight: float
    samples: int
    #: Mean binocular disagreement after fitting, in degrees. Large values mean
    #: the fit did not explain the data and the default was kept.
    residual_deg: float
    converged: bool

    @classmethod
    def default(cls) -> "AnchorCalibration":
        return cls(OUTER_CORNER_WEIGHT, 0, float("nan"), False)


def _linear_terms(eye: EyeGeometry, pose: HeadPose) -> tuple[np.ndarray, np.ndarray] | None:
    """Write this eye's gaze estimate as ``a + w * b`` in the anchor weight ``w``."""
    if eye.iris_semi_major <= 0.0 or pose.axes_are_degenerate():
        return None
    axes = pose.projected_axes(eye.pixels_per_mm)
    forward = pose.forward
    parallax = eye.pixels_per_mm * EYEBALL_DEPTH_MM * np.array([forward[0], -forward[1]])

    p = eye.iris_center - eye.inner_corner + parallax
    q = eye.outer_corner - eye.inner_corner
    try:
        a = np.linalg.solve(axes, p) / EYEBALL_RADIUS_MM
        b = -np.linalg.solve(axes, q) / EYEBALL_RADIUS_MM
    except np.linalg.LinAlgError:
        return None
    return a, b


def fit_outer_corner_weight(
    samples: Iterable[tuple[EyeGeometry, EyeGeometry, HeadPose]],
    min_samples: int = MIN_SAMPLES,
    bounds: Sequence[float] = WEIGHT_BOUNDS,
) -> AnchorCalibration:
    """Fit the anchor weight that best reconciles the two eyes.

    Args:
        samples: ``(right_eye, left_eye, pose)`` triples, one per usable frame.
        min_samples: Below this many frames the default is kept; a short clip's
            fit is dominated by landmark noise.
        bounds: Anatomically plausible range for the fitted weight.

    Both eyes' estimates are linear in the weight, so the disagreement between
    them is too, and the best weight comes straight out of a one-dimensional
    least squares with no iteration.
    """
    diff_const: list[np.ndarray] = []
    diff_slope: list[np.ndarray] = []
    for right, left, pose in samples:
        terms_r = _linear_terms(right, pose)
        terms_l = _linear_terms(left, pose)
        if terms_r is None or terms_l is None:
            continue
        diff_const.append(terms_r[0] - terms_l[0])
        diff_slope.append(terms_r[1] - terms_l[1])

    if len(diff_const) < min_samples:
        return AnchorCalibration(OUTER_CORNER_WEIGHT, len(diff_const), float("nan"), False)

    a = np.asarray(diff_const)
    b = np.asarray(diff_slope)
    denom = float(np.sum(b * b))
    if denom < 1e-12:
        return AnchorCalibration(OUTER_CORNER_WEIGHT, len(a), float("nan"), False)

    weight = float(-np.sum(a * b) / denom)
    residual = a + weight * b
    residual_deg = float(np.degrees(np.mean(np.linalg.norm(residual, axis=1))))

    if not bounds[0] <= weight <= bounds[1]:
        return AnchorCalibration(OUTER_CORNER_WEIGHT, len(a), residual_deg, False)
    return AnchorCalibration(weight, len(a), residual_deg, True)
