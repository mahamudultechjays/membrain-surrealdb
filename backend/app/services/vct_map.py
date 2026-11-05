"""The VCT metro map, read once from app/data/vct.

A copy of membrain's backend/data/spreetail-metro-map.json; `topology_version`
says which revision. Only nodes and domains are used here.
"""

import json
from functools import cache
from pathlib import Path

from app.domain.vct import VctDomain, VctMap, VctNode

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
    )
