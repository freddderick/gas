"""Alert math (spec section 6.3). Pure functions, no I/O.

Everything here works on a single sea-level pressure series (pressure_msl
from Open-Meteo), keyed by hour-aligned unix timestamps. Surface pressure is
never passed in, by design (spec section 5.3, the one-variable rule).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Literal, Mapping
from zoneinfo import ZoneInfo

HOUR = 3600

Direction = Literal["fall", "rise"]
DIRECTIONS: tuple[Direction, Direction] = ("fall", "rise")

# Pressure must recover this far from the alerted level before the same
# direction can alert again (spec 6.3).
RECOVERY_HPA = 2.0

# If the evaluator has been down, never replay more than this many hours of
# crossings: a stale alert is worse than none.
MAX_CATCH_UP_HOURS = 6

Series = Mapping[int, float]


def floor_hour(ts: int) -> int:
    return ts - ts % HOUR


def change(series: Series, at: int, hours: int) -> float | None:
    """pressure(at) - pressure(at - hours). None if either end is missing."""
    now = series.get(at)
    then = series.get(at - hours * HOUR)
    if now is None or then is None:
        return None
    return now - then


@dataclass(frozen=True)
class Rule:
    enabled: bool
    hpa: float
    hours: int


@dataclass(frozen=True)
class DirectionRules:
    short: Rule
    long: Rule

    def enabled(self) -> list[Rule]:
        return [r for r in (self.short, self.long) if r.enabled]


@dataclass(frozen=True)
class QuietHours:
    enabled: bool = True
    start: time = time(22, 0)
    end: time = time(7, 0)

    def contains(self, local: time) -> bool:
        if not self.enabled or self.start == self.end:
            return False
        if self.start < self.end:
            return self.start <= local < self.end
        # Wraps past midnight, e.g. 22:00-07:00.
        return local >= self.start or local < self.end


Unit = Literal["hPa", "inHg", "mmHg"]


@dataclass(frozen=True)
class AlertSettings:
    fall: DirectionRules
    rise: DirectionRules
    quiet_hours: QuietHours = field(default_factory=QuietHours)
    unit: Unit = "hPa"

    def rules(self, direction: Direction) -> DirectionRules:
        return self.fall if direction == "fall" else self.rise


def default_alert_settings() -> AlertSettings:
    """Spec 4.1: 5 hPa in 3 hours and 10 hPa in 24 hours, both directions."""
    rules = DirectionRules(short=Rule(True, 5.0, 3), long=Rule(True, 10.0, 24))
    return AlertSettings(fall=rules, rise=rules)


@dataclass
class DirectionState:
    """None means armed. A number is the pressure we last alerted at."""

    alerted_level: float | None = None
    alerted_ts: int | None = None

    @property
    def armed(self) -> bool:
        return self.alerted_level is None


@dataclass(frozen=True)
class Crossing:
    direction: Direction
    ts: int
    pressure: float
    change: float
    rule: Rule


@dataclass(frozen=True)
class AlertDecision:
    crossing: Crossing
    quiet: bool
    title: str
    body: str


def find_crossing(series: Series, at: int, direction: Direction, rules: DirectionRules) -> Crossing | None:
    """The first enabled rule (short window before long) crossed at `at`."""
    pressure = series.get(at)
    if pressure is None:
        return None
    for rule in rules.enabled():
        delta = change(series, at, rule.hours)
        if delta is None:
            continue
        moved = -delta if direction == "fall" else delta
        if moved >= rule.hpa:
            return Crossing(direction, at, pressure, delta, rule)
    return None


def _recovered(direction: Direction, state: DirectionState, pressure: float) -> bool:
    assert state.alerted_level is not None
    if direction == "fall":
        return pressure >= state.alerted_level + RECOVERY_HPA
    return pressure <= state.alerted_level - RECOVERY_HPA


def step(
    series: Series,
    at: int,
    settings: AlertSettings,
    states: dict[Direction, DirectionState],
) -> list[Crossing]:
    """Advance the dedup state machine by one hour. Mutates `states`.

    Returns the crossings that should alert at this hour. A direction that has
    already alerted stays quiet until pressure recovers by RECOVERY_HPA from
    the alerted level, or until a crossing in the opposite direction alerts.
    """
    pressure = series.get(at)
    if pressure is None:
        return []

    for direction in DIRECTIONS:
        state = states[direction]
        if not state.armed and _recovered(direction, state, pressure):
            states[direction] = DirectionState()

    fired: list[Crossing] = []
    for direction in DIRECTIONS:
        crossing = find_crossing(series, at, direction, settings.rules(direction))
        if crossing is not None and states[direction].armed:
            fired.append(crossing)

    fired_directions = {c.direction for c in fired}
    for crossing in fired:
        states[crossing.direction] = DirectionState(crossing.pressure, crossing.ts)
    for direction in DIRECTIONS:
        opposite: Direction = "rise" if direction == "fall" else "fall"
        if opposite in fired_directions and direction not in fired_directions:
            states[direction] = DirectionState()
    return fired


def evaluate(
    series: Series,
    now: int,
    last_evaluated: int | None,
    settings: AlertSettings,
    states: dict[Direction, DirectionState],
    tz: ZoneInfo,
) -> tuple[list[AlertDecision], int | None]:
    """Run the state machine over every complete hour since the last run.

    Returns at most one decision per direction (the most recent crossing) and
    the new last-evaluated hour. Mutates `states`.
    """
    current = floor_hour(now)
    available = [ts for ts in series if ts <= current]
    if not available:
        return [], last_evaluated
    current = max(available)

    start = current - (MAX_CATCH_UP_HOURS - 1) * HOUR
    if last_evaluated is not None:
        start = max(start, last_evaluated + HOUR)

    latest: dict[Direction, Crossing] = {}
    ts = start
    while ts <= current:
        for crossing in step(series, ts, settings, states):
            latest[crossing.direction] = crossing
        ts += HOUR

    decisions = []
    for direction in DIRECTIONS:
        crossing = latest.get(direction)
        if crossing is None:
            continue
        local = datetime.fromtimestamp(now, tz).time()
        title, body = alert_text(crossing, settings.unit)
        decisions.append(AlertDecision(crossing, settings.quiet_hours.contains(local), title, body))
    return decisions, max(current, last_evaluated or current)


# --- Units and plain-language text -------------------------------------------

_PER_HPA = {"hPa": 1.0, "inHg": 0.029529983071445, "mmHg": 0.750061683}
_PRESSURE_DECIMALS = {"hPa": 0, "inHg": 2, "mmHg": 0}
_CHANGE_DECIMALS = {"hPa": 1, "inHg": 2, "mmHg": 1}


def _trim(value: float, decimals: int) -> str:
    """6.0 -> "6", 5.25 -> "5.3" (at 1 decimal)."""
    text = f"{value:.{decimals}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def format_pressure(hpa: float, unit: Unit) -> str:
    return f"{hpa * _PER_HPA[unit]:.{_PRESSURE_DECIMALS[unit]}f} {unit}"


def format_change(hpa: float, unit: Unit) -> str:
    return f"{_trim(abs(hpa) * _PER_HPA[unit], _CHANGE_DECIMALS[unit])} {unit}"


def _hours(n: int) -> str:
    return "1 hour" if n == 1 else f"{n} hours"


def alert_text(crossing: Crossing, unit: Unit) -> tuple[str, str]:
    """Title and body. Information-only language: "often linked to", never a
    claim that pressure causes symptoms (spec section 11)."""
    rule = crossing.rule
    falling = crossing.direction == "fall"
    fast = rule.hours <= 6
    verb = "falling" if falling else "rising"
    title = f"Pressure {verb} fast" if fast else f"Big pressure {'drop' if falling else 'rise'}"
    lead = f"Pressure is {verb} fast" if fast else f"Pressure is {verb}"
    window = "hour" if rule.hours == 1 else f"{rule.hours} hours"
    body = (
        f"{lead}: {'down' if falling else 'up'} {format_change(crossing.change, unit)} "
        f"in the last {window}, now {format_pressure(crossing.pressure, unit)}. "
        f"Your alert is set for {format_change(rule.hpa, unit)} in {_hours(rule.hours)}. "
        "A swing like this is often linked to headaches."
    )
    return title, body
