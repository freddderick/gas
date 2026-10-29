from datetime import time
from zoneinfo import ZoneInfo

from pressure_backend import analysis as a

H = a.HOUR
T0 = 1_790_000_000 - 1_790_000_000 % H  # an arbitrary hour boundary
UTC = ZoneInfo("UTC")
NO_QUIET = a.QuietHours(enabled=False)


def series(*values: float, start: int = T0) -> dict[int, float]:
    return {start + i * H: v for i, v in enumerate(values)}


def settings(**kw) -> a.AlertSettings:
    base = a.default_alert_settings()
    return a.AlertSettings(base.fall, base.rise, kw.get("quiet", NO_QUIET), kw.get("unit", "hPa"))


def fresh_states():
    return {d: a.DirectionState() for d in a.DIRECTIONS}


def test_change_needs_both_ends():
    s = series(1010, 1009, 1008, 1004)
    assert a.change(s, T0 + 3 * H, 3) == -6
    assert a.change(s, T0 + 2 * H, 3) is None


def test_fall_crossing_fires_at_threshold_exactly():
    s = series(1013, 1011, 1010, 1008)  # -5 in 3 h
    fired = a.step(s, T0 + 3 * H, settings(), fresh_states())
    assert [c.direction for c in fired] == ["fall"]
    assert fired[0].change == -5 and fired[0].rule.hours == 3


def test_rise_crossing_fires():
    s = series(1000, 1002, 1004, 1006)
    fired = a.step(s, T0 + 3 * H, settings(), fresh_states())
    assert [c.direction for c in fired] == ["rise"]


def test_below_threshold_does_not_fire():
    s = series(1013, 1012, 1011, 1009)  # -4
    assert a.step(s, T0 + 3 * H, settings(), fresh_states()) == []


def test_24_hour_rule_fires_when_short_window_is_quiet():
    values = [1020 - i * 0.5 for i in range(25)]  # -12 over 24 h, -1.5 per 3 h
    s = series(*values)
    fired = a.step(s, T0 + 24 * H, settings(), fresh_states())
    assert len(fired) == 1 and fired[0].rule.hours == 24


def test_disabled_long_rule_is_ignored():
    rules = a.DirectionRules(a.Rule(True, 5, 3), a.Rule(False, 10, 24))
    st = a.AlertSettings(rules, rules, NO_QUIET)
    s = series(*[1020 - i * 0.5 for i in range(25)])
    assert a.step(s, T0 + 24 * H, st, fresh_states()) == []


def test_no_duplicate_alert_until_recovered_by_2_hpa():
    # Falls fast, keeps falling, wobbles up 1.5, then recovers 2.
    values = [1015, 1013, 1011, 1009, 1007, 1005, 1006.5, 1007.5, 1000, 998, 996, 994]
    s = series(*values)
    states = fresh_states()
    fires = []
    for i in range(3, len(values)):
        fires += [(i, c.direction) for c in a.step(s, T0 + i * H, settings(), states)]
    # Fires at hour 3 (1009). Later hours still cross but pressure never
    # gets back to 1011, so there is no second fall alert.
    assert fires == [(3, "fall")]


def test_realerts_after_recovery():
    values = [1015, 1013, 1011, 1009, 1011.5, 1012, 1010, 1008, 1006]
    s = series(*values)
    states = fresh_states()
    fires = []
    for i in range(3, len(values)):
        fires += [(i, c.direction) for c in a.step(s, T0 + i * H, settings(), states)]
    # Alert at 1009, recovers to 1011.5 (>= 1011) at hour 4 which re-arms,
    # then 1012 -> 1006 over 3 h crosses again at hour 8.
    assert fires == [(3, "fall"), (8, "fall")]


