# Methodology

The canonical methodology text lives in `defensive_ten/site.py`
(`METHODOLOGY_BODY`) and renders to `output/site/methodology.html` with every
build, so the published page can never drift from the shipped code.

Summary of `defensive-ten-v0.1`:

- Two cohorts, published separately: non-catchers (The Defensive Ten) and
  catchers (The Catching Five). Pitchers excluded.
- All z-scores computed within primary position among qualified players.
- Non-catcher season composite:
  `0.50·z(FRV total) + 0.30·z(OAA) + 0.20·position module`
  (infield module = mean z of FRV double-play runs and arm runs; outfield
  module = mean z of FRV arm runs and jump burst vs league).
- Catcher season composite:
  `0.40·z(framing runs) + 0.30·z(blocking runs) + 0.30·z(throwing runs)`.
- Current Defensive Value: `0.50·season + 0.30·trailing-30-delta +
  0.20·trailing-week-delta`, deltas taken between dated snapshots of the
  cumulative leaderboards; missing windows renormalize and are disclosed.
- Confidence tiers (high/moderate/limited) from workload terciles within
  cohort; confidence never changes a score.
- `revised_by_source` flags metric movement with zero new outs recorded
  (source recalculation, not new plays).

What this is **not**: the true value of defense, a causal skill measure, a
replacement for OAA/DRS, an accounting of team positioning, or a recreation
of Statcast's models.
