"""Forecast GTA VI's launch-day Twitch viewers, hour by hour.

Reads one case (schema "makefun/twitch-ccu-case/v1") from the input directory
and writes, for each of hours 2..24 of the release day, five quantiles
(5%, 25%, 50%, 75%, 95%) of that hour's Twitch category concurrent viewers.

Method
------
The program only ever sees the case file it is given: hour 1's print and the
`comparables`, past big game launches' hourly Twitch curves. Launch days have
a shape that is remarkably stable once you know how big hour 1 was: a launch
whose first hour is already huge (its regions have unlocked) stays near that
level, while one whose first hour is still tiny (its unlock is still coming)
climbs several-fold by the evening. So for each hour h the program fits, over
the comparables,

    log(viewers_h) = a_h + b_h * log(viewers_1)

an ordinary least-squares line of that hour's count on the first hour's
count. The fitted slope falls from about 1 at hour 2 (the next hour tracks
hour 1 almost one-for-one) to near 0 by hour 20 (the evening peak barely
depends on hour 1 at all) -- the launches regress to a common evening level.
The forecast median is the fitted line at the case's own hour-1 print; the
spread is the honest between-launch spread, the empirical quantiles of the
fit's residuals, so hours launches disagree about get wide bands.

Two fits are blended. One uses every comparable; the other only the
"launched" ones, whose hour-1 print is already at least 10,000 viewers --
launches whose first hour was still pre-unlock have enormous later ratios and
would otherwise drag the line. The blend weight is p1 / (p1 + 20,000), so a
small hour-1 print leans on the all-launch fit and a big one on the
launched-only fit. A light three-hour moving average smooths the fitted
quantile curves across neighbouring hours, and a flat persistence forecast
(the house baseline's shape) covers any hour too thin to fit.

Everything is standard library only, deterministic (the same case file always
yields the same bytes), and fast: fitting 23 hours x 2 lines over a few dozen
launches takes a fraction of a second.

Run it:
    mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
"""

import json
import math
import os
from datetime import datetime, timedelta
from pathlib import Path

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

# The quantile levels the contest scores, in the order each row lists them.
LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
# Hour-1 print at or above this counts a comparable as already launched.
LAUNCHED_MIN_H1 = 10000
# Blend weight w = p1 / (p1 + BLEND_SCALE): small hour-1 leans on the
# all-launch fit, big hour-1 on the launched-only fit.
BLEND_SCALE = 20000.0
# The persistence fallback's log spread per square-root hour (house baseline).
BASELINE_SIGMA = 0.15
# Standard normal quantiles at LEVELS (for the persistence fallback only).
Z = [-1.6448536269514722, -0.6744897501960817, 0.0,
     0.6744897501960817, 1.6448536269514722]
# A fit needs at least this many launches with both hours printed.
MIN_FIT_POINTS = 8
# Quantiles must stay inside (0, 1e9]; keep a small margin from the edges.
Q_MIN = 0.01
Q_MAX = 1e9


def round2(x):
    """Round x to 2 decimals, half up (the way JavaScript rounds it).

    A whole number comes back as an int, so json.dumps writes 1240 where
    JavaScript writes 1240 (not 1240.0).
    """
    scaled = x * 100
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100
    return int(value) if float(value).is_integer() else value


