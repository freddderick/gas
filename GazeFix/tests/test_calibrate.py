"""The anchor calibration has to recover a weight it never sees.

Each test builds eyes whose irises are placed by construction from a chosen
"true" anchor weight, then checks the fit finds that weight back. If it does,
the binocular agreement signal really is identifying the parameter rather than
returning the prior.
"""

import numpy as np
import pytest

from gazefix.anatomy import (
    EYEBALL_DEPTH_MM,
    EYEBALL_RADIUS_MM,
    LEFT_EYE,
    OUTER_CORNER_WEIGHT,
    RIGHT_EYE,
)
from gazefix.calibrate import AnchorCalibration, fit_outer_corner_weight
from gazefix.geometry import extract_eye
from gazefix.headpose import HeadPose

from test_gaze import rotation
from test_geometry import synthetic_landmarks


def make_frame(true_weight, gaze, pose, iris_radius=5.0, half_width=15.0,
               centres=((100.0, 50.0), (200.0, 50.0))):
    """Build both eyes of one face looking in a shared direction.

    The iris of each eye is placed exactly where ``true_weight`` says it should
    be for that gaze, so a fit that recovers ``true_weight`` has genuinely
    inverted the geometry.
    """
    eyes = []
    for indices, centre, outer_sign in ((RIGHT_EYE, centres[0], -1), (LEFT_EYE, centres[1], +1)):
        points = synthetic_landmarks(center=centre, iris_radius=iris_radius,
                                     half_width=half_width, eye=indices)
        # Orient the eye so its outer corner faces away from the face's midline.
        points[indices.outer_corner] = [centre[0] + outer_sign * half_width, centre[1]]
        points[indices.inner_corner] = [centre[0] - outer_sign * half_width, centre[1]]

        eye = extract_eye(points, indices)
        scale = eye.pixels_per_mm
        anchor = eye.eyeball_center_anchor(true_weight)
        forward = pose.forward
        centre_px = anchor - scale * EYEBALL_DEPTH_MM * np.array([forward[0], -forward[1]])
        axes = pose.projected_axes(scale)
        points[indices.iris_center] = centre_px + axes @ (EYEBALL_RADIUS_MM * np.asarray(gaze))
        iris = points[indices.iris_center]
        for i, index in enumerate(indices.iris_ring):
            angle = i * np.pi / 2
            points[index] = iris + iris_radius * np.array([np.cos(angle), np.sin(angle)])
        eyes.append(extract_eye(points, indices))
    return eyes[0], eyes[1], pose


def clip(true_weight, count=40, seed=0):
    rng = np.random.default_rng(seed)
    frames = []
    for _ in range(count):
        pose = HeadPose.from_matrix(rotation(yaw_deg=rng.uniform(-20, 20),
                                             pitch_deg=rng.uniform(-12, 12)))
        gaze = rng.uniform(-0.25, 0.25, size=2)
        frames.append(make_frame(true_weight, gaze, pose))
    return frames


@pytest.mark.parametrize("true_weight", [0.50, 0.57, 0.62])
def test_calibration_recovers_the_weight_it_was_built_from(true_weight):
    result = fit_outer_corner_weight(clip(true_weight))
    assert result.converged
    assert result.outer_weight == pytest.approx(true_weight, abs=0.01)
    assert result.residual_deg == pytest.approx(0.0, abs=0.5)


def test_calibration_survives_landmark_noise():
    frames = []
    rng = np.random.default_rng(7)
    for right, left, pose in clip(0.60, count=60, seed=3):
        jittered = []
        for eye in (right, left):
            noisy = type(eye)(
                side=eye.side,
                iris_center=eye.iris_center + rng.normal(0, 0.15, 2),
                iris_semi_major=eye.iris_semi_major,
                outer_corner=eye.outer_corner + rng.normal(0, 0.15, 2),
                inner_corner=eye.inner_corner + rng.normal(0, 0.15, 2),
                lid_polygon=eye.lid_polygon,
                openness=eye.openness,
            )
            jittered.append(noisy)
        frames.append((jittered[0], jittered[1], pose))
    result = fit_outer_corner_weight(frames)
    assert result.converged
    assert result.outer_weight == pytest.approx(0.60, abs=0.04)


def test_too_few_frames_keeps_the_default():
    result = fit_outer_corner_weight(clip(0.62, count=4))
    assert not result.converged
    assert result.outer_weight == OUTER_CORNER_WEIGHT
    assert result.samples == 4


def test_an_implausible_fit_is_rejected():
    """A weight outside the anatomical range means the input was degenerate."""
    result = fit_outer_corner_weight(clip(0.20, count=40))
    assert not result.converged
    assert result.outer_weight == OUTER_CORNER_WEIGHT


def test_no_frames_at_all():
    result = fit_outer_corner_weight([])
    assert not result.converged
    assert result.samples == 0
    assert np.isnan(result.residual_deg)


def test_profile_frames_are_skipped_not_fatal():
    frames = clip(0.57, count=30)
    frames += [make_frame(0.57, (0.0, 0.0), HeadPose.from_matrix(rotation(yaw_deg=89.0)))]
    result = fit_outer_corner_weight(frames)
    assert result.converged
    assert result.samples == 30


def test_default_calibration_reports_the_population_value():
    default = AnchorCalibration.default()
    assert default.outer_weight == OUTER_CORNER_WEIGHT
    assert not default.converged
