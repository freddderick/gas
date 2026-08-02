"""Anatomical constants and MediaPipe FaceLandmarker index tables.

Landmark indices refer to the 478-point mesh produced by the MediaPipe Face
Landmarker task with iris refinement (points 468-477 are the two iris rings).

Sides are named from the *subject's* point of view: ``EyeSide.LEFT`` is the
person's own left eye, which appears on the right-hand side of the image.
MediaPipe's own index naming uses the opposite convention, so the tables below
are the single place where that flip is resolved.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# Population means, in millimetres. These set the scale that converts a measured
# iris size in pixels into a physical eye model, so only their ratios matter.
IRIS_RADIUS_MM = 5.85
EYEBALL_RADIUS_MM = 12.0

# Depth from the plane of the eyelid margins back to the centre of rotation of
# the eyeball. Only matters when the head is turned, where it produces the
# parallax between the visible eye opening and the true centre of rotation.
EYEBALL_DEPTH_MM = 7.0

# The eyeball's centre of rotation does not project onto the midpoint of the two
# eyelid corners: the palpebral fissure extends further towards the temple than
# towards the nose. This is the weight given to the outer (temporal) corner when
# interpolating between the corners, and 0.5 would be the naive midpoint.
#
# The default was fitted by minimising binocular disagreement -- the two eyes of
# one face must report the same gaze direction -- across several faces, which
# put the optimum between 0.55 and 0.585. ``gazefix.calibrate`` re-fits it per
# subject when a clip provides enough usable frames.
OUTER_CORNER_WEIGHT = 0.57


class EyeSide(Enum):
    LEFT = "left"    # the subject's left eye, on the right of the image
    RIGHT = "right"  # the subject's right eye, on the left of the image


@dataclass(frozen=True)
class EyeIndices:
    """Landmark indices describing one eye."""

    side: EyeSide
    iris_center: int
    iris_ring: tuple[int, ...]
    outer_corner: int
    inner_corner: int
    lid_ring: tuple[int, ...]
    ear_pairs: tuple[tuple[int, int], ...]


#: The subject's right eye — the one on the left of the image.
RIGHT_EYE = EyeIndices(
    side=EyeSide.RIGHT,
    iris_center=468,
    iris_ring=(469, 470, 471, 472),
    outer_corner=33,
    inner_corner=133,
    lid_ring=(33, 246, 161, 160, 159, 158, 157, 173,
              133, 155, 154, 153, 145, 144, 163, 7),
    ear_pairs=((159, 145), (158, 153), (160, 144)),
)

#: The subject's left eye — the one on the right of the image.
LEFT_EYE = EyeIndices(
    side=EyeSide.LEFT,
    iris_center=473,
    iris_ring=(474, 475, 476, 477),
    outer_corner=263,
    inner_corner=362,
    lid_ring=(263, 466, 388, 387, 386, 385, 384, 398,
              362, 382, 381, 380, 374, 373, 390, 249),
    ear_pairs=((386, 374), (385, 380), (387, 373)),
)

EYES: tuple[EyeIndices, ...] = (RIGHT_EYE, LEFT_EYE)

#: Total landmark count expected from the refined face mesh.
NUM_LANDMARKS = 478
