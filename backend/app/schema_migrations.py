"""Small idempotent compatibility migrations for the Render deployment.

The project uses additive startup migrations so an existing demo database can be
upgraded without deleting imported UCI data. Larger production deployments should
move these statements into Alembic revisions.
"""
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from .config import settings


def migrate_customer_email(engine: Engine) -> None:
    columns = {column["name"] for column in inspect(engine).get_columns("customers")}
    with engine.begin() as connection:
        if "email" not in columns:
            connection.execute(text("ALTER TABLE customers ADD COLUMN email VARCHAR(320)"))
        connection.execute(
            text("UPDATE customers SET email = :email WHERE email IS NULL OR TRIM(email) = ''"),
            {"email": settings.demo_recipient_email},
        )
        if engine.dialect.name == "postgresql":
            connection.execute(text("ALTER TABLE customers ALTER COLUMN email SET DEFAULT 'temp66642@gmail.com'"))
            connection.execute(text("ALTER TABLE customers ALTER COLUMN email SET NOT NULL"))


def migrate_customer_segments(engine: Engine) -> None:
    """Keep risk and value visible as two independent customer dimensions."""
    with engine.begin() as connection:
        connection.execute(text("""
            UPDATE customers SET segment = CASE
                WHEN churn_risk >= 0.65 AND lifetime_value >= 250 THEN 'at_risk_high_value'
                WHEN churn_risk >= 0.65 THEN 'at_risk_lower_value'
                WHEN lifetime_value >= 250 THEN 'high_value_active'
                ELSE 'regular_active'
            END
        """))
