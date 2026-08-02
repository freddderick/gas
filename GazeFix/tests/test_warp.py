import cv2
import numpy as np
import pytest

from gazefix.warp import (
    WarpParams,
    build_displacement_field,
    min_jacobian,
    warp_eye,
)


def eye_polygon(cx=60.0, cy=40.0, half_width=18.0, half_height=6.0, points=16):
    angles = np.linspace(0, 2 * np.pi, points, endpoint=False)
    return np.column_stack([cx + half_width * np.cos(angles),
                            cy + half_height * np.sin(angles)])


def corners_of(polygon):
    return polygon[polygon[:, 0].argmin()], polygon[polygon[:, 0].argmax()]


def textured_frame(width=140, height=90):
    """Noise plus structure, so any displacement is measurable."""
    rng = np.random.default_rng(0)
    yy, xx = np.mgrid[0:height, 0:width]
    base = (128 + 60 * np.sin(xx / 3.0) * np.cos(yy / 2.5)).astype(np.float64)
    noise = rng.normal(0, 12, size=base.shape)
    gray = np.clip(base + noise, 0, 255).astype(np.uint8)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


# ------------------------------------------------------------------ fields

def test_field_is_zero_at_the_eye_corners():
    polygon = eye_polygon()
    outer, inner = corners_of(polygon)
    fx, fy = build_displacement_field((90, 140), polygon, (outer, inner), np.array([0.0, 3.0]))
    for corner in (outer, inner):
        x, y = int(round(corner[0])), int(round(corner[1]))
        assert abs(fx[y, x]) < 0.1
        assert abs(fy[y, x]) < 0.1


def test_field_moves_the_middle_of_the_eye():
    polygon = eye_polygon()
    displacement = np.array([0.0, 2.0])
    fx, fy = build_displacement_field((90, 140), polygon, corners_of(polygon), displacement)
    # The backward map reaches the opposite way from the displacement.
    assert fy[40, 60] < -1.0
    assert abs(fx[40, 60]) < 0.2


def test_field_vanishes_far_from_the_eye():
    polygon = eye_polygon()
    fx, fy = build_displacement_field((90, 140), polygon, corners_of(polygon),
                                      np.array([2.0, 2.0]))
    assert abs(fx[2, 2]) < 1e-3
    assert abs(fy[2, 2]) < 1e-3


def test_lid_follow_carries_skin_above_the_eye():
    polygon = eye_polygon()
    corners = corners_of(polygon)
    displacement = np.array([0.0, 3.0])
    with_follow = build_displacement_field((90, 140), polygon, corners, displacement,
                                           WarpParams(lid_follow=(0.1, 0.5)))
    without = build_displacement_field((90, 140), polygon, corners, displacement,
                                       WarpParams(lid_follow=(0.0, 0.0)))
    # Well clear of the opening, where only the socket layer can reach.
    above = (28, 60)
    assert abs(with_follow[1][above]) > 0.5
    # Not exactly zero: smoothing the eyeball weight leaves a faint tail.
    assert abs(without[1][above]) < 1e-3


def test_a_reasonable_displacement_does_not_fold():
    """Every eye-sized shift within budget must keep the map injective."""
    polygon = eye_polygon(half_height=6.0)
    corners = corners_of(polygon)
    for displacement in ([0.0, 3.0], [0.0, -3.0], [3.0, 0.0], [2.0, 2.0]):
        fx, fy = build_displacement_field((90, 140), polygon, corners, np.array(displacement))
        assert min_jacobian(fx, fy) > 0.0, displacement


def test_jacobian_of_an_untouched_field_is_one():
    zeros = np.zeros((40, 40), np.float32)
    assert min_jacobian(zeros, zeros) == pytest.approx(1.0)


def test_jacobian_detects_a_fold():
    """A ramp steeper than one pixel per pixel is a fold by definition."""
    yy, xx = np.mgrid[0:40, 0:40]
    folding = (-2.0 * xx).astype(np.float32)
    assert min_jacobian(folding, np.zeros((40, 40), np.float32)) < 0


# ------------------------------------------------------------------- warp

def test_warp_moves_pixels_inside_the_eye_and_leaves_the_rest():
    frame = textured_frame()
    polygon = eye_polygon()
    result = warp_eye(frame, polygon, corners_of(polygon), np.array([0.0, 2.0]))
    changed = np.abs(result.image.astype(int) - frame.astype(int)).sum(axis=2) > 4
    assert changed[38:42, 55:65].any(), "the eye itself should change"
    assert not changed[:10, :].any(), "the top of the frame should not"
    assert not changed[:, :10].any(), "nor the left edge"


def test_warp_is_a_no_op_for_a_negligible_displacement():
    frame = textured_frame()
    polygon = eye_polygon()
    result = warp_eye(frame, polygon, corners_of(polygon), np.array([0.0, 1e-6]))
    assert np.array_equal(result.image, frame)
    assert result.applied_fraction == 1.0


def test_warp_does_not_modify_its_input():
    frame = textured_frame()
    original = frame.copy()
    polygon = eye_polygon()
    warp_eye(frame, polygon, corners_of(polygon), np.array([0.0, 2.5]))
    assert np.array_equal(frame, original)


def test_warp_preserves_shape_and_dtype():
    frame = textured_frame()
    polygon = eye_polygon()
    result = warp_eye(frame, polygon, corners_of(polygon), np.array([1.5, 1.5]))
    assert result.image.shape == frame.shape
    assert result.image.dtype == frame.dtype


def test_fold_guard_backs_off_an_impossible_request():
    """An enormous shift on a narrow eye must be scaled down, not smeared."""
    frame = textured_frame()
    polygon = eye_polygon(half_height=2.0)
    result = warp_eye(frame, polygon, corners_of(polygon), np.array([0.0, 40.0]))
    assert result.applied_fraction < 1.0


def test_warp_survives_an_eye_at_the_frame_edge():
    frame = textured_frame()
    polygon = eye_polygon(cx=6.0, cy=5.0, half_width=8.0, half_height=3.0)
    result = warp_eye(frame, polygon, corners_of(polygon), np.array([0.0, 1.5]))
    assert result.image.shape == frame.shape
    assert np.isfinite(result.image).all()


def test_bigger_requests_move_the_eye_further_up_to_the_budget():
    frame = textured_frame()
    polygon = eye_polygon()
    corners = corners_of(polygon)
    moved = []
    for magnitude in (0.5, 1.5, 3.0):
        image = warp_eye(frame, polygon, corners, np.array([0.0, magnitude])).image
        moved.append(float(np.abs(image.astype(int) - frame.astype(int)).sum()))
    assert moved[0] < moved[1] < moved[2]
