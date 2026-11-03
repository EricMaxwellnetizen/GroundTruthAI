from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from groundtruth.config import Settings
from groundtruth.models.connector import ConnectionTest, ConnectorResult
from groundtruth.models.enums import ConnectorStatus


class BaseConnector(ABC):
    name: str
    source: str

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @abstractmethod
    def is_configured(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def test_connection(self) -> ConnectionTest:
        raise NotImplementedError

    def result(
        self,
        status: ConnectorStatus,
        *,
        data: Any = None,
        coverage: dict[str, Any] | None = None,
        warnings: list[str] | None = None,
        error: str | None = None,
        pages: int = 0,
        records: int = 0,
        fixture: bool = False,
        source: str | None = None,
    ) -> ConnectorResult:
        return ConnectorResult(
            status=status,
            source=source or self.source,
            queried_at=datetime.now(timezone.utc),
            data=data,
            coverage=coverage or {},
            warnings=warnings or [],
            error=error,
            pages=pages,
            records=records,
            fixture=fixture,
        )

    def not_configured(self, message: str) -> ConnectorResult:
        return self.result(ConnectorStatus.NOT_CONFIGURED, error=message)


def classify_http_error(status_code: int) -> ConnectorStatus:
    if status_code in {401, 403}:
        return ConnectorStatus.PERMISSION_DENIED
    if status_code == 404:
        return ConnectorStatus.NOT_FOUND
    if status_code == 429:
        return ConnectorStatus.RATE_LIMITED
    return ConnectorStatus.FAILED


def safe_error_message(exc: BaseException) -> str:
    text = str(exc).strip()
    return text[:500] if text else exc.__class__.__name__
