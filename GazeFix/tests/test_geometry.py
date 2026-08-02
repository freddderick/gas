import numpy as np
import pytest

from gazefix.anatomy import LEFT_EYE, NUM_LANDMARKS, RIGHT_EYE, EyeSide
from gazefix.geometry import (
    aperture_half_height,
    extract_eye,
    eye_aspect_ratio,
    _points_in_polygon,
)


def synthetic_landmarks(center=(100.0, 50.0), iris_offset=(0.0, 0.0), iris_radius=4.0,
                        half_width=15.0, half_height=4.0, eye=RIGHT_EYE):
    """A landmark array with one eye filled in as a clean ellipse.

    ``center`` places the eye opening; ``iris_offset`` moves the iris *within*
    it, leaving the lids and corners where they are. Keeping those independent
    matters: the corners are the reference the gaze solver measures against, so
    a fixture that slid them along with the iris would describe an eye that is
    not looking anywhere in particular.
    """
    points = np.zeros((NUM_LANDMARKS, 2))
    cx, cy = center
    ix, iy = cx + iris_offset[0], cy + iris_offset[1]
    points[eye.iris_center] = [ix, iy]
    for i, index in enumerate(eye.iris_ring):
        angle = i * np.pi / 2
        points[index] = [ix + iris_radius * np.cos(angle), iy + iris_radius * np.sin(angle)]

    ring = list(eye.lid_ring)
    for i, index in enumerate(ring):
        angle = 2 * np.pi * i / len(ring)
        points[index] = [cx - half_width * np.cos(angle), cy - half_height * np.sin(angle)]
    points[eye.outer_corner] = [cx - half_width, cy]
    points[eye.inner_corner] = [cx + half_width, cy]
    for a, b in eye.ear_pairs:
        points[a] = [cx, cy - half_height]
        points[b] = [cx, cy + half_height]
    return points


def test_extract_eye_reads_iris_and_corners():
    points = synthetic_landmarks()
    eye = extract_eye(points, RIGHT_EYE)
    assert eye.side is EyeSide.RIGHT
    assert eye.iris_center == pytest.approx([100.0, 50.0])
    assert eye.iris_semi_major == pytest.approx(4.0)
    assert eye.fissure_width == pytest.approx(30.0)


def test_pixels_per_mm_scales_with_the_iris():
    small = extract_eye(synthetic_landmarks(iris_radius=4.0), RIGHT_EYE)
    large = extract_eye(synthetic_landmarks(iris_radius=8.0), RIGHT_EYE)
    assert large.pixels_per_mm == pytest.approx(2 * small.pixels_per_mm)


def test_eyeball_anchor_sits_towards_the_outer_corner():
    eye = extract_eye(synthetic_landmarks(), RIGHT_EYE)
    anchor = eye.eyeball_center_anchor(0.57)
    midpoint = (eye.outer_corner + eye.inner_corner) / 2
    assert np.linalg.norm(anchor - eye.outer_corner) < np.linalg.norm(anchor - eye.inner_corner)
    # 7% of the way from the midpoint towards the outer corner.
    assert anchor[0] == pytest.approx(midpoint[0] - 0.07 * eye.fissure_width)


def test_anchor_weight_of_a_half_is_the_midpoint():
    eye = extract_eye(synthetic_landmarks(), RIGHT_EYE)
    midpoint = (eye.outer_corner + eye.inner_corner) / 2
    assert eye.eyeball_center_anchor(0.5) == pytest.approx(midpoint)


def test_aspect_ratio_falls_as_the_eye_closes():
    open_eye = eye_aspect_ratio(synthetic_landmarks(half_height=5.0), RIGHT_EYE)
    narrow = eye_aspect_ratio(synthetic_landmarks(half_height=2.0), RIGHT_EYE)
    shut = eye_aspect_ratio(synthetic_landmarks(half_height=0.0), RIGHT_EYE)
    assert open_eye > narrow > shut
    assert shut == pytest.approx(0.0)


def test_aspect_ratio_is_scale_invariant():
    """A face twice as far away must not read as a blink."""
    near = eye_aspect_ratio(synthetic_landmarks(half_width=30.0, half_height=8.0), RIGHT_EYE)
    far = eye_aspect_ratio(synthetic_landmarks(half_width=15.0, half_height=4.0), RIGHT_EYE)
    assert near == pytest.approx(far)


def test_aperture_half_height_tracks_the_opening():
    wide = aperture_half_height(extract_eye(
        synthetic_landmarks(half_height=6.0), RIGHT_EYE).lid_polygon)
    narrow = aperture_half_height(extract_eye(
        synthetic_landmarks(half_height=2.0), RIGHT_EYE).lid_polygon)
    assert wide > narrow > 0
    assert narrow == pytest.approx(2.0, abs=0.4)


def test_aperture_half_height_of_a_degenerate_polygon_is_zero():
    flat = np.array([[0.0, 5.0], [10.0, 5.0], [20.0, 5.0]])
    assert aperture_half_height(flat) == 0.0
    assert aperture_half_height(np.zeros((2, 2))) == 0.0


def test_point_in_polygon_matches_a_known_square():
    square = np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]])
    pts = np.array([[5.0, 5.0], [-1.0, 5.0], [5.0, 11.0], [9.9, 0.1]])
    assert _points_in_polygon(pts, square).tolist() == [True, False, False, True]


def test_both_eyes_use_distinct_landmarks():
    assert set(RIGHT_EYE.lid_ring).isdisjoint(LEFT_EYE.lid_ring)
    assert set(RIGHT_EYE.iris_ring).isdisjoint(LEFT_EYE.iris_ring)


def test_extract_eye_rejects_the_wrong_shape():
    with pytest.raises(ValueError):
        extract_eye(np.zeros((NUM_LANDMARKS, 3)), RIGHT_EYE)
