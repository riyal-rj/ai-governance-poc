"""Low - cardinatlity promethus metrics owned by one application instance."""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest
)

from src.application.ports.health import ReadinessReport

class Metrics:
    """Per application metric registry safe for tests and app factories"""

    def __init__(self,*,
                 service_name: str,
                 service_version: str,
                 environment: str) -> None:
        self.registry = CollectorRegistry(auto_describe=True)

        build = Info(
            "finassist_build",
            "Build and deployment identity",
            registry = self.registry
        )

        build.info(
            {
                "service": str(service_name),
                "version": service_version,
                "environment": environment
            }
        )

        self.http_requests = Counter(
            "finassist_http_requests_total",
            "HTTP requests completed",
            labelnames = {
                "method",
                "route",
                "status_code"
            },
            registry= self.registry
        )

        self.http_duration = Histogram(
            "finassist_http_request_duration_seconds",
            "HTTP request duration",
            labelnames={"method","route"},
            buckets = (0.005, 0.01, 0.025, 0.05, 0.1, 0.5, 1, 2.5, 5, 10),
            registry= self.registry
        )

        self.http_in_progress = Gauge(
            "finassist_http_requests_in_progress",
            "HTTP requests in progress",
            registry= self.registry
        )

        self.dependency_up = Gauge(
            "finassist_dependency_up",
            "Whether a dependency passed its latest readiness probe",
            labelnames = {
                "component",
                "critical"
            },
            registry=self.registry
        )

        self.dependency_latency = Gauge(
            "finassist_dependency_health_latency_seconds",
            "Latest dependency readiness probe latency",
            labelnames=("component",),
            registry=self.registry,
        )

        self.service_ready = Gauge(
            "finassist_service_ready",
            "Whether all critical dependencies are ready",
            registry=self.registry,
        )

    def observe_http(self,*,
                     method: str,
                     route: str,
                     status_code: int,
                     duration_seconds: float) -> None:
        """Record a complete request using a route template, never a raw url."""

        self.http_requests.labels(
            method = method,
            route = route,
            status_code = str(status_code)
        ).inc()
        self.http_duration.labels(
            method = method,
            route  = route
        ).observe(duration_seconds)

    def observe_readiness(self,
                          report: ReadinessReport) -> None:
        """Implement Health Observer and publish dependency readiness metrics."""

        self.service_ready.set(1 if report.ready else 0)
        for component in report.components:
            self.dependency_up.labels(
                component=component.component,
                critical=str(component.critical).lower()
            ).set(1 if component.healthy else 0)
            self.dependency_latency.labels(component=component.component).set(
                component.latency_ms / 1000
            )

    def render(self) -> tuple[bytes, str] :
        """Serialize the registry in prometheus exposition format."""

        return generate_latest(self.registry), CONTENT_TYPE_LATEST