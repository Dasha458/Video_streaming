"""Creator analytics. `from src.services.analytics import AnalyticsService`
keeps working -- the package replaced the single module."""

from .service import AnalyticsService

__all__ = ["AnalyticsService"]
