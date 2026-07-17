"""Import the public UCI Online Retail workbook into normalized CustomerPulse tables.

Run after startup: python -m app.import_retail_data
"""
from io import BytesIO
from decimal import Decimal
import httpx
import pandas as pd
from sqlalchemy import select
from .db import Base, SessionLocal, engine
from .models import Customer, Order, OrderItem, Product

UCI_URL = "https://archive.ics.uci.edu/ml/machine-learning-databases/00352/Online%20Retail.xlsx"


def import_data() -> None:
    Base.metadata.create_all(engine)
    workbook = httpx.get(UCI_URL, timeout=60).content
    df = pd.read_excel(BytesIO(workbook)).dropna(subset=["CustomerID", "Description"])
    df["CustomerID"] = df["CustomerID"].astype(int).astype(str)
    df["InvoiceNo"] = df["InvoiceNo"].astype(str)
    df["line_total"] = df["Quantity"] * df["UnitPrice"]
    with SessionLocal() as session:
        product_cache, customer_cache = {}, {}
        for sku, description, price in df[["StockCode", "Description", "UnitPrice"]].drop_duplicates("StockCode").itertuples(index=False):
            key = str(sku)
            product = session.scalar(select(Product).where(Product.external_sku == key))
            if not product:
                product = Product(external_sku=key, name=str(description)[:300], unit_price=Decimal(str(price)))
                session.add(product); session.flush()
            product_cache[key] = product.id
        for external_id, country in df[["CustomerID", "Country"]].drop_duplicates("CustomerID").itertuples(index=False):
            customer = session.scalar(select(Customer).where(Customer.external_id == external_id))
            if not customer:
                customer = Customer(external_id=external_id, country=str(country))
                session.add(customer); session.flush()
            customer_cache[external_id] = customer.id
        for number, (invoice, rows) in enumerate(df.groupby("InvoiceNo"), start=1):
            if session.scalar(select(Order.id).where(Order.invoice_number == invoice)):
                continue
            first = rows.iloc[0]
            order = Order(invoice_number=invoice, customer_id=customer_cache[first.CustomerID], order_date=first.InvoiceDate.to_pydatetime(), status="cancelled" if invoice.startswith("C") else "completed", total=Decimal(str((rows.Quantity * rows.UnitPrice).sum())))
            session.add(order); session.flush()
            for row in rows.itertuples(index=False):
                session.add(OrderItem(order_id=order.id, product_id=product_cache[str(row.StockCode)], quantity=int(row.Quantity), unit_price=Decimal(str(row.UnitPrice))))
            # Keep memory bounded on Render's small instances during the 500k-row import.
            if number % 200 == 0:
                session.commit()
        session.commit()

        # Create deterministic operational features the agent can reason about.
        reference_date = df["InvoiceDate"].max()
        customer_stats = df.groupby("CustomerID").agg(
            lifetime_value=("line_total", "sum"),
            last_purchase_at=("InvoiceDate", "max"),
            order_count=("InvoiceNo", "nunique"),
        )
        for external_id, stats in customer_stats.iterrows():
            customer = session.scalar(select(Customer).where(Customer.external_id == external_id))
            recency_days = max(0, (reference_date - stats.last_purchase_at).days)
            recency_score = min(recency_days / 180, 1.0)
            frequency_penalty = 0.25 if stats.order_count <= 1 else 0.0
            customer.lifetime_value = Decimal(str(max(0, round(stats.lifetime_value, 2))))
            customer.last_purchase_at = stats.last_purchase_at.to_pydatetime()
            customer.churn_risk = round(min(0.95, recency_score * 0.7 + frequency_penalty), 2)
            customer.segment = "at_risk_high_value" if customer.churn_risk >= 0.65 and customer.lifetime_value >= 250 else ("champion" if customer.lifetime_value >= 500 and stats.order_count >= 3 else "active")

        df["is_cancelled"] = df["InvoiceNo"].str.startswith("C")
        product_stats = df.groupby("StockCode").agg(
            cancellation_rate=("is_cancelled", "mean"),
            total_sales=("line_total", "sum"),
        )
        midpoint = df["InvoiceDate"].min() + (df["InvoiceDate"].max() - df["InvoiceDate"].min()) / 2
        early = df[df["InvoiceDate"] < midpoint].groupby("StockCode")["line_total"].sum()
        late = df[df["InvoiceDate"] >= midpoint].groupby("StockCode")["line_total"].sum()
        for sku, stats in product_stats.iterrows():
            product = session.scalar(select(Product).where(Product.external_sku == str(sku)))
            if product:
                product.cancellation_rate = round(float(stats.cancellation_rate), 3)
                baseline = float(early.get(sku, 0))
                product.sales_trend = round((float(late.get(sku, 0)) - baseline) / max(abs(baseline), 1), 3)
        session.commit()
    print("Import completed")


if __name__ == "__main__":
    import_data()
