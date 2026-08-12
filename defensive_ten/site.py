"""Static site generator. Plain HTML from scores.json + graph.json.

No JS framework: the output is a set of self-contained pages deployable to
any static host (GitHub Pages included). The site never computes anything —
it renders what the pipeline already scored.
"""

import json
import shutil
from html import escape
from pathlib import Path

from .article import LIMITATION, METRIC_LABELS, intro, player_explanation
from .fetch import DATA_DIR
from .graph import GRAPH_PATH
from .scoring import SCORES_PATH

SITE_DIR = Path(__file__).resolve().parent.parent / "output" / "site"

CSS = """
:root { --ink:#1a1f2b; --muted:#5b6472; --line:#e3e6eb; --accent:#0f6b3f;
        --bg:#fbfbf9; --card:#ffffff; }
@media (prefers-color-scheme: dark) {
  :root { --ink:#e8eaf0; --muted:#9aa3b2; --line:#2a3040; --accent:#5dc389;
          --bg:#12151c; --card:#1a1f2b; } }
* { box-sizing:border-box; }
body { margin:0; font:17px/1.6 Georgia, 'Times New Roman', serif;
       color:var(--ink); background:var(--bg); }
header { border-bottom:3px solid var(--ink); padding:28px 20px 18px; }
header .wrap, main { max-width:880px; margin:0 auto; }
header h1 { font-size:34px; margin:0; letter-spacing:-0.5px; }
header p { color:var(--muted); margin:6px 0 0; font-style:italic; }
nav a { color:var(--accent); margin-right:18px; text-decoration:none;
        font:14px system-ui, sans-serif; }
main { padding:28px 20px 60px; }
h2 { font-size:24px; margin-top:44px; border-bottom:1px solid var(--line);
     padding-bottom:6px; }
.limitation { border-left:4px solid var(--accent); padding:8px 14px;
              color:var(--muted); font-size:15px; background:var(--card); }
.entry { background:var(--card); border:1px solid var(--line); border-radius:8px;
         padding:18px 22px; margin:18px 0; }
.entry h3 { margin:0 0 4px; font-size:20px; }
.entry .meta { font:13px system-ui, sans-serif; color:var(--muted); }
.statrow { display:flex; flex-wrap:wrap; gap:14px; margin:10px 0;
           font:13px system-ui, sans-serif; }
.stat { background:var(--bg); border:1px solid var(--line); border-radius:6px;
        padding:6px 10px; }
.stat b { display:block; font-size:16px; }
table { border-collapse:collapse; width:100%; font:14px system-ui, sans-serif;
        background:var(--card); }
th, td { border:1px solid var(--line); padding:7px 10px; text-align:left; }
th { background:var(--bg); }
td.num { text-align:right; font-variant-numeric:tabular-nums; }
.conf-high { color:var(--accent); } .conf-limited { color:#b0651a; }
a { color:var(--accent); }
footer { max-width:880px; margin:0 auto; padding:20px; color:var(--muted);
         font:13px system-ui, sans-serif; border-top:1px solid var(--line); }
.overflow { overflow-x:auto; }
"""


def _page(title: str, body: str, depth: int = 0) -> str:
    pre = "../" * depth
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title><style>{CSS}</style></head><body>
<header><div class="wrap"><h1>The Defensive Ten</h1>
<p>MLB's best defensive players this week — and the evidence behind every ranking.</p>
<nav><a href="{pre}index.html">This week</a>
<a href="{pre}methodology.html">Methodology &amp; limitations</a>
<a href="{pre}data/rankings.json">Rankings JSON</a>
<a href="{pre}data/graph.json">Evidence graph JSON</a></nav>
</div></header><main>{body}</main>
<footer>Data: Baseball Savant / MLB Statcast leaderboards and the MLB Stats API.
This site is an independent synthesis of published metrics; it is not affiliated
with MLB. MLB data is subject to MLB's usage terms. Not a replacement for OAA,
FRV, or DRS.</footer></body></html>"""


def _stat(label: str, value, digits=1) -> str:
    if value is None:
        v = "—"
    elif isinstance(value, float):
        v = f"{value:+.{digits}f}" if label != "Score" else f"{value:.2f}"
    else:
        v = str(value)
    return f'<div class="stat"><b>{v}</b>{escape(label)}</div>'


def _entry_html(e: dict, cohort: str) -> str:
    pid = e["player_id"]
    name = escape(str(e.get("name") or f"MLB {pid}"))
    meta = " · ".join(filter(None, [str(e.get("position") or ""), str(e.get("team") or "")]))
    if cohort == "catcher":
        stats = (
            _stat("Score", e["current_value"])
            + _stat("Framing runs", e.get("framing_runs"))
            + _stat("Blocking runs", e.get("blocking_runs"))
            + _stat("Throwing runs", e.get("throwing_runs"))
        )
    else:
        stats = (
            _stat("Score", e["current_value"])
            + _stat("Fielding Run Value", e.get("frv_total"))
            + _stat("OAA", e.get("outs_above_average"), 0)
            + _stat("Innings", int(e["innings"]) if e.get("innings") else None)
        )
    conf = e.get("confidence", "limited")
    return f"""<div class="entry"><h3>{e['rank']}. {name}</h3>
