"""Fill identity gaps (name/team/position) from the MLB Stats API.

Only players already in the warehouse are looked up, in one batched call per
100 ids. MLB data is subject to MLB's usage terms; this is metadata lookup,
not bulk redistribution.
"""

import json
import urllib.request

from .sources import MLB_API
from .warehouse import connect

USER_AGENT = "defensive-ten/0.1 (personal research project)"


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def enrich_players() -> int:
    con = connect()
    missing = [r[0] for r in con.execute(
        "SELECT player_id FROM players WHERE team IS NULL OR position IS NULL"
    ).fetchall()]
    # framing-only catchers may not be in the players table at all yet
    orphans = [r[0] for r in con.execute(
        """SELECT DISTINCT o.player_id FROM metric_observations o
           LEFT JOIN players p USING (player_id) WHERE p.player_id IS NULL"""
    ).fetchall()]
    ids = missing + orphans
    updated = 0
    for i in range(0, len(ids), 100):
        chunk = ids[i:i + 100]
        url = f"{MLB_API}/people?personIds={','.join(map(str, chunk))}&hydrate=currentTeam"
        data = _get_json(url)
        for person in data.get("people", []):
            pid = person["id"]
            name = person.get("fullName")
            team = (person.get("currentTeam") or {}).get("name")
            pos = (person.get("primaryPosition") or {}).get("abbreviation")
            con.execute(
                """INSERT INTO players VALUES (?, ?, ?, ?)
                   ON CONFLICT (player_id) DO UPDATE SET
                     name = COALESCE(players.name, excluded.name),
                     team = COALESCE(players.team, excluded.team),
                     position = COALESCE(players.position, excluded.position)""",
                [pid, name, team, pos],
            )
            updated += 1
    con.close()
    print(f"  enriched {updated} players via MLB Stats API")
    return updated


if __name__ == "__main__":
    enrich_players()
