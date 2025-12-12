from email.message import EmailMessage
from typing import Iterable, Tuple
import smtplib

from app.config import settings

Attachment = Tuple[str, bytes, str]


def send_email(
    *,
    to_address: str,
    subject: str,
    body: str,
    attachments: Iterable[Attachment] | None = None,
):
    if not settings.EMAIL_SENDING_ENABLED:
        raise RuntimeError("Email sending is disabled.")

    if not settings.EMAIL_SMTP_HOST:
        raise RuntimeError("SMTP host is not configured.")

    msg = EmailMessage()
    msg["From"] = settings.EMAIL_FROM_ADDRESS
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.set_content(body)

    for attachment in attachments or []:
        name, content, mime_type = attachment
        if isinstance(content, str):
            content_bytes = content.encode("utf-8")
        else:
            content_bytes = content
        maintype, subtype = mime_type.split("/", 1)
        msg.add_attachment(content_bytes, maintype=maintype, subtype=subtype, filename=name)

    with smtplib.SMTP(settings.EMAIL_SMTP_HOST, settings.EMAIL_SMTP_PORT) as smtp:
        smtp.starttls()
        if settings.EMAIL_SMTP_USERNAME and settings.EMAIL_SMTP_PASSWORD:
            smtp.login(settings.EMAIL_SMTP_USERNAME, settings.EMAIL_SMTP_PASSWORD)
        smtp.send_message(msg)
