# GTA VI launch-day Twitch CCU forecaster

Entry for make.fun's `gta6-twitch-ccu-forecast-01` bounty: forecast, hour by
hour, how many people watch Grand Theft Auto VI live on Twitch over the 24
UTC hours of its release day (2026-11-19), from everything recorded up to the
end of the first hour — as five quantiles (5%, 25%, 50%, 75%, 95%) per hour.

## Run it

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

`main.py` (Python 3.13, standard library only) reads every `<id>.in` case in
the input directory and writes `<id>.out` for each: 23 rows, hours 2–24.

## Method

The program never sees the future: it works only from the case file it is
given. For each hour `h = 2..24` it looks at the case's `comparables` — past
big game launches' hourly Twitch curves — and measures, across those launches,
the distribution of `log(viewers_h / viewers_1)`, the launch-day curve's rise
or fall from its own first hour. The forecast's median is hour 1's print times
the median log-ratio; the 5/25/75/95% quantiles are the matching empirical
quantiles of the same log-ratio distribution, so the spread is the honest
between-launch spread of launch-day shapes, widening where launches disagree
most. A small shrinkage toward the pooled launch-day shape keeps thin hours
stable, and a fallback to the flat persistence forecast covers degenerate
cases (no usable comparables, tiny hour-1 print).

## Score

Pinball loss on the log scale, mean over every scored hour and level; lower
is better. See `EVALUATION.md` for the locally measured practice loss versus
the house baseline.
