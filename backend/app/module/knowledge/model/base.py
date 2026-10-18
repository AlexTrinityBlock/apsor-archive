"""Backward-compatible import of the shared declarative base."""

from app.infrastructure.database.base import Base

__all__ = ["Base"]
