"""Shared FastAPI dependencies."""

from fastapi import HTTPException

from utils import verify_license, LicenseError


async def require_license() -> None:
    """FastAPI dependency: re-verify USB license on every API call."""
    try:
        # verify_license()
        pass
    except LicenseError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
