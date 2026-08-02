"""Where an eye is looking, where it should look, and how far the iris must move.

The model treats the eye as a sphere of known radius whose centre of rotation
sits behind the eyelid plane. Measuring the iris's offset from that centre gives
the current gaze direction; asking what offset would point the eye at the lens
gives the target. The difference, projected back into the image, is the pixel
displacement the warp has to deliver.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .anatomy import EYEBALL_DEPTH_MM, EYEBALL_RADIUS_MM, EyeSide, OUTER_CORNER_WEIGHT
from .camera import CameraModel
from .geometry import EyeGeometry
from .headpose import HeadPose


@dataclass(frozen=True)
class GazeSolution:
    """The gaze estimate and required correction for a single eye."""

    side: EyeSide
    eyeball_center_px: np.ndarray
    #: Sines of the horizontal and vertical gaze angles, in the head's own frame.
    gaze_now: np.ndarray
    gaze_target: np.ndarray
    #: Iris displacement in pixels that would put the eye on the lens.
    displacement_px: np.ndarray
    pixels_per_mm: float

    @property
    def residual_deg(self) -> float:
        """Angle between where the eye looks now and the lens."""
        return float(np.degrees(angle_between(self.gaze_now, self.gaze_target)))

    @property
    def gaze_now_deg(self) -> np.ndarray:
        return np.degrees(np.arcsin(np.clip(self.gaze_now, -1.0, 1.0)))


def unit_gaze(sines: np.ndarray) -> np.ndarray:
    """Lift horizontal/vertical sines to a unit gaze vector in the head frame."""
    xy = np.asarray(sines, dtype=np.float64)
    n2 = float(xy[0] ** 2 + xy[1] ** 2)
    if n2 >= 1.0:  # past the equator of the eyeball; renormalise onto it
        xy = xy / np.sqrt(n2) * 0.999
        n2 = 0.998
    return np.array([xy[0], xy[1], np.sqrt(max(1.0 - n2, 0.0))])


def angle_between(a_sines: np.ndarray, b_sines: np.ndarray) -> float:
    """Angle in radians between two gaze directions given as sine pairs."""
    a, b = unit_gaze(a_sines), unit_gaze(b_sines)
    return float(np.arccos(np.clip(float(a @ b), -1.0, 1.0)))


def eyeball_center(
    eye: EyeGeometry,
    pose: HeadPose,
    outer_weight: float = OUTER_CORNER_WEIGHT,
) -> np.ndarray:
    """Projected centre of rotation of the eyeball, in pixels.

    Starts from the anchor between the eyelid corners and pushes it back along
    the face's forward direction. That second step only matters once the head is
    turned, but then it matters a lot: the centre of rotation is well behind the
    eyelids, so it slides across the image as the head rotates.
    """
    anchor = eye.eyeball_center_anchor(outer_weight)
    forward = pose.forward
    parallax = eye.pixels_per_mm * EYEBALL_DEPTH_MM * np.array([forward[0], -forward[1]])
    return anchor - parallax


def solve_eye(
    eye: EyeGeometry,
    pose: HeadPose,
    camera: CameraModel,
    outer_weight: float = OUTER_CORNER_WEIGHT,
) -> GazeSolution | None:
    """Solve one eye. Returns ``None`` if the head is turned too far to be usable."""
    if pose.axes_are_degenerate() or eye.iris_semi_major <= 0.0:
        return None

    scale = eye.pixels_per_mm
    center = eyeball_center(eye, pose, outer_weight)
    axes = pose.projected_axes(scale)

    # Current gaze: undo the projection to recover the iris offset in the head's
    # own frame, then divide by the eyeball radius to get direction sines.
    offset_mm = np.linalg.solve(axes, eye.iris_center - center)
    gaze_now = offset_mm / EYEBALL_RADIUS_MM

    # Target gaze: the direction from this eye to the lens, expressed in the
    # head's frame. Solved per eye, so the two eyes converge slightly, as they
    # do when a person actually looks at something close by.
    to_lens = camera.direction_to_lens(center)
    gaze_target = (pose.rotation.T @ to_lens)[:2]

    displacement = axes @ (EYEBALL_RADIUS_MM * (gaze_target - gaze_now))
    return GazeSolution(
        side=eye.side,
        eyeball_center_px=center,
        gaze_now=gaze_now,
        gaze_target=gaze_target,
        displacement_px=displacement,
        pixels_per_mm=scale,
    )


def smoothstep(edge0: float, edge1: float, x: np.ndarray | float):
    """Hermite ramp from 0 to 1 across ``[edge0, edge1]``, flat outside it."""
    span = max(float(edge1) - float(edge0), 1e-9)
    t = np.clip((np.asarray(x, dtype=np.float64) - edge0) / span, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def look_away_attenuation(residual_deg: float, falloff_start: float, cutoff: float) -> float:
    """How much of the correction to keep, given how far off the lens the eye is.

    Someone glancing at a second monitor or turning to a colleague is looking
    away on purpose, and dragging their eyes back to the lens reads as unsettling
    rather than attentive. Corrections fade out past ``falloff_start`` and stop
    entirely past ``cutoff``, so only the small persistent offset of a person
    reading just below the lens gets fixed.
    """
    if cutoff <= falloff_start:
        return 0.0 if residual_deg > cutoff else 1.0
    return float(1.0 - smoothstep(falloff_start, cutoff, residual_deg))


def head_pose_attenuation(pose: HeadPose, max_yaw: float, max_pitch: float) -> float:
    """Fade the correction out as the head turns away from the camera.

    A profile view hides the far eye and foreshortens the near one, and a flat
    warp has nothing convincing to work with. Fades over the last third of the
    allowed range rather than switching off at a threshold.
    """
    yaw = min(abs(pose.yaw_deg) / max(max_yaw, 1e-6), 2.0)
    pitch = min(abs(pose.pitch_deg) / max(max_pitch, 1e-6), 2.0)
    return float((1.0 - smoothstep(0.66, 1.0, yaw)) * (1.0 - smoothstep(0.66, 1.0, pitch)))


#: Requested shift, as a multiple of the eye opening's half-height, past which
#: asking for more stops buying anything. Set from the measured response curve
#: in ``tools/measure_fidelity.py``; see ``docs/limits.md``.
BUDGET_FRACTION = 1.0


def displacement_budget(aperture_half_height: float) -> float:
    """Largest eyeball shift, in pixels, worth asking the warp for.

    The eyeball slides inside the eye opening while the lids stay put, so the
    opening's own depth sets the ceiling. The displacement has to fall back to
    zero at the lid margin, and once the request approaches that depth the ramp
    gets steeper than one pixel per pixel: the map folds, the fold guard scales
    it back, and the eye stops moving further no matter what is asked for.

    This is the hard limit of warp-based redirection, and it is why large
    corrections need a model that redraws the eye rather than rearranging the
    pixels already there.
    """
    return BUDGET_FRACTION * max(aperture_half_height, 0.0)


def limit_displacement(displacement: np.ndarray, budget: float) -> tuple[np.ndarray, bool]:
    """Clamp a displacement to the warp's budget, reporting whether it bit."""
    magnitude = float(np.linalg.norm(displacement))
    if budget <= 0.0:
        return np.zeros(2), magnitude > 1e-6
    if magnitude <= budget:
        return np.asarray(displacement, dtype=np.float64), False
    return np.asarray(displacement, dtype=np.float64) * (budget / magnitude), True
