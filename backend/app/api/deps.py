"""FastAPI dependency wiring — bridges the framework to the composition root.

Concrete adapter selection lives in app/composition.py; this module only
adapts those factories to FastAPI's Depends() mechanism.
"""

from typing import Annotated

from fastapi import Depends

from app.composition import get_memory_probe
from app.domain.ports.memory_probe import MemoryProbe

MemoryProbeDep = Annotated[MemoryProbe, Depends(get_memory_probe)]
