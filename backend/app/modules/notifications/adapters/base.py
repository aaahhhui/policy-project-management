from dataclasses import dataclass
from datetime import datetime
from typing import Literal

DeliveryOutcome = Literal[
    "succeeded",
    "retryable_failure",
    "permanent_failure",
    "uncertain",
]


@dataclass(frozen=True)
class NotificationMessage:
    title: str
    object_name: str
    facts: tuple[str, ...]
    detail_url: str
    triggered_at: datetime


@dataclass(frozen=True)
class DeliveryResult:
    outcome: DeliveryOutcome
    error_code: str | None
    failure_summary: str | None
    http_status: int | None
    provider_error_code: str | None

    @classmethod
    def succeeded(cls, *, http_status: int) -> "DeliveryResult":
        return cls(
            outcome="succeeded",
            error_code=None,
            failure_summary=None,
            http_status=http_status,
            provider_error_code=None,
        )
