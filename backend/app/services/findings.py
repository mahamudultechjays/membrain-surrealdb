"""Static findings catalogue: tests, capabilities and gaps, read once from app/data/findings.

The JSON is generated from the gap-validation results; each file names its
source and the date it was checked.
"""

import json
from functools import cache
from pathlib import Path
from typing import Any, Literal

FindingsKind = Literal["tests", "capabilities", "gaps"]

FINDINGS_DIR = Path(__file__).resolve().parent.parent / "data" / "findings"


@cache
def load(kind: FindingsKind) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FINDINGS_DIR / f"{kind}.json").read_text(encoding="utf-8"))
    return data
