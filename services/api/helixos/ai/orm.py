"""SQLAlchemy ORM model for AI usage (the spend ledger)."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from helixos.db.base import Base


class AiUsageORM(Base):
    """One settled agent run: what it consumed and what it cost.

    Append-only. Spend caps are sums over this table, so it must survive
    restarts. ``cost_micros`` is millionths of a US dollar.
    """

    __tablename__ = "ai_usage"
    __table_args__ = (
        Index("ix_ai_usage_org_created", "organization_id", "created_at"),
        Index("ix_ai_usage_user_created", "user_id", "created_at"),
        Index("ix_ai_usage_created", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_micros: Mapped[int] = mapped_column(BigInteger, nullable=False)
    estimated: Mapped[bool] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
