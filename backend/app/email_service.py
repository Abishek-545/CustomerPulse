"""Campaign email delivery using the address stored on each customer.

All demo customer records currently contain one safe test inbox until real customer
emails and consent management are added. Delivery is idempotent per campaign target.
"""
from datetime import datetime
from email.message import EmailMessage
import smtplib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .models import Campaign, CampaignTarget, Customer, EmailDelivery


def _message(campaign: Campaign, customer: Customer) -> tuple[str, str]:
    subject = f"A thank-you offer from CustomerPulse: {campaign.offer}"
    body = f"""Hello Customer {customer.external_id},

Thank you for being a valued customer. We would love to welcome you back.

Your retention offer: {campaign.offer}
Campaign reference: CP-{campaign.id}-{customer.external_id}

Use this offer on your next eligible purchase. This demonstration message was
generated only after a manager approved the campaign in CustomerPulse.

Regards,
{settings.smtp_from_name}
"""
    return subject, body


def deliver_campaign_emails(session: Session, campaign_id: int) -> dict:
    campaign = session.get(Campaign, campaign_id)
    if not campaign or campaign.status != "active":
        raise ValueError("Only an approved active campaign can send email")
    rows = session.execute(
        select(CampaignTarget, Customer)
        .join(Customer, Customer.id == CampaignTarget.customer_id)
        .where(CampaignTarget.campaign_id == campaign_id)
        .order_by(CampaignTarget.id)
    ).all()
    existing_target_ids = set(session.scalars(select(EmailDelivery.campaign_target_id).where(EmailDelivery.campaign_id == campaign_id)).all())
    deliveries: list[EmailDelivery] = []
    for target, customer in rows:
        if target.id in existing_target_ids:
            continue
        subject, body = _message(campaign, customer)
        delivery = EmailDelivery(
            campaign_id=campaign.id,
            campaign_target_id=target.id,
            customer_id=customer.id,
            recipient=customer.email or settings.demo_recipient_email,
            subject=subject,
            body=body,
        )
        session.add(delivery)
        deliveries.append(delivery)
    session.commit()

    if deliveries and settings.email_mode.lower() == "smtp":
        if not settings.smtp_username or not settings.smtp_password:
            for delivery in deliveries:
                delivery.status = "failed"
                delivery.error = "SMTP credentials are not configured"
        else:
            try:
                with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
                    smtp.starttls()
                    smtp.login(settings.smtp_username, settings.smtp_password)
                    for delivery in deliveries:
                        message = EmailMessage()
                        message["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email or settings.smtp_username}>"
                        message["To"] = delivery.recipient
                        message["Subject"] = delivery.subject
                        message.set_content(delivery.body)
                        try:
                            smtp.send_message(message)
                            delivery.status = "sent"
                            delivery.sent_at = datetime.utcnow()
                            delivery.provider_message_id = message["Message-ID"]
                        except Exception as error:  # keep other campaign deliveries running
                            delivery.status = "failed"
                            delivery.error = f"{type(error).__name__}: {error}"[:1000]
            except Exception as error:
                for delivery in deliveries:
                    if delivery.status == "queued":
                        delivery.status = "failed"
                        delivery.error = f"{type(error).__name__}: {error}"[:1000]
    else:
        for delivery in deliveries:
            delivery.status = "simulated"
            delivery.sent_at = datetime.utcnow()
            delivery.provider_message_id = f"demo-{campaign.id}-{delivery.campaign_target_id}"
    session.commit()
    return delivery_summary(session, campaign_id)


def delivery_summary(session: Session, campaign_id: int) -> dict:
    counts = dict(session.execute(
        select(EmailDelivery.status, func.count()).where(EmailDelivery.campaign_id == campaign_id).group_by(EmailDelivery.status)
    ).all())
    total = sum(counts.values())
    return {
        "campaign_id": campaign_id,
        "recipient_source": "customers.email",
        "mode": settings.email_mode,
        "total": total,
        "queued": counts.get("queued", 0),
        "sent": counts.get("sent", 0),
        "simulated": counts.get("simulated", 0),
        "failed": counts.get("failed", 0),
        "manager_notification": f"Email processing finished for {total} campaign customers: {counts.get('sent', 0)} sent, {counts.get('simulated', 0)} simulated, {counts.get('failed', 0)} failed.",
    }
