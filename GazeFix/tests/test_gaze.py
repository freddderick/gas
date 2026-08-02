import numpy as np
import pytest

from gazefix.anatomy import EYEBALL_RADIUS_MM, RIGHT_EYE
from gazefix.camera import CameraModel
from gazefix.gaze import (
    angle_between,
    displacement_budget,
    eyeball_center,
    head_pose_attenuation,
    limit_displacement,
    look_away_attenuation,
    solve_eye,
    unit_gaze,
)
from gazefix.geometry import extract_eye
from gazefix.headpose import HeadPose

from test_geometry import synthetic_landmarks


def rotation(yaw_deg=0.0, pitch_deg=0.0):
    yaw, pitch = np.radians(yaw_deg), np.radians(pitch_deg)
    ry = np.array([[np.cos(yaw), 0, np.sin(yaw)], [0, 1, 0], [-np.sin(yaw), 0, np.cos(yaw)]])
    rx = np.array([[1, 0, 0], [0, np.cos(pitch), -np.sin(pitch)],
                   [0, np.sin(pitch), np.cos(pitch)]])
    return ry @ rx


# ------------------------------------------------------------------ camera

def test_focal_length_follows_the_field_of_view():
    """A narrower view is a longer lens."""
    wide = CameraModel(1000, 1000, fov_deg=90.0)
    narrow = CameraModel(1000, 1000, fov_deg=30.0)
    assert wide.focal_px == pytest.approx(500.0)
    assert narrow.focal_px > wide.focal_px


def test_lens_direction_from_the_centre_points_straight_out():
    camera = CameraModel(640, 480)
    assert camera.direction_to_lens(camera.center) == pytest.approx([0, 0, 1], abs=1e-9)


def test_lens_direction_tilts_towards_the_axis():
    """A point high in the frame must look downwards to meet the lens."""
    camera = CameraModel(640, 480)
    direction = camera.direction_to_lens(np.array([320.0, 100.0]))
    assert direction[1] < 0
    assert direction[0] == pytest.approx(0.0, abs=1e-9)


def test_camera_rejects_impossible_geometry():
    with pytest.raises(ValueError):
        CameraModel(0, 480)
    with pytest.raises(ValueError):
        CameraModel(640, 480, fov_deg=200.0)


# -------------------------------------------------------------- head pose

def test_identity_pose_is_square_to_the_camera():
    pose = HeadPose.from_matrix(np.eye(4))
    assert pose.yaw_deg == pytest.approx(0.0)
    assert pose.pitch_deg == pytest.approx(0.0)
    assert pose.roll_deg == pytest.approx(0.0)
    assert pose.forward == pytest.approx([0, 0, 1])


def test_yaw_and_pitch_come_back_out_of_the_matrix():
    pose = HeadPose.from_matrix(rotation(yaw_deg=25.0))
    assert pose.yaw_deg == pytest.approx(25.0, abs=0.5)
    pose = HeadPose.from_matrix(rotation(pitch_deg=-15.0))
    assert pose.pitch_deg == pytest.approx(-15.0, abs=0.5)


def test_projected_axes_flip_the_vertical():
    """Up in the world is up the screen, which is towards row zero."""
    axes = HeadPose.from_matrix(np.eye(4)).projected_axes(2.0)
    assert axes @ np.array([1.0, 0.0]) == pytest.approx([2.0, 0.0])
    assert axes @ np.array([0.0, 1.0]) == pytest.approx([0.0, -2.0])


def test_projected_axes_foreshorten_with_yaw():
    frontal = HeadPose.from_matrix(np.eye(4)).projected_axes(1.0)
    turned = HeadPose.from_matrix(rotation(yaw_deg=60.0)).projected_axes(1.0)
    assert abs(turned[0, 0]) < abs(frontal[0, 0])


def test_a_profile_view_is_flagged_as_degenerate():
    assert not HeadPose.from_matrix(rotation(yaw_deg=30.0)).axes_are_degenerate()
    assert HeadPose.from_matrix(rotation(yaw_deg=89.0)).axes_are_degenerate()


# ------------------------------------------------------------ gaze solving

def test_gaze_directions_and_angles():
    assert unit_gaze([0.0, 0.0]) == pytest.approx([0, 0, 1])
    assert np.linalg.norm(unit_gaze([0.9, 0.9])) == pytest.approx(1.0, abs=1e-3)
    assert np.degrees(angle_between([0.0, 0.0], [0.0, 0.0])) == pytest.approx(0.0)
    assert np.degrees(angle_between([0.0, 0.0], [np.sin(np.radians(20)), 0.0])) \
        == pytest.approx(20.0, abs=0.01)


