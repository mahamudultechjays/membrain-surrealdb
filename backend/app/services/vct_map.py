"""The VCT metro map, read once from app/data/vct.

A copy of membrain's backend/data/spreetail-metro-map.json; `topology_version`
says which revision.
"""

import json
from functools import cache
from pathlib import Path

from app.domain.vct import VctDomain, VctGoal, VctMap, VctNode, VctSection

MAP_FILE = Path(__file__).resolve().parent.parent / "data" / "vct" / "spreetail-metro-map.json"


@cache
def load() -> VctMap:
    data = json.loads(MAP_FILE.read_text(encoding="utf-8"))
    return VctMap(
        topology_version=data["topology_version"],
        domains=tuple(
            VctDomain(id=d["id"], name=d["name"], node_ids=tuple(d["node_ids"]))
            for d in data["domains"]
        ),
        nodes=tuple(
            VctNode(
                id=n["id"],
                name=n["name"],
                description=n["description"],
                domain_id=n["domain_id"],
                section_id=n["section_id"],
                keywords=tuple(n.get("keywords", [])),
            )
            for n in data["nodes"]
        ),
        sections=tuple(
            VctSection(id=s["id"], label=s["label"], ebitda_weight=float(s["ebitda_weight"]))
            for s in data["sections"]
        ),
        goals=tuple(
            VctGoal(
                id=g["id"],
                name=g["name"],
                description=g["description"],
                section_id=g["section_id"],
                weight=float(g["effective_weight"]),
            )
            for g in data["vct_goals"]
        ),
    )
