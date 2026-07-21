"""Registry of upstream data sources.

Every source is fetched as-is and stored as an immutable snapshot before any
parsing happens. URLs are templated on season year only; weekly behavior comes
from snapshot dates, not from upstream query parameters (Savant leaderboards
are cumulative season-to-date views).
"""

SEASON = 2026

SAVANT = "https://baseballsavant.mlb.com"
MLB_API = "https://statsapi.mlb.com/api/v1"

# name -> (url, description)
SAVANT_SOURCES = {
    "oaa": (
        f"{SAVANT}/leaderboard/outs_above_average"
        f"?type=Fielder&startYear={SEASON}&endYear={SEASON}"
        "&split=no&team=&range=year&min=q&pos=&roles=&viz=hide&csv=true",
        "Outs Above Average + Fielding Runs Prevented, qualified fielders",
    ),
    "fielding_run_value": (
        f"{SAVANT}/leaderboard/fielding-run-value"
        f"?type=fielder&seasonStart={SEASON}&seasonEnd={SEASON}&minInnings=q&csv=true",
        "Fielding Run Value with components (range, arm, DP, framing, throwing, blocking)",
    ),
    "catcher_framing": (
        f"{SAVANT}/leaderboard/catcher-framing"
        f"?type=catcher&seasonStart={SEASON}&seasonEnd={SEASON}"
        "&team=&min=q&sortColumn=rv_tot&sortDirection=desc&csv=true",
        "Catcher framing run value by attack zone",
    ),
    "catcher_blocking": (
        f"{SAVANT}/leaderboard/catcher-blocking"
        f"?game_type=Regular&n=q&season_end={SEASON}&season_start={SEASON}"
        "&split=no&team=&type=Cat&with_team_only=1&csv=true",
        "Catcher blocking runs / blocks above average",
    ),
    "catcher_throwing": (
        f"{SAVANT}/leaderboard/catcher-throwing"
        f"?game_type=Regular&n=q&season_end={SEASON}&season_start={SEASON}"
        "&split=no&team=&type=Cat&with_team_only=1&csv=true",
        "Catcher throwing (stealing runs, CS above average, pop time)",
    ),
    "outfield_jump": (
        f"{SAVANT}/leaderboard/outfield_jump?year={SEASON}&min=q&csv=true",
        "Outfielder jump (reaction / burst / route, feet vs league)",
    ),
    "arm_strength": (
        f"{SAVANT}/leaderboard/arm-strength"
        f"?type=player&year={SEASON}&minThrows=q&pos=&csv=true",
        "Average/max throw speed by position (context only, not a score input)",
    ),
}

METHOD_VERSION = "defensive-ten-v0.1"
