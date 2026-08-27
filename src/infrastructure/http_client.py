import httpx

from src.core.config import HttpClientSettings


def create_http_client(
    settings: HttpClientSettings, *, service_name: str, service_version: str
) -> httpx.AsyncClient:
    """Create one bounded pooled client reused across dependency adapters."""

    timeout = httpx.Timeout(
        connect=settings.connect_timeout_seconds,
        read=settings.read_timeout_seconds,
        write=settings.write_timeout_seconds,
        pool=settings.pool_timeout_seconds,
    )

    limits = httpx.Limits(
        max_connections=settings.max_connections,
        max_keepalive_connections=settings.max_keepalive_connections,
        keepalive_expiry=settings.keepalive_expiry_seconds,
    )

    return httpx.AsyncClient(
        timeout=timeout,
        limits=limits,
        follow_redirects=False,
        trust_env=False,
        headers={"User-Agent": f"{service_name} / {service_version}"},
    )
