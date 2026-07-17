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
        for invoice, rows in df.groupby("InvoiceNo"):
            if session.scalar(select(Order.id).where(Order.invoice_number == invoice)):
                continue
            first = rows.iloc[0]
            order = Order(invoice_number=invoice, customer_id=customer_cache[first.CustomerID], order_date=first.InvoiceDate.to_pydatetime(), status="cancelled" if invoice.startswith("C") else "completed", total=Decimal(str((rows.Quantity * rows.UnitPrice).sum())))
            session.add(order); session.flush()
            for row in rows.itertuples(index=False):
                session.add(OrderItem(order_id=order.id, product_id=product_cache[str(row.StockCode)], quantity=int(row.Quantity), unit_price=Decimal(str(row.UnitPrice))))
        session.commit()
    print("Import completed")


if __name__ == "__main__":
    import_data()