def parse_time(text):
    """Parse an ISO 8601 UTC timestamp (with a trailing Z or an offset)."""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def quantile(sorted_values, q):
    """The q-quantile of a sorted list, by linear interpolation."""
    n = len(sorted_values)
    if n == 0:
        return None
    if n == 1:
        return sorted_values[0]
    pos = q * (n - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return sorted_values[lo]
    return sorted_values[lo] * (hi - pos) + sorted_values[hi] * (pos - lo)


def ols(points):
    """Least squares for y ~ a + b*x over [(x, y), ...]; returns (a, b, residuals)."""
    n = len(points)
    mean_x = sum(p[0] for p in points) / n
    mean_y = sum(p[1] for p in points) / n
    sxx = sum((p[0] - mean_x) ** 2 for p in points)
    sxy = sum((p[0] - mean_x) * (p[1] - mean_y) for p in points)
    slope = sxy / sxx if sxx > 0 else 0.0
    intercept = mean_y - slope * mean_x
    residuals = [p[1] - (intercept + slope * p[0]) for p in points]
    return intercept, slope, residuals


def comparable_day_series(comparable):
    """A comparable's release-day hourly counts as {hour 1..24: viewers}.

    Hours with no point, or a non-positive count, are left out; a launch with
    no hour-1 print cannot anchor a forecast and yields an empty dict.
    """
    try:
        day_start = parse_time(comparable["day_start"])
    except (KeyError, TypeError, ValueError):
        return {}
    series = {}
    for row in comparable.get("hourly") or []:
        try:
            at = parse_time(row["from"])
            viewers = row["viewers"]
        except (KeyError, TypeError, ValueError):
            continue
        if viewers is None or viewers <= 0:
            continue
        hour = int((at - day_start).total_seconds() // 3600) + 1
        if 1 <= hour <= 24:
            series[hour] = viewers
    return series


def fit_hour(series_list, hour, min_h1):
    """Fit log(viewers_hour) on log(viewers_1) over the given launch series.

    Returns (intercept, slope, sorted residuals) or None when too few
    launches print both hours.
    """
    points = []
    for series in series_list:
        first = series.get(1)
        value = series.get(hour)
        if first is None or value is None:
            continue
        if first < 1 or value < 1 or first < min_h1:
            continue
        points.append((math.log(first), math.log(value)))
    points.sort()
    if len(points) < MIN_FIT_POINTS:
        return None
    intercept, slope, residuals = ols(points)
    return intercept, slope, sorted(residuals)


def baseline_row(p1, hour):
    """The flat persistence forecast: every hour stays at hour 1's print."""
    spread = BASELINE_SIGMA * math.sqrt(hour - 1)
    return [round2(p1 * math.exp(z * spread)) for z in Z]


def clamp_quantiles(values):
    """Keep quantiles inside (0, 1e9] and non-decreasing."""
    out = []
    prev = Q_MIN
    for value in values:
        clamped = min(max(value, Q_MIN), Q_MAX)
        if clamped < prev:
            clamped = prev
        out.append(clamped)
        prev = clamped
    return out


def forecast_case(case):
    """Forecast one case: {"hours": [{"hour": h, "q": [q05, ..., q95]}]}."""
    levels = case.get("levels") or LEVELS
    known = case.get("known") or []
    first = next((k for k in known if k.get("hour") == 1), None)
    if first is None:
        raise ValueError("case has no hour-1 print")
    p1 = max(1, first["viewers"])
    log_p1 = math.log(p1)

    # The comparables' release-day curves, in name order for determinism.
    comparables = sorted(
        (c for c in (case.get("comparables") or []) if isinstance(c, dict)),
        key=lambda c: str(c.get("name", "")),
    )
    series_list = []
    for comparable in comparables:
        series = comparable_day_series(comparable)
        if series.get(1):
            series_list.append(series)

    hours = [row["hour"] for row in (case.get("forecast") or [])]
    if not hours:
        hours = list(range(2, 25))
    hours = sorted(set(int(h) for h in hours if 2 <= int(h) <= 24))

    # One blended log-quantile curve per hour, before smoothing.
    log_quantiles = {}
    for hour in hours:
        fit_all = fit_hour(series_list, hour, 0)
        fit_launched = fit_hour(series_list, hour, LAUNCHED_MIN_H1)
        if fit_all is None and fit_launched is None:
            log_quantiles[hour] = None  # persistence fallback below
            continue
        if fit_all is None:
            fit_all = fit_launched
        if fit_launched is None:
            fit_launched = fit_all
        weight = p1 / (p1 + BLEND_SCALE)
        median = weight * (fit_launched[0] + fit_launched[1] * log_p1) \
            + (1 - weight) * (fit_all[0] + fit_all[1] * log_p1)
        row = []
        for level in levels:
            offset = weight * quantile(fit_launched[2], level) \
                + (1 - weight) * quantile(fit_all[2], level)
            row.append(median + offset)
        log_quantiles[hour] = row

    # Light smoothing across neighbouring hours: launch-day curves move
    # smoothly, so average each log-quantile over its hour and its neighbours.
    smoothed = {}
    for hour in hours:
        row = log_quantiles[hour]
        if row is None:
            smoothed[hour] = None
            continue
        neighbours = [log_quantiles[h] for h in (hour - 1, hour, hour + 1)
                      if h in log_quantiles and log_quantiles[h] is not None]
        smoothed[hour] = [sum(values[i] for values in neighbours) / len(neighbours)
                          for i in range(len(levels))]

    out_hours = []
    for hour in hours:
        row = smoothed[hour]
        if row is None:
            quantiles = baseline_row(p1, hour)
        else:
            quantiles = clamp_quantiles([round2(math.exp(x)) for x in row])
        out_hours.append({"hour": hour, "q": quantiles})
    return {"hours": out_hours}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Every case file, in name order, so two runs write the same bytes.
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
