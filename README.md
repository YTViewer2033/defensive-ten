# The Defensive Ten

MLB's best defensive players this week — and the evidence behind every ranking.

A weekly, position-aware synthesis of publicly available defensive evidence.
Not a new defensive metric, not a Statcast recreation, not a replacement for
OAA or DRS: a transparent aggregation of published leaderboards with full
source provenance and an evidence graph behind every ranked player.

## Pipeline

```
fetch      Savant leaderboard CSVs -> immutable dated snapshot + sha256 manifest
warehouse  snapshots -> DuckDB metric_observations (one row per player/metric/date)
enrich     MLB Stats API fills name/team/position gaps
score      deterministic position-normalized composites (see methodology)
graph      NetworkX evidence graph -> data/graph.json (node-link JSON)
site       static HTML: weekly article, per-player evidence pages, methodology
```

Run it:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m defensive_ten all      # fetch today's snapshot + build everything
.venv/bin/python -m defensive_ten fetch    # snapshot only (idempotent per day)
.venv/bin/python -m defensive_ten build    # rebuild from existing snapshots
open output/site/index.html
```

## Data sources

- Baseball Savant leaderboards: Outs Above Average, Fielding Run Value (+
  components), catcher framing / blocking / throwing, outfielder jump, arm
  strength. Fetched as CSV, stored raw before parsing.
- MLB Stats API: player identity, team, primary position.

MLB data is subject to MLB's usage terms. This project stores small snapshots
for provenance, links back to every source, and does not republish bulk data.

## Design decisions

- **Snapshots are the unit of truth.** Savant leaderboards are cumulative, so
  weekly form is a delta between two dated snapshots — never a scrape of a
  "weekly" view that does not exist upstream. First run scores season-only and
  says so; recent-form weighting activates automatically as snapshots accrue.
- **Catchers rank separately** (The Catching Five). Framing volume and
  shortstop range do not belong on one scale. Pitchers excluded in v0.1.
- **No LLM in the scoring path.** Article prose is deterministic template text
  interpolated from scored facts. An LLM drafting pass is a possible later
  step, but it must never compute or reorder rankings.
- **Static site, no framework.** Plain HTML from Python — deployable to GitHub
  Pages, nothing to hydrate. (The original sketch said Next.js/Astro; for an
  MVP whose pages are pure renderings of a JSON file, a generator is less
  machinery for the same result.)
- **revised-by-source flag.** A cumulative metric that moves while a player
  records zero new outs is a source-side recalculation, not new plays; the
  pipeline flags it instead of narrating it as performance.

## Repo layout

```
defensive_ten/         pipeline package (sources, fetch, warehouse, mlb_api,
                       scoring, graph, article, site)
data/snapshots/        immutable dated CSVs + manifests (committed)
data/warehouse.duckdb  local DuckDB (gitignored, rebuildable)
data/scores.json       scored output of the latest build
data/graph.json        evidence graph, node-link JSON
output/site/           the generated site
docs/METHODOLOGY.md    pointer to the rendered methodology page
.github/workflows/     weekly refresh -> PR for human review
```

Method version: `defensive-ten-v0.1`. Scoring details and known limitations:
`output/site/methodology.html` (generated) — the formula is also documented in
`defensive_ten/scoring.py`'s module docstring.
