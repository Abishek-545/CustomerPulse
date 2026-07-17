from datetime import datetime
from decimal import Decimal
from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    country: Mapped[str | None] = mapped_column(String(100))
    segment: Mapped[str] = mapped_column(String(50), default="unsegmented", index=True)
    churn_risk: Mapped[float] = mapped_column(default=0.0)
    lifetime_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    last_purchase_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    external_sku: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(300))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    cancellation_rate: Mapped[float] = mapped_column(default=0.0)
    sales_trend: Mapped[float] = mapped_column(default=0.0)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    order_date: Mapped[datetime] = mapped_column(DateTime(timezone=False), index=True)
    status: Mapped[str] = mapped_column(String(32), default="completed")
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)


class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))


class Investigation(Base):
    __tablename__ = "investigations"
    id: Mapped[int] = mapped_column(primary_key=True)
    goal: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="running")
    plan: Mapped[list] = mapped_column(JSON, default=list)
    findings: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Campaign(Base):
    __tablename__ = "campaigns"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    segment: Mapped[str] = mapped_column(String(50))
    offer: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), default="draft")
    investigation_id: Mapped[int | None] = mapped_column(ForeignKey("investigations.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SupportCase(Base):
    __tablename__ = "support_cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    title: Mapped[str] = mapped_column(String(250))
    status: Mapped[str] = mapped_column(String(32), default="open")
    priority: Mapped[str] = mapped_column(String(32), default="normal")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    decided_by: Mapped[str | None] = mapped_column(String(120))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)


class Memory(Base):
    __tablename__ = "memories"
    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    content: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(default=0.7)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    investigation_id: Mapped[int | None] = mapped_column(ForeignKey("investigations.id"), index=True)
    tool: Mapped[str] = mapped_column(String(120))
    input_data: Mapped[dict] = mapped_column(JSON, default=dict)
    output_data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
