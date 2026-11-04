"""Aggregates all v1 endpoint routers."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    ask,
    auth,
    brain,
    capture,
    documents,
    findings,
    graph,
    health,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(capture.router, tags=["capture"])
api_router.include_router(ask.router, tags=["ask"])
api_router.include_router(findings.router, tags=["findings"])
api_router.include_router(admin.router, tags=["admin"])
api_router.include_router(documents.router, tags=["documents"])
api_router.include_router(graph.router, tags=["graph"])
api_router.include_router(brain.router, tags=["brain"])
