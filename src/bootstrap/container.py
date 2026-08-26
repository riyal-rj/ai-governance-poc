"""Explicit dependency container : the application's only composition root"""

from __future__ import annotations

from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from src.application.services.health_service import ReadinessService
from src.core.config import AppSettings
from src.infrastructure.database import PosytgresSQL
from src.infrastructure.