"""Build the evidence graph for ranked + candidate players.

Node types: Player, Team, Position, MetricObservation, Source, Week,
WeeklyRanking. Edges follow the model in the methodology doc:

  (Player)-[:PLAYS_FOR]->(Team)
  (Player)-[:PLAYS_POSITION]->(Position)
  (Player)-[:HAS_METRIC]->(MetricObservation)
  (MetricObservation)-[:MEASURED_DURING]->(Week)
  (MetricObservation)-[:DERIVED_FROM]->(Source)
  (Player)-[:RANKED_IN {rank}]->(WeeklyRanking)

Exported as node-link JSON (data/graph.json) — the site reads it directly,
and it round-trips into Neo4j/Kuzu later without remodeling.
"""

import json

import networkx as nx

from .fetch import DATA_DIR, SNAPSHOT_DIR
from .scoring import SCORES_PATH
from .warehouse import connect

GRAPH_PATH = DATA_DIR / "graph.json"


def build_graph() -> nx.MultiDiGraph:
    scores = json.loads(SCORES_PATH.read_text())
    snap_date = scores["snapshot_date"]
    week_id = f"week:{scores['period_start']}..{scores['period_end']}"

    candidate_ids = {
        p["player_id"]
        for pool in scores["candidates"].values()
        for p in pool
    }

    con = connect()
    obs = con.execute(
        """SELECT o.*, p.name, p.team, p.position
           FROM metric_observations o JOIN players p USING (player_id)
           WHERE o.snapshot_date = ? AND o.player_id IN ({})""".format(
            ",".join(map(str, candidate_ids))
        ),
        [snap_date],
    ).df()
    con.close()

    g = nx.MultiDiGraph()
    g.add_node(week_id, kind="Week", start=scores["period_start"], end=scores["period_end"])

    for _, o in obs.iterrows():
        pid = f"player:{int(o.player_id)}"
        if pid not in g:
            g.add_node(pid, kind="Player", name=o["name"], mlb_id=int(o.player_id))
            if o.team and str(o.team) != "None":
                tid = f"team:{o.team}"
                g.add_node(tid, kind="Team", name=o.team)
                g.add_edge(pid, tid, key="PLAYS_FOR")
            if o.position and str(o.position) != "None":
                posid = f"position:{o.position}"
                g.add_node(posid, kind="Position", name=o.position)
                g.add_edge(pid, posid, key="PLAYS_POSITION")
        src_id = f"source:{o.source_url}"
        if src_id not in g:
            g.add_node(src_id, kind="Source", publisher=o.source, url=o.source_url)
        mid = f"obs:{int(o.player_id)}:{o.metric}:{o.snapshot_date}"
        g.add_node(
            mid, kind="MetricObservation", metric=o.metric, value=float(o.value),
            snapshot_date=o.snapshot_date, retrieved_at=o.retrieved_at,
            method_version=o.method_version,
        )
        g.add_edge(pid, mid, key="HAS_METRIC")
        g.add_edge(mid, week_id, key="MEASURED_DURING")
        g.add_edge(mid, src_id, key="DERIVED_FROM")

    for list_name, entries in scores["ranked"].items():
        rid = f"ranking:{list_name}:{scores['period_end']}"
        g.add_node(rid, kind="WeeklyRanking", list=list_name,
                   period_end=scores["period_end"],
                   method_version=scores["method_version"])
        g.add_edge(rid, week_id, key="MEASURED_DURING")
        for e in entries:
            g.add_edge(f"player:{e['player_id']}", rid, key="RANKED_IN",
                       rank=e["rank"], score=e["current_value"],
                       confidence=e["confidence"])

    GRAPH_PATH.write_text(json.dumps(nx.node_link_data(g, edges="edges"), indent=1))
    print(f"graph: {g.number_of_nodes()} nodes, {g.number_of_edges()} edges -> {GRAPH_PATH}")
    return g


if __name__ == "__main__":
    build_graph()
