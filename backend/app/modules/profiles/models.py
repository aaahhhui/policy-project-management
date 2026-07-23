from __future__ import annotations

from typing import Any

from sqlalchemy import Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class EnterpriseProfile(Base, TimestampMixin):
    __tablename__ = "enterprise_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    verification_status: Mapped[str] = mapped_column(String(64), nullable=False)


class BusinessEntity(Base, TimestampMixin):
    __tablename__ = "business_entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seed_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    verification_status: Mapped[str] = mapped_column(String(64), nullable=False)
