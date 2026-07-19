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
                WHEN last_purchase_at IS NULL THEN 'insufficient_history'
                WHEN churn_risk >= 0.65 AND lifetime_value >= 250 THEN 'at_risk_high_value'
                WHEN churn_risk >= 0.65 THEN 'at_risk_lower_value'
                WHEN lifetime_value >= 250 THEN 'high_value_active'
                ELSE 'regular_active'
            END
        """))


def recalculate_customer_risk(engine: Engine) -> None:
    """Calibrate inactivity risk to the current customer population.

    This is deliberately a relative risk score, not a probability prediction.
    Percentile ranks prevent an old static dataset from collapsing at one cap.
    """
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as connection:
        connection.execute(text("""
            WITH stats AS (
                SELECT customer_id,
                       COALESCE(MAX(order_date) FILTER (WHERE status = 'completed'), MAX(order_date)) AS last_completed_at,
                       COUNT(*) FILTER (WHERE status = 'completed') AS completed_orders
                FROM orders GROUP BY customer_id
            ), ranked AS (
                SELECT customer_id,
                       PERCENT_RANK() OVER (ORDER BY last_completed_at DESC) AS recency_percentile,
                       PERCENT_RANK() OVER (ORDER BY completed_orders DESC) AS frequency_percentile
                FROM stats
            )
            UPDATE customers c SET churn_risk = ROUND(
                LEAST(0.95, GREATEST(0.05,
                    0.75 * ranked.recency_percentile + 0.25 * ranked.frequency_percentile
                ))::numeric, 2
            )
            FROM ranked WHERE c.id = ranked.customer_id
        """))
        connection.execute(text("""
            UPDATE customers c SET churn_risk = 0.05
            WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.customer_id = c.id)
        """))


def recalculate_product_sales_trends(engine: Engine) -> None:
    """Compare completed units in the newer and earlier halves of the dataset.

    The UCI dataset is historical, so wall-clock windows would incorrectly make
    every product look inactive. Splitting its observed timeline in half creates
    an honest, reproducible relative trend for this static snapshot.
    """
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as connection:
        connection.execute(text("""
            WITH bounds AS (
                SELECT MIN(order_date) AS first_date, MAX(order_date) AS last_date
                FROM orders WHERE status = 'completed'
            ), periods AS (
                SELECT first_date + ((last_date - first_date) / 2) AS midpoint
                FROM bounds
            ), stats AS (
                SELECT oi.product_id,
                       SUM(CASE WHEN o.status = 'completed' AND o.order_date <= periods.midpoint
                                THEN GREATEST(oi.quantity, 0) ELSE 0 END)::numeric AS earlier_units,
                       SUM(CASE WHEN o.status = 'completed' AND o.order_date > periods.midpoint
                                THEN GREATEST(oi.quantity, 0) ELSE 0 END)::numeric AS newer_units
                FROM order_items oi
                JOIN orders o ON o.id = oi.order_id
                CROSS JOIN periods
                GROUP BY oi.product_id
            )
            UPDATE products p SET sales_trend = ROUND(
                CASE
                    WHEN stats.earlier_units > 0 THEN
                        GREATEST(-1, LEAST(5, (stats.newer_units - stats.earlier_units) / stats.earlier_units))
                    WHEN stats.newer_units > 0 THEN 1
                    ELSE 0
                END, 3
            )
            FROM stats WHERE p.id = stats.product_id
        """))
