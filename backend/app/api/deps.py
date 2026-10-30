"""FastAPI dependency wiring — bridges the framework to the composition root.

Concrete adapter selection lives in app/composition.py; this module only
adapts those factories to FastAPI's Depends() mechanism.
"""

from typing import Annotated

from fastapi import Depends

from app.composition import get_database_probe
from app.domain.ports.database_probe import DatabaseProbe

DatabaseProbeDep = Annotated[DatabaseProbe, Depends(get_database_probe)]
