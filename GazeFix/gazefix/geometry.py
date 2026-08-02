"""Per-eye measurements taken from a frame's face landmarks.

Everything here is plain numpy over an ``(N, 2)`` array of pixel coordinates, so
it can be exercised without a detector or a video file.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .anatomy import EyeIndices, EyeSide, IRIS_RADIUS_MM, OUTER_CORNER_WEIGHT


@dataclass(frozen=True)
class EyeGeometry:
    """One eye, measured in image pixels."""

    side: EyeSide
    iris_center: np.ndarray
    iris_semi_major: float
    outer_corner: np.ndarray
    inner_corner: np.ndarray
    lid_polygon: np.ndarray
    openness: float

    @property
    def fissure_width(self) -> float:
        """Corner-to-corner width of the eye opening."""
        return float(np.linalg.norm(self.outer_corner - self.inner_corner))

    @property
    def pixels_per_mm(self) -> float:
        """Image scale at this eye's depth, from the known physical iris size.

        The iris projects to an ellipse whose semi-major axis is unaffected by
        how far the eye is turned, which makes it a stable ruler.
        """
        return self.iris_semi_major / IRIS_RADIUS_MM

    def eyeball_center_anchor(self, outer_weight: float = OUTER_CORNER_WEIGHT) -> np.ndarray:
        """Where the eyeball's centre of rotation projects, ignoring head turn.

        Interpolates between the eyelid corners. ``gaze`` applies the remaining
        depth parallax, which needs the head pose.
        """
        return outer_weight * self.outer_corner + (1.0 - outer_weight) * self.inner_corner


def _iris_semi_major(points: np.ndarray, center: np.ndarray) -> float:
    return float(np.max(np.linalg.norm(points - center, axis=1)))


def eye_aspect_ratio(landmarks: np.ndarray, eye: EyeIndices) -> float:
    """Height-to-width ratio of the eye opening, the usual blink signal.

    Around 0.25-0.35 for an open eye and near zero for a closed one, though the
    exact value varies enough between people that ``processor`` treats it with
    hysteresis rather than a hard threshold.
    """
    width = float(np.linalg.norm(landmarks[eye.outer_corner] - landmarks[eye.inner_corner]))
    if width < 1e-6:
        return 0.0
    heights = [float(np.linalg.norm(landmarks[a] - landmarks[b])) for a, b in eye.ear_pairs]
    return float(np.mean(heights) / width)


def extract_eye(landmarks: np.ndarray, eye: EyeIndices) -> EyeGeometry:
    """Measure one eye from a frame's landmark array.

    Args:
        landmarks: ``(478, 2)`` array of pixel coordinates.
        eye: Which eye's indices to read.
    """
    if landmarks.ndim != 2 or landmarks.shape[1] != 2:
        raise ValueError("landmarks must be an (N, 2) array of pixel coordinates")
    center = np.asarray(landmarks[eye.iris_center], dtype=np.float64)
    ring = np.asarray(landmarks[list(eye.iris_ring)], dtype=np.float64)
    return EyeGeometry(
        side=eye.side,
        iris_center=center,
        iris_semi_major=_iris_semi_major(ring, center),
        outer_corner=np.asarray(landmarks[eye.outer_corner], dtype=np.float64),
        inner_corner=np.asarray(landmarks[eye.inner_corner], dtype=np.float64),
        lid_polygon=np.asarray(landmarks[list(eye.lid_ring)], dtype=np.float64),
        openness=eye_aspect_ratio(landmarks, eye),
    )


def aperture_half_height(lid_polygon: np.ndarray) -> float:
    """Largest distance from inside the eye opening to its boundary, in pixels.

    This is what limits how far the iris can be slid before the warp runs out of
    room, so ``warp`` and ``gaze`` both budget against it. Computed as the
    polygon's inradius by sampling, which avoids rasterising at this stage.
    """
    poly = np.asarray(lid_polygon, dtype=np.float64)
    if len(poly) < 3:
        return 0.0
    lo = poly.min(axis=0)
    hi = poly.max(axis=0)
    if np.any(hi - lo < 1e-6):
        return 0.0

    # Sample the bounding box and keep the interior point furthest from any edge.
    gx, gy = np.meshgrid(np.linspace(lo[0], hi[0], 33), np.linspace(lo[1], hi[1], 33))
    pts = np.column_stack([gx.ravel(), gy.ravel()])

    a = poly
    b = np.roll(poly, -1, axis=0)
    seg = b - a
    seg_len2 = np.maximum(np.einsum("ij,ij->i", seg, seg), 1e-12)
    rel = pts[:, None, :] - a[None, :, :]
    t = np.clip(np.einsum("nij,ij->ni", rel, seg) / seg_len2, 0.0, 1.0)
    closest = a[None, :, :] + t[..., None] * seg[None, :, :]
    edge_dist = np.min(np.linalg.norm(pts[:, None, :] - closest, axis=2), axis=1)

    inside = _points_in_polygon(pts, poly)
    if not np.any(inside):
        return 0.0
    return float(edge_dist[inside].max())


def _points_in_polygon(pts: np.ndarray, poly: np.ndarray) -> np.ndarray:
    """Even-odd ray casting for a batch of points."""
    x, y = pts[:, 0], pts[:, 1]
    inside = np.zeros(len(pts), dtype=bool)
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        straddles = (yi > y) != (yj > y)
        with np.errstate(divide="ignore", invalid="ignore"):
            x_cross = (xj - xi) * (y - yi) / np.where(yj - yi == 0, np.nan, yj - yi) + xi
        inside ^= straddles & (x < x_cross)
        j = i
    return inside
