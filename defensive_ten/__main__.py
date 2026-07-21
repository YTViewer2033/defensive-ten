"""Pipeline entrypoint.

    python -m defensive_ten fetch     # snapshot today's leaderboards
    python -m defensive_ten build     # warehouse -> scores -> graph -> site
    python -m defensive_ten all       # fetch + build
"""

import sys


def build():
    from .warehouse import load_all_snapshots
    from .mlb_api import enrich_players
    from .scoring import compute_scores
    from .graph import build_graph
    from .site import build_site

    load_all_snapshots()
    enrich_players()
    compute_scores()
    build_graph()
    build_site()


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("fetch", "all"):
        from .fetch import snapshot_today
        snapshot_today(force="--force" in sys.argv)
    if cmd in ("build", "all"):
        build()
    if cmd not in ("fetch", "build", "all"):
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
