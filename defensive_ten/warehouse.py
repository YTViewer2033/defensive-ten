"""Load raw snapshots into a DuckDB warehouse of metric observations.

Two tables:

    players(player_id, name, team, position)      -- best-known identity info
    metric_observations(player_id, metric, value, snapshot_date,
                        source, source_url, retrieved_at, method_version)

Every observation keeps full provenance. The same metric on different
snapshot dates coexists — that is what makes weekly deltas computable and
auditable later.
"""

import json
from pathlib import Path

import duckdb
import pandas as pd

from .fetch import DATA_DIR, SNAPSHOT_DIR
from .sources import METHOD_VERSION

DB_PATH = DATA_DIR / "warehouse.duckdb"

# metric name -> (source file, csv column, id column)
METRIC_MAP = {
    "outs_above_average":        ("oaa", "outs_above_average", "player_id"),
    "fielding_runs_prevented":   ("oaa", "fielding_runs_prevented", "player_id"),
    "frv_total":                 ("fielding_run_value", "total_runs", "id"),
    "frv_range":                 ("fielding_run_value", "range_runs", "id"),
    "frv_arm":                   ("fielding_run_value", "arm_runs", "id"),
    "frv_dp":                    ("fielding_run_value", "dp_runs", "id"),
    "frv_framing":               ("fielding_run_value", "framing_runs", "id"),
    "frv_throwing":              ("fielding_run_value", "throwing_runs", "id"),
    "frv_blocking":              ("fielding_run_value", "blocking_runs", "id"),
    "outs_total":                ("fielding_run_value", "outs_total", "id"),
    "framing_runs":              ("catcher_framing", "rv_tot", "id"),
    "framing_pitches":           ("catcher_framing", "pitches", "id"),
    "blocking_runs":             ("catcher_blocking", "catcher_blocking_runs", "player_id"),
    "blocks_above_average":      ("catcher_blocking", "blocks_above_average", "player_id"),
    "throwing_runs":             ("catcher_throwing", "catcher_stealing_runs", "player_id"),
    "cs_above_average":          ("catcher_throwing", "caught_stealing_above_average", "player_id"),
    "pop_time":                  ("catcher_throwing", "pop_time", "player_id"),
    "jump_burst_ft":             ("outfield_jump", "rel_league_burst_distance", "resp_fielder_id"),
    "jump_reaction_ft":          ("outfield_jump", "rel_league_reaction_distance", "resp_fielder_id"),
    "jump_route_ft":             ("outfield_jump", "rel_league_routing_distance", "resp_fielder_id"),
    "arm_strength_mph":          ("arm_strength", "arm_overall", "player_id"),
}

# where to pick up name/team/position per source file
IDENTITY_MAP = {
    "oaa": ("last_name, first_name", "display_team_name", "primary_pos_formatted"),
    "catcher_blocking": ("player_name", "team_name", None),
    "catcher_throwing": ("player_name", "team_name", None),
    "arm_strength": ("fielder_name", "team_name", "primary_position_name"),
}


def _read_csv(snap: Path, name: str) -> pd.DataFrame | None:
    p = snap / f"{name}.csv"
    if not p.exists():
        return None
    return pd.read_csv(p, encoding="utf-8-sig")


def load_snapshot(snapshot_date: str, con: duckdb.DuckDBPyConnection) -> int:
    snap = SNAPSHOT_DIR / snapshot_date
    manifest = json.loads((snap / "manifest.json").read_text())

    frames = {name: _read_csv(snap, name) for name in manifest["files"]}

    obs_rows = []
    for metric, (src, col, id_col) in METRIC_MAP.items():
        df = frames.get(src)
        if df is None or col not in df.columns:
            continue
        meta = manifest["files"][src]
        for _, row in df.iterrows():
            val = pd.to_numeric(row[col], errors="coerce")
            if pd.isna(val) or pd.isna(row[id_col]):
                continue
            obs_rows.append(
                (int(row[id_col]), metric, float(val), snapshot_date,
                 "Baseball Savant", meta["url"], meta["retrieved_at"], METHOD_VERSION)
            )

    id_rows = {}
    for src, (name_col, team_col, pos_col) in IDENTITY_MAP.items():
        df = frames.get(src)
        if df is None:
            continue
        id_field = next(c for c in ("player_id", "id", "resp_fielder_id") if c in df.columns)
        for _, row in df.iterrows():
            if pd.isna(row[id_field]):
                continue
            pid = int(row[id_field])
            raw = str(row[name_col])
            name = " ".join(part.strip() for part in reversed(raw.split(","))) if "," in raw else raw
            team = str(row[team_col]) if team_col and pd.notna(row.get(team_col)) else None
            pos = str(row[pos_col]) if pos_col and pd.notna(row.get(pos_col)) else None
            prev = id_rows.get(pid)
            # earlier sources in IDENTITY_MAP win; fill gaps from later ones
            if prev is None:
                id_rows[pid] = [pid, name, team, pos]
            else:
                if prev[2] is None and team:
                    prev[2] = team
                if prev[3] is None and pos:
                    prev[3] = pos

    con.execute("DELETE FROM metric_observations WHERE snapshot_date = ?", [snapshot_date])
    if obs_rows:
        con.executemany(
            "INSERT INTO metric_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?)", obs_rows
        )
    for pid, name, team, pos in id_rows.values():
        con.execute(
            """INSERT INTO players VALUES (?, ?, ?, ?)
               ON CONFLICT (player_id) DO UPDATE SET
                 name = excluded.name,
                 team = COALESCE(excluded.team, players.team),
                 position = COALESCE(excluded.position, players.position)""",
            [pid, name, team, pos],
        )
    return len(obs_rows)


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(DB_PATH))
    con.execute("""
        CREATE TABLE IF NOT EXISTS players (
            player_id BIGINT PRIMARY KEY, name TEXT, team TEXT, position TEXT)""")
    con.execute("""
        CREATE TABLE IF NOT EXISTS metric_observations (
            player_id BIGINT, metric TEXT, value DOUBLE, snapshot_date TEXT,
            source TEXT, source_url TEXT, retrieved_at TEXT, method_version TEXT)""")
    return con


def load_all_snapshots() -> None:
    from .fetch import list_snapshots

    con = connect()
    for snap_date in list_snapshots():
        n = load_snapshot(snap_date, con)
        print(f"  loaded {snap_date}: {n} observations")
    con.close()


if __name__ == "__main__":
    load_all_snapshots()
