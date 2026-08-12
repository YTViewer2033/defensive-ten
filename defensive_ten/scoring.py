"""Position-aware scoring. Deterministic: same snapshots in, same ranks out.

Two cohorts, published separately (combining framing volume with shortstop
range would force arbitrary cross-position weights):

  non-catchers (1B 2B 3B SS LF CF RF)   -> "The Defensive Ten"
  catchers                              -> "The Catching Five"

Pitchers are excluded in v0.1.

Season composite (z-scores computed within primary position):

  non-catcher: 0.50 z(FRV total) + 0.30 z(OAA) + 0.20 position module
     infield module  = mean of z(FRV double-play runs), z(FRV arm runs)
     outfield module = mean of z(FRV arm runs), z(jump burst ft vs league)
  catcher:     0.40 z(framing runs) + 0.30 z(blocking runs) + 0.30 z(throwing runs)

Current Defensive Value blends season with recent form when prior snapshots
exist (they are cumulative leaderboards, so deltas need two dated snapshots):

  0.50 season + 0.30 trailing-30-day delta + 0.20 trailing-week delta

Missing windows renormalize the remaining weights and are flagged in the
output — a first run scores on season only and says so.
"""

import json
from datetime import date, timedelta

import pandas as pd

from .fetch import DATA_DIR, find_snapshot_near, list_snapshots
from .sources import METHOD_VERSION
from .warehouse import connect

INFIELD = {"1B", "2B", "3B", "SS"}
OUTFIELD = {"LF", "CF", "RF"}
NON_CATCHER = INFIELD | OUTFIELD

# cumulative counting metrics eligible for snapshot-to-snapshot deltas
DELTA_METRICS = ["frv_total", "outs_above_average", "framing_runs",
                 "blocking_runs", "throwing_runs", "outs_total"]

SCORES_PATH = DATA_DIR / "scores.json"


def _wide(con, snapshot_date: str) -> pd.DataFrame:
    df = con.execute(
        "SELECT player_id, metric, value FROM metric_observations WHERE snapshot_date = ?",
        [snapshot_date],
    ).df()
    if df.empty:
        return df
    wide = df.pivot_table(index="player_id", columns="metric", values="value").reset_index()
    players = con.execute("SELECT * FROM players").df()
    return wide.merge(players, on="player_id", how="left")


def _z(series: pd.Series) -> pd.Series:
    sd = series.std(ddof=0)
    if not sd or pd.isna(sd):
        return pd.Series(0.0, index=series.index)
    return (series - series.mean()) / sd


def _zscore_within(df: pd.DataFrame, col: str, group: str = "position") -> pd.Series:
    if col not in df.columns:
        return pd.Series(float("nan"), index=df.index)
    return df.groupby(group)[col].transform(_z)


def _season_composite(df: pd.DataFrame, cohort: str) -> pd.DataFrame:
    df = df.copy()
    if cohort == "catcher":
        parts = {"framing_runs": 0.40, "blocking_runs": 0.30, "throwing_runs": 0.30}
        for col in parts:
            df[f"z_{col}"] = _z(df[col]) if col in df.columns else float("nan")
        df["season_score"] = sum(w * df[f"z_{c}"].fillna(0) for c, w in parts.items())
        df["primary_component"] = df[[f"z_{c}" for c in parts]].idxmax(axis=1).str[2:]
        return df

    df["z_frv_total"] = _zscore_within(df, "frv_total")
    df["z_oaa"] = _zscore_within(df, "outs_above_average")
    df["z_arm"] = _zscore_within(df, "frv_arm")
    df["z_dp"] = _zscore_within(df, "frv_dp")
    df["z_jump"] = _zscore_within(df, "jump_burst_ft")
    is_inf = df["position"].isin(INFIELD)
    df["pos_module"] = pd.concat(
        [
            df.loc[is_inf, ["z_dp", "z_arm"]].mean(axis=1),
            df.loc[~is_inf, ["z_arm", "z_jump"]].mean(axis=1),
        ]
    ).reindex(df.index)
    df["season_score"] = (
        0.50 * df["z_frv_total"].fillna(0)
        + 0.30 * df["z_oaa"].fillna(0)
        + 0.20 * df["pos_module"].fillna(0)
    )
    df["primary_component"] = (
        df[["z_frv_total", "z_oaa", "z_arm", "z_dp", "z_jump"]]
        .idxmax(axis=1).str[2:]
        .map({"frv_total": "overall run prevention", "oaa": "range (OAA)",
              "arm": "arm value", "dp": "double-play value", "jump": "outfield jump"})
    )
    return df


