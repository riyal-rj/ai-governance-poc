"""Fastapi dependency function that expose the composistion root."""

from typing import Annotated, cast

from fastapi import Depends, Request

from src.application.services.health_service import ReadinessService
from src.bootstrap.container import Container
from src.core.errors import DependencyUnavailableError
from src.observability.metrics import Metrics

def get_container(request : Request) -> Container:
    """Resolve the process container created by the fastapi lifecycle span."""

    container = getattr(request.app.state, "container", None)
    if container is None:
        raise DependencyUnavailableError("application_container")
    return cast(Container, container)

def get_readiness_service(container: Annotated[Container,Depends(get_container)]) -> ReadinessService:
    """Resolve the readiness use case without contructing it in the route."""
    return container.readiness

def get_metrics(container: Annotated[Container,Depends(get_container)]) -> Metrics:
    """Resolve the process -local Prometheus registry."""
    return container.metrics

ContainerDependency = Annotated[Container, Depends(get_container)]
ReadinessDependency = Annotated[ReadinessService, Depends(get_readiness_service)]
MetricsDependency = Annotated[Metrics, Depends(get_metrics)]

