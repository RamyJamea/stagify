"""SDK adapters are imported explicitly so core works without provider extras."""

from .base import Provider

__all__ = ["Provider"]
