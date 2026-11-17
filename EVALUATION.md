# Evaluation (measured locally, 2026-11-17)

All numbers below were measured by running `main.py` on the kit's practice
cases and scoring the outputs with the pinball loss exactly as RULES.txt
defines it (mean of `2 * max(tau*d, (tau-1)*d)` over every hour and level,
`d = ln(y) - ln(q)`). The scorer was cross-checked two ways:

- the spec's worked example reproduces exactly: loss **0.112545**;
- the kit's own starter (the house baseline) scores **0.3871** on the
  practice, matching the house's stated "about 0.387".

Practice actuals are the four launches' recorded release-day hourly counts
(SullyGnome hourly averages, read once at low volume via the fetch method the
kit's own `input/NOTICE.txt` documents).

## Practice score (the board's dev score)

| Case | This entry | House baseline |
| --- | --- | --- |
| p00 Marvel's Wolverine | 0.200 | 0.744 |
| p01 Red Dead Redemption 2 | 0.223 | 0.287 |
| p02 God of War Ragnarök | 0.157 | 0.215 |
| p03 Marvel's Spider-Man 2 | 0.192 | 0.303 |
| **Mean** | **0.193** | **0.387** |

Typical miss 36.5% (baseline 90.2%), 90% coverage 0.924 (baseline 0.783;
an honest forecast covers about 0.9). The entry beats the house baseline on
all four practice cases, by 50% on the mean.

## Leave-one-out over 41 past launches

Holding each launch out in turn, fitting on the other 40 and forecasting it
from its own hour-1 print: mean loss **0.375**, vs 0.877 for the baseline
and 0.670 for a pooled empirical-quantile forecaster. On the 30 launches
that were already launched at hour 1 (the GTA VI-like subset: hour-1 print
>= 10,000 and peak < 10x hour 1): **0.233**, vs 0.299 baseline.

## Why this shape

Across past launches, `log(viewers_h)` on `log(viewers_1)` has a slope that
falls from ~1.0 at hour 2 to ~0.06 by hour 20, and the correlation of the
later hours' log-ratios with `log(hour-1 print)` reaches -0.93: a big first
hour means the evening peak is already in view, a tiny first hour means the
unlock (and the peak) is still coming. The blended regression is built on
exactly that relationship; the runner-up designs (pooled quantiles 0.324,
jump-binned quantiles 0.287, single all-launch regression 0.237 on the
practice) all scored worse.

## Verification

- Format: 23 rows, hours 2–24 each once, five non-decreasing quantiles in
  (0, 1e9], files ~1.5 KB (limit 65,536 bytes) — checked for all four
  practice outputs.
- Determinism: two runs on the practice cases write byte-identical outputs.
- Runtime: ~0.05 s per case (limit 8 s, 1 CPU, 1024 MB).
- Edge cases: no comparables, one comparable, hour-1 print 0, hour-1 print
  5,000,000, missing `levels` — all produce valid output (persistence
  fallback where there is nothing to fit).
- `docs/demo.html` plots the p00 forecast (median + 5–95% band) against the
  recorded counts; the plotted points round-trip to the program's output
  within 0.06%.

## Honest gaps

- The practice is SullyGnome hourly averages, not the final's mean of 60
  minute reads; the practice score is no guarantee for the final day.
- The final case's comparables (42, including the four practice launches)
  differ slightly from the 37 used in the practice evaluation above.
- The house AI-model forecast is not public, so it cannot be compared
  against; the entry only has to beat the lower of the two house entries.
- No live-gateway test was run: the kit states there is no local grade for
  this competition ("the server grades every entry"), so the practice
  numbers above are the local evidence.
