"""Deterministic article copy generated from scored facts.

Every sentence traces to a field in scores.json. No LLM is involved: the
structure is fixed and the numbers are interpolated. (An LLM drafting pass
over these same structured facts is a possible later step; it must never
compute or reorder the rankings.)
"""

METRIC_LABELS = {
    "frv_total": "Fielding Run Value",
    "outs_above_average": "Outs Above Average",
    "fielding_runs_prevented": "Fielding Runs Prevented",
    "frv_range": "range runs",
    "frv_arm": "arm runs",
    "frv_dp": "double-play runs",
    "framing_runs": "framing runs",
    "blocking_runs": "blocking runs",
    "throwing_runs": "throwing runs",
    "pop_time": "pop time (s)",
    "cs_above_average": "caught stealing above average",
    "blocks_above_average": "blocks above average",
    "jump_burst_ft": "burst vs league (ft)",
    "jump_reaction_ft": "reaction vs league (ft)",
    "jump_route_ft": "route vs league (ft)",
    "arm_strength_mph": "avg throw (mph)",
    "outs_total": "outs recorded",
    "framing_pitches": "pitches received",
}

LIMITATION = (
    "This score measures publicly observable defensive results from published "
    "leaderboards. It cannot separate a player's range from team positioning "
    "instructions, and week-to-week samples at a single position are small."
)


def _fmt(v, digits=1):
    if v is None:
        return "—"
    return f"{v:+.{digits}f}" if isinstance(v, float) else str(v)


def player_explanation(e: dict, cohort: str) -> str:
    """Two short paragraphs built only from scored fields."""
    name, pos, team = e.get("name", "Unknown"), e.get("position", "?"), e.get("team", "?")
    conf = e.get("confidence", "limited")
    innings = e.get("innings")

    if cohort == "catcher":
        p1 = (
            f"{name} ranks here on a blend of the three catcher run-value components: "
            f"{_fmt(e.get('framing_runs'))} framing runs, {_fmt(e.get('blocking_runs'))} "
            f"blocking runs, and {_fmt(e.get('throwing_runs'))} throwing runs. "
            f"The composite weights framing 40% and blocking and throwing 30% each, "
            f"normalized across qualified catchers."
        )
        strongest = e.get("primary_component", "framing_runs")
        p2 = (
            f"The largest single contribution is {METRIC_LABELS.get(strongest, strongest)}. "
            f"Evidence confidence is {conf}, based on workload relative to other qualified catchers."
        )
    else:
        p1 = (
            f"{name} ({pos}, {team}) scores {_fmt(e.get('frv_total'))} Fielding Run Value "
            f"and {_fmt(e.get('outs_above_average'), 0)} Outs Above Average season to date. "
            f"Scores are normalized within position, so this reflects standing among {pos}s, "
            f"not raw totals across the league."
        )
        p2_bits = [f"Primary contribution: {e.get('primary_component') or 'overall run prevention'}."]
        if e.get("wk_d_frv_total") is not None:
            p2_bits.append(f"Weekly Fielding Run Value change: {_fmt(e['wk_d_frv_total'])}.")
        if e.get("wk_d_outs_above_average") is not None:
            p2_bits.append(f"Weekly OAA change: {_fmt(e['wk_d_outs_above_average'], 0)}.")
        if innings:
            p2_bits.append(f"Sample: about {int(innings)} innings in the field.")
        p2_bits.append(f"Evidence confidence: {conf}.")
        if e.get("revised_by_source"):
            p2_bits.append(
                "Note: part of this week's movement reflects a source-side recalculation, "
                "not new plays (flagged revised-by-source)."
            )
        p2 = " ".join(p2_bits)
    return f"<p>{p1}</p>\n<p>{p2}</p>"


def intro(scores: dict) -> str:
    windows = scores["ranked"]["defensive_ten"][0].get("windows_used", "season") if scores["ranked"]["defensive_ten"] else "season"
    week_note = (
        "Rankings blend season-to-date value with trailing-30-day and trailing-week form."
        if "week" in windows
        else (
            "This edition ranks on season-to-date evidence only: weekly deltas require two "
            "dated snapshots of the cumulative leaderboards, and this is the first snapshot. "
            "Recent-form weighting activates automatically once prior snapshots exist."
        )
    )
    return (
        f"<p>A transparent, position-aware synthesis of publicly available defensive "
        f"evidence for the week of {scores['period_start']} to {scores['period_end']}. "
        f"Catchers are ranked separately — framing volume and shortstop range do not "
        f"belong on one scale. {week_note}</p>"
        f"<p class='limitation'>{LIMITATION}</p>"
    )