<div class="meta">{escape(meta)} · evidence confidence:
<span class="conf-{conf}">{conf}</span> ·
<a href="players/{pid}.html">evidence page</a> ·
<a href="https://baseballsavant.mlb.com/savant-player/{pid}">Savant profile</a></div>
<div class="statrow">{stats}</div>
{player_explanation(e, cohort)}</div>"""


def _player_page(e: dict, cohort: str, graph: dict) -> str:
    pid = e["player_id"]
    name = str(e.get("name") or f"MLB {pid}")
    obs_rows, edges_out = [], []
    node_by_id = {n["id"]: n for n in graph["nodes"]}
    for edge in graph["edges"]:
        if edge["source"] == f"player:{pid}":
            tgt = node_by_id.get(edge["target"], {})
            if tgt.get("kind") == "MetricObservation":
                src_url = next(
                    (node_by_id[e2["target"]].get("url") for e2 in graph["edges"]
                     if e2["source"] == edge["target"] and node_by_id.get(e2["target"], {}).get("kind") == "Source"),
                    "",
                )
                obs_rows.append((tgt, src_url))
            else:
                edges_out.append((edge.get("key", ""), tgt))

    # volume/context metrics read as plain numbers; run-value metrics keep the sign
    unsigned = {"outs_total", "framing_pitches", "pop_time", "arm_strength_mph"}
    obs_rows.sort(key=lambda t: t[0]["metric"])
    rows = "\n".join(
        "<tr><td>{}</td><td class='num'>{}</td><td>{}</td><td>{}Z</td>"
        "<td><a href='{}'>Baseball Savant</a></td><td>{}</td></tr>".format(
            escape(METRIC_LABELS.get(o["metric"], o["metric"])),
            f"{o['value']:.2f}" if o["metric"] in unsigned else f"{o['value']:+.2f}",
            escape(o["snapshot_date"]),
            escape(o["retrieved_at"][:19]),
            escape(u),
            escape(o["method_version"]),
        )
        for o, u in obs_rows
    )
    rel = "\n".join(
        f"<li><code>{escape(k)}</code> → {escape(str(t.get('name', t.get('list', '?'))))}"
        f" <span style='color:var(--muted)'>({escape(t.get('kind', ''))})</span></li>"
        for k, t in edges_out
    )
    body = f"""<h2>{escape(name)} — evidence</h2>
<p>Rank {e['rank']} in this week's {'Catching Five' if cohort == 'catcher' else 'Defensive Ten'}.
Composite score {e['current_value']:.2f} (windows used: {escape(e.get('windows_used', 'season'))};
confidence: {escape(e.get('confidence', 'limited'))}).</p>
{player_explanation(e, cohort)}
<h2>Metric observations</h2>
<div class="overflow"><table><tr><th>Metric</th><th>Value</th><th>Snapshot</th>
<th>Retrieved (UTC)</th><th>Source</th><th>Method</th></tr>{rows}</table></div>
<h2>Graph relationships</h2><ul>{rel}</ul>
<p class="limitation">{LIMITATION}</p>"""
    return _page(f"{name} — evidence — The Defensive Ten", body, depth=1)


METHODOLOGY_BODY = """
<h2>What this is</h2>
<p>A weekly, position-aware synthesis of publicly available defensive evidence:
Baseball Savant's Outs Above Average, Fielding Run Value and its components,
catcher framing/blocking/throwing, outfielder jump, and arm strength, joined
with identity data from the MLB Stats API. It is <strong>not</strong> the true
value of defense, a causal measure of skill, a replacement for OAA or DRS, a
complete accounting of positioning, or a recreation of Statcast's models.</p>

