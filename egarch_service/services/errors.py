from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceError(Exception):
    """Controlled service error that can be mapped to an API contract error."""

    error_code: str
    message: str
