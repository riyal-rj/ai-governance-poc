"""Prometheus exposition endpoint."""

from fastapi import APIRouter, Response

from src.api.dependencies import MetricsDependency

router = APIRouter(tags=["operations"])


@router.get("", include_in_schema=False)
async def metrics(metrics_registry: MetricsDependency) -> Response:
    """Render the process-local metric registry for Prometheus scraping."""

    body, content_type = metrics_registry.render()
    return Response(content=body, headers={"Content-Type": content_type})