<h2>Pipeline</h2>
<ol>
<li><strong>Snapshot.</strong> Each run stores the raw upstream CSVs unmodified under a dated
directory with a manifest (URL, UTC retrieval time, SHA-256). Numbers on this site
trace back to exact source bytes.</li>
<li><strong>Warehouse.</strong> Snapshots load into DuckDB as one row per
(player, metric, snapshot date) with full provenance.</li>
<li><strong>Graph.</strong> Players, teams, positions, metric observations, sources,
weeks, and rankings become a typed graph (exported as JSON). Every ranking entry
is reachable from its component observations and their sources.</li>
<li><strong>Score.</strong> Deterministic Python; same snapshots in, same ranks out.
No LLM touches any number.</li>
</ol>

<h2>Scoring formula (defensive-ten-v0.1)</h2>
<p>Two cohorts, published separately. Combining catcher framing volume with
infield range would force arbitrary cross-position weights, so we do not.
Pitchers are excluded in v0.1. All z-scores are computed within primary
position among qualified players.</p>
<h3>Non-catchers — season composite</h3>
<pre>0.50 · z(Fielding Run Value total)
+ 0.30 · z(Outs Above Average)
+ 0.20 · position module
  infield module  = mean( z(FRV double-play runs), z(FRV arm runs) )
  outfield module = mean( z(FRV arm runs), z(jump burst vs league) )</pre>
<h3>Catchers — season composite</h3>
<pre>0.40 · z(framing runs) + 0.30 · z(blocking runs) + 0.30 · z(throwing runs)</pre>
<h3>Current Defensive Value</h3>
<pre>0.50 · season + 0.30 · trailing-30-day delta + 0.20 · trailing-week delta</pre>
<p>Savant leaderboards are cumulative, so weekly and 30-day form are computed as
deltas between dated snapshots — the week window uses the nearest snapshot
5&ndash;9 days back, the trailing-30 window the nearest 20&ndash;40 days back.
When a window has no prior snapshot (including the first edition), remaining
weights renormalize and the article says so.
A cumulative metric that moved while a player recorded zero new outs is flagged
<em>revised-by-source</em>: model recalculation, not new plays.</p>

<h2>Confidence</h2>
<p>Each player carries an evidence-confidence tier (high / moderate / limited)
from workload terciles within their cohort — innings for fielders, pitches
received for catchers. Confidence never changes a score; it tells you how much
to trust one.</p>

<h2>Known limitations</h2>
<ul>
<li>Public leaderboards cannot separate player range from team positioning instructions.</li>
<li>One week at one position is a small sample; treat weekly movement as descriptive.</li>
<li>Savant revises models and history; snapshot dates and the revised-by-source flag
make that visible but cannot undo it.</li>
<li>First-edition rankings are season-to-date only until prior snapshots accumulate.</li>
<li>Editorial notes (signature plays, injuries) are annotations, never scoring inputs.</li>
</ul>

<h2>Terms</h2>
<p>MLB and Baseball Savant data remain subject to MLB's terms of use. This project
stores small snapshots for provenance, links back to original sources, and does not
republish bulk data or use MLB marks.</p>
"""


def build_site() -> None:
    scores = json.loads(SCORES_PATH.read_text())
    graph = json.loads(GRAPH_PATH.read_text())

    if SITE_DIR.exists():
        shutil.rmtree(SITE_DIR)
    (SITE_DIR / "players").mkdir(parents=True)
    (SITE_DIR / "data").mkdir()

    body = [f"<h2>Week of {scores['period_start']} to {scores['period_end']}</h2>",
            intro(scores), "<h2>The Defensive Ten</h2>"]
    body += [_entry_html(e, "non_catcher") for e in scores["ranked"]["defensive_ten"]]
    body.append("<h2>The Catching Five</h2>")
    body += [_entry_html(e, "catcher") for e in scores["ranked"]["catching_five"]]
    (SITE_DIR / "index.html").write_text(_page("The Defensive Ten", "\n".join(body)))

    for cohort, key in [("non_catcher", "defensive_ten"), ("catcher", "catching_five")]:
        for e in scores["ranked"][key]:
            (SITE_DIR / "players" / f"{e['player_id']}.html").write_text(
                _player_page(e, cohort, graph)
            )

    (SITE_DIR / "methodology.html").write_text(
        _page("Methodology — The Defensive Ten", METHODOLOGY_BODY)
    )
    shutil.copy(SCORES_PATH, SITE_DIR / "data" / "rankings.json")
    shutil.copy(GRAPH_PATH, SITE_DIR / "data" / "graph.json")
    n_pages = 3 + len(scores["ranked"]["defensive_ten"]) + len(scores["ranked"]["catching_five"])
    print(f"site: {n_pages} pages -> {SITE_DIR}")


if __name__ == "__main__":
    build_site()
