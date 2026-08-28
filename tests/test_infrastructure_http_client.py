from __future__ import annotations

from src.core.config import HttpClientSettings
from src.infrastructure.http_client import create_http_client


async def test_create_http_client_applies_bounded_defaults() -> None:
    settings = HttpClientSettings()
    client = create_http_client(settings, service_name="finassist-api", service_version="0.1.0")
    try:
        assert client.follow_redirects is False
        assert client.headers["user-agent"] == "finassist-api / 0.1.0"
    finally:
        await client.aclose()


async def test_create_http_client_trusts_no_environment_proxies() -> None:
    settings = HttpClientSettings()
    client = create_http_client(settings, service_name="svc", service_version="1")
    try:
        assert client._trust_env is False
    finally:
        await client.aclose()