def test_an_eye_centred_on_its_anchor_reads_as_looking_straight_ahead():
    points = synthetic_landmarks()
    eye = extract_eye(points, RIGHT_EYE)
    pose = HeadPose.from_matrix(np.eye(4))
    # Put the lens exactly where this eye is looking, so nothing needs fixing.
    center = eyeball_center(eye, pose, outer_weight=0.5)
    camera = CameraModel(200, 100, principal_point=tuple(center))
    solution = solve_eye(eye, pose, camera, outer_weight=0.5)
    assert solution is not None
    assert solution.gaze_now == pytest.approx([0.0, 0.0], abs=1e-9)
    assert solution.residual_deg == pytest.approx(0.0, abs=1e-6)
    assert solution.displacement_px == pytest.approx([0.0, 0.0], abs=1e-9)


def test_a_displaced_iris_reads_as_looking_that_way():
    """An iris pushed right of centre must report gaze to the right."""
    scale = 4.0 / 5.85  # pixels per mm for a 4 px iris
    offset = EYEBALL_RADIUS_MM * np.sin(np.radians(15.0)) * scale
    points = synthetic_landmarks(iris_offset=(offset, 0.0))
    eye = extract_eye(points, RIGHT_EYE)
    pose = HeadPose.from_matrix(np.eye(4))
    camera = CameraModel(200, 100, principal_point=(100.0, 50.0))
    solution = solve_eye(eye, pose, camera, outer_weight=0.5)
    assert np.degrees(np.arcsin(solution.gaze_now[0])) == pytest.approx(15.0, abs=0.3)


def test_correction_points_the_eye_back_at_the_lens():
    scale = 4.0 / 5.85
    offset = EYEBALL_RADIUS_MM * np.sin(np.radians(12.0)) * scale
    points = synthetic_landmarks(iris_offset=(offset, 0.0))
    eye = extract_eye(points, RIGHT_EYE)
    pose = HeadPose.from_matrix(np.eye(4))
    camera = CameraModel(200, 100, principal_point=(100.0, 50.0))
    solution = solve_eye(eye, pose, camera, outer_weight=0.5)
    # The eye is looking right of the lens, so it must be pulled back left.
    assert solution.displacement_px[0] < 0
    assert solution.displacement_px[0] == pytest.approx(-offset, abs=0.15)
    assert solution.residual_deg == pytest.approx(12.0, abs=0.4)


def test_solving_gives_up_on_a_profile():
    eye = extract_eye(synthetic_landmarks(), RIGHT_EYE)
    camera = CameraModel(200, 100)
    assert solve_eye(eye, HeadPose.from_matrix(rotation(yaw_deg=89.0)), camera) is None


def test_eyeball_centre_slides_back_when_the_head_turns():
    eye = extract_eye(synthetic_landmarks(), RIGHT_EYE)
    square = eyeball_center(eye, HeadPose.from_matrix(np.eye(4)), 0.5)
    turned = eyeball_center(eye, HeadPose.from_matrix(rotation(yaw_deg=35.0)), 0.5)
    assert square[0] == pytest.approx((eye.outer_corner[0] + eye.inner_corner[0]) / 2)
    assert abs(turned[0] - square[0]) > 0.5


# --------------------------------------------------------------- gating

def test_look_away_fades_out_between_the_thresholds():
    assert look_away_attenuation(0.0, 11.0, 16.0) == pytest.approx(1.0)
    assert look_away_attenuation(11.0, 11.0, 16.0) == pytest.approx(1.0)
    assert look_away_attenuation(30.0, 11.0, 16.0) == pytest.approx(0.0)
    middle = look_away_attenuation(13.5, 11.0, 16.0)
    assert 0.2 < middle < 0.8


def test_look_away_is_monotone():
    values = [look_away_attenuation(d, 11.0, 16.0) for d in range(0, 40)]
    assert all(a >= b - 1e-12 for a, b in zip(values, values[1:]))


def test_head_pose_gate_closes_as_the_head_turns_away():
    assert head_pose_attenuation(HeadPose.from_matrix(np.eye(4)), 32.0, 26.0) \
        == pytest.approx(1.0)
    assert head_pose_attenuation(
        HeadPose.from_matrix(rotation(yaw_deg=60.0)), 32.0, 26.0) == pytest.approx(0.0)
    partial = head_pose_attenuation(HeadPose.from_matrix(rotation(yaw_deg=28.0)), 32.0, 26.0)
    assert 0.0 < partial < 1.0


def test_budget_scales_with_the_eye_opening():
    assert displacement_budget(4.0) > displacement_budget(2.0) > 0
    assert displacement_budget(0.0) == 0.0
    assert displacement_budget(-1.0) == 0.0


def test_limiting_preserves_direction_and_reports_clamping():
    kept, clamped = limit_displacement(np.array([1.0, 0.0]), 3.0)
    assert kept == pytest.approx([1.0, 0.0])
    assert not clamped

    kept, clamped = limit_displacement(np.array([6.0, 8.0]), 5.0)
    assert clamped
    assert np.linalg.norm(kept) == pytest.approx(5.0)
    assert kept[1] / kept[0] == pytest.approx(8.0 / 6.0)


def test_a_zero_budget_blocks_everything():
    kept, clamped = limit_displacement(np.array([2.0, 0.0]), 0.0)
    assert kept == pytest.approx([0.0, 0.0])
    assert clamped
