"""Pinhole camera model used to decide where "the camera" is from an eye's point of view.

Correcting gaze means pointing each eye at the lens, so we need the direction
from the eye to the lens. The lens sits at the origin, and a pixel's viewing ray
is recovered from the focal length implied by the frame's field of view.

Coordinates follow the convention MediaPipe's head-pose matrix uses: x right,
y up, z towards the viewer, with the camera looking down -z. Image coordinates
have y pointing down, so every conversion flips it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class CameraModel:
    """A frame's imaging geometry.

    Args:
        width: Frame width in pixels.
        height: Frame height in pixels.
        fov_deg: Horizontal field of view. 60 degrees is typical of a laptop
            webcam; longer lenses want a smaller number.
        principal_point: Where the optical axis crosses the image, in pixels.
            Defaults to the frame centre, which is correct for uncropped camera
            output. Footage that has been cropped or reframed needs the lens
            position passed explicitly, otherwise the direction to the lens --
            and so the whole correction -- is biased.
    """

    width: int
    height: int
    fov_deg: float = 60.0
    principal_point: tuple[float, float] | None = None

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("frame size must be positive")
        if not 1.0 < self.fov_deg < 179.0:
            raise ValueError("fov_deg must be within (1, 179)")

    @property
    def focal_px(self) -> float:
        return (self.width / 2.0) / math.tan(math.radians(self.fov_deg) / 2.0)

    @property
    def center(self) -> np.ndarray:
        if self.principal_point is not None:
            return np.asarray(self.principal_point, dtype=np.float64)
        return np.array([self.width / 2.0, self.height / 2.0], dtype=np.float64)

    def direction_to_lens(self, pixel: np.ndarray) -> np.ndarray:
        """Unit vector pointing from the surface seen at ``pixel`` back to the lens."""
        cx, cy = self.center
        f = self.focal_px
        ray = np.array([(pixel[0] - cx) / f, -(pixel[1] - cy) / f, -1.0])
        return -ray / np.linalg.norm(ray)
