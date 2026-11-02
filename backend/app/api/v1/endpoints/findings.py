"""Findings endpoints: static catalogues for the Findings screen. No scope needed."""

from fastapi import APIRouter

from app.schemas.findings import CapabilitiesResponse, GapsResponse, TestsResponse
from app.services import findings

router = APIRouter(prefix="/findings")


@router.get("/tests", response_model=TestsResponse)
async def tests() -> TestsResponse:
    """Every gap-analysis claim and what the hands-on run found."""
    return TestsResponse.model_validate(findings.load("tests"))


@router.get("/capabilities", response_model=CapabilitiesResponse)
async def capabilities() -> CapabilitiesResponse:
    """What this POC calls in Agent Memory, and the 30 Oct plan check."""
    return CapabilitiesResponse.model_validate(findings.load("capabilities"))


@router.get("/gaps", response_model=GapsResponse)
async def gaps() -> GapsResponse:
    """The 40 rows of the validated gap analysis."""
    return GapsResponse.model_validate(findings.load("gaps"))