def _window_delta(con, latest: str, days_back: int, tolerance: int) -> tuple[pd.DataFrame | None, str | None]:
    target = date.fromisoformat(latest) - timedelta(days=days_back)
    prior = find_snapshot_near(target, tolerance)
    if prior is None or prior == latest:
        return None, None
    cur = _wide(con, latest).set_index("player_id")
    prev = _wide(con, prior).set_index("player_id")
    deltas = {}
    for m in DELTA_METRICS:
        if m in cur.columns and m in prev.columns:
            deltas[f"d_{m}"] = cur[m].sub(prev[m], fill_value=None)
    if not deltas:
        return None, None
    return pd.DataFrame(deltas), prior


def compute_scores() -> dict:
    con = connect()
    snapshots = list_snapshots()
    if not snapshots:
        raise SystemExit("no snapshots — run fetch first")
    latest = snapshots[-1]
    df = _wide(con, latest)

    week_delta, week_prior = _window_delta(con, latest, 7, 2)
    # trailing-30 accepts the nearest snapshot 20-40 days back: early-life
    # snapshot cadence is irregular, and a 3-week-old baseline is still
    # recent-form evidence worth more than discarding
    month_delta, month_prior = _window_delta(con, latest, 30, 10)

    cohorts = {}
    for cohort, mask in [
        ("non_catcher", df["position"].isin(NON_CATCHER)),
        ("catcher", df["position"] == "C"),
    ]:
        cdf = _season_composite(df[mask], cohort)

        # confidence from opportunity volume: innings terciles within cohort
        vol = cdf["outs_total"] / 3 if "outs_total" in cdf.columns else cdf.get("framing_pitches")
        if vol is not None and vol.notna().sum() >= 3:
            t1, t2 = vol.quantile([1 / 3, 2 / 3])
            cdf["confidence"] = vol.apply(
                lambda v: "limited" if pd.isna(v) or v <= t1 else ("moderate" if v <= t2 else "high")
            )
        else:
            cdf["confidence"] = "limited"
        cdf["innings"] = (cdf["outs_total"] / 3).round(0) if "outs_total" in cdf.columns else None

        # blend recent-form windows when available; renormalize missing weights
        weights = {"season": 0.50, "month": 0.30, "week": 0.20}
        components = {"season": cdf["season_score"]}
        key = "framing_runs" if cohort == "catcher" else "frv_total"
        for wname, wdelta in [("month", month_delta), ("week", week_delta)]:
            if wdelta is not None and f"d_{key}" in wdelta.columns:
                zd = _z(wdelta[f"d_{key}"].reindex(cdf["player_id"]).reset_index(drop=True))
                components[wname] = zd.set_axis(cdf.index).fillna(0)
        active = {k: weights[k] for k in components}
        total_w = sum(active.values())
        cdf["current_value"] = sum(
            (w / total_w) * components[k] for k, w in active.items()
        )
        cdf["windows_used"] = ", ".join(active)

        if week_delta is not None:
            wd = week_delta.reindex(cdf["player_id"]).set_axis(cdf.index)
            for m in DELTA_METRICS:
                if f"d_{m}" in wd.columns:
                    cdf[f"wk_d_{m}"] = wd[f"d_{m}"]
            # a moving cumulative stat with zero new outs recorded means the
            # source recalculated history, not that the player did anything
            if "wk_d_outs_total" in cdf.columns and "wk_d_frv_total" in cdf.columns:
                cdf["revised_by_source"] = (
                    (cdf["wk_d_outs_total"].fillna(0) == 0)
                    & (cdf["wk_d_frv_total"].abs() > 0.01)
                )

        cohorts[cohort] = cdf.sort_values("current_value", ascending=False)

    week_end = date.fromisoformat(latest)
    result = {
        "method_version": METHOD_VERSION,
        "snapshot_date": latest,
        "week_prior_snapshot": week_prior,
        "month_prior_snapshot": month_prior,
        "period_start": (week_end - timedelta(days=6)).isoformat(),
        "period_end": latest,
        "candidates": {
            "non_catcher": _serialize(cohorts["non_catcher"].head(30)),
            "catcher": _serialize(cohorts["catcher"].head(15)),
        },
        "ranked": {
            "defensive_ten": _serialize(cohorts["non_catcher"].head(10)),
            "catching_five": _serialize(cohorts["catcher"].head(5)),
        },
    }
    con.close()
    SCORES_PATH.write_text(json.dumps(result, indent=2, allow_nan=False))
    print(f"scored {len(cohorts['non_catcher'])} non-catchers, "
          f"{len(cohorts['catcher'])} catchers -> {SCORES_PATH}")
    return result


def _serialize(df: pd.DataFrame) -> list[dict]:
    out = []
    for rank, (_, row) in enumerate(df.iterrows(), start=1):
        rec = {"rank": rank}
        for col, val in row.items():
            if pd.isna(val):
                rec[col] = None
            elif isinstance(val, float):
                rec[col] = round(val, 4)
            elif hasattr(val, "item"):
                rec[col] = val.item()
            else:
                rec[col] = val
        out.append(rec)
    return out


if __name__ == "__main__":
    compute_scores()
