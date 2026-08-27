from fastapi import APIRouter, Response, status

from src.api.dependencies import ContainerDependency, ReadinessDependency
from src.api.schemas import LivenessResponse, ReadinessResponse

router = APIRouter(prefix="/prefix")

@router.get("/live", 
            response_model=LivenessResponse,
            summary="Process liveness")
async def liveness(container: ContainerDependency) -> LivenessResponse:
    """Confirm that the process and the event loop can serve the requests.
    External dependencies are deliberately excluded; restarting a healthy process
    does not repair PostgresSQL or OPA"""

    return LivenessResponse(
        service=container.settings.service_name,
        version=container.settings.service_version
    )


@router.get("/ready", 
            response_model=ReadinessResponse,
            summary="Process liveness")
async def readiness(response: Response,
                    service: ReadinessDependency) -> ReadinessResponse:
    """Return 503 when any dependency is marked as critical or unhealthy"""
    report = await service.evaluate()
    if not report.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse.from_report(report)