def test_opposite_crossing_rearms_direction():
    values = [1015, 1013, 1011, 1009, 1011, 1013, 1015, 1013, 1011, 1009]
    s = series(*values)
    # Fall is disarmed at a level it can never recover from, so only the
    # opposite-direction rule can re-arm it.
    states = {"fall": a.DirectionState(2000.0, T0), "rise": a.DirectionState()}
    fires = []
    for i in range(3, len(values)):
        fires += [(i, c.direction) for c in a.step(s, T0 + i * H, settings(), states)]
    # Rise of 6 at hour 6 fires and re-arms fall; fall of 6 at hour 9 fires.
    assert fires == [(6, "rise"), (9, "fall")]


def test_quiet_hours_wrap_midnight():
    q = a.QuietHours(True, time(22, 0), time(7, 0))
    assert q.contains(time(23, 30)) and q.contains(time(3, 0))
    assert not q.contains(time(7, 0)) and not q.contains(time(12, 0))
    same_day = a.QuietHours(True, time(13, 0), time(15, 0))
    assert same_day.contains(time(14, 0)) and not same_day.contains(time(16, 0))
    assert not a.QuietHours(False).contains(time(23, 0))


def test_evaluate_marks_quiet_decisions_in_local_time():
    s = series(1013, 1011, 1010, 1008)
    now = T0 + 3 * H + 600
    tz = ZoneInfo("America/Toronto")
    from datetime import datetime

    local_hour = datetime.fromtimestamp(now, tz).hour
    start = time((local_hour - 1) % 24, 0)
    end = time((local_hour + 1) % 24, 0)
    st = settings(quiet=a.QuietHours(True, start, end))
    decisions, last = a.evaluate(s, now, None, st, fresh_states(), tz)
    assert len(decisions) == 1 and decisions[0].quiet
    assert last == T0 + 3 * H


def test_evaluate_catches_up_on_missed_hours_once():
    # Crossing happens at hour 3; evaluator last ran at hour 2 and runs again at hour 5.
    s = series(1013, 1011, 1010, 1008, 1008, 1008)
    states = fresh_states()
    decisions, last = a.evaluate(s, T0 + 5 * H, T0 + 2 * H, settings(), states, UTC)
    assert [d.crossing.ts for d in decisions] == [T0 + 3 * H]
    assert last == T0 + 5 * H
    # Running again does not re-send.
    again, _ = a.evaluate(s, T0 + 5 * H + 900, last, settings(), states, UTC)
    assert again == []


def test_evaluate_ignores_future_forecast_hours():
    s = series(1013, 1013, 1013, 1013, 1000)  # the drop is in the future
    decisions, last = a.evaluate(s, T0 + 3 * H, None, settings(), fresh_states(), UTC)
    assert decisions == [] and last == T0 + 3 * H


def test_evaluate_caps_catch_up_window():
    values = [1013, 1011, 1010, 1008] + [1008] * 20
    s = series(*values)
    decisions, _ = a.evaluate(s, T0 + 23 * H, None, settings(), fresh_states(), UTC)
    assert decisions == []  # the hour-3 crossing is far older than MAX_CATCH_UP_HOURS


def test_alert_text_matches_spec_example():
    crossing = a.Crossing("fall", T0, 1008.0, -6.0, a.Rule(True, 5, 3))
    title, body = a.alert_text(crossing, "hPa")
    assert title == "Pressure falling fast"
    assert body.startswith("Pressure is falling fast: down 6 hPa in the last 3 hours, now 1008 hPa.")
    assert "often linked to headaches" in body
    assert "5 hPa in 3 hours" in body


def test_alert_text_long_window_and_units():
    crossing = a.Crossing("rise", T0, 1020.0, 10.4, a.Rule(True, 10, 24))
    title, body = a.alert_text(crossing, "inHg")
    assert title == "Big pressure rise"
    assert "up 0.31 inHg in the last 24 hours, now 30.12 inHg" in body
    _, mm = a.alert_text(crossing, "mmHg")
    assert "up 7.8 mmHg" in mm and "now 765 mmHg" in mm
