import pytest

from gazefix.config import CorrectionSettings
from gazefix.warp import WarpParams


def test_defaults_are_self_consistent():
    settings = CorrectionSettings()
    assert settings.falloff_start_deg <= settings.max_correction_deg
    assert settings.blink_close_ear < settings.blink_open_ear
    assert 0.0 <= settings.strength <= 1.0


def test_lens_position_resolves_against_a_frame():
    settings = CorrectionSettings(lens_position=(0.5, 0.25))
    assert settings.principal_point_px(1920, 1080) == (960.0, 270.0)


def test_a_lens_outside_the_frame_is_allowed():
    """Cropped footage often puts the real camera outside the final framing."""
    settings = CorrectionSettings(lens_position=(0.5, -0.3))
    assert settings.principal_point_px(1000, 1000) == (500.0, -300.0)


@pytest.mark.parametrize("kwargs", [
    {"strength": 1.5},
    {"strength": -0.1},
    {"max_correction_deg": 5.0, "falloff_start_deg": 10.0},
    {"blink_close_ear": 0.3, "blink_open_ear": 0.2},
    {"max_faces": 0},
    {"fov_deg": 0.5},
    {"fov_deg": 200.0},
    {"lens_position": (0.5, 9.0)},
])
def test_impossible_settings_are_refused(kwargs):
    with pytest.raises(ValueError):
        CorrectionSettings(**kwargs)


def test_round_trips_through_a_dict():
    original = CorrectionSettings(strength=0.6, lens_position=(0.4, 0.2), fov_deg=48.0)
    restored = CorrectionSettings.from_dict(original.to_dict())
    assert restored.strength == 0.6
    assert restored.lens_position == (0.4, 0.2)
    assert restored.fov_deg == 48.0
    assert restored.warp == original.warp


def test_unknown_keys_are_ignored():
    """A newer client must not be able to crash an older server."""
    settings = CorrectionSettings.from_dict({"strength": 0.5, "invented_later": True})
    assert settings.strength == 0.5


def test_nulls_fall_back_to_defaults():
    settings = CorrectionSettings.from_dict({"strength": None})
    assert settings.strength == CorrectionSettings().strength


def test_warp_params_survive_a_json_style_round_trip():
    settings = CorrectionSettings.from_dict({"warp": {"lid_follow": [0.2, 0.6]}})
    assert settings.warp.lid_follow == (0.2, 0.6)
    assert settings.warp.corner_pin == WarpParams().corner_pin


def test_from_dict_accepts_nothing_at_all():
    assert CorrectionSettings.from_dict({}).strength == 1.0
    assert CorrectionSettings.from_dict(None).strength == 1.0
