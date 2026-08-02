"""End-to-end tests against the real detector.

These need the landmarker model and a real face, so they skip when either is
missing. ``tools/fetch_fixtures.py`` gets both.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from gazefix.anatomy import EYES  # noqa: E402
from gazefix.camera import CameraModel  # noqa: E402
from gazefix.config import CorrectionSettings  # noqa: E402
from gazefix.gaze import solve_eye  # noqa: E402
from gazefix.geometry import aperture_half_height, extract_eye  # noqa: E402
from gazefix.pipeline import correct_image, correct_video, split_comparison  # noqa: E402

FIXTURE_DIR = Path(__file__).parent / "fixtures"
PORTRAIT = FIXTURE_DIR / "portrait.jpg"

pytestmark = pytest.mark.model


@pytest.fixture
def portrait(needs_model):
    if not PORTRAIT.exists():
        pytest.skip("no portrait fixture; run tools/fetch_fixtures.py")
    return cv2.imread(str(PORTRAIT))


@pytest.fixture
def tracker(needs_model):
    from gazefix.landmarks import FaceTracker

    with FaceTracker(video=False) as t:
        yield t


@pytest.fixture
def face(portrait, tracker):
    faces = tracker.detect(portrait, 0)
    assert faces, "the detector should find the fixture's face"
    return faces[0]


def test_the_detector_returns_a_full_refined_mesh(face):
    assert face.landmarks.shape == (478, 2)
    assert np.isfinite(face.landmarks).all()


def test_the_fixture_is_facing_the_camera(face):
    assert abs(face.pose.yaw_deg) < 15
    assert abs(face.pose.roll_deg) < 15


def test_the_two_eyes_agree_about_where_they_are_looking(face, portrait):
    """The strongest available check with no ground truth.

    Real eyes converge on a single point, so two eyes of one face must report
    nearly the same direction. They are solved independently from different
    landmarks, so agreement is evidence the geometry is right rather than
    self-fulfilling.
    """
    height, width = portrait.shape[:2]
    camera = CameraModel(width, height)
    gazes = []
    for indices in EYES:
        solution = solve_eye(extract_eye(face.landmarks, indices), face.pose, camera)
        assert solution is not None
        gazes.append(solution.gaze_now)
    disagreement = np.degrees(np.arcsin(np.clip(gazes[0] - gazes[1], -1, 1)))
    assert abs(disagreement[0]) < 4.0, f"horizontal disagreement {disagreement[0]:.1f} deg"
    assert abs(disagreement[1]) < 4.0, f"vertical disagreement {disagreement[1]:.1f} deg"


def test_measured_eye_geometry_is_anatomically_sane(face):
    for indices in EYES:
        eye = extract_eye(face.landmarks, indices)
        assert 2.0 < eye.iris_semi_major < 40.0
        # An eye opening is a few times wider than it is deep.
        assert 0.15 < aperture_half_height(eye.lid_polygon) / eye.iris_semi_major < 1.5
        assert 0.1 < eye.openness < 0.6


def test_correcting_a_still_changes_only_the_eyes(portrait, tracker):
    settings = CorrectionSettings(lens_position=(0.5, 0.30), max_correction_deg=30.0,
                                  falloff_start_deg=24.0)
    corrected, report = correct_image(portrait, settings, tracker)
    assert report["faces_detected"] == 1
    assert len(report["eyes"]) == 2
    assert all(eye["applied_px"] > 0 for eye in report["eyes"])

    changed = np.abs(corrected.astype(int) - portrait.astype(int)).sum(axis=2) > 6
    ys, xs = np.nonzero(changed)
    assert len(ys) > 0, "something should have changed"

    # Everything that moved must sit near an eye, not elsewhere on the face.
    eye_centres = [extract_eye(f, i).iris_center
                   for f in [tracker.detect(portrait, 0)[0].landmarks] for i in EYES]
    reach = 3.0 * extract_eye(tracker.detect(portrait, 0)[0].landmarks, EYES[0]).fissure_width
    for cx, cy in zip(xs, ys):
        assert min(np.hypot(cx - e[0], cy - e[1]) for e in eye_centres) < reach


def test_a_face_looking_at_the_lens_is_left_alone(portrait, tracker):
    """With the lens placed where the subject is already looking, do nothing."""
    height, width = portrait.shape[:2]
    camera = CameraModel(width, height)
    face = tracker.detect(portrait, 0)[0]
    eye = extract_eye(face.landmarks, EYES[0])
    solution = solve_eye(eye, face.pose, camera)

    # Aim the lens along this eye's current gaze, which zeroes the correction.
    direction = face.pose.rotation @ np.array(
        [solution.gaze_now[0], solution.gaze_now[1],
         np.sqrt(max(1 - solution.gaze_now @ solution.gaze_now, 0.0))]
    )
    centre = solution.eyeball_center_px
    lens = centre + camera.focal_px * np.array([direction[0], -direction[1]]) / max(
        direction[2], 1e-6)
    settings = CorrectionSettings(
        lens_position=(float(lens[0] / width), float(lens[1] / height)))
    _, report = correct_image(portrait, settings, tracker)
    assert report["eyes"][0]["residual_deg"] < 2.0
    assert report["eyes"][0]["applied_px"] < 0.5


def test_strength_scales_the_correction(portrait, tracker):
    def shift(strength):
        settings = CorrectionSettings(strength=strength, lens_position=(0.5, 0.30),
                                      max_correction_deg=30.0, falloff_start_deg=24.0)
        _, report = correct_image(portrait, settings, tracker)
        return report["eyes"][0]["applied_px"]

    assert shift(0.0) == pytest.approx(0.0, abs=1e-6)
    assert shift(0.5) < shift(1.0)


def test_a_deliberate_look_away_is_left_alone(portrait, tracker):
    """Way off the lens, the correction should switch itself off."""
    settings = CorrectionSettings(lens_position=(0.5, 0.9),
                                  falloff_start_deg=6.0, max_correction_deg=9.0)
    _, report = correct_image(portrait, settings, tracker)
    assert all(eye["gain"] == pytest.approx(0.0, abs=1e-6) for eye in report["eyes"])
    assert all(eye["applied_px"] == pytest.approx(0.0, abs=1e-6) for eye in report["eyes"])


def test_split_comparison_joins_two_frames(portrait):
    other = np.zeros_like(portrait)
    joined = split_comparison(portrait, other, 0.5)
    width = portrait.shape[1]
    assert np.array_equal(joined[:, : width // 2], portrait[:, : width // 2])
    assert joined[:, width // 2 + 2:].max() == 0

    with pytest.raises(ValueError):
        split_comparison(portrait, np.zeros((4, 4, 3), np.uint8))


def test_a_whole_clip_runs_and_calibrates(portrait, tmp_path, needs_model):
    """Correct a short clip built by drifting a real face around the frame."""
    frame = cv2.resize(portrait, (512, 640))
    source = tmp_path / "clip.webm"
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"vp09"), 25, (512, 640))
    if not writer.isOpened():
        pytest.skip("no VP9 encoder in this OpenCV build")
    height, width = frame.shape[:2]
    for i in range(40):
        t = i / 25.0
        matrix = cv2.getRotationMatrix2D((width / 2, height / 2), 3.0 * np.sin(t * 1.1), 1.0)
        matrix[0, 2] += 7 * np.sin(t * 1.4)
        matrix[1, 2] += 5 * np.cos(t * 0.9)
        writer.write(cv2.warpAffine(frame, matrix, (width, height),
                                    borderMode=cv2.BORDER_REPLICATE))
    writer.release()

    seen = []
    report = correct_video(source, tmp_path / "out.mp4",
                           CorrectionSettings(lens_position=(0.5, 0.32),
                                              max_correction_deg=30.0,
                                              falloff_start_deg=24.0),
                           progress=lambda f, s: seen.append((f, s)))

    assert Path(report.output_path).exists()
    assert report.stats["frames"] == 40
    assert report.stats["frames_with_face"] == 40
    assert report.stats["frames_corrected"] > 30
    assert report.stats["mean_iris_shift_px"] > 0.2
    assert {stage for _, stage in seen} == {"calibrating", "correcting"}

    # A real subject should let the per-clip calibration converge, and land on
    # an anchor close to the population default rather than at a bound.
    assert report.calibration["converged"]
    assert 0.50 < report.calibration["outer_corner_weight"] < 0.66
    assert report.calibration["binocular_residual_deg"] < 4.0
