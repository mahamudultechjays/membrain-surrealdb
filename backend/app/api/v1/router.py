"""Aggregates all v1 endpoint routers."""

from fastapi import APIRouter

from app.api.v1.endpoints import capture, documents, graph, health

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(capture.router, tags=["capture"])
api_router.include_router(documents.router, tags=["documents"])
api_router.include_router(graph.router, tags=["graph"])
