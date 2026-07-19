from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import Customer, Memory, Order, OrderItem, Product
from .config import settings


def seed(session: Session) -> None:
    if session.scalar(select(Customer.id).limit(1)):
        return
    products = [
        Product(external_sku="P-100", name="Vintage Ceramic Mug", unit_price=Decimal("14.50"), cancellation_rate=0.03, sales_trend=0.18),
        Product(external_sku="P-200", name="Eco Tote Bag", unit_price=Decimal("8.00"), cancellation_rate=0.17, sales_trend=-0.32),
        Product(external_sku="P-300", name="LED Desk Light", unit_price=Decimal("28.00"), cancellation_rate=0.12, sales_trend=-0.21),
    ]
    session.add_all(products); session.flush()
    customers = [
        Customer(external_id="C-1001", email=settings.demo_recipient_email, country="United Kingdom", segment="champion", churn_risk=0.21, lifetime_value=Decimal("1250"), last_purchase_at=datetime.utcnow()-timedelta(days=4)),
        Customer(external_id="C-1002", email=settings.demo_recipient_email, country="Germany", segment="at_risk_high_value", churn_risk=0.82, lifetime_value=Decimal("1120"), last_purchase_at=datetime.utcnow()-timedelta(days=140)),
        Customer(external_id="C-1003", email=settings.demo_recipient_email, country="France", segment="at_risk_high_value", churn_risk=0.74, lifetime_value=Decimal("890"), last_purchase_at=datetime.utcnow()-timedelta(days=102)),
        Customer(external_id="C-1004", email=settings.demo_recipient_email, country="United Kingdom", segment="new", churn_risk=0.32, lifetime_value=Decimal("90"), last_purchase_at=datetime.utcnow()-timedelta(days=12)),
    ]
    session.add_all(customers); session.flush()
    for index, customer in enumerate(customers):
        cancelled = index in (1, 2)
        order = Order(invoice_number=f"{'C-' if cancelled else ''}INV-{1000+index}", customer_id=customer.id, order_date=datetime.utcnow()-timedelta(days=10+index), status="cancelled" if cancelled else "completed", total=Decimal("-50.00" if cancelled else "50.00"))
        session.add(order); session.flush()
        session.add(OrderItem(order_id=order.id, product_id=products[index % 3].id, quantity=2, unit_price=Decimal("25.00")))
    session.add(Memory(category="campaign_outcome", content="A 10% welcome-back offer performed well for high-value customers inactive for over 90 days.", confidence=0.86))
    session.add(Memory(category="product", content="Eco Tote Bag cancellations increase when delivery expectations are unclear.", confidence=0.79))
    session.commit()
