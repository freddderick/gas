"""Head orientation, read out of the detector's face transformation matrix."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class HeadPose:
    """Rotation of the head relative to the camera.

    ``rotation`` maps the canonical face's own axes into camera space: x right,
    y up, z out of the face towards whoever is looking at it. A head facing the
    lens square-on gives the identity.
    """

    rotation: np.ndarray

    @classmethod
    def from_matrix(cls, matrix: np.ndarray) -> "HeadPose":
        """Take the rotation block out of a 4x4 (or 3x3) transformation matrix."""
        m = np.asarray(matrix, dtype=np.float64)
        if m.shape not in {(4, 4), (3, 3)}:
            raise ValueError("expected a 3x3 or 4x4 matrix")
        return cls(rotation=np.array(m[:3, :3], dtype=np.float64))

    @property
    def forward(self) -> np.ndarray:
        """Direction the face points, in camera space."""
        return self.rotation[:, 2]

    @property
    def yaw_deg(self) -> float:
        """Turn left/right. Positive when the subject turns towards image right."""
        r = self.rotation
        return float(np.degrees(np.arctan2(-r[2, 0], r[2, 2])))

    @property
    def pitch_deg(self) -> float:
        """Nod up/down. Positive when the chin lifts."""
        r = self.rotation
        return float(np.degrees(np.arcsin(np.clip(r[2, 1], -1.0, 1.0))))

    @property
    def roll_deg(self) -> float:
        """Head tilt towards a shoulder."""
        r = self.rotation
        return float(np.degrees(np.arctan2(-r[0, 1], r[1, 1])))

    def projected_axes(self, pixels_per_mm: float) -> np.ndarray:
        """2x2 matrix taking head-local millimetres to image pixels.

        A weak-perspective projection of the head's x and y axes, with the sign
        flip that turns "up" in the world into "up" in an image whose rows run
        downwards. Depth foreshortening from head turn falls out of the rotation
        block, which is why an eye seen at an angle needs a smaller pixel shift
        for the same change in gaze.
        """
        r = self.rotation
        return pixels_per_mm * np.array([[r[0, 0], r[0, 1]],
                                         [-r[1, 0], -r[1, 1]]], dtype=np.float64)

    def axes_are_degenerate(self, tol: float = 0.15) -> bool:
        """True once the head is turned so far that the projection is unusable."""
        r = self.rotation
        det = r[0, 0] * r[1, 1] - r[0, 1] * r[1, 0]
        return abs(det) < tol
